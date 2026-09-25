import json
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from brain import DeepDeepBrain
from gui import _markdown_html
from memory import Memory
from rag import LocalRAG


class LocalComponentsTests(unittest.TestCase):
    def test_memory_round_trip(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / "memory.db")
            memory.upsert_user("u")
            memory.set_fact("u", "language", "Python")
            memory.add_message("u", "user", "hello")
            memory.add_message("u", "assistant", "hi")
            self.assertEqual(memory.facts("u")["language"], "Python")
            self.assertEqual(len(memory.recent_messages("u", 10)), 2)
            memory.close()

    def test_conversations_are_isolated_and_deletable(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / "memory.db")
            first = memory.create_conversation("u")
            second = memory.create_conversation("u")
            memory.add_message("u", first, "user", "first")
            memory.add_message("u", second, "user", "second")
            self.assertEqual(memory.conversation_messages(first, 10)[0]["content"], "first")
            self.assertEqual(memory.conversation_messages(second, 10)[0]["content"], "second")
            memory.delete_conversation("u", first)
            self.assertEqual(memory.conversation_messages(first, 10), [])
            self.assertEqual(len(memory.list_conversations("u")), 1)
            memory.close()

    def test_clear_history_can_be_scoped_to_one_conversation(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / "memory.db")
            first = memory.create_conversation("u")
            second = memory.create_conversation("u")
            memory.add_message("u", first, "user", "first")
            memory.add_message("u", second, "user", "second")
            memory.clear_history("u", first)
            self.assertEqual(memory.conversation_messages(first, 10), [])
            self.assertEqual(memory.conversation_messages(second, 10)[0]["content"], "second")
            memory.close()

    def test_memory_serializes_concurrent_access(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / "memory.db")
            conversation_id = memory.create_conversation("u")

            def write_messages(worker: int) -> None:
                for index in range(20):
                    memory.add_message("u", conversation_id, "user", f"{worker}-{index}")

            with ThreadPoolExecutor(max_workers=4) as executor:
                list(executor.map(write_messages, range(4)))
            self.assertEqual(len(memory.conversation_messages(conversation_id, 100)), 80)
            memory.close()

    def test_conversation_can_be_renamed(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / "memory.db")
            conversation_id = memory.create_conversation("u")
            memory.rename_conversation("u", conversation_id, "  Project planning  ")
            self.assertEqual(memory.list_conversations("u")[0]["title"], "Project planning")
            with self.assertRaises(ValueError):
                memory.rename_conversation("u", conversation_id, "   ")
            memory.close()

    def test_chats_auto_rename_from_first_message(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / "memory.db")
            conversation_id = memory.create_conversation("u")
            memory.add_message("u", conversation_id, "user", "  /web  Find local hiking trails  ")
            self.assertEqual(memory.list_conversations("u")[0]["title"], "Find local hiking trails")
            memory.add_message("u", conversation_id, "user", "A later request should not replace the title")
            self.assertEqual(memory.list_conversations("u")[0]["title"], "Find local hiking trails")
            memory.close()

    def test_auto_rename_can_be_disabled(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / "memory.db", auto_rename_chats=False)
            conversation_id = memory.create_conversation("u")
            memory.add_message("u", conversation_id, "user", "Keep the default title")
            self.assertEqual(memory.list_conversations("u")[0]["title"], "New conversation")
            memory.close()

    def test_rag_persists_and_retrieves(self):
        with tempfile.TemporaryDirectory() as folder:
            index = Path(folder) / "index.json"
            rag = LocalRAG(index)
            rag.add_text("Python uses indentation to define code blocks.", "python")
            rag.add_text("Apples and pears are fruit.", "fruit")
            results = rag.search("How does Python define blocks?")
            self.assertEqual(results[0]["source"], "python")
            self.assertTrue(json.loads(index.read_text()))

    def test_rag_ignores_malformed_index_entries(self):
        with tempfile.TemporaryDirectory() as folder:
            index = Path(folder) / "index.json"
            index.write_text(
                json.dumps(
                    [
                        {"source": "valid", "text": "Python"},
                        {"source": "other", "text": "Apples"},
                        {"source": "broken"},
                    ]
                )
            )
            rag = LocalRAG(index)
            self.assertEqual([item["source"] for item in rag.search("Python")], ["valid"])

    def test_research_detection_is_conservative(self):
        self.assertTrue(DeepDeepBrain._needs_web_research("What is the latest Python release?"))
        self.assertTrue(DeepDeepBrain._needs_web_research("Can you recommend a laptop?"))
        self.assertTrue(DeepDeepBrain._needs_web_research("What is the weather today?"))
        self.assertFalse(DeepDeepBrain._needs_web_research("Explain Python decorators."))
        self.assertFalse(DeepDeepBrain._needs_web_research("Help me debug this function."))

    def test_attachments_are_added_to_the_current_prompt(self):
        prompt = DeepDeepBrain._with_attachments(
            "Summarize this.",
            [{"name": "notes.md", "text": "# Notes\nImportant detail"}],
        )
        self.assertIn("Attached files:", prompt)
        self.assertIn("--- Attached file: notes.md ---", prompt)
        self.assertIn("Important detail", prompt)
        self.assertEqual(DeepDeepBrain._with_attachments("Hello", []), "Hello")

    def test_attachment_summary_is_visible_in_session_history(self):
        summary = DeepDeepBrain._session_message_with_attachments(
            "Summarize this.",
            [{"name": "notes.md", "text": "# Notes\nImportant detail"}],
        )
        self.assertIn("Summarize this.", summary)
        self.assertIn("Attached files:", summary)
        self.assertIn("notes.md", summary)
        self.assertNotIn("Important detail", summary)
        self.assertEqual(DeepDeepBrain._session_message_with_attachments("Hello", []), "Hello")

    def test_markdown_rejects_unsafe_url_schemes(self):
        rendered = _markdown_html(
            "[bad](javascript:alert(1)) ![bad](javascript:alert(2)) [good](https://example.com)"
        )
        self.assertNotIn("javascript:", rendered.lower())
        self.assertIn('href="#"', rendered)
        self.assertIn('href="https://example.com"', rendered)


if __name__ == "__main__":
    unittest.main()
