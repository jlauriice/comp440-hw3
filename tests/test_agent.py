"""Offline tests: a scripted stand-in for Claude and for Wikipedia, so the loop,
its limit of lookups, the parts in loop_parts.py and the check of an answer's
quotes can be tested with no API key and no network. The loop tested here is
the reference loop (reference_loop.py), the plainest loop, on every reply the
parts must keep it safe from; the check of the student's own loop is tested in
test_loop_check.py."""

import sys
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import agent  # noqa: E402
import baselines  # noqa: E402
import evaluate  # noqa: E402
import reference_loop  # noqa: E402
import wiki  # noqa: E402


def tool_use(name, args, i):
    return NS(type="tool_use", name=name, input=args, id=f"call{i}")


def reply(*blocks, stop="tool_use"):
    return NS(content=list(blocks), stop_reason=stop, usage=NS(input_tokens=100, output_tokens=10))


class ScriptedClaude:
    """Returns the scripted responses in order, and records what it was sent."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.sent = []
        self.messages = self

    def create(self, **kwargs):
        self.sent.append(kwargs)
        return self.responses.pop(0)


PAGES = {
    "Forrest Gump": "Forrest Gump is a 1994 American film directed by Robert Zemeckis.",
    "Robert Zemeckis": "Robert Lee Zemeckis (born May 14, 1952) is an American filmmaker. "
                       "He was born in Chicago, Illinois.",
}


def fake_lookup(name, args):
    if name == "search":
        return "1. Forrest Gump: 1994 film"
    if name == "read":
        return PAGES.get(args["title"], "no such page")
    return "Wikidata: nothing"


def test_answer_with_real_evidence_is_accepted():
    claude = ScriptedClaude([
        reply(tool_use("search", {"query": "1994 Best Picture"}, 1)),
        reply(tool_use("read", {"title": "Forrest Gump"}, 2)),
        reply(tool_use("read", {"title": "Robert Zemeckis"}, 3)),
        reply(tool_use("answer", {"verdict": "supported",
                                  "evidence": ["directed by Robert Zemeckis",
                                               "He was born in Chicago,  Illinois."],
                                  "explanation": "Zemeckis was born in Chicago."}, 4)),
    ])
    result = reference_loop.run_agent("claim", client=claude, lookup=fake_lookup)
    assert result["verdict"] == "supported"
    assert result["steps"] == 3
    assert "tokens" not in result and "cost_usd" not in result     # the loop counts no tokens
    # Each tool result went back with the id of the call it answers.
    # (The list is shared, so the last entry is Claude's answer; the one before is ours.)
    last_user = claude.sent[-1]["messages"][-2]
    assert last_user["content"][0]["tool_use_id"] == "call3"


def well_formed(sent):
    """Every request the loop sent is one the real Claude API takes: turns alternate from the
    user's, none is empty, and every tool call in a reply has exactly one result in the turn
    after it (a reply that is the last turn has none yet)."""
    for request in sent:
        turns = request["messages"]
        assert [t["role"] for t in turns] == ["user", "assistant"] * (len(turns) // 2) + ["user"] * (len(turns) % 2)
        assert turns[-1]["role"] == "user"
        for i, turn in enumerate(turns):
            assert turn["content"] not in ([], "", None), turns
            if turn["role"] == "assistant":
                ids = [b.id for b in turn["content"] if b.type == "tool_use"]
                after = turns[i + 1]["content"]
                given = [r["tool_use_id"] for r in after if isinstance(r, dict)] if isinstance(after, list) else []
                assert sorted(given) == sorted(ids), (ids, after)


class Sent(ScriptedClaude):
    """ScriptedClaude that keeps each request's conversation as it was when sent."""

    def create(self, **kwargs):
        kwargs = {**kwargs, "messages": list(kwargs["messages"])}
        self.sent.append(kwargs)
        if not self.responses:
            raise AssertionError("the loop asked the model again after the last scripted reply")
        return self.responses.pop(0)


def bare(responses, **kwargs):
    claude = Sent(responses)
    result = reference_loop.run_agent("claim", client=claude, lookup=fake_lookup, **kwargs)
    well_formed(claude.sent)
    return result, claude


MADE_UP = {"verdict": "supported", "evidence": ["Zemeckis was born in Ohio."], "explanation": "x"}
NOTHING = NS(type="text", text="I think it's true.")


