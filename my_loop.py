"""Your agent's loop, which you design in step 1a. The homework page says what the
loop is for, under "1a. Design the loop" (also in instructions/part1.md), and the
check tells you each rule it must follow when your loop breaks it.

You design the loop as an outline in plain words, in WRITEUP.md under 1a. The
loop below the line that says where it goes is Claude's translation of that
outline, written with the parts in loop_parts.py: each line of your outline is a
comment, with about one line of Python for it under it. To change the loop,
change your outline and ask Claude to translate it again.

Check it after each translation. The check uses a scripted stand-in for the
model and for Wikipedia, so it needs no key and costs nothing:

    uv run python check_loop.py

Part 0 runs the agent on the reference loop. Once every rule passes, the agent
runs on this loop and no other: the runs of 1c and later need it to pass.
"""

import re

import anthropic

# The names below include every one the file had before the parts, so that a loop written
# then still runs.
from agent import (ACCEPTED, DECLINED, INSTRUCTIONS, MAX_REJECTED, MAX_STEPS, MODEL, NO_ANSWER,
                   OUT_OF_STEPS, RAN_OUT, REJECTED, REJECTED_TOO_OFTEN, REMINDED, REMINDER,
                   TOOLS, answer_problem, clean_answer, finish, run_tool)
from loop_parts import Conversation


# ---- sorting a claim into a lookup budget: 12, 8 or 3 ----

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]
DAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
CAUSAL = ["led to", "because", "caused"]
AGGREGATE = ["every", "majority", "worldwide", "timeline"]
JOINING = ["and", "while", "whereas"]
COMPARISON = ["than", "more", "less", "fewer", "greater", "higher", "lower", "earlier", "later",
              "older", "newer", "larger", "smaller", "longer", "shorter", "faster", "slower",
              "better", "worse", "first", "last", "only", "most", "least", "largest", "smallest",
              "oldest", "newest", "highest", "lowest", "longest", "shortest", "fastest", "slowest",
              "best", "worst"]
RATE = ["doubled", "tripled", "halved", "increased", "decreased", "grew", "fell", "dropped",
        "rose", "average", "mean", "median", "ratio", "percentage", "percent", "share",
        "proportion", "per capita", "year over year", "month over month"]
ABBREVIATIONS = ["U.S.", "U.K.", "Dr.", "Mr.", "Ms.", "Mrs.", "St.", "Jr.", "Sr.", "vs.",
                 "e.g.", "i.e."]


def has_any(text, words):
    """Whether the text holds any of the words or phrases, as whole words, ignoring case."""
    pattern = r"\b(" + "|".join(re.escape(word) for word in words) + r")\b"
    return re.search(pattern, text, re.IGNORECASE) is not None


def sentences(text):
    for abbreviation in ABBREVIATIONS:
        text = text.replace(abbreviation, abbreviation.replace(".", ""))
    text = re.sub(r"(\d)\.(\d)", r"\1\2", text)
    return [chunk for chunk in re.split(r"[.!?;]+", text) if chunk.strip()]


def count_names(text):
    """Runs of capitalized words, not counting a sentence's first word or days and months."""
    count = 0
    for sentence in sentences(text):
        in_run = False
        for i, word in enumerate(sentence.split()):
            word = word.strip(".,!?;:\"'()")
            if i > 0 and word[:1].isupper() and word not in DAYS + MONTHS:
                if not in_run:
                    count += 1
                in_run = True
            else:
                in_run = False
    return count


def count_numbers(text):
    """Numbers and years, plus month names with a number right before or after them."""
    numbers = re.findall(r"\b\d+(?:[.,]\d+)*%?\b", text)
    month = "(" + "|".join(MONTHS) + ")"
    dates = re.findall(r"\b\d+\s+" + month + r"\b|\b" + month + r"\s+\d+", text)
    return len(numbers) + len(dates)


