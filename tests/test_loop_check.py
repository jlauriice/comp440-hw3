"""Do not open this file before step 1a is done: it holds complete loops, and
reading them first gives the exercise away.

Offline tests for check_loop.py, the check of the loop in my_loop.py, and for how
the agent chooses between that loop and the reference loop. Every test keeps
runs/part1/loop-check.txt in a temporary folder, so none of them reads or leaves
a runs/ folder in the repository.

Since November 14 the check asks for the plainest loop (five rules), and the
reference loop is that loop. Loops written for the six rules before then, which
check quotes, warn the model at the limit and remind it, must still pass and
still run as they did: the raw loop below and the full loop are kept for that.

Since November 16 rule 4 leaves a reply that asks for more lookups than are
left to the loop: it may stop there or ask the model again (the section "where
the loop looks at the limit" below)."""

import json
import re
import shutil
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(ROOT))

import agent  # noqa: E402
import check  # noqa: E402
import check_loop  # noqa: E402
import evaluate  # noqa: E402
import wiki  # noqa: E402

# A loop as it was written before the parts in loop_parts.py: straight against the Claude API, for
# the six rules of November 13 (it checks quotes, warns the model at the limit, reminds it, and
# stops on a refusal). Students who started step 1a before it changed wrote loops like it, and it
# must still pass, so most of the broken loops below are made by editing it.
REFERENCE = '''"""The reference loop. The homework uses it in Part 0, before your own loop, in
my_loop.py, has passed the check (uv run python check_loop.py), and not after.

Do not open this file before step 1a is done: reading it first gives the
exercise away. After that, compare it with yours (the write-up asks you to).
"""

import anthropic

from agent import (ACCEPTED, DECLINED, INSTRUCTIONS, MAX_REJECTED, MAX_STEPS, MODEL, NO_ANSWER,
                   OUT_OF_STEPS, RAN_OUT, REJECTED, REJECTED_TOO_OFTEN, REMINDED, REMINDER,
                   TOOLS, answer_problem, clean_answer, finish, run_tool)


def run_agent(claim, client=None, max_steps=MAX_STEPS, lookup=run_tool):
    """Check one claim. Returns a dict with the verdict, the evidence, the
    trace of every step, and the number of lookups."""
    client = client or anthropic.Anthropic()
    system = INSTRUCTIONS.read_text()
    messages = [{"role": "user", "content": f"Claim: {claim}"}]
    trace, read_so_far = [], []
    steps = 0
    rejected = 0        # how many answers the loop has sent back
    warned = False      # has it been told it is out of steps?

    while True:
        response = client.messages.create(
            model=MODEL, max_tokens=16000, system=system, tools=TOOLS, messages=messages,
        )
        messages.append({"role": "assistant", "content": response.content})

        if response.stop_reason == "refusal":
            return finish(claim, None, [], DECLINED, trace, steps)

        calls = [block for block in response.content if block.type == "tool_use"]
        if not calls:
            # Claude stopped without calling a tool. Remind it once how to finish.
            if trace and trace[-1]["tool"] == "(reminder)":
                return finish(claim, None, [], NO_ANSWER, trace, steps)
            trace.append({"tool": "(reminder)", "input": {}, "result": REMINDED})
            messages.append({"role": "user", "content": REMINDER})
            continue

        results = []
        warned_before = warned
        for call in calls:
            if call.name == "answer":
                answer = clean_answer(call.input)
                problem = answer_problem(answer, read_so_far)
                if problem is None:
                    trace.append({"tool": "answer", "input": call.input, "result": ACCEPTED})
                    return finish(claim, answer["verdict"], answer["evidence"],
                                  answer["explanation"], trace, steps)
                result = REJECTED + problem
                rejected += 1
                if rejected >= MAX_REJECTED:
                    trace.append({"tool": "answer", "input": call.input, "result": result})
                    return finish(claim, None, [], REJECTED_TOO_OFTEN.format(n=rejected),
                                  trace, steps)
            elif steps >= max_steps:
                if warned_before:
                    # It was told last turn that it was out of steps: stop here.
                    return finish(claim, None, [], RAN_OUT, trace, steps)
                result = OUT_OF_STEPS.format(n=max_steps)
                warned = True
            else:
                steps += 1
                result = lookup(call.name, call.input)
                if call.name != "search":  # snippets are too short to count as evidence
                    read_so_far.append(result)
            trace.append({"tool": call.name, "input": call.input, "result": result})
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": result})

        messages.append({"role": "user", "content": results})
'''

# The full loop: reference_loop.py as it was from November 13 to 14, built with the parts for the
# six rules. Students who passed the check in that time, and the instructor's own copy, have loops
# like it. With the parts as they are now, it must still pass and still run as it did.
FULL_LOOP = '''"""The reference loop. The homework uses it in Part 0, before your own loop, in
my_loop.py, has passed the check (uv run python check_loop.py), and not after.
It is built from the same parts as yours, in loop_parts.py.

Do not open this file before step 1a is done: reading it first gives the
exercise away. After that, compare it with yours (the write-up asks you to).
"""

import anthropic

from agent import (DECLINED, INSTRUCTIONS, MAX_REJECTED, MAX_STEPS, NO_ANSWER, OUT_OF_STEPS,
                   RAN_OUT, REJECTED_TOO_OFTEN, run_tool)
from loop_parts import Conversation


def run_agent(claim, client=None, max_steps=MAX_STEPS, lookup=run_tool):
    """Check one claim. Returns what talk.accept() or talk.stop() returns."""
    client = client or anthropic.Anthropic()
    system = INSTRUCTIONS.read_text()
    messages = [{"role": "user", "content": f"Claim: {claim}"}]
    trace, read_so_far = [], []
    talk = Conversation(claim, client, system, messages, trace, read_so_far, lookup)
    steps = 0           # lookups made so far
    rejected = 0        # answers sent back so far
    warned = False      # has the model been told it is out of lookups?
    reminded = False    # was the model reminded after its last reply?

    while True:
        reply = talk.ask()
        if reply.refused:
            return talk.stop(DECLINED, steps)
        if not reply.calls:
            # The model asked for nothing. Remind it once how to finish.
            if reminded:
                return talk.stop(NO_ANSWER, steps)
            talk.remind()
            reminded = True
            continue
        reminded = False

        warned_before = warned
        for call in reply.calls:
            if call.is_answer:
                problem = talk.problem_with(call)
                if problem is None:
                    return talk.accept(call, steps)
                talk.give(call, problem)
                rejected += 1
                if rejected >= MAX_REJECTED:
                    return talk.stop(REJECTED_TOO_OFTEN.format(n=rejected), steps)
            elif steps >= max_steps:
                if warned_before:
                    # It was told on an earlier reply that it was out of lookups: stop here.
                    return talk.stop(RAN_OUT, steps)
                talk.give(call, OUT_OF_STEPS.format(n=max_steps))
                warned = True
            else:
                talk.give(call, talk.run(call))
                steps += 1
        talk.send_results()
'''
KIT_REFERENCE = (ROOT / "reference_loop.py").read_text()     # the plainest loop, with the parts
NOT_WRITTEN = "the loop is not written yet."
FIVE = [f"ok         {n}. {title}" for n, title in enumerate(check_loop.RULES, 1)]


@pytest.fixture(autouse=True)
def saved(monkeypatch, tmp_path):
    """runs/part1/loop-check.txt, in a temporary folder."""
    path = tmp_path / "runs" / "part1" / "loop-check.txt"
    monkeypatch.setattr(agent, "LOOP_CHECK", path)
    return path


def a_loop(tmp_path, source, monkeypatch=None):
    """Write source as my_loop.py in its own folder; with monkeypatch, make it the one
    check_loop.py checks."""
    folder = tmp_path / f"loop{len(list(tmp_path.glob('loop*')))}"
    folder.mkdir()
    path = folder / "my_loop.py"
    path.write_text(source)
    if monkeypatch is not None:
        monkeypatch.setattr(check_loop, "MY_LOOP", path)
    return path


def edited(source, *edits):
    for old, new in edits:
        assert source.count(old) == 1, old
        source = source.replace(old, new)
    return source


def broken(*edits):
    """The raw loop with each (old, new) edit made once."""
    return edited(REFERENCE, *edits)


def kit(*edits):
    """The reference loop, the plainest loop with the parts, with each (old, new) edit made once."""
    return edited(KIT_REFERENCE, *edits)


def full(*edits):
    """The full loop with the parts, with each (old, new) edit made once."""
    return edited(FULL_LOOP, *edits)


def shown(path):
    return check_loop.lines(check_loop.check(path))


# ---------- the skeleton, the reference loop and the way out ----------

def test_the_skeleton_gives_five_not_yet_lines_and_no_file(monkeypatch, saved, capsys):
    monkeypatch.setattr(check_loop, "MY_LOOP", ROOT / "my_loop.py")
    assert check_loop.main([]) == 1
    printed = capsys.readouterr().out.splitlines()
    assert len(check_loop.RULES) == 5
    assert printed[:5] == [f"NOT YET    {n}. {title}: {NOT_WRITTEN}"
                           for n, title in enumerate(check_loop.RULES, 1)]
    assert printed[5:] == ["", f"The rule (1. {check_loop.RULES[0]}): {check_loop.rule_text(1)}", "",
                           check_loop.FAILED]
    assert not saved.exists()
    assert agent.which_loop() == "reference"


@pytest.mark.parametrize("name", ["only the first call", "an empty turn after nothing",
                                  "the limit is MAX_STEPS"])
def test_the_check_states_the_rule_behind_the_first_not_yet_line(tmp_path, monkeypatch, capsys, name):
    """The page does not list the rules: the check states the one behind the first NOT YET line,
    in plain words, once, under the five lines."""
    rule, edits, _ = BROKEN[name]
    a_loop(tmp_path, broken(*edits), monkeypatch)
    assert check_loop.main([]) == 1
    printed = capsys.readouterr().out.splitlines()
    stated = [line for line in printed if line.startswith("The rule (")]
    assert stated == [f"The rule ({rule}. {check_loop.RULES[rule - 1]}): {check_loop.rule_text(rule)}"]
    assert printed.index(stated[0]) == 6


def test_the_rules_are_stated_without_code_names_and_without_the_old_rules():
    for n in range(1, 6):
        text = check_loop.rule_text(n)
        assert not any(name in text for name in ("MAX_", "max_steps", "talk.", "()", "_"))
        for gone in ("evidence check", "warning", "remind", "refuse", "rejected"):
            assert gone not in text, (n, gone)
    assert "12 in a real run" in check_loop.rule_text(4)


def test_no_rule_is_stated_when_every_rule_passes(tmp_path, monkeypatch, capsys):
    a_loop(tmp_path, KIT_REFERENCE, monkeypatch)
    assert check_loop.main([]) == 0
    assert "The rule (" not in capsys.readouterr().out


def test_the_skeleton_names_no_rule_and_gives_nothing_more():
    """The page does not list the rules: the student meets each one when the check states it."""
    source = (ROOT / "my_loop.py").read_text()
    assert "# Your loop should repeatedly call the model with the message history so far" in source
    for title in check_loop.RULES:
        assert title not in source
    assert 'raise NotImplementedError("The loop is not written yet: see step 1a.")' in source
    below = source[source.index("# ---- your loop goes below this line"):].strip().splitlines()
    assert [line.strip() for line in below[1:]] == [
        'raise NotImplementedError("The loop is not written yet: see step 1a.")']
    assert "messages.create" not in source and "tool_result" not in source


def test_the_skeleton_keeps_every_name_and_set_up_line_a_forked_loop_uses():
    """Students take changes to my_loop.py through the page's Update button, a git merge into the
    file that holds their loop. Every name the file imported and every set-up line it had stays, so
    a loop written below the line keeps running after the merge."""
    source = (ROOT / "my_loop.py").read_text()
    for line in ("from agent import (ACCEPTED, DECLINED, INSTRUCTIONS, MAX_REJECTED, MAX_STEPS, MODEL, NO_ANSWER,",
                 "                   OUT_OF_STEPS, RAN_OUT, REJECTED, REJECTED_TOO_OFTEN, REMINDED, REMINDER,",
                 "                   TOOLS, answer_problem, clean_answer, finish, run_tool)",
                 "def run_agent(claim, client=None, max_steps=MAX_STEPS, lookup=run_tool):",
                 "    talk = Conversation(claim, client, system, messages, trace, read_so_far, lookup)",
                 "    steps = 0          # lookups made so far"):
        assert line in source.splitlines(), line
    assert "    rejected = 0  " in source