def test_the_reference_loop_accepts_an_answer_whatever_its_quotes():
    """The loop does not check quotes (Nov 14): an answer quoting what the agent never read ends
    the check with that answer. The results viewer marks such a quote."""
    result, claude = bare([reply(tool_use("read", {"title": "Forrest Gump"}, 1)),
                           reply(tool_use("answer", MADE_UP, 2))])
    assert result["verdict"] == "supported" and result["evidence"] == ["Zemeckis was born in Ohio."]
    assert [t["result"] for t in result["trace"]] == [PAGES["Forrest Gump"], "accepted"]
    assert len(claude.sent) == 2


def test_the_check_of_quotes_is_still_there_for_a_loop_that_uses_it():
    read = [PAGES["Forrest Gump"]]
    assert agent.answer_problem(agent.clean_answer(MADE_UP), read).startswith(
        "These quotes are not in anything you read in this check: Zemeckis was born in Ohio.")
    for evidence in ([], [" "]):
        answer = agent.clean_answer({"verdict": "refuted", "evidence": evidence, "explanation": "x"})
        assert "needs at least one quote" in agent.answer_problem(answer, read)
    # Evidence sent as one string is checked as one quote, not letter by letter.
    answer = agent.clean_answer({"verdict": "supported", "evidence": "Zemeckis was born in Ohio."})
    assert agent.answer_problem(answer, read).endswith(": Zemeckis was born in Ohio.")
    assert agent.answer_problem(agent.clean_answer(
        {"verdict": "supported", "evidence": "directed by Robert Zemeckis"}), read) is None
    for verdict in (None, "true"):
        answer = agent.clean_answer({"verdict": verdict, "evidence": [], "explanation": "x"})
        assert agent.answer_problem(answer, read).startswith("The verdict must be")


def test_evidence_as_one_string_is_saved_as_one_quote():
    result, _ = bare([reply(tool_use("read", {"title": "Forrest Gump"}, 1)),
                      reply(tool_use("answer", {"verdict": "supported", "evidence": "directed by Robert Zemeckis",
                                                "explanation": "x"}, 2))])
    assert result["evidence"] == ["directed by Robert Zemeckis"]


def test_a_missing_or_unknown_verdict_is_no_verdict():
    for answer in ({"evidence": [], "explanation": "x"},
                   {"verdict": "true", "evidence": [], "explanation": "x"}):
        result, claude = bare([reply(tool_use("answer", answer, 1))])
        assert result["verdict"] is None and result["explanation"] == "x"
        assert len(claude.sent) == 1


def test_the_limit_stops_the_agent_with_no_verdict():
    result, claude = bare([reply(tool_use("search", {"query": f"q{i}"}, i)) for i in range(10)], max_steps=3)
    assert result["verdict"] is None
    assert result["steps"] == 3
    assert result["explanation"] == agent.RAN_OUT
    assert len(claude.sent) == 4            # the fourth reply asked for more, with 3 made
    assert not any("You have used all" in t["result"] for t in result["trace"])     # no warning


def test_an_answer_at_the_limit_ends_the_check_with_that_answer():
    claude = [reply(tool_use("search", {"query": f"q{i}"}, i)) for i in range(2)]
    claude.append(reply(tool_use("answer", {"verdict": "doesn't say", "evidence": [],
                                            "explanation": "ran short"}, 9)))
    result, _ = bare(claude, max_steps=2)
    assert result["verdict"] == "doesn't say"
    assert result["steps"] == 2


def test_one_reply_can_take_the_reference_loops_count_past_the_limit():
    """The reference loop looks at the limit once a reply, before its lookups: every lookup of a
    reply that came below the limit is made. (That is one of the ways the check accepts; rule 4
    leaves a reply that asks for more lookups than are left to the loop.)"""
    result, claude = bare([
        reply(tool_use("search", {"query": "q0"}, 0)),
        reply(tool_use("read", {"title": "Forrest Gump"}, 1), tool_use("read", {"title": "Robert Zemeckis"}, 2),
              tool_use("search", {"query": "q3"}, 3)),
        reply(tool_use("search", {"query": "q4"}, 4))], max_steps=2)
    assert result["verdict"] is None and result["explanation"] == agent.RAN_OUT
    assert result["steps"] == 4 and len(claude.sent) == 3


def test_an_answer_with_lookups_in_the_same_reply_ends_the_check():
    result, claude = bare([
        reply(tool_use("read", {"title": "Forrest Gump"}, 1)),
        reply(tool_use("search", {"query": "Zemeckis"}, 2),
              tool_use("answer", {"verdict": "supported", "evidence": ["directed by Robert Zemeckis"],
                                  "explanation": "x"}, 3)),
    ])
    assert result["verdict"] == "supported" and result["steps"] == 1
    assert len(claude.sent) == 2


