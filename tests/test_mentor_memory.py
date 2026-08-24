import json

import pytest

from app.mentor.memory import MAX_FACTS, MentorMemory


@pytest.fixture
def memory(tmp_path):
    return MentorMemory(tmp_path / "memory.json", keep_turns=2)


# ------------------------------------------------------------------- facts


def test_a_fact_survives_a_restart(tmp_path):
    path = tmp_path / "memory.json"
    MentorMemory(path).remember("I trade in Midas, not Alpaca.")

    reopened = MentorMemory(path)
    assert [f["text"] for f in reopened.facts()] == ["I trade in Midas, not Alpaca."]


def test_the_same_fact_twice_is_stored_once(memory):
    memory.remember("I am a beginner")
    memory.remember("i am a BEGINNER")

    assert len(memory.facts()) == 1


def test_whitespace_is_tidied_up(memory):
    fact = memory.remember("  keep   it   short \n")

    assert fact["text"] == "keep it short"


def test_an_empty_fact_is_refused(memory):
    with pytest.raises(ValueError):
        memory.remember("   ")


def test_only_the_most_recent_facts_are_kept(memory):
    for i in range(MAX_FACTS + 10):
        memory.remember(f"fact number {i}")

    facts = memory.facts()
    assert len(facts) == MAX_FACTS
    assert facts[-1]["text"] == f"fact number {MAX_FACTS + 9}"


def test_a_fact_can_be_forgotten(memory):
    memory.remember("wrong thing")

    assert memory.forget(0) is True
    assert memory.facts() == []
    assert memory.forget(0) is False


def test_facts_reach_the_system_prompt(memory):
    memory.remember("My broker is Midas.")

    prompt = memory.as_prompt()
    assert "My broker is Midas." in prompt


def test_no_facts_means_nothing_is_appended(memory):
    assert memory.as_prompt() == ""


# ----------------------------------------------------------------- history


def test_a_conversation_survives_a_restart(tmp_path):
    path = tmp_path / "memory.json"
    MentorMemory(path).record("what is my stake?", "Five dollars.")

    reopened = MentorMemory(path)
    assert reopened.turns() == [
        {"role": "user", "content": "what is my stake?"},
        {"role": "assistant", "content": "Five dollars."},
    ]


def test_history_is_trimmed_to_the_kept_turns(memory):
    for i in range(6):
        memory.record(f"q{i}", f"a{i}")

    turns = memory.turns()
    assert len(turns) == 4                       # keep_turns=2, two messages each
    assert turns[0]["content"] == "q4"


def test_clearing_history_leaves_the_facts(memory):
    memory.remember("keep me")
    memory.record("q", "a")

    memory.clear_history()

    assert memory.turns() == []
    assert len(memory.facts()) == 1


def test_wipe_removes_everything(memory):
    memory.remember("keep me")
    memory.record("q", "a")

    memory.wipe()

    assert memory.facts() == []
    assert memory.turns() == []


# -------------------------------------------------------------- resilience


def test_a_corrupt_file_does_not_stop_startup(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text("{ this is not json", encoding="utf-8")

    memory = MentorMemory(path)

    assert memory.facts() == []
    memory.remember("still works")
    assert len(memory.facts()) == 1


def test_junk_entries_are_dropped_on_load(tmp_path):
    path = tmp_path / "memory.json"
    path.write_text(json.dumps({
        "facts": [{"text": "good"}, {"nope": 1}, "string"],
        "history": [
            {"role": "user", "content": "ok"},
            {"role": "system", "content": "not a chat role"},
            {"role": "assistant", "content": ""},
        ],
    }), encoding="utf-8")

    memory = MentorMemory(path)

    assert [f["text"] for f in memory.facts()] == ["good"]
    assert memory.turns() == [{"role": "user", "content": "ok"}]
