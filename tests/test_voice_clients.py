"""Tests for voice client abstraction layer."""
import asyncio
import queue
import unittest
from unittest.mock import AsyncMock, MagicMock, patch


class TestVoiceClientABC(unittest.TestCase):
    def test_cannot_instantiate_directly(self):
        from app.voice.base_client import VoiceClient
        with self.assertRaises(TypeError):
            VoiceClient(queue.Queue())

    def test_emit_puts_to_queue(self):
        """emit() must put exactly the given event onto the queue."""
        from app.voice.base_client import VoiceClient

        class ConcreteClient(VoiceClient):
            async def connect(self, system_prompt, voice_config): pass
            async def send_audio_chunk(self, chunk): pass
            async def close(self): pass

        q = queue.Queue()
        client = ConcreteClient(q)
        event = {"type": "status", "text": "hello"}
        client.emit(event)
        self.assertEqual(q.get_nowait(), event)

    def test_emit_does_not_block(self):
        """emit() must be non-blocking (uses put_nowait)."""
        from app.voice.base_client import VoiceClient

        class ConcreteClient(VoiceClient):
            async def connect(self, system_prompt, voice_config): pass
            async def send_audio_chunk(self, chunk): pass
            async def close(self): pass

        q = queue.Queue()
        client = ConcreteClient(q)
        for i in range(100):
            client.emit({"type": "status", "text": str(i)})
        self.assertEqual(q.qsize(), 100)


class TestMockVoiceClient(unittest.TestCase):
    def setUp(self):
        self.q = queue.Queue()

    def test_instantiates_with_queue(self):
        from app.voice.mock_client import MockVoiceClient
        client = MockVoiceClient(self.q)
        self.assertIsNotNone(client)

    def test_default_mode_is_encounter(self):
        from app.voice.mock_client import MockVoiceClient
        client = MockVoiceClient(self.q)
        self.assertEqual(client.mode, "encounter")

    def test_interview_mode_accepted(self):
        from app.voice.mock_client import MockVoiceClient
        client = MockVoiceClient(self.q, mode="interview")
        self.assertEqual(client.mode, "interview")

    def test_connect_emits_status(self):
        from app.voice.mock_client import MockVoiceClient

        async def run():
            client = MockVoiceClient(self.q)
            await client.connect("system prompt", {})

        asyncio.run(run())
        events = []
        while not self.q.empty():
            events.append(self.q.get_nowait())
        status_events = [e for e in events if e.get("type") == "status"]
        self.assertTrue(len(status_events) >= 1)

    def test_send_audio_chunk_does_not_raise(self):
        from app.voice.mock_client import MockVoiceClient

        async def run():
            client = MockVoiceClient(self.q)
            await client.send_audio_chunk(b"\x00" * 1024)

        asyncio.run(run())  # should not raise

    def test_close_emits_status(self):
        from app.voice.mock_client import MockVoiceClient

        async def run():
            client = MockVoiceClient(self.q)
            client._running = True
            await client.close()

        asyncio.run(run())
        events = []
        while not self.q.empty():
            events.append(self.q.get_nowait())
        status_texts = [e.get("text", "") for e in events if e.get("type") == "status"]
        self.assertTrue(any("closed" in t.lower() for t in status_texts))

    def test_emit_user_turn_emits_transcript(self):
        from app.voice.mock_client import MockVoiceClient
        client = MockVoiceClient(self.q)
        client.emit_user_turn("Hello doctor")
        event = self.q.get_nowait()
        self.assertEqual(event["type"], "transcript")
        self.assertEqual(event["role"], "user")
        self.assertEqual(event["text"], "Hello doctor")

    def test_emit_user_turn_increments_turn_index(self):
        from app.voice.mock_client import MockVoiceClient
        client = MockVoiceClient(self.q)
        client.emit_user_turn("first")
        client.emit_user_turn("second")
        e1 = self.q.get_nowait()
        e2 = self.q.get_nowait()
        self.assertEqual(e2["turn_index"], e1["turn_index"] + 1)


class TestMockAnalysisResult(unittest.TestCase):
    def test_mock_result_has_required_keys(self):
        from app.voice.mock_client import MOCK_ANALYSIS_RESULT
        self.assertIn("overall_scores", MOCK_ANALYSIS_RESULT)
        self.assertIn("summary_feedback", MOCK_ANALYSIS_RESULT)
        self.assertIn("anki_cards", MOCK_ANALYSIS_RESULT)
        self.assertIn("corrections", MOCK_ANALYSIS_RESULT)

    def test_overall_scores_all_floats(self):
        from app.voice.mock_client import MOCK_ANALYSIS_RESULT
        for k, v in MOCK_ANALYSIS_RESULT["overall_scores"].items():
            self.assertIsInstance(v, float, f"{k} is not float")
            self.assertGreater(v, 0)
            self.assertLessEqual(v, 10)

    def test_checklist_results_structure(self):
        from app.voice.mock_client import MOCK_ANALYSIS_RESULT
        for item in MOCK_ANALYSIS_RESULT.get("checklist_results", []):
            self.assertIn("item", item)
            self.assertIn("required", item)
            self.assertIn("passed", item)


