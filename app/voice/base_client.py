from abc import ABC, abstractmethod
import queue


class VoiceClient(ABC):
    def __init__(self, ui_queue: queue.Queue):
        self.ui_queue = ui_queue

    @abstractmethod
    async def connect(self, system_prompt: str, voice_config: dict) -> None:
        """Open WebSocket/session and send system prompt."""

    @abstractmethod
    async def send_audio_chunk(self, chunk: bytes) -> None:
        """Stream one audio chunk from the microphone."""

    @abstractmethod
    async def close(self) -> None:
        """Gracefully close the session."""

    def emit(self, event: dict) -> None:
        self.ui_queue.put_nowait(event)
