"""Tests for app/voice/audio_io.py — buffer logic and stream lifecycle.

These avoid real audio hardware: AudioPlayer's buffering is pure Python, and
the capture/availability paths are checked without opening PortAudio streams.
"""
import unittest


class TestSounddeviceAvailable(unittest.TestCase):
    def test_returns_bool(self):
        from app.voice.audio_io import sounddevice_available
        self.assertIsInstance(sounddevice_available(), bool)


class TestAudioPlayerBuffer(unittest.TestCase):
    def _player(self):
        from app.voice.audio_io import AudioPlayer
        return AudioPlayer(24000)

    def test_play_appends_bytes(self):
        p = self._player()
        p.play(b"\x01\x02\x03\x04")
        self.assertEqual(p.buffered_bytes, 4)

    def test_play_accumulates(self):
        p = self._player()
        p.play(b"\x00\x00")
        p.play(b"\x00\x00\x00\x00")
        self.assertEqual(p.buffered_bytes, 6)

    def test_play_ignores_empty(self):
        p = self._player()
        p.play(b"")
        p.play(None)  # type: ignore[arg-type]
        self.assertEqual(p.buffered_bytes, 0)

    def test_clear_empties_buffer(self):
        p = self._player()
        p.play(b"\x01" * 10)
        p.clear()
        self.assertEqual(p.buffered_bytes, 0)

    def test_stop_without_start_is_safe(self):
        p = self._player()
        p.play(b"\x01" * 4)
        p.stop()  # no stream was started; must not raise
        self.assertEqual(p.buffered_bytes, 0)


class TestAudioCaptureConfig(unittest.TestCase):
    def test_default_blocksize_is_100ms(self):
        from app.voice.audio_io import AudioCapture
        cap = AudioCapture(lambda b: None, 16000)
        self.assertEqual(cap._blocksize, 1600)

    def test_explicit_blocksize_respected(self):
        from app.voice.audio_io import AudioCapture
        cap = AudioCapture(lambda b: None, 24000, blocksize=512)
        self.assertEqual(cap._blocksize, 512)

    def test_stop_without_start_is_safe(self):
        from app.voice.audio_io import AudioCapture
        cap = AudioCapture(lambda b: None, 16000)
        cap.stop()  # nothing started; must not raise


class TestVoiceClientSampleRates(unittest.TestCase):
    def test_gemini_rates(self):
        from app.voice.gemini_client import GeminiLiveClient
        self.assertEqual(GeminiLiveClient.INPUT_SAMPLE_RATE, 16000)
        self.assertEqual(GeminiLiveClient.OUTPUT_SAMPLE_RATE, 24000)

    def test_openai_rates(self):
        from app.voice.openai_client import OpenAIRealtimeClient
        self.assertEqual(OpenAIRealtimeClient.INPUT_SAMPLE_RATE, 24000)
        self.assertEqual(OpenAIRealtimeClient.OUTPUT_SAMPLE_RATE, 24000)


if __name__ == "__main__":
    unittest.main()
