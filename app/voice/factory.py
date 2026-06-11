import queue

from app.voice.base_client import VoiceClient
from app.db.queries import get_setting


def create_voice_client(ui_queue: queue.Queue, dev_mode: bool = False, mode: str = "encounter") -> VoiceClient:
    if dev_mode:
        from app.voice.mock_client import MockVoiceClient
        return MockVoiceClient(ui_queue, mode=mode)

    backend = get_setting("voice_backend", default="gemini")
    if backend == "openai":
        from app.voice.openai_client import OpenAIRealtimeClient
        return OpenAIRealtimeClient(ui_queue)

    from app.voice.gemini_client import GeminiLiveClient
    return GeminiLiveClient(ui_queue)
