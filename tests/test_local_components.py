import json
import tempfile
import unittest
from pathlib import Path

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

    def test_conversation_can_be_renamed(self):
        with tempfile.TemporaryDirectory() as folder:
            memory = Memory(Path(folder) / "memory.db")
            conversation_id = memory.create_conversation("u")
            memory.rename_conversation("u", conversation_id, "  Project planning  ")
            self.assertEqual(memory.list_conversations("u")[0]["title"], "Project planning")
            with self.assertRaises(ValueError):
                memory.rename_conversation("u", conversation_id, "   ")
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


if __name__ == "__main__":
    unittest.main()