def test_a_reply_that_asks_for_nothing_gets_one_reminder():
    result, claude = bare([reply(NOTHING, stop="end_turn"),
                           reply(tool_use("answer", {"verdict": "doesn't say", "evidence": [],
                                                     "explanation": "x"}, 1))])
    assert result["verdict"] == "doesn't say"
    assert claude.sent[1]["messages"][-1] == {"role": "user", "content": agent.REMINDER}
    assert [t["tool"] for t in result["trace"]] == ["(reminder)", "answer"]


def test_asking_for_nothing_twice_running_ends_with_no_verdict():
    result, claude = bare([reply(NOTHING, stop="end_turn"), reply(NOTHING, stop="end_turn")])
    assert result["verdict"] is None and result["explanation"] == agent.NO_ANSWER
    assert len(claude.sent) == 2
    assert [t["tool"] for t in result["trace"]] == ["(reminder)"]
    # A later stall is reminded again: the reminder is once in a row, not once a check.
    result, claude = bare([reply(NOTHING, stop="end_turn"), reply(tool_use("search", {"query": "q"}, 1)),
                           reply(NOTHING, stop="end_turn"), reply(NOTHING, stop="end_turn")])
    assert result["explanation"] == agent.NO_ANSWER and len(claude.sent) == 4
    assert [t["tool"] for t in result["trace"]] == ["(reminder)", "search", "(reminder)"]


def test_refusal_ends_the_check():
    result, claude = bare([reply(stop="refusal")])
    assert result["verdict"] is None and result["explanation"] == agent.DECLINED
    assert result["trace"] == [{"tool": "(refusal)", "input": {}, "result": agent.DECLINED}]
    assert len(claude.sent) == 1
    # And after a reminder.
    result, claude = bare([reply(NOTHING, stop="end_turn"), reply(NOTHING, stop="refusal")])
    assert result["explanation"] == agent.DECLINED and len(claude.sent) == 2
    assert [t["tool"] for t in result["trace"]] == ["(reminder)", "(refusal)"]


def test_a_reply_after_a_reminder_counts_the_tokens_of_both_asks():
    import loop_parts
    claude = Sent([reply(NOTHING, stop="end_turn"),
                   reply(tool_use("answer", {"verdict": "doesn't say", "evidence": [], "explanation": "x"}, 1))])
    talk = loop_parts.Conversation("claim", claude, "", [{"role": "user", "content": "Claim: c"}], [], [],
                                   fake_lookup)
    step = talk.ask()
    assert (step.usage.input_tokens, step.usage.output_tokens) == (200, 20)
    assert step.answer is not None and step.lookups == []


# ---------- the parts' last resort: no more than 3 * MAX_STEPS + 10 calls to the model ----------
# An answer sent back is not a lookup, so the limit of lookups never ends a loop that sends answers
# back. The 3b live check of Nov 14 found that such a loop with no count of its own passes the
# check, and on a model that keeps quoting what it never read would ask it again and again.

def sends_back_every_answer(claude, max_steps=agent.MAX_STEPS):
    """A loop a student might write in 3b: it sends back every answer whose quotes are not in what
    the agent read, and keeps no count of the answers it sends back."""
    import loop_parts
    talk = loop_parts.Conversation("claim", claude, "", [{"role": "user", "content": "Claim: c"}], [], [],
                                   fake_lookup)
    steps = 0
    while True:
        reply = talk.ask()
        if reply.answer:
            problem = talk.problem_with(reply.answer)
            if problem is None:
                return talk.accept(reply.answer, steps)
            talk.give(reply.answer, problem)
        elif steps >= max_steps:
            return talk.stop(agent.RAN_OUT, steps)
        for call in reply.lookups:
            talk.give(call, talk.run(call))
            steps += 1
        talk.send_results()


def made_up_answers(n):
    return [reply(tool_use("answer", MADE_UP, i)) for i in range(n)]