def lookup_budget(claim):
    """12, 8 or 3 lookups, trying the hardest kind of claim first."""
    words = len(claim.split())
    if (len(sentences(claim)) > 1 or words > 30
            or has_any(claim, CAUSAL) or has_any(claim, AGGREGATE)):
        return 12
    if (16 <= words <= 30 or count_numbers(claim) >= 2 or count_names(claim) >= 3
            or has_any(claim, JOINING) or has_any(claim, COMPARISON) or has_any(claim, RATE)):
        return 8
    return 3


def run_agent(claim, client=None, max_steps=None, lookup=run_tool):
    """Check one claim. Returns what talk.accept() or talk.stop() returns."""
    client = client or anthropic.Anthropic()
    system = INSTRUCTIONS.read_text()
    messages = [{"role": "user", "content": f"Claim: {claim}"}]
    trace, read_so_far = [], []
    talk = Conversation(claim, client, system, messages, trace, read_so_far, lookup)
    steps = 0          # lookups made so far
    rejected = 0       # answers sent back so far

    # Your loop should repeatedly call the model with the message history so far, and ask for
    # its next step. It should check whether the model has given an answer yet. If not, it should
    # make the lookups that step asks for, and add what they return to the history. It should
    # also pay attention to whether the loop has reached its limit: a claim that runs out of
    # lookups cannot be decided.
    # ---- your loop goes below this line (step 1a) ----
    if max_steps is None:
        max_steps = lookup_budget(claim)
    reminded = False   # whether the last reply had no tool call and got a reminder
    out_of_steps_sent = False   # whether an earlier turn sent OUT_OF_STEPS
    while True:
        # Rule 1: ask the model, and keep its reply in the conversation.
        reply = client.messages.create(model=MODEL, max_tokens=16000, system=system,
                                       tools=TOOLS, messages=messages)
        messages.append({"role": "assistant", "content": reply.content})
        calls = [block for block in reply.content if block.type == "tool_use"]

        # Rule 6: stop if the model refuses; remind it once if it stops calling tools.
        if reply.stop_reason == "refusal":
            return finish(claim, None, [], DECLINED, trace, steps)
        if not calls:
            if reminded:
                return finish(claim, None, [], NO_ANSWER, trace, steps)
            trace.append({"tool": "(reminder)", "input": {}, "result": REMINDED})
            messages.append({"role": "user", "content": REMINDER})
            reminded = True
            continue
        reminded = False

        results = []   # a tool_result for each of this reply's tool calls
        out_of_steps_now = False
        for call in calls:
            if call.name == "answer":
                # Rule 4: check the answer; finish if it passes, send it back if not.
                answer = clean_answer(call.input)
                problem = answer_problem(answer, read_so_far)
                if problem is None:
                    trace.append({"tool": call.name, "input": call.input, "result": ACCEPTED})
                    return finish(claim, answer["verdict"], answer["evidence"],
                                  answer["explanation"], trace, steps)
                rejected += 1
                note = REJECTED + problem
                trace.append({"tool": call.name, "input": call.input, "result": note})
                if rejected >= MAX_REJECTED:
                    return finish(claim, None, [], REJECTED_TOO_OFTEN.format(n=rejected),
                                  trace, steps)
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": note})
            else:
                # Rule 5: no lookup once the budget is used up; stop if the model asks again.
                if steps >= max_steps:
                    if out_of_steps_sent:
                        return finish(claim, None, [], RAN_OUT, trace, steps)
                    error = OUT_OF_STEPS.format(n=max_steps)
                    trace.append({"tool": call.name, "input": call.input, "result": error})
                    results.append({"type": "tool_result", "tool_use_id": call.id,
                                    "content": error})
                    out_of_steps_now = True
                    continue
                # Rule 2: run the lookup, count it, log it, keep what read and wikidata return.
                result = lookup(call.name, call.input)
                steps += 1
                trace.append({"tool": call.name, "input": call.input, "result": result})
                if call.name in ("read", "wikidata"):
                    read_so_far.append(result)
                results.append({"type": "tool_result", "tool_use_id": call.id, "content": result})
        if out_of_steps_now:
            out_of_steps_sent = True

        # Rule 3: send every result back in one user turn, then start the next round.
        messages.append({"role": "user", "content": results})
