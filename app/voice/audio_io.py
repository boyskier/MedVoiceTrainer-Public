"""
Real-time microphone capture and speaker playback for the live voice backends.

PCM16, mono, little-endian throughout (the format both Gemini Live and OpenAI
Realtime expect/produce). Sample rates differ per backend and are supplied by
the caller (Gemini mic 16 kHz / speaker 24 kHz; OpenAI 24 kHz both ways).

Threading model
---------------
PortAudio runs its stream callbacks in a dedicated high-priority thread, so the
callbacks here do as little as possible and never touch the asyncio loop or
tkinter directly:

- ``AudioCapture`` hands each raw PCM chunk to a plain ``on_chunk(bytes)``
  callback. The owning session bridges that to the voice client's event loop via
  ``run_coroutine_threadsafe`` (see ``SessionBase._on_mic_chunk``).
- ``AudioPlayer`` keeps a thread-safe byte buffer that its output callback
  drains; ``play(bytes)`` simply appends (safe to call from any thread).

We use the ``Raw*`` stream variants so the dependency is just ``sounddevice``
(PortAudio) — no numpy required at runtime.
"""
from __future__ import annotations

import threading
from typing import Callable, Optional


def sounddevice_available() -> bool:
    """True if sounddevice (PortAudio) can be imported."""
    try:
        import sounddevice  # noqa: F401
    except Exception:
        return False
    return True


def resample_pcm16(data: bytes, from_rate: int, to_rate: int) -> bytes:
    if from_rate == to_rate or not data:
        return data
    try:
        import numpy as np
        samples = np.frombuffer(data, dtype=np.int16)
        num_samples = len(samples)
        if num_samples == 0:
            return data
        num_target_samples = int(num_samples * to_rate / from_rate)
        if num_target_samples <= 0:
            return b""
        src_indices = np.arange(num_samples)
        target_indices = np.linspace(0, num_samples - 1, num_target_samples)
        resampled = np.interp(target_indices, src_indices, samples)
        return resampled.astype(np.int16).tobytes()
    except Exception:
        import array
        samples_arr = array.array("h")
        samples_arr.frombytes(data[: len(data) - (len(data) % 2)])
        if not samples_arr:
            return data
        ratio = to_rate / from_rate
        out_len = int(len(samples_arr) * ratio)
        if out_len <= 0:
            return b""
        out_samples = array.array("h", [0] * out_len)
        for i in range(out_len):
            src_idx = min(int(i / ratio), len(samples_arr) - 1)
            out_samples[i] = samples_arr[src_idx]
        return out_samples.tobytes()


# PortAudio snapshots the device list at initialization, so devices that
# (dis)connect later — e.g. Bluetooth earbuds switching profiles — are
# invisible until re-init. Re-init is only safe with no open streams, so the
# capture/playback classes keep a count.
_active_streams = 0
_streams_lock = threading.Lock()


def _stream_opened() -> None:
    global _active_streams
    with _streams_lock:
        _active_streams += 1


def _stream_closed() -> None:
    global _active_streams
    with _streams_lock:
        _active_streams = max(0, _active_streams - 1)


def refresh_devices() -> None:
    """Re-scan the audio device list if no streams are open (best-effort)."""
    with _streams_lock:
        if _active_streams:
            return
    try:
        import sounddevice as sd
        sd._terminate()
        sd._initialize()
    except Exception:
        pass


def _device_label(device: dict, hostapis) -> str:
    return f"[{hostapis[device['hostapi']]['name']}] {device['name']}"


def list_input_devices() -> list[str]:
    """Labels for every input-capable device, qualified by host API.

    The same physical mic appears once per Windows audio path (MME,
    DirectSound, WASAPI, WDM-KS) and these are NOT equivalent — a mic can be
    dead through one path and fine through another — so each path must be
    individually selectable."""
    import sounddevice as sd
    apis = sd.query_hostapis()
    labels: list[str] = []
    for d in sd.query_devices():
        if d["max_input_channels"] > 0:
            label = _device_label(d, apis)
            if label not in labels:
                labels.append(label)
    return labels


def list_output_devices() -> list[str]:
    """Labels for every output-capable device, qualified by host API."""
    import sounddevice as sd
    apis = sd.query_hostapis()
    labels: list[str] = []
    for d in sd.query_devices():
        if d["max_output_channels"] > 0:
            label = _device_label(d, apis)
            if label not in labels:
                labels.append(label)
    return labels


def resolve_output_device(label: str) -> Optional[int]:
    """Map a saved output device label to an index; None = system default."""
    if not label:
        return None
    import sounddevice as sd
    apis = sd.query_hostapis()
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d["max_output_channels"] > 0 and _device_label(d, apis) == label:
            return i
    for i, d in enumerate(devices):
        if d["max_output_channels"] > 0 and d["name"] == label:
            return i
    return None


def resolve_input_device(label: str) -> Optional[int]:
    """Map a saved device label back to a device index; None = system default.

    Labels are stored (not indices) because indices shift as devices come and
    go; an unplugged device silently falls back to the default. Bare names
    saved by older versions still match via the fallback."""
    if not label:
        return None
    import sounddevice as sd
    apis = sd.query_hostapis()
    devices = sd.query_devices()
    for i, d in enumerate(devices):
        if d["max_input_channels"] > 0 and _device_label(d, apis) == label:
            return i
    for i, d in enumerate(devices):  # legacy: bare device name
        if d["max_input_channels"] > 0 and d["name"] == label:
            return i
    return None