def test_a_loop_that_sends_back_every_answer_is_stopped_after_46_calls():
    claude = Sent(made_up_answers(100))
    result = sends_back_every_answer(claude)
    well_formed(claude.sent)
    assert len(claude.sent) == 46 == 3 * agent.MAX_STEPS + 10
    assert result["verdict"] is None and result["evidence"] == [] and result["steps"] == 0
    assert result["explanation"] == agent.TOO_MANY_ASKS.format(n=46) == \
        "The agent asked the model 46 times for this claim and was stopped."
    assert [t["tool"] for t in result["trace"]] == ["answer"] * 46 + ["(stopped)"]
    assert result["trace"][-1] == {"tool": "(stopped)", "input": {}, "result": result["explanation"]}


@pytest.mark.parametrize("max_steps", [1, 20])
def test_the_hard_stop_follows_max_steps(monkeypatch, max_steps):
    monkeypatch.setattr(agent, "MAX_STEPS", max_steps)        # read when the Conversation is made
    claude = Sent(made_up_answers(100))
    result = sends_back_every_answer(claude, max_steps)
    well_formed(claude.sent)
    assert len(claude.sent) == 3 * max_steps + 10
    assert result["explanation"] == agent.TOO_MANY_ASKS.format(n=3 * max_steps + 10)


def test_the_hard_stop_can_fall_between_a_reply_that_asks_for_nothing_and_its_reminder(monkeypatch):
    monkeypatch.setattr(agent, "MAX_STEPS", 1)               # 13 calls at most: two for each ask
    claude = Sent([r for i in range(10) for r in (reply(NOTHING, stop="end_turn"),
                                                  reply(tool_use("answer", MADE_UP, i)))])
    result = sends_back_every_answer(claude, 1)
    well_formed(claude.sent)
    assert len(claude.sent) == 13
    assert [t["tool"] for t in result["trace"]] == ["(reminder)", "answer"] * 6 + ["(stopped)"]
    assert result["explanation"] == agent.TOO_MANY_ASKS.format(n=13)


def test_a_loop_that_asks_again_after_the_hard_stop_stops_with_an_error(monkeypatch):
    import loop_parts
    monkeypatch.setattr(agent, "MAX_STEPS", 1)
    claude = Sent(made_up_answers(20))
    talk = loop_parts.Conversation("claim", claude, "", [{"role": "user", "content": "Claim: c"}], [], [],
                                   fake_lookup)
    for _ in range(13):
        step = talk.ask()
        talk.give(step.answer, "Answer rejected. ")
        talk.send_results()
    step = talk.ask()
    assert step.answer.why == agent.TOO_MANY_ASKS.format(n=13) and step.lookups == []
    assert (step.usage.input_tokens, step.usage.output_tokens) == (0, 0)
    with pytest.raises(RuntimeError, match="The loop asked again after that."):
        talk.ask()
    assert len(claude.sent) == 13


def test_evaluate_counts_the_hard_stop_as_no_verdict(monkeypatch, tmp_path, capsys):
    import json
    record = tmp_path / "runs" / "part1" / "loop-check.txt"
    record.parent.mkdir(parents=True)
    record.write_text("yours\n")
    monkeypatch.setattr(agent, "LOOP_CHECK", record)
    monkeypatch.setitem(evaluate.METHODS, "agent",
                        lambda claim: sends_back_every_answer(Sent(made_up_answers(50))))
    claims = tmp_path / "claims.jsonl"
    claims.write_text(json.dumps({"id": "c1", "claim": "claim", "source": "hover", "label": "SUPPORTED",
                                  "hops": 2}) + "\n")
    monkeypatch.setattr(sys, "argv", ["evaluate.py", str(claims), "--methods", "agent",
                                      "--out", str(tmp_path / "run")])
    evaluate.main()
    assert "1 runs gave no verdict (for example a refusal, or out of lookups)." in capsys.readouterr().out
    row = json.loads((tmp_path / "run" / "agent.jsonl").read_text())
    assert row["verdict"] is None and row["explanation"] == agent.TOO_MANY_ASKS.format(n=46)


def test_scoring_hover_and_fever():
    hover_true = {"source": "hover", "label": "SUPPORTED"}
    hover_false = {"source": "hover", "label": "NOT_SUPPORTED"}
    fever_nei = {"source": "fever", "label": "NOT ENOUGH INFO"}
    assert evaluate.is_correct(hover_true, "supported")
    assert evaluate.is_correct(hover_false, "refuted")
    assert evaluate.is_correct(hover_false, "doesn't say")
    assert not evaluate.is_correct(hover_true, None)
    assert evaluate.is_correct(fever_nei, "doesn't say")
    assert not evaluate.is_correct(fever_nei, "refuted")
    mine = {"source": "mine", "label": "refuted"}
    assert evaluate.is_correct(mine, "refuted")
    assert not evaluate.is_correct(mine, "doesn't say")
    assert evaluate.group_of(mine) == "Your claims"
    assert evaluate.group_of(fever_nei) == "FEVER"