@pytest.mark.parametrize("source", [KIT_REFERENCE, FULL_LOOP, REFERENCE],
                         ids=["the-reference-loop", "the-full-loop", "the-raw-loop"])
def test_a_right_loop_passes_and_is_saved_as_yours(tmp_path, monkeypatch, saved, capsys, source):
    a_loop(tmp_path, source, monkeypatch)
    assert check_loop.main([]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed == FIVE + ["", check_loop.PASSED]
    assert saved.read_text().splitlines() == ["yours"] + printed
    assert agent.which_loop() == "yours"
    assert not agent.counts_tokens()      # no token line: tokens and cost stay hidden


def test_the_reference_loop_is_the_plainest_loop():
    """The reference loop is the five lines of the instructor's loop (Nov 14), written with the parts:
    no check of quotes, no warning at the limit, and no reminder or refusal of its own."""
    body = KIT_REFERENCE[KIT_REFERENCE.index("    while True:"):].strip().splitlines()
    assert [line.strip() for line in body] == [
        "while True:",
        "reply = talk.ask()",
        "if reply.answer:",
        "return talk.accept(reply.answer, steps)",
        "if steps >= max_steps:",
        "return talk.stop(RAN_OUT, steps)",
        "for call in reply.lookups:",
        "talk.give(call, talk.run(call))",
        "steps += 1",
        "talk.send_results()"]
    for name in ("problem_with", "OUT_OF_STEPS", "remind", "refused", "rejected", "warned"):
        assert name not in KIT_REFERENCE, name


def test_there_is_no_way_to_keep_the_reference_loop(saved, capsys):
    """The instructor, Nov 11: "i don't want them to be able to use the reference loop." The option
    is gone, and an old record of that choice counts as a loop that has not passed."""
    with pytest.raises(SystemExit):
        check_loop.main(["--use-reference"])
    assert not saved.exists()
    saved.parent.mkdir(parents=True)
    saved.write_text("reference\nRecorded: your copy keeps using the reference loop.\n")
    assert agent.which_loop() == "not passed"
    with pytest.raises(agent.LoopNotPassed):
        agent.run_agent("c")


def test_a_failing_check_after_a_pass_stops_the_agent(tmp_path, monkeypatch, saved, capsys):
    a_loop(tmp_path, REFERENCE, monkeypatch)
    assert check_loop.main([]) == 0 and agent.which_loop() == "yours"
    capsys.readouterr()
    # A later change breaks the loop: no agent runs until it passes again, and the file stays,
    # so the homework page still counts step 1a as done.
    a_loop(tmp_path, broken(("                steps += 1\n", "")), monkeypatch)
    assert check_loop.main([]) == 1
    printed = capsys.readouterr().out.splitlines()
    assert printed[5:] == ["", f"The rule (4. {check_loop.RULES[3]}): {check_loop.rule_text(4)}", "",
                           check_loop.FAILED, check_loop.NOT_PASSING_NOW]
    assert saved.read_text().splitlines() == ["not passing", check_loop.FELL_BACK] + printed[:5]
    assert agent.which_loop() == "not passed"
    # Once it says "not passing", a failing check leaves the file as it is.
    before = saved.read_text()
    assert check_loop.main([]) == 1
    assert check_loop.NOT_PASSING_NOW not in capsys.readouterr().out
    assert saved.read_text() == before
    # And passing again puts the agent back on the student's loop.
    a_loop(tmp_path, KIT_REFERENCE, monkeypatch)
    assert check_loop.main([]) == 0 and agent.which_loop() == "yours"


def printing(source, what):
    """The loop, printing `what` after each reply from the model."""
    old = '        messages.append({"role": "assistant", "content": response.content})\n'
    assert source.count(old) == 1
    return source.replace(old, old + f"        {what}\n")


IDS = 'print("ids:", [b.id for b in response.content if b.type == "tool_use"])'


def test_what_the_loop_printed_is_shown_for_the_first_failing_rule(tmp_path, monkeypatch, saved, capsys):
    # Only the first lookup of each reply is made, so rule 2 is the first to fail.
    a_loop(tmp_path, printing(broken(("for call in calls:", "for call in calls[:1]:")),
                              IDS + "; print('to stderr', file=sys.stderr)"), monkeypatch)
    source = check_loop.MY_LOOP.read_text().replace("import anthropic\n",
                                                    "import sys\n\nimport anthropic\n", 1)
    check_loop.MY_LOOP.write_text(source)
    assert check_loop.main([]) == 1
    printed = capsys.readouterr().out.splitlines()
    assert printed[1].startswith("NOT YET    2. ")
    assert printed[5:10] == ["", f"The rule (2. {check_loop.RULES[1]}): {check_loop.rule_text(2)}", "",
                             check_loop.FAILED, ""]
    assert printed[10] == "What your loop printed during the made-up check for rule 2:"
    shown_ = printed[11:]
    # Only the made-up check for rule 2, whose tool ids carry its name; stderr too.
    assert shown_[0] == "ids: ['toolu_lookups_11']"
    assert shown_[1] == "to stderr"
    assert all("toolu_" not in line or "toolu_lookups_" in line for line in shown_)
    # Five replies: its answer quotes the read it did not make, so it is sent back.
    assert len(shown_) == 2 * 5
    assert not saved.exists()        # and nothing of it is saved


def test_what_the_loop_printed_is_not_shown_when_every_rule_passes(tmp_path, monkeypatch, saved, capsys):
    a_loop(tmp_path, printing(REFERENCE, IDS), monkeypatch)
    assert check_loop.main([]) == 0
    out = capsys.readouterr().out
    assert "ids:" not in out and "What your loop printed" not in out
    assert "ids:" not in saved.read_text()


def test_long_output_is_cut_to_40_lines(tmp_path, monkeypatch, capsys):
    a_loop(tmp_path, printing(broken(("system=system, ", "")),
                              "print('\\n'.join(f'line {i}' for i in range(30)))"), monkeypatch)
    assert check_loop.main([]) == 1
    out = capsys.readouterr().out
    shown_ = out.split("What your loop printed during the made-up check for rule 1:\n")[1].splitlines()
    # The made-up check for rule 1 gets three replies: 90 lines printed, 40 shown.
    assert shown_[:40] == [f"line {i % 30}" for i in range(40)]
    assert shown_[40:] == ["(50 more lines not shown)"]


def test_nothing_is_shown_when_the_loop_printed_nothing(tmp_path, monkeypatch, capsys):
    a_loop(tmp_path, broken(("system=system, ", "")), monkeypatch)
    assert check_loop.main([]) == 1
    assert "What your loop printed" not in capsys.readouterr().out


def test_a_failing_check_makes_no_file_when_there_was_none(tmp_path, monkeypatch, saved, capsys):
    a_loop(tmp_path, broken(("                steps += 1\n", "")), monkeypatch)
    assert check_loop.main([]) == 1
    assert not saved.exists() and not saved.parent.exists()
    assert check_loop.NOT_PASSING_NOW not in capsys.readouterr().out


def test_which_loop_follows_the_file(saved):
    """No file: the loop has never passed, so Part 0 runs the reference loop. "yours": the loop
    passed. Anything else (a loop that fails now, an old record of keeping the reference loop, a
    file that cannot be read) is a loop that has not passed, and no agent runs on it."""
    assert agent.which_loop() == "reference"           # no file
    saved.parent.mkdir(parents=True)
    for text, loop in (("yours\nok ...\n", "yours"), ("yours", "yours"),
                       ("reference\n", "not passed"), ("not passing\n", "not passed"), ("", "not passed"),
                       ("yours \n", "not passed"), ("Yours\n", "not passed"),
                       ("ok\nyours\n", "not passed")):
        saved.write_text(text)
        assert agent.which_loop() == loop, text
    saved.write_bytes(b"\xff\xfe\x00yours")              # not text
    assert agent.which_loop() == "not passed"
    saved.unlink()
    saved.mkdir()                                        # not a file
    assert agent.which_loop() == "not passed"


# ---------- fair to loops written differently ----------

# Loops for the six rules, organised differently from the raw loop and from each other. The first
# asks the model in a nested helper function, stops through another, keeps a flag for the
# reminder and for the limit, checks the limit for the whole turn, and sends the reminder as a
# text block.
HELPERS = '''
import anthropic

from agent import (ACCEPTED, DECLINED, INSTRUCTIONS, MAX_REJECTED, MAX_STEPS, MODEL, NO_ANSWER,
                   OUT_OF_STEPS, RAN_OUT, REJECTED, REJECTED_TOO_OFTEN, REMINDED, REMINDER,
                   TOOLS, answer_problem, clean_answer, finish, run_tool)


def run_agent(claim, client=None, max_steps=MAX_STEPS, lookup=run_tool):
    client = client or anthropic.Anthropic()
    system = INSTRUCTIONS.read_text()
    messages = [{"role": "user", "content": f"Claim: {claim}"}]
    trace, read_so_far = [], []
    steps = 0
    rejected = 0
    told_limit = False
    reminded = False

    def ask():
        reply = client.messages.create(model=MODEL, max_tokens=16000, system=system,
                                       tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": reply.content})
        return reply

    def no_verdict(why):
        return finish(claim, None, [], why, trace, steps)

    while True:
        reply = ask()
        if reply.stop_reason == "refusal":
            return no_verdict(DECLINED)
        calls = [block for block in reply.content if block.type == "tool_use"]
        if not calls:
            if reminded:
                return no_verdict(NO_ANSWER)
            reminded = True
            trace.append({"tool": "(reminder)", "input": {}, "result": REMINDED})
            messages.append({"role": "user", "content": [{"type": "text", "text": REMINDER}]})
            continue
        reminded = False
        if told_limit and steps >= max_steps and any(c.name != "answer" for c in calls):
            return no_verdict(RAN_OUT)
        results = []
        for call in calls:
            if call.name == "answer":
                answer = clean_answer(call.input)
                problem = answer_problem(answer, read_so_far)
                if problem is None:
                    trace.append({"tool": "answer", "input": call.input, "result": ACCEPTED})
                    return finish(claim, answer["verdict"], answer["evidence"],
                                  answer["explanation"], trace, steps)
                rejected += 1
                trace.append({"tool": "answer", "input": call.input, "result": REJECTED + problem})
                if rejected >= MAX_REJECTED:
                    return no_verdict(REJECTED_TOO_OFTEN.format(n=rejected))
                content = REJECTED + problem
            elif steps >= max_steps:
                told_limit = True
                content = OUT_OF_STEPS.format(n=max_steps)
                trace.append({"tool": call.name, "input": call.input, "result": content})
            else:
                content = lookup(call.name, call.input)
                steps += 1
                trace.append({"tool": call.name, "input": call.input, "result": content})
                if call.name != "search":
                    read_so_far.append(content)
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": content})
        messages.append({"role": "user", "content": results})
'''

# The second turns the reply into dicts for the conversation, counts quiet replies, keeps
# the results by call id and builds the user turn from them at the end, records the
# cleaned answer in the trace, and runs a bounded number of turns.
BY_ID = '''
import anthropic

from agent import (ACCEPTED, DECLINED, INSTRUCTIONS, MAX_REJECTED, MAX_STEPS, MODEL, NO_ANSWER,
                   OUT_OF_STEPS, RAN_OUT, REJECTED, REJECTED_TOO_OFTEN, REMINDED, REMINDER,
                   TOOLS, answer_problem, clean_answer, finish, run_tool)


def run_agent(claim, client=None, max_steps=MAX_STEPS, lookup=run_tool):
    client = client or anthropic.Anthropic()
    system = INSTRUCTIONS.read_text()
    messages = [{"role": "user", "content": f"Claim: {claim}"}]
    trace, read_so_far = [], []
    steps = 0
    rejected = 0
    warned_on = None
    quiet = 0

    for turn in range(100):
        response = client.messages.create(model=MODEL, max_tokens=16000, system=system,
                                          tools=TOOLS, messages=messages)
        messages.append({"role": "assistant",
                         "content": [block.model_dump() for block in response.content]})
        calls = [block for block in response.content if block.type == "tool_use"]
        if response.stop_reason == "refusal":
            return finish(claim, None, [], DECLINED, trace, steps)
        if not calls:
            quiet += 1
            if quiet == 2:
                return finish(claim, None, [], NO_ANSWER, trace, steps)
            trace.append({"tool": "(reminder)", "input": {}, "result": REMINDED})
            messages.append({"role": "user", "content": REMINDER})
            continue
        quiet = 0
        sent = {}
        for call in calls:
            if call.name == "answer":
                answer = clean_answer(call.input)
                problem = answer_problem(answer, read_so_far)
                if not problem:
                    trace.append({"tool": "answer", "input": answer, "result": ACCEPTED})
                    return finish(claim, answer["verdict"], answer["evidence"],
                                  answer["explanation"], trace, steps)
                rejected = rejected + 1
                trace.append({"tool": "answer", "input": answer, "result": REJECTED + problem})
                if rejected == MAX_REJECTED:
                    return finish(claim, None, [], REJECTED_TOO_OFTEN.format(n=rejected),
                                  trace, steps)
                sent[call.id] = REJECTED + problem
            elif steps < max_steps:
                found = lookup(call.name, call.input)
                steps = steps + 1
                trace.append({"tool": call.name, "input": call.input, "result": found})
                if call.name in ("read", "wikidata"):
                    read_so_far.append(found)
                sent[call.id] = found
            elif warned_on is not None and warned_on < turn:
                return finish(claim, None, [], RAN_OUT, trace, steps)
            else:
                warned_on = turn
                sent[call.id] = OUT_OF_STEPS.format(n=max_steps)
                trace.append({"tool": call.name, "input": call.input, "result": sent[call.id]})
        messages.append({"role": "user", "content": [
            {"type": "tool_result", "tool_use_id": call_id, "content": result}
            for call_id, result in sent.items()]})
    return finish(claim, None, [], RAN_OUT, trace, steps)
'''


# The third asks the model through a helper function at the top of the file, which is given
# the client, the system text and the conversation, and checks answers in another.
MODULE_HELPERS = '''
import anthropic

from agent import (ACCEPTED, DECLINED, INSTRUCTIONS, MAX_REJECTED, MAX_STEPS, MODEL, NO_ANSWER,
                   OUT_OF_STEPS, RAN_OUT, REJECTED, REJECTED_TOO_OFTEN, REMINDED, REMINDER,
                   TOOLS, answer_problem, clean_answer, finish, run_tool)


def ask(client, system, messages):
    return client.messages.create(model=MODEL, max_tokens=16000, system=system, tools=TOOLS,
                                  messages=messages)


def checked(call, read_so_far):
    answer = clean_answer(call.input)
    return answer, answer_problem(answer, read_so_far)


def run_agent(claim, client=None, max_steps=MAX_STEPS, lookup=run_tool):
    client = client or anthropic.Anthropic()
    system = INSTRUCTIONS.read_text()
    messages = [{"role": "user", "content": f"Claim: {claim}"}]
    trace, read_so_far = [], []
    steps = 0
    rejected = 0
    warned = False
    quiet = False

    while True:
        reply = ask(client, system, messages)
        messages.append({"role": "assistant", "content": reply.content})
        if reply.stop_reason == "refusal":
            return finish(claim, None, [], DECLINED, trace, steps)
        calls = [block for block in reply.content if block.type == "tool_use"]
        if not calls:
            if quiet:
                return finish(claim, None, [], NO_ANSWER, trace, steps)
            quiet = True
            trace.append({"tool": "(reminder)", "input": {}, "result": REMINDED})
            messages.append({"role": "user", "content": REMINDER})
            continue
        quiet = False
        warned_last_turn = warned
        results = []
        for call in calls:
            if call.name == "answer":
                answer, problem = checked(call, read_so_far)
                if problem is None:
                    trace.append({"tool": "answer", "input": call.input, "result": ACCEPTED})
                    return finish(claim, answer["verdict"], answer["evidence"],
                                  answer["explanation"], trace, steps)
                rejected += 1
                result = REJECTED + problem
                trace.append({"tool": "answer", "input": call.input, "result": result})
                if rejected >= MAX_REJECTED:
                    return finish(claim, None, [], REJECTED_TOO_OFTEN.format(n=rejected),
                                  trace, steps)
            elif steps >= max_steps:
                if warned_last_turn:
                    return finish(claim, None, [], RAN_OUT, trace, steps)
                warned = True
                result = OUT_OF_STEPS.format(n=max_steps)
                trace.append({"tool": call.name, "input": call.input, "result": result})
            else:
                result = lookup(call.name, call.input)
                steps += 1
                trace.append({"tool": call.name, "input": call.input, "result": result})
                if call.name != "search":
                    read_so_far.append(result)
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": result})
        messages.append({"role": "user", "content": results})
'''

# A student's loop for the six rules, from the simulations of Nov 13: the limit is looked at for
# each lookup, with a memory of the warning that is never reset after a stall. The six rules did
# not pass it; the five do, because its warning still lets the model answer.
STUDENT_GAP = """
import anthropic

from agent import (ACCEPTED, DECLINED, INSTRUCTIONS, MAX_REJECTED, MAX_STEPS, MODEL, NO_ANSWER,
                   OUT_OF_STEPS, RAN_OUT, REJECTED, REJECTED_TOO_OFTEN, REMINDED, REMINDER,
                   TOOLS, answer_problem, clean_answer, finish, run_tool)


def run_agent(claim, client=None, max_steps=MAX_STEPS, lookup=run_tool):
    client = client or anthropic.Anthropic()
    system = INSTRUCTIONS.read_text()
    messages = [{"role": "user", "content": f"Claim: {claim}"}]
    trace, read_so_far = [], []
    steps = 0
    rejected = 0

    warned = False
    reminded = False
    while True:
        reply = client.messages.create(model=MODEL, max_tokens=16000, system=system,
                                       tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": reply.content})
        if reply.stop_reason == "refusal":
            return finish(claim, None, [], DECLINED, trace, steps)
        tool_calls = [block for block in reply.content if block.type == "tool_use"]
        if len(tool_calls) == 0:
            if reminded:
                return finish(claim, None, [], NO_ANSWER, trace, steps)
            reminded = True
            trace.append({"tool": "(reminder)", "input": {}, "result": REMINDED})
            messages.append({"role": "user", "content": REMINDER})
            continue
        results = []
        for call in tool_calls:
            if call.name == "answer":
                answer = clean_answer(call.input)
                problem = answer_problem(answer, read_so_far)
                if problem is None:
                    trace.append({"tool": call.name, "input": call.input, "result": ACCEPTED})
                    return finish(claim, answer["verdict"], answer["evidence"],
                                  answer["explanation"], trace, steps)
                rejected += 1
                trace.append({"tool": call.name, "input": call.input, "result": REJECTED + problem})
                if rejected >= MAX_REJECTED:
                    return finish(claim, None, [], REJECTED_TOO_OFTEN.format(n=rejected),
                                  trace, steps)
                results.append({"type": "tool_result", "tool_use_id": call.id,
                                "content": REJECTED + problem})
                continue
            if steps >= max_steps:
                if warned:
                    return finish(claim, None, [], RAN_OUT, trace, steps)
                warned = True
                out = OUT_OF_STEPS.format(n=max_steps)
                trace.append({"tool": call.name, "input": call.input, "result": out})
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": out})
                continue
            result = lookup(call.name, call.input)
            steps += 1
            trace.append({"tool": call.name, "input": call.input, "result": result})
            if call.name == "read" or call.name == "wikidata":
                read_so_far.append(result)
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": result})
        messages.append({"role": "user", "content": results})
"""

# The plainest loop, written two other ways: with the parts' reply.calls instead of reply.answer
# and reply.lookups, and straight against the Claude API, as a student who started before the
# parts might write it (with a reminder of its own, since it has no parts to remind the model).
BARE_CALLS = kit(("""        if reply.answer:
            return talk.accept(reply.answer, steps)
""", """        for call in reply.calls:
            if call.is_answer:
                return talk.accept(call, steps)
"""), ("""        for call in reply.lookups:
            talk.give(call, talk.run(call))
            steps += 1
""", """        for call in reply.calls:
            if call.is_lookup:
                talk.give(call, talk.run(call))
                steps += 1
"""))
BARE_RAW = REFERENCE[:REFERENCE.index("    rejected = 0")] + '''    reminded = False

    while True:
        response = client.messages.create(model=MODEL, max_tokens=16000, system=system,
                                          tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": response.content})
        calls = [block for block in response.content if block.type == "tool_use"]
        answers = [call for call in calls if call.name == "answer"]
        if answers:
            answer = clean_answer(answers[0].input)
            trace.append({"tool": "answer", "input": answers[0].input, "result": ACCEPTED})
            return finish(claim, answer["verdict"], answer["evidence"], answer["explanation"],
                          trace, steps)
        if steps >= max_steps:
            return finish(claim, None, [], RAN_OUT, trace, steps)
        if not calls:
            if reminded:
                return finish(claim, None, [], NO_ANSWER, trace, steps)
            reminded = True
            trace.append({"tool": "(reminder)", "input": {}, "result": REMINDED})
            messages.append({"role": "user", "content": REMINDER})
            continue
        reminded = False
        results = []
        for call in calls:
            result = lookup(call.name, call.input)
            steps += 1
            trace.append({"tool": call.name, "input": call.input, "result": result})
            results.append({"type": "tool_result", "tool_use_id": call.id, "content": result})
        messages.append({"role": "user", "content": results})
'''

PASSING = {
    "nested-helpers": HELPERS,
    "by-id": BY_ID,
    "module-helpers": MODULE_HELPERS,
    "calls-in-reverse": broken(("for call in calls:", "for call in reversed(calls):")),
    "a-students-loop-from-nov-13": STUDENT_GAP,
    "the-limit-once-per-reply-and-no-warning": broken(("        results = []\n        warned_before = warned\n",
                                                       "        if steps >= max_steps and any(c.name != 'answer' for c in calls):\n"
                                                       "            return finish(claim, None, [], RAN_OUT, trace, steps)\n"
                                                       "        results = []\n        warned_before = warned\n")),
    "a-warning-then-a-stop-in-the-same-reply": broken(("                if warned_before:\n", "                if warned:\n")),
    # Nov 16: it stops in the middle of the reply that asks for more lookups than are left, having
    # made as many as were left. Rule 4 leaves that reply to the loop.
    "a-stop-in-the-middle-of-a-reply": broken(("if warned_before:", "if True:")),
    # Nov 16: once the count is past the limit. It makes the third search at the limit, warns the
    # model at the fourth reply and stops at the fifth: one reply's lookups and one warning.
    "the-limit-checked-one-late": broken(("elif steps >= max_steps:", "elif steps > max_steps:")),
    "the-full-loop-checking-the-limit-once-per-reply": full(
        ("        warned_before = warned\n", "        warned_before = warned\n        over = steps >= max_steps\n"),
        ("            elif steps >= max_steps:", "            elif over:")),
    "the-full-loop-stopping-on-the-last-failed-answer": full(("""                talk.give(call, problem)
                rejected += 1
                if rejected >= MAX_REJECTED:
                    return talk.stop(REJECTED_TOO_OFTEN.format(n=rejected), steps)
""", """                rejected += 1
                if rejected >= MAX_REJECTED:
                    return talk.stop(REJECTED_TOO_OFTEN.format(n=rejected), steps)
                talk.give(call, problem)
""")),
    "the-full-loop-reminding-again-and-again": full(("""            if reminded:
                return talk.stop(NO_ANSWER, steps)
""", "")),
    "the-plainest-loop-with-reply-calls": BARE_CALLS,
    "the-plainest-loop-without-the-parts": BARE_RAW,
    "a-loop-without-the-parts-that-stops-on-a-reply-asking-for-nothing": edited(BARE_RAW, (
        """            if reminded:
                return finish(claim, None, [], NO_ANSWER, trace, steps)
            reminded = True
            trace.append({"tool": "(reminder)", "input": {}, "result": REMINDED})
            messages.append({"role": "user", "content": REMINDER})
            continue
""", "            return finish(claim, None, [], NO_ANSWER, trace, steps)\n")),
}


@pytest.mark.parametrize("name", PASSING)
def test_loops_written_differently_pass_every_rule(tmp_path, name):
    assert check_loop.check(a_loop(tmp_path, PASSING[name])) == [None] * 5


@pytest.mark.parametrize("name, value", [("MAX_STEPS", 3), ("MAX_STEPS", 30),
                                         ("MAX_REJECTED", 1), ("MAX_REJECTED", 6),
                                         ("answer_problem", lambda answer, read_so_far: None)])
def test_a_change_to_agent_py_in_part_3_does_not_fail_a_correct_loop(tmp_path, monkeypatch, name, value):
    # Part 3 lets the student change agent.py, the limit of lookups above all.
    monkeypatch.setattr(agent, name, value)
    for source in (KIT_REFERENCE, FULL_LOOP, REFERENCE, BY_ID):
        assert check_loop.check(a_loop(tmp_path, source)) == [None] * 5


def test_where_the_plainest_loop_and_the_full_loop_differ_the_check_takes_either(tmp_path):
    """On an answer quoting what the agent never read, on a model that keeps asking at the limit and
    on a reply that crosses the limit, the two loops do different things. Both pass."""
    def ends(source):
        path = str(a_loop(tmp_path, source).resolve())
        module = check_loop.load(path)
        with check_loop.offline():
            runs = {key: check_loop.Run(key, module.run_agent, path) for key in check_loop.SCENARIOS}
        return {key: (len(run.requests), run.result["verdict"], run.result["steps"])
                for key, run in runs.items()}
    plain, whole = ends(KIT_REFERENCE), ends(FULL_LOOP)
    assert plain["unread"] == (2, "supported", 1) and whole["unread"] == (3, "doesn't say", 1)
    assert plain["limit_again"] == (3, None, 2) and whole["limit_again"] == (4, None, 2)
    assert plain["limit_cross"] == (3, "doesn't say", 3) and whole["limit_cross"] == (3, "doesn't say", 2)
    assert plain["both"] == (2, "supported", 1) and whole["both"] == (2, "supported", 2)
    same = [key for key in check_loop.SCENARIOS if key not in ("unread", "limit_again", "limit_cross", "both")]
    assert {key: plain[key] for key in same} == {key: whole[key] for key in same}
    assert check_loop.check(a_loop(tmp_path, KIT_REFERENCE)) == check_loop.check(a_loop(tmp_path, FULL_LOOP))


class Endless:
    """A stand-in model that never gives up: its replies follow the pattern, over and over. It keeps
    each request's conversation as it was sent."""

    def __init__(self, pattern):
        self.messages, self.pattern, self.sent = self, pattern, []

    def create(self, **request):
        self.sent.append(repr(request["messages"]))
        k = len(self.sent)
        blocks = []
        for kind in self.pattern[(k - 1) % len(self.pattern)]:
            if kind == "nothing":
                blocks.append(SimpleNamespace(type="text", text="I think it's true."))
            elif kind == "lookup":
                blocks.append(SimpleNamespace(type="tool_use", name="search", input={"query": f"q{k}"},
                                              id=f"s{k}"))
            else:                       # an answer that quotes what the agent never read
                blocks.append(SimpleNamespace(type="tool_use", name="answer", id=f"a{k}", input={
                    "verdict": "supported", "evidence": ["Zemeckis was born in Ohio."], "explanation": "x"}))
        stop = "tool_use" if any(b.type == "tool_use" for b in blocks) else "end_turn"
        return SimpleNamespace(content=blocks, stop_reason=stop,
                               usage=SimpleNamespace(input_tokens=1, output_tokens=1))


ENDLESS = {"a lookup every time": [("lookup",)],
           "nothing, then a lookup": [("nothing",), ("lookup",)],
           "a made-up answer every time": [("answer",)],
           "nothing, then a made-up answer": [("nothing",), ("answer",)],
           "a lookup and a made-up answer": [("lookup", "answer")]}


@pytest.mark.parametrize("pattern", ENDLESS)
@pytest.mark.parametrize("source", [KIT_REFERENCE, FULL_LOOP], ids=["the-reference-loop", "the-full-loop"])
def test_the_plainest_loop_and_the_full_loop_never_reach_the_parts_hard_stop(tmp_path, monkeypatch, source,
                                                                             pattern):
    """Nov 14: the parts stop any loop after 3 * MAX_STEPS + 10 calls to the model for one claim. Each
    ask of these two loops either ends the loop or is followed by a lookup, a sent-back answer or a
    warning, all of them limited, so on a model that never gives up they stop by themselves, well
    before that, and send the same requests as with the hard stop out of reach."""
    module = check_loop.load(str(a_loop(tmp_path, source).resolve()))
    limit = agent.MAX_STEPS

    def run():
        model = Endless(ENDLESS[pattern])
        result = module.run_agent(check_loop.CLAIM, client=model, max_steps=limit,
                                  lookup=lambda name, args: "Some text.")
        return model.sent, result

    sent, result = run()
    assert len(sent) <= 2 * limit + 8 < 3 * limit + 10
    assert result["explanation"] != agent.TOO_MANY_ASKS.format(n=len(sent))
    assert "(stopped)" not in [entry["tool"] for entry in result["trace"]]
    monkeypatch.setattr(agent, "MAX_STEPS", 10 ** 6)         # the hard stop out of reach
    assert run() == (sent, result)


def renamed(source, *names):
    for name in names:
        source = re.sub(rf"\b{name}\b", f"my_{name}", source)
    return source


def test_a_complete_loop_with_other_names_for_the_set_up_variables_passes(tmp_path):
    # The check looks inside run_agent() only for a loop that does not stop yet.
    source = renamed(REFERENCE, "steps", "trace", "read_so_far")
    assert "my_steps += 1" in source and "max_steps" in source
    assert check_loop.check(a_loop(tmp_path, source)) == [None] * 5


def test_an_error_about_the_client_names_the_scripted_model(tmp_path):
    source = broken(("response = client.messages.create(", "response = client.messages.stream("))
    assert "AttributeError: 'ScriptedModel' object has no attribute 'stream'" in \
        check_loop.check(a_loop(tmp_path, source))[0]


# Rules 1 and 2 and nothing more, with the parts: every call a reply makes is made as a lookup, and
# the loop never stops.
FIRST_TWO = KIT_REFERENCE[:KIT_REFERENCE.index("    while True:")] + '''    while True:
        reply = talk.ask()
        for call in reply.calls:
            talk.give(call, talk.run(call))
            steps += 1
        talk.send_results()
'''


def test_rules_1_and_2_can_pass_before_the_loop_can_stop(tmp_path):
    assert shown(a_loop(tmp_path, FIRST_TWO)) == [
        "ok         1. Ask the model",
        "ok         2. Make its lookups",
        "NOT YET    3. Stop with the answer: the model's second reply gave an answer that quotes the "
        "page it had read, and your loop ran the answer as a lookup.",
        "NOT YET    4. Stop at the limit: the model's third reply gave an answer of doesn't say, when "
        "your loop had made 2 lookups, the limit, and your loop asked the model again instead of "
        "stopping.",
        "ok         5. Count the lookups",
    ]


# A half-written loop does not stop, so rule 5 looks inside run_agent() for it.
HALF_BROKEN = {
    "steps not counted": [("            steps += 1\n", "")],
    "steps renamed": [],
}


@pytest.mark.parametrize("name, problem", [
    ("steps not counted", "after the model's first reply, your loop had made one lookup, and its count of "
                          "lookups was 0 when it asked the model again"),
    ("steps renamed", "the check could not find `steps` in run_agent(): keep the names of the set-up lines "
                      "at the top of the function")])
def test_a_half_written_loop_is_checked_from_inside(tmp_path, name, problem):
    source = edited(FIRST_TWO, *HALF_BROKEN[name])
    if name.endswith("renamed"):
        source = renamed(source, "steps")
    problems = check_loop.check(a_loop(tmp_path, source))
    assert problems[:2] == [None] * 2
    assert problems[4] == problem
    assert problems.count(problem) == 1      # said once, on the rule that needed it


# ---------- one broken loop per rule, and what each line says ----------

BROKEN = {
    "no assistant turn": (1, [('        messages.append({"role": "assistant", '
                               '"content": response.content})\n', "")],
                          ["the model's first reply asked for a search, and the next request "
                           "your loop sent did not have that reply in the conversation"]),
    "reply added twice": (1, [('        messages.append({"role": "assistant", "content": response.content})\n',
                               '        messages.append({"role": "assistant", "content": response.content})\n' * 2)],
                          ["the model's first reply asked for a search, and the next request "
                           "your loop sent had that reply in the conversation two times"]),
    "text block dropped": (1, [('"content": response.content}',
                                '"content": [b for b in response.content if b.type == "tool_use"]}')],
                           ["the model's first reply asked for a search, and the next request "
                            "your loop sent had that reply in the conversation with parts of it "
                            "missing or changed"]),
    "no system text": (1, [("system=system, ", "")], ["the first request your loop sent the "
                                                      "model did not have the text of "
                                                      "instructions.md as its system text"]),
    "wrong model": (1, [("model=MODEL,", "model='claude-opus-5-5',")],
                    ["the first request your loop sent the model named the model "
                     "'claude-opus-5-5', not 'claude-haiku-5-5'"]),
    "only the newest turn": (1, [("messages=messages,", "messages=messages[-2:],")],
                             ["the model's first reply asked for a search, and the next request "
                              "your loop sent did not hold the whole conversation so far"]),
    "an empty turn after nothing": (1, [('messages.append({"role": "user", "content": REMINDER})',
                                         'messages.append({"role": "user", "content": []})')],
                                    ["the model's first reply had text and no tool call, and the next "
                                     "request your loop sent had a turn with nothing in it after that "
                                     "reply, which the Claude API refuses"]),
    "only the first call": (2, [("for call in calls:", "for call in calls[:1]:")],
                            ["the model's third reply asked for a wikidata lookup and a read, "
                             "and your loop made the wikidata lookup only, then asked the model "
                             "again without making the read"]),
    "results not sent": (2, [('        messages.append({"role": "user", "content": results})\n', "")],
                         ["the model's first reply asked for a search and a read, and the next "
                          "request your loop sent ended with that reply: the results for it had "
                          "not been sent"]),
    "wrong id": (2, [('"tool_use_id": call.id', '"tool_use_id": calls[0].id')],
                 ["the model's first reply asked for a search and a read, and the next request "
                  "your loop sent held two results for the search"]),
    "a result as a list": (2, [('"tool_use_id": call.id, "content": result}',
                                '"tool_use_id": call.id, "content": [{"type": "text", "text": result}]}')],
                           ["the model's first reply asked for a search and a read, and the "
                            "result given for the search was a list rather than text"]),
    "a turn per result": (2, [('            results.append({"type": "tool_result", '
                               '"tool_use_id": call.id, "content": result})\n',
                               '            messages.append({"role": "user", "content": [{"type": '
                               '"tool_result", "tool_use_id": call.id, "content": result}]})\n'),
                              ('        messages.append({"role": "user", "content": results})\n', "")],
                          ["the model's first reply asked for a search and a read, and your "
                           "loop sent the results for that reply in two separate turns, where "
                           "the model is sent them all together, once every call in the reply "
                           "has its result"]),
    "a refused lookup gets no result": (2, [("                warned = True\n",
                                             "                warned = True\n                continue\n")],
                                        ["the model's third reply asked for a third search, and "
                                         "the next request your loop sent held no result for "
                                         "the search"]),
    "an answer sent back gets no result": (2, [
        ('            results.append({"type": "tool_result", "tool_use_id": call.id, "content": result})\n',
         '            if call.name != "answer":\n'
         '                results.append({"type": "tool_result", "tool_use_id": call.id, '
         '"content": result})\n')],
        ["the model's second reply gave an answer with a quote that is in nothing it had read, "
         "and the next request your loop sent held no result for the answer"]),
    "answer not cleaned": (3, [("answer = clean_answer(call.input)", "answer = call.input")],
                           ["the model's second reply gave an answer with its evidence as one "
                            "string and no explanation, and your loop stopped with an error at "
                            "line 53 of my_loop.py: KeyError: 'explanation'"]),
    "evidence left out": (3, [('return finish(claim, answer["verdict"], answer["evidence"],',
                               'return finish(claim, answer["verdict"], [],')],
                          ["the model's second reply gave an answer that quotes the page it had "
                           "read, and your loop stopped with the evidence [], where this case "
                           "ends with the evidence ['directed by Robert Zemeckis']"]),
    "lookups only in the trace": (3, [
        ('                    trace.append({"tool": "answer", "input": call.input, "result": ACCEPTED})\n', ""),
        ('                    trace.append({"tool": "answer", "input": call.input, "result": result})\n', ""),
        ('            trace.append({"tool": call.name, "input": call.input, "result": result})\n', ""),
        ("                result = lookup(call.name, call.input)\n",
         "                result = lookup(call.name, call.input)\n"
         '                trace.append({"tool": call.name, "input": call.input, "result": result})\n')],
        ["the model's second reply gave an answer that quotes the page it had read, and the "
         "trace your loop stopped with does not record that answer as accepted"]),
    # A loop that stops with an error where the plainest loop and the full loop differ, or on a reply
    # that asks for nothing, does not pass: a full loop damaged by a merge fails where the student sees it.
    "an error on a reply that asks for nothing": (3, [
        ('        calls = [block for block in response.content if block.type == "tool_use"]\n',
         '        calls = [block for block in response.content if block.type == "tool_use"]\n'
         '        first = calls[0]\n')],
        ["the model's first reply had text and no tool call, and your loop stopped with an error at "
         "line 36 of my_loop.py: IndexError: list index out of range"]),
    "an error on an answer that quotes what was never read": (3, [
        ("                result = REJECTED + problem\n", "                raise ValueError(problem)\n")],
        ["the model's second reply gave an answer with a quote that is in nothing it had read, and "
         "your loop stopped with an error at line 54 of my_loop.py: ValueError: "]),
    "an error when the model keeps asking at the limit": (4, [
        ("result = OUT_OF_STEPS.format(n=max_steps)", "result = OUT_OF_STEPS.format(steps=max_steps)")],
        ["the model's third reply asked for a third search, and your loop stopped with an error at "
         "line 64 of my_loop.py: KeyError: 'n'"]),
    "the limit is MAX_STEPS": (4, [("elif steps >= max_steps:", "elif steps >= MAX_STEPS:")],
                               ["the model's fourth reply asked for a fourth search, and your loop "
                                "made it, though it had already made the third search after the "
                                "limit of 2 lookups was reached: it had made 3 lookups before "
                                "this one"]),
    "the limit checked one early": (4, [("elif steps >= max_steps:",
                                         "elif steps >= max_steps - 1:")],
                                    ["the model's second reply asked for a second search, and "
                                     "your loop sent back 'You have used all 2 steps. Call answer() "
                                     "now.' instead of making it, though it had made only 1 "
                                     "lookup and the limit is 2"]),
    "never stops at the limit": (4, [("if warned_before:", "if False:")],
                                 ["the model's fourth reply asked for a fourth search, and your loop "
                                  "sent back a result for it without making it and asked the model "
                                  "again, as it had already done for the third search: it had made 2 "
                                  "lookups, and the limit is 2"]),
    "lookup not in the trace": (5, [('            trace.append({"tool": call.name, "input": '
                                     'call.input, "result": result})\n', "")],
                                ["the model's first reply asked for a search, and the trace "
                                 "your loop stopped with had no entry for the search"]),
    "a warned lookup counted": (5, [("                warned = True\n",
                                     "                warned = True\n                steps += 1\n")],
                                ["the model's fourth reply asked for a fourth search, and when "
                                 "your loop stopped its count of lookups was 3, where it had made "
                                 "two lookups"]),
}


@pytest.mark.parametrize("name", BROKEN)
def test_a_broken_loop_fails_its_rule_and_says_what_happened(tmp_path, name):
    rule, edits, phrases = BROKEN[name]
    printed = shown(a_loop(tmp_path, broken(*edits)))
    first = next(i for i, line in enumerate(printed, 1) if line.startswith("NOT YET"))
    assert first == rule, printed
    line = printed[rule - 1]
    assert line.startswith(f"NOT YET    {rule}. {check_loop.RULES[rule - 1]}: ")
    for phrase in phrases:
        assert phrase in line, line
    assert line.endswith(".") and "\n" not in line


def test_every_broken_rule_is_covered():
    assert {rule for rule, _, _ in BROKEN.values()} == set(range(1, 6))
    assert {rule for rule, _, _ in KIT_WRONG.values()} == {2, 4, 5}


# ---------- loops written with the parts in loop_parts.py ----------

LIMIT = """        if steps >= max_steps:
            return talk.stop(RAN_OUT, steps)
"""
LOOKUPS = """        for call in reply.lookups:
            talk.give(call, talk.run(call))
            steps += 1
"""
ANSWER = """        if reply.answer:
            return talk.accept(reply.answer, steps)
"""
KIT_WRONG = {
    "handles only the first lookup": (2, [("for call in reply.lookups:", "for call in reply.lookups[:1]:")],
        "the model's third reply asked for a wikidata lookup and a read, and your loop made the "
        "wikidata lookup only, then asked the model again without making the read."),
    "results sent inside the for loop": (2, [("""            steps += 1
        talk.send_results()
""", """            steps += 1
            talk.send_results()
""")],
        "the model's first reply asked for a search and a read, and your loop sent the results "
        "for that reply in two separate turns, where the model is sent them all together, once "
        "every call in the reply has its result."),
    "no results sent": (2, [("        talk.send_results()\n", "")],
        "the model's first reply asked for a search and a read, and the next request your loop "
        "sent ended with that reply: the results for it had not been sent."),
    "the limit looked at before the answer": (4, [(ANSWER + LIMIT, LIMIT + ANSWER)],
        "the model's third reply gave an answer of doesn't say, when your loop had made 2 lookups, "
        "the limit, and your loop stopped with no verdict, where this case ends with the verdict "
        "\"doesn't say\"."),
    "no limit": (4, [(LIMIT, "")],
        "the model's fourth reply asked for a fourth search, and your loop made it, though it had "
        "already made the third search after the limit of 2 lookups was reached: it had made 3 "
        "lookups before this one."),
    "the limit looked at after the lookups": (4, [(LIMIT + LOOKUPS, LOOKUPS + LIMIT)],
        "the model's second reply asked for a second search, and your loop made it and then "
        "stopped without asking the model again, though the model had not asked for more than "
        "the limit of 2 lookups."),
    "the wrong sentence at the limit": (4, [("talk.stop(RAN_OUT, steps)", "talk.stop(NO_ANSWER, steps)"),
                                            ("RAN_OUT, run_tool", "RAN_OUT, NO_ANSWER, run_tool")],
        "the model's third reply asked for a third search with the limit of 2 lookups reached, and "
        "your loop stopped with the explanation 'The agent stopped without answering.', where this "
        "case ends with the explanation 'The agent ran out of steps.'."),
    "counts each reply, not each lookup": (5, [("""            talk.give(call, talk.run(call))
            steps += 1
""", """            talk.give(call, talk.run(call))
        steps += 1
""")],
        "the model asked for four lookups before its answer, and when your loop stopped its count "
        "of lookups was 3."),
}


@pytest.mark.parametrize("name", KIT_WRONG)
def test_a_wrong_loop_with_the_parts_gets_a_sentence_about_what_it_did(tmp_path, name):
    rule, edits, sentence = KIT_WRONG[name]
    printed = shown(a_loop(tmp_path, kit(*edits)))
    first = next(i for i, line in enumerate(printed, 1) if line.startswith("NOT YET"))
    assert first == rule, printed
    assert printed[rule - 1] == f"NOT YET    {rule}. {check_loop.RULES[rule - 1]}: {sentence}"


# ---------- where the loop looks at the limit ----------

# The instructor, Nov 16: "the details about whether the model should short-circuit before or after
# an iteration, etc. seem arbitrary. I want to be flexible about that choice. on the other hand, a
# model that has made the maximum number of calls should still be able to interpret them in the next
# turn." Later that day he freed one more case. Rule 4 asks that after the lookup that reaches the
# limit the model is asked once more, and that a reply that then asks for more lookups ends the run
# with no verdict, at once or a little later: the loop may make the lookups of one such reply, and
# warn the model once, but no more (the made-up check limit_again). What a loop does with a reply
# that asks for more lookups than are left (limit_cross) is its own choice. Each loop below is the
# plainest loop with the parts, with another loop body.

def kit_body(body, *names):
    """The reference loop with body in place of its loop, importing more names from agent.py."""
    head = KIT_REFERENCE[:KIT_REFERENCE.index("    while True:")]
    if names:
        head = edited(head, ("RAN_OUT, run_tool", f"{', '.join(names)}, RAN_OUT, run_tool"))
    return head + body


LIMIT_PER_LOOKUP = kit_body('''    while True:
        reply = talk.ask()
        if reply.answer:
            return talk.accept(reply.answer, steps)
        for call in reply.lookups:
            if steps >= max_steps:
                return talk.stop(RAN_OUT, steps)
            talk.give(call, talk.run(call))
            steps += 1
        talk.send_results()
''')
HARD_CAP = kit((LIMIT, """        if steps + len(reply.lookups) > max_steps:
            return talk.stop(RAN_OUT, steps)
"""))
HARD_CAP_TOLD = kit_body('''    told = False        # has the model been told its lookups were not made?
    while True:
        reply = talk.ask()
        if reply.answer:
            return talk.accept(reply.answer, steps)
        if steps + len(reply.lookups) > max_steps:
            if told:
                return talk.stop(RAN_OUT, steps)
            for call in reply.lookups:
                talk.give(call, OUT_OF_STEPS.format(n=max_steps))
            told = True
        else:
            for call in reply.lookups:
                talk.give(call, talk.run(call))
                steps += 1
        talk.send_results()
''', "OUT_OF_STEPS")
# The outline the instructor wrote on Nov 16, with the limit looked at before each lookup.
INSTRUCTOR_OUTLINE = kit_body('''    while True:
        reply = talk.ask()
        for call in reply.calls:
            if call.is_answer:
                return talk.accept(call, steps)
            elif call.is_lookup:
                if steps >= max_steps:
                    return talk.stop(RAN_OUT, steps)
                talk.give(call, talk.run(call))
                steps += 1
        talk.send_results()
''')
# The limit looked at once the count is past it: after the reply (before the lookups), or at the
# end of the turn (after the results are sent). Each makes one search past the limit.
PAST_AFTER_THE_REPLY = kit(("if steps >= max_steps:", "if steps > max_steps:"))
PAST_AT_THE_END = kit((LIMIT + LOOKUPS, LOOKUPS), ("        talk.send_results()\n",
                                                   "        talk.send_results()\n"
                                                   "        if steps > max_steps:\n"
                                                   "            return talk.stop(RAN_OUT, steps)\n"))
# Past the limit once, then one warning, in either order.
MADE_THEN_WARNED = kit_body('''    told = False        # has the model been told its lookups were not made?
    while True:
        reply = talk.ask()
        if reply.answer:
            return talk.accept(reply.answer, steps)
        if steps > max_steps:
            if told:
                return talk.stop(RAN_OUT, steps)
            for call in reply.lookups:
                talk.give(call, OUT_OF_STEPS.format(n=max_steps))
            told = True
        else:
            for call in reply.lookups:
                talk.give(call, talk.run(call))
                steps += 1
        talk.send_results()
''', "OUT_OF_STEPS")
WARNED_THEN_MADE = kit_body('''    told = False        # has the model been told its lookups were not made?
    while True:
        reply = talk.ask()
        if reply.answer:
            return talk.accept(reply.answer, steps)
        if steps > max_steps:
            return talk.stop(RAN_OUT, steps)
        if steps >= max_steps and not told:
            for call in reply.lookups:
                talk.give(call, OUT_OF_STEPS.format(n=max_steps))
            told = True
        else:
            for call in reply.lookups:
                talk.give(call, talk.run(call))
                steps += 1
        talk.send_results()
''', "OUT_OF_STEPS")

# What each way does in limit_again (limit 2, every reply asks for one search): the requests it
# sent the model, the lookups it made in all, and how it stopped.
AGAIN = {
    "none made, a stop at the third reply": (KIT_REFERENCE, 3, 2),
    "a warning, a stop at the fourth reply": (FULL_LOOP, 4, 2),
    "the third search made, a stop with no ask": (PAST_AT_THE_END, 3, 3),
    "the third search made, a stop at the fourth reply": (PAST_AFTER_THE_REPLY, 4, 3),
    "the third search made, a warning, a stop at the fifth reply": (MADE_THEN_WARNED, 5, 3),
    "a warning, the fourth search made, a stop at the fifth reply": (WARNED_THEN_MADE, 5, 3),
}

# What each way does with the second reply of limit_cross (limit 2, one lookup made, a search and
# a read asked for): the requests it sent the model, the lookups it made for that reply, and the
# verdict and explanation it stopped with.
CROSSING = {
    "(a) makes both and asks again": (KIT_REFERENCE, 3, 2, "doesn't say", check_loop.NOT_SAID_WHY),
    "(b) makes one, warns about the other and asks again": (FULL_LOOP, 3, 1, "doesn't say",
                                                            check_loop.NOT_SAID_WHY),
    "(c) makes as many as are left and stops": (LIMIT_PER_LOOKUP, 2, 1, None, agent.RAN_OUT),
    "(d) makes none and stops": (HARD_CAP, 2, 0, None, agent.RAN_OUT),
    "(e) makes none, warns about each and asks again": (HARD_CAP_TOLD, 3, 0, "doesn't say",
                                                        check_loop.NOT_SAID_WHY),
    "(f) makes both and stops": (PAST_AT_THE_END, 2, 2, None, agent.RAN_OUT),
}

LIMIT_PASSING = {
    **{name: source for name, (source, *_) in CROSSING.items()},
    **{name: source for name, (source, *_) in AGAIN.items()},
    "the instructor's outline": INSTRUCTOR_OUTLINE,
    "past the limit, looked at after the lookups, before the results are sent": kit(
        (LIMIT + LOOKUPS, LOOKUPS + LIMIT), ("if steps >= max_steps:", "if steps > max_steps:")),
    "the reference loop, and makes both and stops when a reply crosses the limit": kit(
        (LOOKUPS, LOOKUPS + "        if steps > max_steps:\n            return talk.stop(RAN_OUT, steps)\n")),
    "the limit looked at the end of each turn, then one last ask": kit((LIMIT + LOOKUPS, LOOKUPS), (
        "        talk.send_results()\n", """        talk.send_results()
        if steps >= max_steps:
            reply = talk.ask()
            if reply.answer:
                return talk.accept(reply.answer, steps)
            return talk.stop(RAN_OUT, steps)
""")),
    "before each lookup, the ones past the limit told so and the model asked again": kit_body('''    told = False
    while True:
        reply = talk.ask()
        if reply.answer:
            return talk.accept(reply.answer, steps)
        if steps >= max_steps and told:
            return talk.stop(RAN_OUT, steps)
        for call in reply.lookups:
            if steps >= max_steps:
                talk.give(call, OUT_OF_STEPS.format(n=max_steps))
                told = True
            else:
                talk.give(call, talk.run(call))
                steps += 1
        talk.send_results()
''', "OUT_OF_STEPS"),
}


def run_on(tmp_path, source, key):
    """The loop in source, run on one made-up check."""
    path = str(a_loop(tmp_path, source).resolve())
    module = check_loop.load(path)
    with check_loop.offline():
        return check_loop.Run(key, module.run_agent, path)


@pytest.mark.parametrize("name", CROSSING)
def test_each_way_with_a_reply_that_asks_for_more_than_are_left_does_what_it_says(tmp_path, name):
    source, asks, made, verdict, explanation = CROSSING[name]
    run = run_on(tmp_path, source, "limit_cross")
    assert run.ended == "returned"
    assert (len(run.requests), len(check_loop.made_after(run, 2))) == (asks, made)
    assert (run.result["verdict"], run.result["explanation"]) == (verdict, explanation)
    if asks == 3:       # each call of the second reply had a result, made or not
        for call in run.calls(2):
            assert check_loop.sent_back(run.requests[2], call.id) is not check_loop.MISSING


@pytest.mark.parametrize("name", AGAIN)
def test_each_way_past_the_limit_does_what_it_says(tmp_path, name):
    source, asks, made = AGAIN[name]
    run = run_on(tmp_path, source, "limit_again")
    assert run.ended == "returned"
    assert (len(run.requests), len(run.lookups)) == (asks, made)
    assert (run.result["verdict"], run.result["explanation"], run.result["steps"]) == (None, agent.RAN_OUT, made)


@pytest.mark.parametrize("name", LIMIT_PASSING)
def test_where_the_loop_looks_at_the_limit_is_its_own_choice(tmp_path, name):
    assert shown(a_loop(tmp_path, LIMIT_PASSING[name])) == FIVE


STOPS_AFTER_THE_LAST_LOOKUP = (
    "the model's second reply asked for a second search, and your loop made it and then stopped "
    "without asking the model again, though the model had not asked for more than the limit of 2 "
    "lookups.")
A_SECOND_SEARCH_PAST_THE_LIMIT = (
    "the model's fourth reply asked for a fourth search, and your loop made it, though it had already "
    "made the third search after the limit of 2 lookups was reached: it had made 3 lookups before this "
    "one.")
STILL_NOT_YET = {
    "repeats while the count is under the limit": (kit_body('''    while steps < max_steps:
        reply = talk.ask()
        if reply.answer:
            return talk.accept(reply.answer, steps)
        for call in reply.lookups:
            talk.give(call, talk.run(call))
            steps += 1
        talk.send_results()
    return talk.stop(RAN_OUT, steps)
'''), STOPS_AFTER_THE_LAST_LOOKUP),
    "looks at the limit at the top of each turn, before asking": (kit_body('''    while True:
        if steps >= max_steps:
            return talk.stop(RAN_OUT, steps)
        reply = talk.ask()
        if reply.answer:
            return talk.accept(reply.answer, steps)
        for call in reply.lookups:
            talk.give(call, talk.run(call))
            steps += 1
        talk.send_results()
'''), STOPS_AFTER_THE_LAST_LOOKUP),
    "two past the limit, looked at after the reply": (
        kit(("if steps >= max_steps:", "if steps > max_steps + 1:")), A_SECOND_SEARCH_PAST_THE_LIMIT),
    "two past the limit, looked at the end of the turn": (
        kit((LIMIT + LOOKUPS, LOOKUPS), ("        talk.send_results()\n",
                                         "        talk.send_results()\n"
                                         "        if steps > max_steps + 1:\n"
                                         "            return talk.stop(RAN_OUT, steps)\n")),
        A_SECOND_SEARCH_PAST_THE_LIMIT),
    "no limit at all": (kit((LIMIT, "")), A_SECOND_SEARCH_PAST_THE_LIMIT),
    # Past the limit once, then the wrong sentence at the stop: the line says what came before it.
    "past the limit once, then the wrong sentence": (
        edited(PAST_AFTER_THE_REPLY, ("talk.stop(RAN_OUT, steps)", "talk.stop(NO_ANSWER, steps)"),
               ("RAN_OUT, run_tool", "RAN_OUT, NO_ANSWER, run_tool")),
        "the model's fourth reply asked for a fourth search after your loop had made the third search "
        "with the limit of 2 lookups reached, and your loop stopped with the explanation 'The agent "
        "stopped without answering.', where this case ends with the explanation 'The agent ran out of "
        "steps.'."),
    "past the limit once and a warning, then the wrong sentence": (
        edited(MADE_THEN_WARNED, ("talk.stop(RAN_OUT, steps)", "talk.stop(NO_ANSWER, steps)"),
               ("OUT_OF_STEPS, RAN_OUT, run_tool", "OUT_OF_STEPS, RAN_OUT, NO_ANSWER, run_tool")),
        "the model's fifth reply asked for a fifth search after your loop had made the third search "
        "with the limit of 2 lookups reached, and sent back a result for the fourth search without "
        "making it, and your loop stopped with the explanation 'The agent stopped without answering.', "
        "where this case ends with the explanation 'The agent ran out of steps.'."),
    "gives up one lookup early": (
        kit(("if steps >= max_steps:", "if steps >= max_steps - 1:")),
        "the model's second reply asked for a second search, and your loop stopped instead of making it, "
        "though it had made only 1 lookup and the limit is 2."),
    "warns the model twice": (kit_body('''    told = 0            # how many replies the model has been told its lookups were not made
    while True:
        reply = talk.ask()
        if reply.answer:
            return talk.accept(reply.answer, steps)
        if steps >= max_steps:
            if told == 2:
                return talk.stop(RAN_OUT, steps)
            for call in reply.lookups:
                talk.give(call, OUT_OF_STEPS.format(n=max_steps))
            told += 1
        else:
            for call in reply.lookups:
                talk.give(call, talk.run(call))
                steps += 1
        talk.send_results()
''', "OUT_OF_STEPS"), "the model's fourth reply asked for a fourth search, and your loop sent back a result for it "
                     "without making it and asked the model again, as it had already done for the third search: "
                     "it had made 2 lookups, and the limit is 2."),
    # A stop in the middle of a reply that asks for more than are left, with the wrong sentence.
    "stops in the middle of a reply without saying it ran out": (kit((LOOKUPS, """        for call in reply.lookups:
            if steps >= max_steps:
                return talk.stop(NO_ANSWER, steps)
            talk.give(call, talk.run(call))
            steps += 1
"""), ("RAN_OUT, run_tool", "NO_ANSWER, RAN_OUT, run_tool")),
        "the model's second reply asked for a search and a read in one reply, when your loop had made "
        "1 lookup and the limit is 2, and your loop stopped with the explanation 'The agent stopped "
        "without answering.', where a stop at the limit has the explanation 'The agent ran out of "
        "steps.'."),
    "stops in the middle of a reply with something that is not a result": (kit((LOOKUPS, """        for call in reply.lookups:
            if steps >= max_steps:
                return RAN_OUT
            talk.give(call, talk.run(call))
            steps += 1
""")), "the model's second reply asked for a search and a read in one reply, and your loop ended with "
           "'The agent ran out of steps.', rather than with an answer or with no verdict."),
    # Told the lookups were not made, then stopped at the next reply, whatever it was.
    "asks again and does not stop with the answer": (kit_body('''    told = False
    while True:
        reply = talk.ask()
        if told:
            return talk.stop(RAN_OUT, steps)
        if reply.answer:
            return talk.accept(reply.answer, steps)
        if steps + len(reply.lookups) > max_steps:
            for call in reply.lookups:
                talk.give(call, OUT_OF_STEPS.format(n=max_steps))
            told = True
        else:
            for call in reply.lookups:
                talk.give(call, talk.run(call))
                steps += 1
        talk.send_results()
''', "OUT_OF_STEPS"), "the model's third reply gave an answer of doesn't say, and your loop stopped with no "
                     "verdict, where this case ends with the verdict \"doesn't say\"."),
}


@pytest.mark.parametrize("name", STILL_NOT_YET)
def test_what_rule_4_still_requires(tmp_path, name):
    source, sentence = STILL_NOT_YET[name]
    assert shown(a_loop(tmp_path, source)) == FIVE[:3] + [f"NOT YET    4. Stop at the limit: {sentence}",
                                                          FIVE[4]]


def test_an_error_in_the_middle_of_a_reply_that_asks_for_more_than_are_left_is_not_yet(tmp_path):
    source = kit((LOOKUPS, """        for call in reply.lookups:
            if steps >= max_steps:
                return talk.stop(RAN_OUT)
            talk.give(call, talk.run(call))
            steps += 1
"""))
    line = 1 + source[:source.index("return talk.stop(RAN_OUT)\n")].count("\n")
    printed = shown(a_loop(tmp_path, source))
    assert printed[3] == (
        "NOT YET    4. Stop at the limit: the model's second reply asked for a search and a read in one "
        f"reply, and your loop stopped with an error at line {line} of my_loop.py: TypeError: "
        "Conversation.stop() missing 1 required positional argument: 'steps'.")


def test_a_loop_that_hangs_in_the_middle_of_a_reply_that_asks_for_more_than_are_left_is_not_yet(
        tmp_path, monkeypatch):
    monkeypatch.setattr(check_loop, "TIME_LIMIT", 0.3)
    monkeypatch.setattr(check_loop, "AFTER_A_HANG", 0.1)
    source = kit((LOOKUPS, """        for call in reply.lookups:
            while steps >= max_steps:
                pass
            talk.give(call, talk.run(call))
            steps += 1
"""))
    printed = shown(a_loop(tmp_path, source))
    assert printed[3].startswith(
        "NOT YET    4. Stop at the limit: the model's second reply asked for a search and a read in one "
        "reply, and your loop did not stop: it was still running line "), printed[3]


def test_the_instructors_loop_as_translated_counts_a_lookup_it_did_not_make(tmp_path):
    """His copy's translation counts each lookup before it looks at the limit, so the lookup that
    would pass the limit is counted and not made. Rule 4 passes it; rule 5 says what the count was."""
    source = kit_body('''    while True:
        reply = talk.ask()
        for call in reply.calls:
            if call.is_answer:
                return talk.accept(call, steps)
            elif call.is_lookup:
                steps += 1
                if steps > max_steps:
                    return talk.stop(RAN_OUT, steps)
                else:
                    talk.give(call, talk.run(call))
        talk.send_results()
''')
    assert shown(a_loop(tmp_path, source)) == FIVE[:4] + [
        "NOT YET    5. Count the lookups: the model's third reply asked for a third search, and when "
        "your loop stopped its count of lookups was 3, where it had made two lookups."]


def test_rule_4_states_what_is_required_and_leaves_the_rest_to_the_student():
    text = check_loop.rule_text(4)
    assert "the model is asked once more" in text
    assert "at once or after one more turn of lookups, and no later" in text
    assert text.endswith("A reply that asks for more lookups than are left is yours to decide: the agent "
                         "may make all of them, some or none, and may stop there.")
    for gone in ("all made", "past the limit", "below the limit", "makes no more", "none of them is made"):
        assert gone not in text, gone


# The made-up checks of the six rules that the five no longer have: a reminder, two stalls, a
# refusal, answers sent back, and two lookups at the limit. On them, and on the five's, the full
# loop with the parts as they are now does exactly what the raw loop does, as it did before: the one
# difference is the trace entry for a refusal, which the parts now record.
def old_reply(says, *blocks, stop=None):
    return check_loop.reply(says, *blocks, stop=stop)


OLD_SCENARIOS = {
    "remind": ([old_reply(check_loop.NO_TOOL, check_loop.text("I think the claim is true.")),
                old_reply(check_loop.SAYS_NOT, check_loop.NOT_SAID)], check_loop.PLENTY),
    "no_answer": ([old_reply(check_loop.NO_TOOL, check_loop.text("I think the claim is true.")),
                   old_reply(check_loop.NO_TOOL, check_loop.text("It is true.")),
                   old_reply(check_loop.NO_TOOL, check_loop.text("True."))], check_loop.PLENTY),
    "remind_twice": ([old_reply("asked for nothing", check_loop.text("I think the claim is true.")),
                      old_reply("asked for a search", check_loop.search("Forrest Gump")),
                      old_reply("asked for nothing again", check_loop.text("It is true.")),
                      old_reply(check_loop.SAYS_NOT, check_loop.NOT_SAID)], check_loop.PLENTY),
    "refusal": ([old_reply("refused", check_loop.text("I can't help with that."), stop="refusal"),
                 old_reply(check_loop.SAYS_NOT, check_loop.NOT_SAID)], check_loop.PLENTY),
    "reject_often": ([old_reply(check_loop.QUOTES_NOTHING, check_loop.MADE_UP)] * 12, check_loop.PLENTY),
    "limit_pair": ([old_reply("asked for a search", check_loop.search("Forrest Gump")),
                    old_reply("asked for a second search", check_loop.search("Robert Zemeckis")),
                    old_reply("asked for a search and a read", check_loop.search("Zemeckis Chicago"),
                              check_loop.read("Robert Zemeckis")),
                    old_reply(check_loop.SAYS_NOT, check_loop.NOT_SAID)], 2),
}


def test_the_full_loop_with_the_parts_does_what_the_raw_loop_does(tmp_path, monkeypatch):
    """On every made-up check, old and new: the same requests to the model, the same lookups, the
    same end and the same result as the raw loop written straight against the API."""
    monkeypatch.setattr(check_loop, "SCENARIOS", {**check_loop.SCENARIOS, **OLD_SCENARIOS})

    def record(source):
        path = str(a_loop(tmp_path, source).resolve())
        module = check_loop.load(path)
        seen = {}
        with check_loop.offline():
            for key in check_loop.SCENARIOS:
                run = check_loop.Run(key, module.run_agent, path)
                requests = [[{**turn, "content": [check_loop.view(b) if not isinstance(b, dict)
                                                  else b for b in turn["content"]]}
                             if isinstance(turn.get("content"), list) else turn
                             for turn in request["messages"]] for request in run.requests]
                seen[key] = (requests, run.lookups, run.ended, run.result)
        return seen
    whole, raw = record(FULL_LOOP), record(REFERENCE)
    refusal = whole.pop("refusal"), raw.pop("refusal")
    assert whole == raw
    assert refusal[0][:3] == refusal[1][:3]
    assert refusal[0][3]["trace"] == [{"tool": "(refusal)", "input": {}, "result": agent.DECLINED}]
    assert refusal[1][3]["trace"] == [] and refusal[0][3]["explanation"] == refusal[1][3]["explanation"]


def test_the_parts_record_each_answer_once_whatever_the_order(tmp_path):
    """With the parts, the trace has one entry for each answer checked: give() for an answer sets
    only what is sent back. The guard on the count stays in the check, for loops written without
    the parts."""
    import loop_parts
    trace = []
    talk = loop_parts.Conversation("c", None, "", [], trace, [], None)
    block = type("Block", (), {"name": "answer", "id": "a1", "type": "tool_use",
                               "input": {"verdict": "supported", "evidence": ["nowhere"],
                                         "explanation": "x"}})()
    call = loop_parts.Call(block)
    problem = talk.problem_with(call)
    assert problem.startswith(agent.REJECTED) and len(trace) == 1
    talk.give(call, problem)
    assert len(trace) == 1 and talk.results[0]["content"] == problem
    assert trace[0] == {"tool": "answer", "input": block.input, "result": problem}


def test_the_check_of_quotes_is_a_part_a_loop_may_add(tmp_path):
    """talk.problem_with() stays, documented, for a student who adds the check through their
    outline (step 3b): the plainest loop with it added passes, and sends the answer back."""
    import loop_parts
    assert "talk.problem_with(call)" in loop_parts.__doc__
    source = kit((ANSWER, """        if reply.answer:
            problem = talk.problem_with(reply.answer)
            if problem is None:
                return talk.accept(reply.answer, steps)
            talk.give(reply.answer, problem)
"""))
    path = a_loop(tmp_path, source)
    assert check_loop.check(path) == [None] * 5
    module = check_loop.load(str(path.resolve()))
    with check_loop.offline():
        run = check_loop.Run("unread", module.run_agent, str(path.resolve()))
    assert run.result["verdict"] == "doesn't say" and len(run.requests) == 3


def test_a_loop_written_before_the_parts_still_passes_in_the_new_my_loop(tmp_path):
    """A student who started 1a before it changed wrote Python against the old starter file. Their
    loop, below the line of the new my_loop.py, must still pass: the new file imports every name
    the old one did, and keeps every set-up line."""
    skeleton = (ROOT / "my_loop.py").read_text()
    marker = '    raise NotImplementedError("The loop is not written yet: see step 1a.")\n'
    assert skeleton.count(marker) == 1
    body = REFERENCE[REFERENCE.index("    warned = False"):]
    assert check_loop.check(a_loop(tmp_path, skeleton.replace(marker, body))) == [None] * 5
    # And the full loop's body, which uses rejected from the set-up lines.
    body = FULL_LOOP[FULL_LOOP.index("    warned = False"):]
    assert check_loop.check(a_loop(tmp_path, skeleton.replace(marker, body))) == [None] * 5


# ---------- the token line: the extra credit in step 3b ----------

# The instructor, Nov 11: "have it gone entirely. for the extra credit we can have the student go
# back and add it?" The raw loop with the count added as step 3b asks: a tokens dict, each reply's
# usage added to it, and tokens passed to finish() as its last argument.
TOKENS = ('        tokens["input"] += response.usage.input_tokens\n'
          '        tokens["output"] += response.usage.output_tokens\n')
TURN = '        messages.append({"role": "assistant", "content": response.content})\n'
REFUSAL = ('        if response.stop_reason == "refusal":\n'
           '            return finish(claim, None, [], DECLINED, trace, steps)\n')
COUNTING = broken(("    steps = 0\n", '    tokens = {"input": 0, "output": 0}\n    steps = 0\n'),
                  (TURN, TOKENS + TURN)).replace("trace, steps)", "trace, steps, tokens)")
TOKEN_LINE = f"ok         {agent.TOKEN_RULE}"


def counting(*edits):
    return edited(COUNTING, *edits)


def test_a_loop_that_counts_tokens_gets_the_token_line_and_turns_on_cost(tmp_path, monkeypatch, saved, capsys):
    assert COUNTING.count("trace, steps, tokens)") == 5
    a_loop(tmp_path, COUNTING, monkeypatch)
    assert check_loop.main([]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed == FIVE + [TOKEN_LINE, "", check_loop.PASSED]
    assert saved.read_text().splitlines() == ["yours"] + printed
    assert agent.which_loop() == "yours" and agent.counts_tokens()
    # Without the count again, the loop still passes, and tokens and cost are hidden again.
    a_loop(tmp_path, REFERENCE, monkeypatch)
    assert check_loop.main([]) == 0 and not agent.counts_tokens()


def test_a_loop_written_with_the_old_order_of_finish_still_counts(tmp_path):
    """Before Nov 12, finish() took tokens, then steps. A loop written then still passes."""
    old = COUNTING.replace("trace, steps, tokens)", "trace, tokens, steps)")
    assert check_loop.check(a_loop(tmp_path, old)) == [None] * 6
    assert agent.finish("c", None, [], "x", [], {"input": 2, "output": 1}, 3)["steps"] == 3


TOKEN_BROKEN = {
    "no tokens": ([(TOKENS, "")],
                  ["your loop stopped with tokens {'input': 0, 'output': 0}",
                   "where its three replies used 4,266 input and 132 output tokens"]),
    "output not counted": ([('        tokens["output"] += response.usage.output_tokens\n', "")],
                           ["stopped with tokens {'input': 4266, 'output': 0}"]),
    "one result without them": ([("RAN_OUT, trace, steps, tokens)", "RAN_OUT, trace, steps)")],
                                ["the model's fourth reply asked for a fourth search", "stopped with tokens None"]),
}


@pytest.mark.parametrize("name", TOKEN_BROKEN)
def test_a_wrong_count_fails_the_token_line_and_nothing_else(tmp_path, monkeypatch, saved, capsys, name):
    edits, phrases = TOKEN_BROKEN[name]
    path = a_loop(tmp_path, counting(*edits), monkeypatch)
    printed = shown(path)
    assert printed[:5] == FIVE
    assert printed[5].startswith(f"NOT YET    {agent.TOKEN_RULE}: ")
    for phrase in phrases:
        assert phrase in printed[5], printed[5]
    assert len(printed) == 6
    # A wrong count fails the check: the agent stops, and tokens and cost stay hidden.
    saved.parent.mkdir(parents=True)
    saved.write_text("yours\n")
    assert check_loop.main([]) == 1
    assert agent.which_loop() == "not passed" and not agent.counts_tokens()


# The same count in the plainest loop built with the parts (step 3b): each reply's usage added up,
# and the count passed last to talk.accept() and talk.stop().
KIT_COUNTING = kit(("    steps = 0           # lookups made so far\n",
                    "    steps = 0           # lookups made so far\n"
                    '    tokens = {"input": 0, "output": 0}\n'),
                   ("        reply = talk.ask()\n",
                    "        reply = talk.ask()\n"
                    '        tokens["input"] += reply.usage.input_tokens\n'
                    '        tokens["output"] += reply.usage.output_tokens\n')
                   ).replace(", steps)", ", steps, tokens)")
FULL_COUNTING = full(("    rejected = 0        # answers sent back so far\n",
                      "    rejected = 0        # answers sent back so far\n"
                      '    tokens = {"input": 0, "output": 0}\n'),
                     ("        reply = talk.ask()\n",
                      "        reply = talk.ask()\n"
                      '        tokens["input"] += reply.usage.input_tokens\n'
                      '        tokens["output"] += reply.usage.output_tokens\n')
                     ).replace(", steps)", ", steps, tokens)")


@pytest.mark.parametrize("source", [KIT_COUNTING, FULL_COUNTING], ids=["the-plainest-loop", "the-full-loop"])
def test_a_loop_built_with_the_parts_can_count_tokens(tmp_path, monkeypatch, saved, capsys, source):
    """Its count holds the tokens of both of ask()'s calls when ask() reminds the model (the made-up
    check of a reply that asks for nothing)."""
    assert KIT_COUNTING.count(", steps, tokens)") == 2 and FULL_COUNTING.count(", steps, tokens)") == 5
    a_loop(tmp_path, source, monkeypatch)
    assert check_loop.main([]) == 0
    printed = capsys.readouterr().out.splitlines()
    assert printed == FIVE + [TOKEN_LINE, "", check_loop.PASSED]
    assert agent.which_loop() == "yours" and agent.counts_tokens()


@pytest.mark.parametrize("old, new, phrase", [
    ('        tokens["output"] += reply.usage.output_tokens\n', "",
     "stopped with tokens {'input': 4266, 'output': 0}"),
    ("talk.stop(RAN_OUT, steps, tokens)", "talk.stop(RAN_OUT, steps)",
     "the model's third reply asked for a third search, and your loop stopped with tokens None"),
])
def test_a_wrong_count_with_the_parts_fails_the_token_line_only(tmp_path, old, new, phrase):
    assert KIT_COUNTING.count(old) == 1
    printed = shown(a_loop(tmp_path, KIT_COUNTING.replace(old, new)))
    assert printed[:5] == FIVE
    assert printed[5].startswith(f"NOT YET    {agent.TOKEN_RULE}: ") and phrase in printed[5], printed[5]


def test_the_parts_count_nothing_by_themselves(tmp_path):
    """A loop built with the parts, as 1a leaves it, passes no count: no token line, no cost."""
    assert check_loop.check(a_loop(tmp_path, KIT_REFERENCE)) == [None] * 5


def test_counts_tokens_follows_the_file(saved):
    assert not agent.counts_tokens()                     # no file
    saved.parent.mkdir(parents=True)
    six = FIVE + ["ok         6. Stop when the model stops"]     # a file the six rules wrote
    for lines, counts in ((["yours"] + FIVE + [TOKEN_LINE], True), (["yours"] + FIVE, False),
                          (["yours"] + six + [TOKEN_LINE], True),
                          (["not passing", check_loop.FELL_BACK] + FIVE + [TOKEN_LINE], False),
                          (["yours", f"NOT YET    {agent.TOKEN_RULE}: x."], False)):
        saved.write_text("\n".join(lines) + "\n")
        assert agent.counts_tokens() is counts, lines


def test_finish_holds_tokens_and_cost_only_when_given_them():
    plain = agent.finish("c", "supported", ["q"], "x", [], 2)
    assert set(plain) == {"claim", "verdict", "evidence", "explanation", "trace", "steps"}
    counted = agent.finish("c", "supported", ["q"], "x", [], 2, {"input": 1000, "output": 100})
    assert counted["tokens"] == {"input": 1000, "output": 100}
    assert counted["cost_usd"] == round((1000 * agent.PRICE[0] + 100 * agent.PRICE[1]) / 1_000_000, 6)


# ---------- an error, a loop that never stops, and a file that will not load ----------

def test_an_error_is_reported_with_its_line(tmp_path):
    source = broken(("result = lookup(call.name, call.input)",
                     "result = lookup(call.name, call.inputs)"))
    line = 1 + source[:source.index("call.inputs")].count("\n")
    printed = shown(a_loop(tmp_path, source))
    assert printed[0] == (
        "NOT YET    1. Ask the model: the model's first reply asked for a search, and your loop "
        f"stopped with an error at line {line} of my_loop.py: AttributeError: 'ToolUseBlock' "
        "object has no attribute 'inputs'.")
    # Rule 2's made-up check makes a lookup, so it meets the same error.
    assert "AttributeError: 'ToolUseBlock' object has no attribute 'inputs'" in printed[1]


def test_a_loop_that_never_stops_is_reported(tmp_path, monkeypatch):
    monkeypatch.setattr(check_loop, "TIME_LIMIT", 0.3)
    monkeypatch.setattr(check_loop, "AFTER_A_HANG", 0.1)
    turn = '        messages.append({"role": "assistant", "content": response.content})\n'
    source = broken((turn, turn + "        while True:\n            pass\n"))
    first = 1 + source[:source.index("        while True:\n            pass")].count("\n")
    for problem in check_loop.check(a_loop(tmp_path, source)):
        assert "and your loop did not stop: it was still running line" in problem, problem
        assert (f" line {first} of my_loop.py" in problem
                or f" line {first + 1} of my_loop.py" in problem), problem


def test_a_loop_that_keeps_asking_the_model_is_stopped(tmp_path):
    source = ("def run_agent(claim, client=None, max_steps=12, lookup=None):\n"
              "    while True:\n"
              "        try:\n"
              "            client.messages.create(model='x', messages=[])\n"
              "        except Exception:\n"
              "            pass\n")
    start = time.monotonic()
    problems = check_loop.check(a_loop(tmp_path, source))
    assert time.monotonic() - start < check_loop.TIME_LIMIT
    assert problems[2].endswith("gave an answer that quotes the page it had read, and your loop "
                                "asked the model again instead of stopping")


def test_a_file_that_will_not_load_is_reported_on_every_line(tmp_path):
    problems = check_loop.check(a_loop(tmp_path, "def run_agent(claim:\n    pass\n"))
    assert len(set(problems)) == 1 and len(problems) == 5
    assert problems[0].startswith("my_loop.py could not be loaded, because of an error at line 1: "
                                  "SyntaxError")
    problems = check_loop.check(a_loop(tmp_path, "import nothing_called_this\n"))
    assert "line 1: ModuleNotFoundError" in problems[0]
    problems = check_loop.check(a_loop(tmp_path, "def run(claim):\n    pass\n"))
    assert problems == ["my_loop.py has no function called run_agent"] * 5


def test_the_check_has_no_network_and_hides_what_the_loop_prints(tmp_path, monkeypatch, capsys):
    requests = []
    monkeypatch.setattr(wiki.requests, "get", lambda *args, **kwargs: requests.append(args))
    source = broken(("result = lookup(call.name, call.input)",
                     "print('looking up'); result = run_tool(call.name, call.input)"))
    problems = check_loop.check(a_loop(tmp_path, source))
    assert requests == []
    assert "RuntimeError: this check has no network, and Wikipedia was called directly" in problems[1]
    assert "looking up" not in capsys.readouterr().out
    assert wiki.search.__name__ == "search"    # put back afterwards


# ---------- which loop the agent runs, and what check.py and evaluate.py say ----------

def fake_loops(monkeypatch):
    """Stand-ins for my_loop and reference_loop that say which one ran, with what."""
    calls = []
    for name in ("my_loop", "reference_loop"):
        def run_agent(claim, client=None, max_steps=None, lookup=None, name=name):
            calls.append((name, claim, client, max_steps, lookup))
            return {"claim": claim, "verdict": "supported", "evidence": [], "explanation": "x",
                    "trace": [], "steps": 0}
        monkeypatch.setitem(sys.modules, name, SimpleNamespace(run_agent=run_agent))
    return calls


def test_run_agent_runs_the_loop_in_use(monkeypatch, saved):
    calls = fake_loops(monkeypatch)
    lookup = object()
    agent.run_agent("c1", client="client", max_steps=5, lookup=lookup)
    saved.parent.mkdir(parents=True)
    saved.write_text("yours\n")
    agent.run_agent("c2", client="client", max_steps=5, lookup=lookup)
    agent.run_agent("c3")
    assert calls == [("reference_loop", "c1", "client", 5, lookup),
                     ("my_loop", "c2", "client", 5, lookup),
                     ("my_loop", "c3", None, agent.MAX_STEPS, agent.run_tool)]
    # A loop that passed and fails now runs nothing, and never the reference loop.
    saved.write_text("not passing\n")
    with pytest.raises(agent.LoopNotPassed, match="has not passed the check"):
        agent.run_agent("c4")
    assert len(calls) == 3


def test_check_py_says_which_loop_when_the_agent_runs(monkeypatch, tmp_path, saved, capsys):
    fake_loops(monkeypatch)
    monkeypatch.setitem(check.METHODS, "agent", agent.run_agent)
    monkeypatch.setitem(check.METHODS, "no-tools", lambda claim: sys.modules["my_loop"].run_agent(claim))

    def run(method):
        monkeypatch.setattr(sys, "argv", ["check.py", "--method", method, "--out", str(tmp_path), "c"])
        check.main()
        return capsys.readouterr().out.splitlines()

    assert run("agent")[0] == "Agent loop: the reference loop (reference_loop.py)"    # Part 0
    saved.parent.mkdir(parents=True)
    saved.write_text("yours\n")
    assert run("agent")[0] == "Agent loop: yours (my_loop.py)"
    assert not any(line.startswith("Agent loop") for line in run("no-tools"))
    saved.write_text("not passing\n")
    with pytest.raises(SystemExit) as stopped:
        run("agent")
    assert stopped.value.code == 1
    assert capsys.readouterr().out.strip() == agent.NOT_PASSED


def test_evaluate_py_says_which_loop_when_the_agent_runs(monkeypatch, tmp_path, saved, capsys):
    fake_loops(monkeypatch)
    claims = tmp_path / "claims.jsonl"
    claims.write_text(json.dumps({"id": "c1", "claim": "c", "source": "hover",
                                  "label": "SUPPORTED", "hops": 2}) + "\n")
    monkeypatch.setitem(evaluate.METHODS, "agent", agent.run_agent)
    monkeypatch.setitem(evaluate.METHODS, "no-tools", agent.run_agent)

    def run(methods, out):
        monkeypatch.setattr(sys, "argv", ["evaluate.py", str(claims), "--methods", methods,
                                          "--out", str(tmp_path / out)])
        evaluate.main()
        return capsys.readouterr().out.splitlines()

    # Before the student's loop has passed, evaluate.py runs no agent, and never the reference loop.
    with pytest.raises(SystemExit) as stopped:
        run("no-tools,agent", "a")
    assert stopped.value.code == 1 and capsys.readouterr().out.strip() == agent.NOT_PASSED
    assert not (tmp_path / "a").exists()
    saved.parent.mkdir(parents=True)
    saved.write_text("yours\n")
    assert run("agent", "b")[0] == "Agent loop: yours (my_loop.py)"
    assert not any(line.startswith("Agent loop") for line in run("no-tools", "c"))
    # A loop that fails now stops the run before anything is run or forgotten, --fresh or not.
    kept = (tmp_path / "b" / "agent.jsonl").read_text()
    saved.write_text("not passing\n")
    for extra in ([], ["--fresh"]):
        monkeypatch.setattr(sys, "argv", ["evaluate.py", str(claims), "--methods", "agent",
                                          "--out", str(tmp_path / "b"), *extra])
        with pytest.raises(SystemExit):
            evaluate.main()
        assert capsys.readouterr().out.strip() == agent.NOT_PASSED
        assert (tmp_path / "b" / "agent.jsonl").read_text() == kept


def test_the_fingerprint_covers_the_loop_in_use(monkeypatch, tmp_path, saved):
    # A copy of the files the fingerprint reads, so the test can change them.
    for name in evaluate.AGENT_FILES + ["my_loop.py", "reference_loop.py"]:
        shutil.copy(ROOT / name, tmp_path / name)
    monkeypatch.setattr(evaluate, "HERE", tmp_path)
    on_reference = evaluate.agent_version()
    (tmp_path / "my_loop.py").write_text("# changed\n")
    assert evaluate.agent_version() == on_reference     # my_loop.py is not in use yet

    saved.parent.mkdir(parents=True)
    saved.write_text("yours\n")
    on_yours = evaluate.agent_version()
    assert on_yours != on_reference
    (tmp_path / "my_loop.py").write_text("# changed again\n")
    assert evaluate.agent_version() != on_yours
    on_yours = evaluate.agent_version()
    (tmp_path / "reference_loop.py").write_text("# not in use now\n")
    assert evaluate.agent_version() == on_yours

    # The same bytes in both loop files still make two versions.
    (tmp_path / "my_loop.py").write_text(REFERENCE)
    (tmp_path / "reference_loop.py").write_text(REFERENCE)
    on_yours = evaluate.agent_version()
    saved.unlink()
    assert evaluate.agent_version() != on_yours