class TestVoiceClientFactory(unittest.TestCase):
    def setUp(self):
        self.q = queue.Queue()

    def test_dev_mode_returns_mock_client(self):
        from app.voice.factory import create_voice_client
        from app.voice.mock_client import MockVoiceClient
        client = create_voice_client(self.q, dev_mode=True)
        self.assertIsInstance(client, MockVoiceClient)

    def test_dev_mode_interview_returns_mock_in_interview_mode(self):
        from app.voice.factory import create_voice_client
        from app.voice.mock_client import MockVoiceClient
        client = create_voice_client(self.q, dev_mode=True, mode="interview")
        self.assertIsInstance(client, MockVoiceClient)
        self.assertEqual(client.mode, "interview")

    def test_non_dev_gemini_backend(self):
        from app.voice.factory import create_voice_client
        from app.voice.gemini_client import GeminiLiveClient
        with patch("app.voice.factory.get_setting", return_value="gemini"):
            client = create_voice_client(self.q, dev_mode=False)
        self.assertIsInstance(client, GeminiLiveClient)

    def test_non_dev_openai_backend(self):
        from app.voice.factory import create_voice_client
        from app.voice.openai_client import OpenAIRealtimeClient
        # Patch where get_setting is used inside factory
        with patch("app.voice.factory.get_setting", return_value="openai"):
            client = create_voice_client(self.q, dev_mode=False)
        self.assertIsInstance(client, OpenAIRealtimeClient)

    def test_client_receives_correct_queue(self):
        from app.voice.factory import create_voice_client
        client = create_voice_client(self.q, dev_mode=True)
        self.assertIs(client.ui_queue, self.q)


class TestGeminiClientInit(unittest.TestCase):
    def test_instantiates_without_connecting(self):
        from app.voice.gemini_client import GeminiLiveClient
        q = queue.Queue()
        client = GeminiLiveClient(q)
        self.assertIsNone(client._session)
        self.assertFalse(client._running)

    def test_connect_emits_error_when_no_api_key(self):
        """Gemini client must emit an error event (not raise) when key is missing."""
        from app.voice.gemini_client import GeminiLiveClient
        q = queue.Queue()
        client = GeminiLiveClient(q)

        async def run():
            import os
            # Remove key from env so client detects missing key
            saved = os.environ.pop("GEMINI_API_KEY", None)
            try:
                await client.connect("prompt", {})
            finally:
                if saved:
                    os.environ["GEMINI_API_KEY"] = saved

        asyncio.run(run())
        events = []
        while not q.empty():
            events.append(q.get_nowait())

        # Either an error event about missing key, OR an ImportError-triggered error
        # (google-genai may not be installed in test env — both are valid "error" outcomes)
        error_events = [e for e in events if e["type"] == "error"]
        self.assertGreaterEqual(len(error_events), 1,
            "Expected at least one error event when GEMINI_API_KEY is not set or google-genai is missing")
        session_end_events = [e for e in events if e["type"] == "session_end"]
        self.assertEqual(len(session_end_events), 1, "Expected a session_end event")


class TestOpenAIClientInit(unittest.TestCase):
    def test_instantiates_without_connecting(self):
        from app.voice.openai_client import OpenAIRealtimeClient
        q = queue.Queue()
        client = OpenAIRealtimeClient(q)
        self.assertIsNone(client._ws)
        self.assertFalse(client._running)

    def test_connect_emits_error_when_no_api_key(self):
        from app.voice.openai_client import OpenAIRealtimeClient
        q = queue.Queue()
        client = OpenAIRealtimeClient(q)

        async def run():
            with patch.dict("os.environ", {}, clear=True):
                import os; os.environ.pop("OPENAI_API_KEY", None)
                await client.connect("prompt", {})

        asyncio.run(run())
        events = []
        while not q.empty():
            events.append(q.get_nowait())
        error_events = [e for e in events if e["type"] == "error"]
        self.assertEqual(len(error_events), 1)
        self.assertIn("OPENAI_API_KEY", error_events[0]["message"])
        session_end_events = [e for e in events if e["type"] == "session_end"]
        self.assertEqual(len(session_end_events), 1, "Expected a session_end event")


if __name__ == "__main__":
    unittest.main()