def test_no_verdict_is_always_wrong():
    for label in ["SUPPORTED", "NOT_SUPPORTED"]:
        assert not evaluate.is_correct({"source": "hover", "label": label}, None)
    for label in ["SUPPORTS", "REFUTES", "NOT ENOUGH INFO"]:
        assert not evaluate.is_correct({"source": "fever", "label": label}, None)
    assert not evaluate.is_correct({"source": "mine", "label": "doesn't say"}, None)


def test_sections_and_read(monkeypatch):
    text = "Intro line.\n\n== Early life ==\nBorn in Chicago.\n\n=== School ===\nWent to school.\n"
    monkeypatch.setattr(wiki, "page_text", lambda title: (text, "Robert Zemeckis"))
    assert wiki.split_sections(text) == [("Introduction", "Intro line."),
                                         ("Early life", "Born in Chicago."),
                                         ("School", "Went to school.")]
    assert "Sections: Early life, School" in wiki.read("zemeckis")
    assert "Born in Chicago." in wiki.read("zemeckis", "early life")
    assert "no section called" in wiki.read("zemeckis", "Career")


class FakeResponse:
    """What requests.get() returns, for a scripted Wikipedia."""

    def __init__(self, status, data=None, retry_after=None):
        self.status_code = status
        self.headers = {"Retry-After": retry_after} if retry_after else {}
        self.data = data

    def json(self):
        return self.data

    def raise_for_status(self):
        if self.status_code >= 400:
            raise wiki.requests.HTTPError(f"{self.status_code} error")


FOUND = {"query": {"search": [{"title": "Forrest Gump", "snippet": "1994 film"}]}}


