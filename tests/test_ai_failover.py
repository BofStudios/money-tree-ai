"""When the chosen AI cannot answer (no credit, refused key), the next one does."""
from app.config import MentorConfig
from app.mentor.ai import AIMentor
from app.mentor.providers import Reply


class FakeProvider:
    def __init__(self, name, answer=None, dead=False):
        self.name, self.model, self.answer, self.dead, self.calls = name, name + "-m", answer, dead, 0
        self.dead_why = ""

    def available(self):
        return not self.dead

    def chat(self, system, messages, max_tokens):
        self.calls += 1
        if self.answer is None:
            self.dead, self.dead_why = True, "the account has no credit left"
            return None
        return Reply(self.answer, self.name, self.model)


def mentor(tmp_path, primary, backups):
    m = AIMentor(MentorConfig(enabled=False), {}, tmp_path / "mem.json")
    m.provider = primary
    m._keys = {"groq": "x"}
    m._backups = backups
    return m


def test_no_credit_falls_back_to_the_next_provider(tmp_path):
    paid = FakeProvider("anthropic", answer=None)
    free = FakeProvider("groq", answer="from groq")
    m = mentor(tmp_path, paid, {"groq": free, "gemini": FakeProvider("gemini", dead=True)})
    assert m.research("sys", "q", 100) == "from groq"
    assert m.research("sys", "q", 100) == "from groq"
    assert paid.calls == 1                      # benched after the first failure
    info = m.backend
    assert info["provider"] == "groq" and info["fallback_from"] == "anthropic"


def test_nothing_works_means_no_answer(tmp_path):
    m = mentor(tmp_path, FakeProvider("anthropic", dead=True), {"groq": FakeProvider("groq", dead=True),
                                                                "gemini": FakeProvider("gemini", dead=True)})
    assert not m.available
    assert m.research("sys", "q", 100) is None