class AudioCapture:
    """Streams microphone audio as raw PCM16 mono byte chunks."""

    def __init__(self, on_chunk: Callable[[bytes], None], sample_rate: int,
                 blocksize: int = 0, device: Optional[int] = None):
        self._on_chunk = on_chunk
        self._sample_rate = sample_rate
        # 0 → ~100 ms blocks, a good latency/overhead trade-off.
        self._blocksize = blocksize or (sample_rate // 10)
        self._device = device
        self._stream = None
        self._last_cb = 0.0

        # Determine active stream sample rate (WASAPI shared mode fallback)
        self._stream_sample_rate = sample_rate
        try:
            import sounddevice as sd
            sd.check_input_settings(device=device, samplerate=sample_rate, channels=1, dtype='int16')
        except Exception:
            try:
                import sounddevice as sd
                if device is None:
                    device_info = sd.query_devices(kind='input')
                else:
                    device_info = sd.query_devices(device, 'input')
                self._stream_sample_rate = int(device_info['default_samplerate'])
            except Exception:
                pass

    def start(self) -> None:
        import time as _time
        self._last_cb = _time.monotonic()
        self._open_stream()

    def _open_stream(self) -> None:
        import sounddevice as sd
        import time as _time

        def callback(indata, frames, time_info, status):  # PortAudio thread
            self._last_cb = _time.monotonic()
            # Copy out of the transient CFFI buffer before it is reused.
            data = bytes(indata)
            if self._stream_sample_rate != self._sample_rate:
                data = resample_pcm16(data, self._stream_sample_rate, self._sample_rate)
            self._on_chunk(data)

        # Scale blocksize to match target duration at stream sample rate
        stream_blocksize = int(self._blocksize * self._stream_sample_rate / self._sample_rate)

        self._stream = sd.RawInputStream(
            samplerate=self._stream_sample_rate,
            channels=1,
            dtype="int16",
            blocksize=stream_blocksize,
            device=self._device,
            callback=callback,
        )
        self._stream.start()
        self._last_cb = _time.monotonic()
        _stream_opened()

    def ensure_alive(self) -> None:
        """Restart the input stream if it silently stopped firing callbacks."""
        import time as _time
        if _time.monotonic() - self._last_cb < 0.5:
            return
            
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            _stream_closed()
            self._stream = None

        self._last_cb = _time.monotonic()
        try:
            self._open_stream()
        except Exception:
            pass

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
            _stream_closed()


class AudioPlayer:
    """Plays raw PCM16 mono audio fed incrementally via ``play()``."""

    _BYTES_PER_FRAME = 2  # int16 mono

    def __init__(self, sample_rate: int, device: Optional[int] = None):
        self._sample_rate = sample_rate
        self._device = device
        self._buffer = bytearray()
        self._lock = threading.Lock()
        self._stream = None
        self._last_cb = 0.0  # monotonic time of the last output callback

        # Determine active stream sample rate (WASAPI shared mode fallback)
        self._stream_sample_rate = sample_rate
        try:
            import sounddevice as sd
            sd.check_output_settings(device=device, samplerate=sample_rate, channels=1, dtype='int16')
        except Exception:
            try:
                import sounddevice as sd
                if device is None:
                    device_info = sd.query_devices(kind='output')
                else:
                    device_info = sd.query_devices(device, 'output')
                self._stream_sample_rate = int(device_info['default_samplerate'])
            except Exception:
                pass

    def start(self) -> None:
        self._open_stream()

    def _open_stream(self) -> None:
        import sounddevice as sd
        import time as _time

        def callback(outdata, frames, time_info, status):  # PortAudio thread
            self._last_cb = _time.monotonic()
            needed = frames * self._BYTES_PER_FRAME
            with self._lock:
                n = min(needed, len(self._buffer))
                chunk = bytes(self._buffer[:n])
                del self._buffer[:n]
            if n < needed:
                # Underrun: pad with silence so playback stays glitch-free.
                chunk += b"\x00" * (needed - n)
            outdata[:] = chunk

        self._stream = sd.RawOutputStream(
            samplerate=self._stream_sample_rate,
            channels=1,
            dtype="int16",
            device=self._device,
            callback=callback,
        )
        self._stream.start()
        self._last_cb = _time.monotonic()
        _stream_opened()

    def ensure_alive(self) -> None:
        """Restart the output stream if it silently stopped consuming.

        Some Windows audio drivers (seen with Realtek + Intel SST) kill an
        idle stream after a few seconds without raising any error; the
        callback just stops firing. A healthy callback runs every few ms
        (emitting silence when the buffer is empty), so a stale timestamp
        means the stream is dead — reopen it and playback resumes from the
        buffered audio."""
        import time as _time
        if _time.monotonic() - self._last_cb < 0.5:
            return
            
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            _stream_closed()
            self._stream = None
            
        self._last_cb = _time.monotonic()
        try:
            self._open_stream()
        except Exception:
            pass  # device gone; next ensure_alive/play retries

    def play(self, data: bytes) -> None:
        """Queue PCM bytes for playback. Safe to call from any thread."""
        if not data:
            return
        if self._stream_sample_rate != self._sample_rate:
            data = resample_pcm16(data, self._sample_rate, self._stream_sample_rate)
        with self._lock:
            self._buffer.extend(data)
        self.ensure_alive()

    def clear(self) -> None:
        """Drop any buffered audio (e.g. on barge-in / stop)."""
        with self._lock:
            self._buffer.clear()

    @property
    def buffered_bytes(self) -> int:
        with self._lock:
            return len(self._buffer)

    def stop(self) -> None:
        if self._stream is not None:
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
            _stream_closed()
        self.clear()