def scripted_wikipedia(monkeypatch, tmp_path, responses):
    """Send wiki.py's requests to the scripted responses, in order, with the
    cache in tmp_path. Returns the headers of each request and each pause.
    WIKIPEDIA_CONTACT starts unset, whatever your own environment or .env says,
    and the warning about it starts unprinted, as at the start of a run."""
    sent, pauses = [], []
    responses = list(responses)
    monkeypatch.setattr(wiki, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(wiki.requests, "get",
                        lambda url, **kwargs: sent.append(kwargs["headers"]) or responses.pop(0))
    monkeypatch.setattr(wiki.time, "sleep", pauses.append)
    monkeypatch.delenv("WIKIPEDIA_CONTACT", raising=False)
    monkeypatch.setattr(wiki, "_warned", False)
    return sent, pauses


def test_user_agent_gives_your_contact(monkeypatch, tmp_path, capsys):
    sent, _ = scripted_wikipedia(monkeypatch, tmp_path, [FakeResponse(200, FOUND)])
    # Set after wiki.py was imported, as when a script loads .env late.
    monkeypatch.setenv("WIKIPEDIA_CONTACT", "student@macalester.edu")
    assert wiki.search("Forrest Gump").startswith("1. Forrest Gump")
    assert sent[0]["User-Agent"] == ("COMP440-HW3/0.1 (student@macalester.edu; "
                                     "Macalester College course assignment)")
    assert "WIKIPEDIA_CONTACT" not in capsys.readouterr().err


def test_without_a_contact_it_gives_the_course_site_and_warns_once(monkeypatch, tmp_path, capsys):
    sent, _ = scripted_wikipedia(monkeypatch, tmp_path,
                                 [FakeResponse(200, FOUND), FakeResponse(200, FOUND)])
    wiki.search("Forrest Gump")
    wiki.search("Robert Zemeckis")
    assert len(sent) == 2
    assert all(h["User-Agent"] == wiki.SHARED_USER_AGENT for h in sent)
    assert "https://shilad.github.io/comp440-website/" in wiki.SHARED_USER_AGENT
    assert capsys.readouterr().err.count("WIKIPEDIA_CONTACT is not set") == 1


def test_too_many_requests_waits_as_long_as_asked(monkeypatch, tmp_path):
    _, pauses = scripted_wikipedia(monkeypatch, tmp_path, [
        FakeResponse(429, retry_after="7"), FakeResponse(200, FOUND)])
    assert wiki.search("Forrest Gump").startswith("1. Forrest Gump")
    assert pauses == [7]
    # With no Retry-After header, it waits 2, 4, 8, ... seconds.
    _, pauses = scripted_wikipedia(monkeypatch, tmp_path, [
        FakeResponse(429), FakeResponse(429), FakeResponse(200, FOUND)])
    assert wiki.search("Robert Zemeckis").startswith("1. Forrest Gump")
    assert pauses == [2, 4]


def test_too_many_requests_for_too_long_is_an_error(monkeypatch, tmp_path):
    _, pauses = scripted_wikipedia(monkeypatch, tmp_path,
                                   [FakeResponse(429, retry_after="100")] * 20)
    with pytest.raises(wiki.RateLimited):
        wiki.search("Forrest Gump")
    assert pauses == [wiki.MAX_PAUSE] * 5   # 60 seconds at most each time, 300 in all
    assert list(tmp_path.iterdir()) == []   # nothing cached


def test_a_claim_that_fails_is_not_saved_and_runs_again(monkeypatch, tmp_path, capsys):
    item = {"id": "c1", "claim": "claim", "source": "hover", "label": "NOT_SUPPORTED", "hops": 2}

    def rate_limited(claim):
        raise wiki.RateLimited("too many requests")

    monkeypatch.setitem(evaluate.METHODS, "agent", rate_limited)
    [result] = evaluate.run_method("agent", [item], tmp_path, workers=1)
    assert result["verdict"] is None and not result["correct"]
    assert (tmp_path / "agent.jsonl").read_text() == ""
    evaluate.report([item], {"agent": [result]})
    assert "run the same command again" in capsys.readouterr().out

    answer = {"verdict": "doesn't say", "evidence": [], "explanation": "x"}
    monkeypatch.setitem(evaluate.METHODS, "agent", lambda claim: reference_loop.run_agent(
        claim, client=ScriptedClaude([reply(tool_use("answer", answer, 1))]), lookup=fake_lookup))
    [result] = evaluate.run_method("agent", [item], tmp_path, workers=1)
    assert result["verdict"] == "doesn't say" and result["correct"]
    assert len((tmp_path / "agent.jsonl").read_text().splitlines()) == 1


def test_one_search_reads_the_top_hit():
    query = NS(type="text", text='"1994 Best Picture"')
    answer = NS(type="text", text='{"verdict": "refuted", "explanation": "wrong state"}')
    claude = ScriptedClaude([reply(query, stop="end_turn"), reply(answer, stop="end_turn")])
    read_titles, queries = [], []
    result = baselines.one_search(
        "claim", client=claude,
        search=lambda q: queries.append(q) or "1. Forrest Gump: snippet\n2. Other: x",
        read=lambda title: read_titles.append(title) or "page text")
    assert queries == ["1994 Best Picture"]
    assert read_titles == ["Forrest Gump"]
    assert result["tokens"] == {"input": 200, "output": 20}
    assert result["verdict"] == "refuted"
    assert result["steps"] == 2


def test_one_search_unwraps_only_a_wholly_quoted_query():
    cases = {'"1994 Best Picture"': "1994 Best Picture",
             '"One Dance" Drake Wizkid Kyla song': '"One Dance" Drake Wizkid Kyla song',
             '"One Dance" "Drake"': '"One Dance" "Drake"',
             "Forrest Gump director": "Forrest Gump director"}
    for written, searched in cases.items():
        query = NS(type="text", text=written)
        answer = NS(type="text", text='{"verdict": "refuted", "explanation": "x"}')
        claude = ScriptedClaude([reply(query, stop="end_turn"), reply(answer, stop="end_turn")])
        queries = []
        baselines.one_search("claim", client=claude,
                             search=lambda q: queries.append(q) or "1. Forrest Gump: snippet",
                             read=lambda title: "page text")
        assert queries == [searched]


def test_lookup_prints_and_logs(monkeypatch, tmp_path, capsys):
    import lookup
    monkeypatch.setattr(lookup, "load_dotenv", lambda: None)  # leave your own .env alone
    monkeypatch.setattr(lookup, "LOG", tmp_path / "lookups.jsonl")
    monkeypatch.setattr(wiki, "search", lambda q: f"1. Forrest Gump: {q}")
    monkeypatch.setattr(sys, "argv", ["lookup.py", "search", "1994 Best Picture"])
    lookup.main()
    assert "1. Forrest Gump: 1994 Best Picture" in capsys.readouterr().out
    assert '"tool": "search"' in (tmp_path / "lookups.jsonl").read_text()
