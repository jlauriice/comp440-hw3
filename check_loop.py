"""Check the loop in my_loop.py against the five rules of step 1a.

    uv run python check_loop.py

It runs your loop on eleven short made-up checks of one claim, with a
scripted stand-in for the model and for Wikipedia, so it needs no key and no
network, costs nothing and takes a few seconds. It prints one line per rule: ok,
or NOT YET and what happened. Under the five lines it states the rule behind the
first NOT YET line, in plain words. Then it shows what your loop printed (with
print(), for example) during the made-up check behind that line, up to 40
lines; nothing your loop prints is saved. The stand-in
for the model is as strict about the conversation it is sent as the real
Claude API, so a loop that passes here does not fail on its first real run.

When every rule passes, it saves the lines it printed as
runs/part1/loop-check.txt, with "yours" on the first line, and from then on
your copy's agent runs on your loop. If your loop passed earlier and a rule
fails now, it rewrites that file with "not passing" on the first line: until
every rule passes again, evaluate.py and check.py run no agent and say so. The
file is still there, so step 1a stays done on the homework page.

There is no way to keep the reference loop instead: from step 1a on, the agent
runs only on your own loop.

A loop that passes finish() a token count (extra credit, step 3b) gets one more
line, after the five, which checks that count. It must say ok too.

A loop may do more than the rules ask: check that an answer's quotes are in
what the agent read and send back one that fails, or warn the model once
before it stops at the limit, as loops written before November 14 do. Where
such a loop and the plainest loop part ways, the made-up checks accept either.

What a loop does with a reply that asks for more lookups than are left is its
own choice, and the check accepts each way: make them all, as many as are
left, or none, and then stop with no verdict, or give every call a result and
ask the model again. Once the limit is reached, a loop may also make the
lookups of one more reply before it stops, with or without asking the model
once more, but not those of a second.
"""

import argparse
import contextlib
import importlib.util
import io
import os
import sys
import threading
import time
import traceback
from pathlib import Path

from anthropic.types import Message, TextBlock, ToolUseBlock, Usage

import agent
import wiki

MY_LOOP = Path(__file__).resolve().parent / "my_loop.py"
RULES = ["Ask the model", "Make its lookups", "Stop with the answer", "Stop at the limit",
         "Count the lookups"]
TIME_LIMIT = 2      # seconds your loop has for one made-up check
AFTER_A_HANG = 0.5  # seconds for each later one, once a loop has not stopped
MAX_LOOKUPS = 40    # far more lookups than any made-up check asks for
SHOWN_LINES = 40    # the most lines of what your loop printed that the check shows
LOOKUPS = ("search", "read", "wikidata")
PLENTY = 20         # the limit of lookups in the made-up checks that do not test the limit
LIMIT = 2           # the limit in the two that do
PASSED = "Every rule passes. From now on your copy's agent runs on your loop (my_loop.py)."
FAILED = "Not yet. Work on the first NOT YET line, then run this again."
FELL_BACK = "Your loop passed the check earlier and does not pass now."
NOT_PASSING_NOW = ("Your loop passed earlier and does not pass now, so no agent run starts until every "
                   "rule passes again.")
# What each rule asks, in plain words. The page does not list the rules: under the five lines, the
# check prints the one behind the first NOT YET line, so that a student meets each rule when their
# design breaks it. The number comes from agent.py when the check runs.
def rule_text(number):
    return [
        "The model remembers nothing between calls, so each time it is asked it must be sent "
        "everything that has happened so far: the claim, its own replies, and what came of each.",
        "Whatever lookups a reply asks for, one or several, are all made, and the model is not "
        "asked again until it has been told, all at once, what came of everything that reply "
        "asked for.",
        "An answer is not a lookup: it is not made and not counted. When the model gives an "
        "answer, the agent stops with that answer: its verdict, its evidence and its explanation.",
        f"Once the agent has made as many lookups as its limit ({agent.MAX_STEPS} in a real run), "
        "the model is asked once more, so that it can answer from what the lookups found. If it "
        "asks for more lookups instead, the agent stops with no verdict, at once or after one "
        "more turn of lookups, and no later. A reply that asks for more lookups than are left is "
        "yours to decide: the agent may make all of them, some or none, and may stop there.",
        "The agent's count of lookups is the number of lookups it made, and its trace has an "
        "entry for each one, with what it found.",
    ][number - 1]


NOT_FOUND = ("the check could not find `{name}` in run_agent(): keep the names of the set-up "
             "lines at the top of the function")

# ---------- the made-up claim, Wikipedia and model ----------

CLAIM = "The director of Forrest Gump was born in Chicago."
PAGES = {
    "Forrest Gump": "Forrest Gump is a 1994 American film directed by Robert Zemeckis.",
    "Robert Zemeckis": ("Robert Lee Zemeckis (born May 14, 1952) is an American filmmaker. "
                        "He was born in Chicago, Illinois."),
}


def wikipedia(name, args):
    """What the made-up Wikipedia returns for one lookup."""
    args = args if isinstance(args, dict) else {}
    if name == "search":
        return (f"Search results for {args.get('query')!r}:\n"
                "1. Forrest Gump: a 1994 film\n2. Robert Zemeckis: an American filmmaker")
    if name == "read":
        return PAGES.get(args.get("title"), f"There is no page called {args.get('title')!r}.")
    if name == "wikidata":
        return f"Wikidata: {args.get('entity')}, {args.get('property')}: Chicago"
    return f"There is no tool called {name!r}."


def reply(says, *blocks, stop=None):
    """One scripted reply. `says` finishes the sentence "the model's first reply ..."."""
    return {"says": says, "blocks": blocks, "stop": stop}


def text(words):
    return ("text", words)


def use(name, args):
    return ("tool_use", name, args)


def search(query):
    return use("search", {"query": query})


def read(title):
    return use("read", {"title": title})


BIRTHPLACE = use("wikidata", {"entity": "Robert Zemeckis", "property": "place of birth"})
GOOD = use("answer", {"verdict": "supported", "evidence": ["directed by Robert Zemeckis"],
                      "explanation": "The page names him as the director."})
ALL_THREE = use("answer", {"verdict": "supported",
                           "evidence": ["directed by Robert Zemeckis", "place of birth: Chicago",
                                        "He was born in Chicago, Illinois."],
                           "explanation": "Both pages and Wikidata agree."})
MADE_UP = use("answer", {"verdict": "supported", "evidence": ["Zemeckis was born in Ohio."],
                         "explanation": "He was born in Ohio."})
NOT_SAID_WHY = "The page does not say where he was born."
NOT_SAID = use("answer", {"verdict": "doesn't say", "evidence": [], "explanation": NOT_SAID_WHY})
QUOTES_GOOD = "gave an answer that quotes the page it had read"
QUOTES_NOTHING = "gave an answer with a quote that is in nothing it had read"
SAYS_NOT = "gave an answer of doesn't say"
NO_TOOL = "had text and no tool call"

# Each made-up check: the model's replies, in order, and the limit of lookups. Most end with an
# answer, so that a loop that handles answers stops, and its result shows what the rules ask for;
# a last "doesn't say" is there for a loop that sends an answer back or warns the model at the
# limit, which the check also accepts.
SCENARIOS = {
    "ask": ([reply("asked for a search", text("I will start with a search."),
                   search("Forrest Gump director")),
             reply("asked for a read", read("Forrest Gump")),
             reply(QUOTES_GOOD, GOOD),
             reply(SAYS_NOT, NOT_SAID)], PLENTY),
    "lookups": ([reply("asked for a search", search("Forrest Gump")),
                 reply("asked for a read", text("Now the film's page."), read("Forrest Gump")),
                 reply("asked for a wikidata lookup and a read", BIRTHPLACE,
                       read("Robert Zemeckis")),
                 reply("gave an answer that quotes its two reads and its wikidata lookup",
                       ALL_THREE),
                 reply(SAYS_NOT, NOT_SAID)], PLENTY),
    "results": ([reply("asked for a search and a read", search("Robert Zemeckis"),
                       read("Robert Zemeckis")),
                 reply("asked for a wikidata lookup", BIRTHPLACE),
                 reply(SAYS_NOT, NOT_SAID)], PLENTY),
    "accept": ([reply("asked for a read", read("Forrest Gump")),
                reply(QUOTES_GOOD, GOOD)], PLENTY),
    "clean": ([reply("asked for a read", read("Robert Zemeckis")),
               reply("gave an answer with its evidence as one string and no explanation",
                     use("answer", {"verdict": "supported",
                                    "evidence": "He was born in Chicago, Illinois."}))],
              PLENTY),
    # One reply with a lookup and an answer: the agent stops with the answer, with the lookup
    # made or not.
    "both": ([reply("asked for a read", read("Forrest Gump")),
              reply("asked for a search and gave an answer that quotes the page it had read",
                    search("Robert Zemeckis"), GOOD),
              reply(SAYS_NOT, NOT_SAID)], PLENTY),
    # An answer quoting what the agent never read: the plainest loop stops with it; a loop that
    # checks quotes sends it back and stops with the next answer. Either passes.
    "unread": ([reply("asked for a read", read("Forrest Gump")),
                reply(QUOTES_NOTHING, MADE_UP),
                reply(SAYS_NOT, NOT_SAID)], PLENTY),
    # A reply that asks for nothing: the parts remind the model once, and the loop stops with the
    # answer that follows (rule 3). Rule 1 looks at the requests, as the real Claude API would.
    "nothing": ([reply(NO_TOOL, text("I think the claim is true.")),
                 reply(SAYS_NOT, NOT_SAID)], PLENTY),
    # The answer comes when the limit has been reached.
    "limit_answer": ([reply("asked for a search", search("Forrest Gump")),
                      reply("asked for a second search", search("Robert Zemeckis")),
                      reply(SAYS_NOT, NOT_SAID)], LIMIT),
    # The model keeps asking. The plainest loop stops at the third reply. A loop may instead make
    # the third reply's search and stop then, or ask again and stop at the fourth; a loop that also
    # warns the model once stops one reply later. None may make a second search past the limit, so
    # the fifth reply is the last one a loop stops at; the sixth is there to be asked for.
    "limit_again": ([reply("asked for a search", search("Forrest Gump")),
                     reply("asked for a second search", search("Robert Zemeckis")),
                     reply("asked for a third search", search("Zemeckis birthplace")),
                     reply("asked for a fourth search", search("Zemeckis Chicago")),
                     reply("asked for a fifth search", search("Zemeckis Illinois")),
                     reply("asked for a sixth search", search("Zemeckis early life"))], LIMIT),
    # One lookup is left, and one reply asks for two. What the loop does with that reply is its own
    # choice: it may make both, one or neither, and then stop there with no verdict, or give each
    # call a result and ask the model again, which then answers. The plainest loop makes both and
    # asks again; a loop that warns makes one, warns about the other and asks again.
    "limit_cross": ([reply("asked for a search", search("Forrest Gump")),
                     reply("asked for a search and a read in one reply", search("Robert Zemeckis"),
                           read("Robert Zemeckis")),
                     reply(SAYS_NOT, NOT_SAID)], LIMIT),
}


def build(script, tag):
    """The scripted replies as the Claude API's own objects, so the loop sees what it will
    see in a real run. Each reply uses a different number of tokens."""
    replies = []
    for i, spec in enumerate(script, 1):
        blocks = []
        for j, block in enumerate(spec["blocks"], 1):
            if block[0] == "text":
                blocks.append(TextBlock(type="text", text=block[1]))
            else:
                blocks.append(ToolUseBlock(type="tool_use", id=f"toolu_{tag}_{i}{j}",
                                           name=block[1], input=dict(block[2])))
        calls = any(block.type == "tool_use" for block in blocks)
        replies.append(Message(
            id=f"msg_{tag}_{i}", type="message", role="assistant", model=agent.MODEL,
            content=blocks, stop_reason=spec["stop"] or ("tool_use" if calls else "end_turn"),
            stop_sequence=None,
            usage=Usage(input_tokens=1000 + 211 * i, output_tokens=30 + 7 * i)))
    return replies


# ---------- running your loop on one made-up check ----------

class Stop(BaseException):
    """Raised inside your loop by the check, to end a made-up check. It is a BaseException,
    so an `except Exception` in your loop does not catch it."""


class AskedTooOften(Stop):
    """The loop asked the model again after the last scripted reply."""


class TooManyLookups(Stop):
    """The loop ran more than MAX_LOOKUPS lookups."""


class DidNotStop(Stop):
    def __init__(self, line):
        super().__init__(line)
        self.line = line


class NotYet(Exception):
    """A rule that does not pass yet: the sentence that says what happened, and the made-up
    check (a Run) it is about."""

    def __init__(self, run, sentence):
        super().__init__(sentence)
        self.run = run


def stop_at(deadline, loop_file):
    """A trace function that stops the loop in loop_file once the deadline has passed."""
    def each_line(frame, event, arg):
        if time.monotonic() > deadline:
            raise DidNotStop(frame.f_lineno)
        return each_line

    def each_call(frame, event, arg):
        return each_line if frame.f_code.co_filename == loop_file else None
    return each_call


def in_thread(work, loop_file, seconds=TIME_LIMIT):
    """Run work() with a time limit. Returns (value, error, still_running)."""
    box = {}

    def target():
        sys.settrace(stop_at(time.monotonic() + seconds, loop_file))
        try:
            box["value"] = work()
        except BaseException as error:  # noqa: BLE001  whatever the loop raised, report it
            box["error"] = error
        finally:
            sys.settrace(None)
    thread = threading.Thread(target=target, daemon=True)
    thread.start()
    thread.join(seconds + 1)
    return box.get("value"), box.get("error"), thread.is_alive()


def line_in(error, loop_file):
    """The line of loop_file where the error happened, or None."""
    if isinstance(error, SyntaxError) and error.filename == loop_file:
        return error.lineno
    lines = [frame.lineno for frame in traceback.extract_tb(error.__traceback__)
             if frame.filename == loop_file]
    return lines[-1] if lines else None


def described(error):
    if isinstance(error, SyntaxError):
        return f"{type(error).__name__}: {error.msg}"
    message = " ".join(str(error).split())
    message = message if len(message) <= 160 else message[:157] + "..."
    return f"{type(error).__name__}: {message}" if message else type(error).__name__


def copy_request(request):
    """What the loop sent, copied, since the loop goes on to change its conversation."""
    request = dict(request)
    if isinstance(request.get("messages"), (list, tuple)):
        request["messages"] = [
            {**turn, "content": list(turn["content"])}
            if isinstance(turn, dict) and isinstance(turn.get("content"), list) else
            (dict(turn) if isinstance(turn, dict) else turn)
            for turn in request["messages"]]
    return request


def copy_value(value):
    if isinstance(value, list):
        return [dict(item) if isinstance(item, dict) else item for item in value]
    if isinstance(value, dict):
        return dict(value)
    return value


def loop_variables(loop_file):
    """steps and trace as run_agent() in my_loop.py has them while it waits for the model, read
    (never changed) from run_agent()'s own frame, wherever in the file the model was asked
    from. The check uses them only for what it cannot see from outside: how far a loop that
    does not stop yet has got."""
    frame = sys._getframe(1)
    while frame is not None:
        if frame.f_code.co_name == "run_agent" and frame.f_code.co_filename == loop_file:
            names = frame.f_locals
            return {name: copy_value(names[name]) for name in ("steps", "trace") if name in names}
        frame = frame.f_back
    return {}


CURRENT = threading.local()     # the made-up check running in this thread


class ScriptedModel:
    """The client your loop is given: client.messages.create(...) returns the next scripted
    reply."""

    def __init__(self, run):
        self.messages = self
        self.run = run

    def create(self, **request):
        return self.run.create(**request)


class Run:
    """Your loop on one made-up check: every request it sent the model, every lookup, what it
    printed, what it returned, and how it ended."""

    def __init__(self, key, run_agent, loop_file, seconds=TIME_LIMIT):
        self.script, self.max_steps = SCENARIOS[key]
        self.replies = build(self.script, key)
        self.first_answer = next((i for i, spec in enumerate(self.script, 1)
                                  if any(b[0] == "tool_use" and b[1] == "answer"
                                         for b in spec["blocks"])), None)
        self.loop_file = loop_file
        self.requests, self.states, self.lookups, self.lookups_at = [], [], [], []
        self.result = self.error = self.line = None
        self.abandoned = False

        def work():
            CURRENT.run = self
            return run_agent(CLAIM, client=ScriptedModel(self), max_steps=self.max_steps,
                             lookup=self.lookup)
        out = io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(out):
            result, error, alive = in_thread(work, loop_file, seconds)
        self.printed = out.getvalue()
        if alive:
            self.abandoned, self.ended = True, "did not stop"
        elif error is None:
            self.ended, self.result = "returned", result
        else:
            self.error, self.line = error, line_in(error, loop_file)
            self.ended = {AskedTooOften: "asked too often", TooManyLookups: "too many lookups",
                          DidNotStop: "did not stop", NotImplementedError: "not written"}.get(
                              type(error), "error")
            if isinstance(error, DidNotStop):
                self.line = error.line

    def create(self, **request):
        if self.abandoned:
            raise DidNotStop(None)
        self.requests.append(copy_request(request))
        self.lookups_at.append(len(self.lookups))
        self.states.append(loop_variables(self.loop_file))
        if len(self.requests) > len(self.replies):
            raise AskedTooOften()
        return self.replies[len(self.requests) - 1]

    def lookup(self, name, args):
        if self.abandoned:
            raise DidNotStop(None)
        self.lookups.append((name, args))
        if len(self.lookups) > MAX_LOOKUPS:
            raise TooManyLookups()
        return wikipedia(name, args)

    # ----- what happened, in words

    def said(self, n):
        """"the model's second reply asked for a read", for the nth reply."""
        return f"the model's {nth(n)} reply {self.script[n - 1]['says']}"

    def given(self):
        """How many replies the loop was given."""
        return min(len(self.requests), len(self.replies))

    def your_loop(self):
        n = self.given()
        return f"{self.said(n)}, and your loop" if n else "your loop"

    def returned(self):
        """"stopped", or what else ended the run, for a run that returned."""
        if self.result is None:
            return "ended without an answer or a verdict (it returned nothing)"
        return "stopped" if is_finished(self.result) else f"ended with {short(self.result)}"

    def ending(self):
        """How the run ended, for a rule that needed it to go further."""
        if self.ended == "not written" and not self.requests:
            return "the loop is not written yet"
        where = f" at line {self.line} of my_loop.py" if self.line else ""
        if self.ended == "returned":
            if not self.requests:
                return "your loop stopped without asking the model anything"
            return f"{self.your_loop()} {self.returned()} without asking the model again"
        if self.ended == "not written":
            return (f"{self.your_loop()} reached the line that says the loop is not written "
                    f"yet{where}")
        if self.ended == "did not stop":
            line = f" line {self.line} of my_loop.py" if self.line else ""
            return (f"{self.your_loop()} did not stop: it was still running{line} when the check "
                    "stopped it")
        if self.ended == "too many lookups":
            return f"{self.your_loop()} had made more than {MAX_LOOKUPS} lookups"
        if self.ended == "asked too often":
            return f"{self.your_loop()} asked the model again"
        return f"{self.your_loop()} stopped with an error{where}: {described(self.error)}"

    # ----- what the rules look at

    def finished(self):
        """Whether the loop returned what finish() returns."""
        return self.ended == "returned" and is_finished(self.result)

    def request(self, k):
        """The kth request the loop sent the model."""
        if len(self.requests) < k:
            raise NotYet(self, self.ending())
        return self.requests[k - 1]

    def variable(self, k, name):
        """One of run_agent()'s variables when it sent the kth request."""
        self.request(k)
        if name not in self.states[k - 1]:
            raise NotYet(self, NOT_FOUND.format(name=name))
        return self.states[k - 1][name]

    def made_for(self, k):
        """The lookups the loop made between the model's kth reply and its next request."""
        self.request(k + 1)
        return self.lookups[self.lookups_at[k - 1]:self.lookups_at[k]]

    def calls(self, k):
        return [block for block in self.replies[k - 1].content if block.type == "tool_use"]

    def used(self, n):
        """The tokens the model's first n replies used."""
        return {"input": sum(r.usage.input_tokens for r in self.replies[:n]),
                "output": sum(r.usage.output_tokens for r in self.replies[:n])}

    def returned_after(self, k, asked_again, after=""):
        """The result, when the loop returned right after the model's kth reply."""
        if len(self.requests) > k:
            raise NotYet(self, f"{self.said(k)}{after}, and your loop {asked_again}")
        if self.ended != "returned" or len(self.requests) < k:
            raise NotYet(self, self.ending())
        if not is_finished(self.result):
            raise NotYet(self, f"{self.said(k)}, and your loop ended with {short(self.result)}, "
                         "rather than with an answer or with no verdict")
        return self.result

    def expect(self, k, result, verdict, evidence, explanation, name=None, after="",
               where="this case ends with"):
        """The verdict, evidence and explanation the result should hold after the kth reply.
        `where` names what should hold them, in the sentence for one that does not."""
        def shown(field, value):
            if field == "verdict" and value is None:
                return "no verdict"
            return f"the {field} {short(value)}"
        for field, want in (("verdict", verdict), ("evidence", evidence),
                            ("explanation", explanation)):
            if result[field] != want:
                raise NotYet(self, f"{self.said(k)}{after}, and your loop stopped with "
                             f"{shown(field, result[field])}, where {where} "
                             f"{shown(field, want)}")


FINISH_KEYS = set(agent.finish("", None, [], "", [], 0))


def is_finished(result):
    return isinstance(result, dict) and FINISH_KEYS <= set(result)


# ---------- small helpers ----------

ORDINALS = ["first", "second", "third", "fourth", "fifth", "sixth", "seventh", "eighth",
            "ninth", "tenth"]
NUMBERS = ["no", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten"]


def nth(n):
    return ORDINALS[n - 1] if 1 <= n <= len(ORDINALS) else f"{n}th"


def count(n, word=None):
    """"two lookups", "one lookup", or just "two" with no word."""
    number = NUMBERS[n] if 0 <= n < len(NUMBERS) else str(n)
    return number if word is None else f"{number} {word}{'' if n == 1 else 's'}"


def short(value, n=120):
    shown = " ".join(repr(value).split())
    return shown if len(shown) <= n else shown[: n - 3] + "..."


def get(item, key):
    return item.get(key) if isinstance(item, dict) else getattr(item, key, None)


def view(block):
    """The parts of a content block that matter, whether it is the library's object or a dict."""
    kind = get(block, "type")
    if kind == "tool_use":
        return (kind, get(block, "id"), get(block, "name"), get(block, "input"))
    if kind == "text":
        return (kind, get(block, "text"))
    return (kind,)


def same_text(sent, words):
    """Text sent as a string, or as a list holding one text block."""
    return sent == words or (isinstance(sent, (list, tuple)) and len(sent) == 1
                             and view(sent[0]) == ("text", words))


def same_items(a, b):
    """The same items, in any order."""
    rest = list(b)
    for item in a:
        if item not in rest:
            return False
        rest.remove(item)
    return not rest


def after_reply(request):
    """The turns after the last assistant turn in a request: what the loop added after the
    model's latest reply."""
    messages = request.get("messages")
    messages = list(messages) if isinstance(messages, (list, tuple)) else []
    last = max((i for i, turn in enumerate(messages) if get(turn, "role") == "assistant"),
               default=None)
    return messages[last + 1:] if last is not None else messages[-1:]


MISSING = object()


def sent_back(request, call_id):
    """What the loop sent back for one tool call in a request, or MISSING."""
    for turn in after_reply(request):
        content = get(turn, "content")
        for item in content if isinstance(content, list) else []:
            if get(item, "tool_use_id") == call_id:
                return get(item, "content")
    return MISSING


def has_entry(trace, want):
    return isinstance(trace, list) and any(
        isinstance(entry, dict) and all(entry.get(key) == want[key] for key in want)
        for entry in trace)


def answer_entries(trace, call, result):
    """The trace's entries for one answer call with the given result. The entry's input may be
    the call's input or the cleaned answer."""
    return [entry for entry in (trace if isinstance(trace, list) else [])
            if isinstance(entry, dict) and entry.get("tool") == "answer"
            and entry.get("result") == result
            and entry.get("input") in (call.input, agent.clean_answer(call.input))]


# ---------- the five rules ----------

def rule_1(runs):
    """Ask the model. Every request in every made-up check is looked at, as the real API
    would look at it."""
    system = agent.INSTRUCTIONS.read_text()
    run = runs["ask"]
    if not run.requests:
        raise NotYet(run, run.ending())
    for other in runs.values():     # "ask" first
        for k, request in enumerate(other.requests[:len(other.replies) + 1], 1):
            request_problem(other, k, request, system)
        if other is run:
            run.request(run.first_answer)


def reports_count(runs):
    """Whether the loop passes finish() a token count (extra credit, step 3b) in any made-up
    check. Only then is there a token line."""
    return any(run.finished() and run.result.get("tokens") is not None for run in runs.values())


def token_rule(runs):
    """Count the tokens, for a loop that passes finish() a count: in every made-up check, the
    count is what the model's replies used. (Only a loop that returns a result has a count to
    look at, so there is no look inside run_agent() for the tokens, as rule 5 has.)"""
    for other in runs.values():
        if other.finished():
            n = len(other.requests)
            if other.result.get("tokens") != other.used(n):
                used = other.used(n)
                replies = "its reply" if n == 1 else f"its {count(n)} replies"
                raise NotYet(other, f"{other.said(n)}, and your loop stopped with tokens "
                             f"{short(other.result.get('tokens'))}, where {replies} used "
                             f"{used['input']:,} input and {used['output']:,} output tokens")


def request_problem(run, k, request, system):
    """What the kth request of a made-up check has wrong for rule 1, if anything."""
    sent = ("the first request your loop sent the model" if k == 1 else
            f"{run.said(k - 1)}, and the next request your loop sent")
    if request.get("model") != agent.MODEL:
        raise NotYet(run, f"{sent} named the model {short(request.get('model'))}, not "
                     f"{agent.MODEL!r}")
    if request.get("max_tokens") != 16000:
        raise NotYet(run, f"{sent} let a reply be at most {short(request.get('max_tokens'))} "
                     "tokens long, where the agent allows 16000")
    if not same_text(request.get("system"), system):
        raise NotYet(run, f"{sent} did not have the text of instructions.md as its system text")
    if request.get("tools") != agent.TOOLS:
        raise NotYet(run, f"{sent} did not offer the model the four tools")
    messages = request.get("messages")
    if k == 1:
        if messages != [{"role": "user", "content": f"Claim: {CLAIM}"}]:
            raise NotYet(run, f"{sent} did not hold the conversation the set-up lines make, just "
                         "the claim")
        return
    before = run.requests[k - 2].get("messages")
    if not isinstance(messages, list) or messages[:len(before)] != before:
        raise NotYet(run, f"{sent} did not hold the whole conversation so far")
    turn = messages[len(before)] if len(messages) > len(before) else None
    content = get(turn, "content") if turn is not None else None
    if get(turn, "role") != "assistant":
        raise NotYet(run, f"{sent} did not have that reply in the conversation")
    if (not isinstance(content, (list, tuple))
            or [view(b) for b in content] != [view(b) for b in run.replies[k - 2].content]):
        raise NotYet(run, f"{sent} had that reply in the conversation with parts of it missing "
                     "or changed")
    added = [t for t in messages[len(before):] if get(t, "role") == "assistant"]
    if len(added) > 1:
        raise NotYet(run, f"{sent} had that reply in the conversation {count(len(added))} times")
    # After a reply that asked for nothing. (After one that asked for something, rule 2 says which
    # result is missing.)
    for later in messages[len(before) + 1:] if not run.calls(k - 1) else []:
        said = get(later, "content")
        if said is None or (isinstance(said, (str, list, tuple)) and len(said) == 0):
            raise NotYet(run, f"{sent} had a turn with nothing in it after that reply, which the "
                         "Claude API refuses")


def rule_2(runs):
    """Make its lookups. In the made-up check for this rule, every lookup a reply asks for is
    made, in any order, before the model is asked again, and in the next one the results are what
    the lookups found; in every made-up check, every tool call has its result in the next turn,
    as the real API requires."""
    run = runs["lookups"]
    for k in range(1, run.first_answer):
        left = list(run.made_for(k))
        made = len(left)
        for call in run.calls(k):
            if (call.name, call.input) in left:
                left.remove((call.name, call.input))
            elif left:
                name, args = left[0]
                raise NotYet(run, f"{run.said(k)}, and your loop made a {lookup_name(name)} with "
                             f"{short(args)}, where the model asked for a "
                             f"{lookup_name(call.name)} with {short(call.input)}")
            else:
                done = [lookup_name(name) for name, _ in run.made_for(k)]
                if done:
                    raise NotYet(run, f"{run.said(k)}, and your loop made the "
                                 f"{' and the '.join(done)} only, then asked the model again "
                                 f"without making the {lookup_name(call.name)}")
                raise NotYet(run, f"{run.said(k)}, and your loop asked the model again without "
                             f"making the {lookup_name(call.name)}")
        if left:
            raise NotYet(run, f"{run.said(k)}, and your loop made {count(made, 'lookup')} for it "
                         "before asking the model again")
    run = runs["results"]
    for k in range(1, run.first_answer):
        results_problem(run, k, run.request(k + 1), exact=True)
    for other in runs.values():
        for k in range(1, min(len(other.requests), len(other.replies) + 1)):
            if other.calls(k):
                results_problem(other, k, other.requests[k])


def lookup_name(name):
    """"search", "read" or "wikidata lookup", as the sentences name a lookup."""
    return "wikidata lookup" if name == "wikidata" else name


def results_problem(run, k, request, exact=False):
    """What is wrong with the turn the loop added after the model's kth reply, if anything."""
    said = f"{run.said(k)}, and"
    tail = after_reply(request)
    if not tail:
        raise NotYet(run, f"{said} the next request your loop sent ended with that reply: the "
                     "results for it had not been sent")
    if len(tail) > 1:
        raise NotYet(run, f"{said} your loop sent the results for that reply in "
                     f"{count(len(tail))} separate turns, where the model is sent them all "
                     "together, once every call in the reply has its result")
    if get(tail[0], "role") != "user":
        raise NotYet(run, f"{said} in the next request your loop sent, the turn after that reply "
                     "was not a turn of results")
    content = get(tail[0], "content")
    if not isinstance(content, list):
        raise NotYet(run, f"{said} in the next request your loop sent, the turn after that reply "
                     f"held {short(content)} rather than the results")
    for call in run.calls(k):
        matching = [item for item in content if get(item, "tool_use_id") == call.id]
        if not matching:
            raise NotYet(run, f"{said} the next request your loop sent held no result for the "
                         f"{lookup_name(call.name)}")
        if len(matching) > 1:
            raise NotYet(run, f"{said} the next request your loop sent held "
                         f"{count(len(matching))} results for the {lookup_name(call.name)}")
        if get(matching[0], "type") != "tool_result":
            raise NotYet(run, f"{said} the result for the {lookup_name(call.name)} was not in "
                         "the form of a result")
        sent = get(matching[0], "content")
        if not isinstance(sent, str):
            kind = type(sent).__name__
            kind = "nothing" if sent is None else f"{'an' if kind[0] in 'aeiou' else 'a'} {kind}"
            raise NotYet(run, f"{said} the result given for the {lookup_name(call.name)} was "
                         f"{kind} rather than text")
        if exact and sent != wikipedia(call.name, call.input):
            raise NotYet(run, f"{said} the result given for the {lookup_name(call.name)} was "
                         f"{short(sent)} rather than what that lookup found")
    ids = {call.id for call in run.calls(k)}
    for item in content:
        if get(item, "type") == "tool_result" and get(item, "tool_use_id") not in ids:
            raise NotYet(run, f"{said} the next request your loop sent held a result for a call "
                         "that reply did not make, as well as its own")


def rule_3(runs):
    """Stop with the answer. An answer is not run as a lookup, and the run ends with it; after a
    reply that asks for nothing, it ends with the answer that follows the reminder. For an answer
    that quotes what the agent never read, a loop may instead send it back (a loop that checks
    quotes) and stop with the next answer, or give up with no verdict once it has sent back as
    many as MAX_REJECTED allows. A loop that stops with an error in any of these does not pass."""
    def stopped_with(run, k, verdict, evidence, explanation, after=""):
        call = next(c for c in run.calls(k) if c.name == "answer")
        if any(name == "answer" for name, _ in run.lookups):
            raise NotYet(run, f"{run.said(k)}{after}, and your loop ran the answer as a lookup")
        result = run.returned_after(k, "asked the model again instead of stopping", after)
        run.expect(k, result, verdict, evidence, explanation, after=after)
        if not answer_entries(result["trace"], call, agent.ACCEPTED):
            raise NotYet(run, f"{run.said(k)}{after}, and the trace your loop stopped with does "
                         "not record that answer as accepted")

    director = ["directed by Robert Zemeckis"]
    stopped_with(runs["accept"], 2, "supported", director, "The page names him as the director.")
    stopped_with(runs["clean"], 2, "supported", ["He was born in Chicago, Illinois."], "")
    stopped_with(runs["both"], 2, "supported", director, "The page names him as the director.")

    # A reply that asks for nothing: the parts remind the model, and the loop stops with the answer
    # that follows. A loop that stops at once with no verdict passes too.
    run = runs["nothing"]
    if not (len(run.requests) == 1 and run.finished() and run.result["verdict"] is None):
        stopped_with(run, 2, "doesn't say", [], NOT_SAID_WHY,
                     after=" after one that had text and no tool call")

    run = runs["unread"]
    if any(name == "answer" for name, _ in run.lookups):
        raise NotYet(run, f"{run.said(2)}, and your loop ran the answer as a lookup")
    gave_up = agent.REJECTED_TOO_OFTEN.split("{n}")[0]
    if len(run.requests) <= 2:
        if (run.finished() and run.result["verdict"] is None
                and str(run.result["explanation"]).startswith(gave_up)):
            return      # a loop that checks quotes, with MAX_REJECTED set to 1
        stopped_with(run, 2, "supported", ["Zemeckis was born in Ohio."], "He was born in Ohio.")
    else:               # a loop that checks quotes sent it back
        stopped_with(run, 3, "doesn't say", [], NOT_SAID_WHY,
                     after=" after your loop had sent the answer before it back")


def ran(run, k):
    """"2 lookups": how many lookups the loop had made before it handled the model's kth reply,
    as the made-up Wikipedia saw them."""
    n = sum(name in LOOKUPS for name, _ in run.lookups[:run.lookups_at[k - 1]])
    return f"{n} lookup{'' if n == 1 else 's'}"


def made_after(run, k):
    """The lookups the loop made after the model's kth reply: up to its next request, or to the
    end of the run if there was none."""
    end = run.lookups_at[k] if len(run.lookups_at) > k else len(run.lookups)
    return [(name, args) for name, args in run.lookups[run.lookups_at[k - 1]:end]
            if name in LOOKUPS]


def made_up_to_the_limit(run, m):
    """In a made-up check whose first m replies each ask for one search, each search is made:
    the limit leaves room for all of them."""
    for k in range(1, m + 1):
        run.request(k)
        if len(run.requests) == k and run.ended == "returned":
            if made_after(run, k):
                raise NotYet(run, f"{run.said(k)}, and your loop made it and then "
                             f"{run.returned()} without asking the model again, though the model "
                             f"had not asked for more than the limit of {m} lookups")
            raise NotYet(run, f"{run.said(k)}, and your loop {run.returned()} instead of making "
                         f"it, though it had made only {ran(run, k)} and the limit is {m}")
        if not made_after(run, k):
            back = sent_back(run.request(k + 1), run.calls(k)[0].id)
            back = "nothing" if back is MISSING else short(back)
            raise NotYet(run, f"{run.said(k)}, and your loop sent back {back} instead of making "
                         f"it, though it had made only {ran(run, k)} and the limit is {m}")


def rule_4(runs):
    """Stop at the limit. Each sentence gives the numbers that tell what the loop did: how many
    lookups it had made (as the made-up Wikipedia saw them) and max_steps. What is required: a
    reply that asks for one lookup below the limit has it made, and after the lookup that reaches
    the limit the model is asked once more; an answer then ends the run with that answer. A reply
    that asks for more lookups after the limit was reached ends the run with no verdict, at once
    or a little later: the loop may make the lookups of one such reply, and may warn the model
    once (send back something other than a lookup's result and ask again), in either order, but
    no more than that. What the loop does with a reply that asks for more lookups than are left is
    free: it may make all of them, some or none, and then stop there with no verdict, or give each
    call a result and ask the model again, and then stop with the answer that follows."""
    run = runs["limit_answer"]
    m = run.max_steps
    made_up_to_the_limit(run, m)
    after = f", when your loop had made {ran(run, m + 1)}, the limit"
    result = run.returned_after(m + 1, "asked the model again instead of stopping", after)
    run.expect(m + 1, result, "doesn't say", [], NOT_SAID_WHY, after=after)

    # Every reply asks for one search. From the first reply that comes with the limit reached, the
    # loop may make the lookups of one reply, and may send back something other than a lookup's
    # result (a warning) for one reply and ask again, in either order; then it stops with no verdict.
    run = runs["limit_again"]
    m = run.max_steps
    made_up_to_the_limit(run, m)
    k, made_at, warned_at = m + 1, None, None
    while True:
        run.request(k)
        if made_after(run, k):
            if made_at is not None:
                raise NotYet(run, f"{run.said(k)}, and your loop made it, though it had already "
                             f"made the {asked(run, made_at)} after the limit of {m} lookups was "
                             f"reached: it had made {ran(run, k)} before this one")
            made_at = k
        if len(run.requests) == k:      # it did not ask the model again: it stops here
            break
        if made_at != k:                # it asked again without making this reply's lookup
            if warned_at is not None:
                raise NotYet(run, f"{run.said(k)}, and your loop sent back a result for it "
                             "without making it and asked the model again, as it had already "
                             f"done for the {asked(run, warned_at)}: it had made {ran(run, k)}, "
                             f"and the limit is {m}")
            warned_at = k
        k += 1
    after = past_the_limit(run, m, k, made_at, warned_at)
    result = run.returned_after(k, "asked the model again instead of stopping", after)
    run.expect(k, result, None, [], agent.RAN_OUT, after=after)

    # A reply that asks for more lookups than are left: the loop may make all of them, some or
    # none. If it asks the model again, it stops with the answer that follows; if it does not, it
    # stops there with no verdict.
    run = runs["limit_cross"]
    m = run.max_steps
    run.made_for(1)
    if len(run.requests) > 2:
        result = run.returned_after(3, "asked the model again instead of stopping")
        run.expect(3, result, "doesn't say", [], NOT_SAID_WHY)
        return
    after = f", when your loop had made {ran(run, 2)} and the limit is {m}"
    result = run.returned_after(2, "asked the model again instead of stopping", after)
    run.expect(2, result, None, [], agent.RAN_OUT, after=after, where="a stop at the limit has")


def asked(run, k):
    """"third search": the lookup the model's kth reply asked for, in a made-up check whose
    replies each ask for one."""
    calls = run.calls(k)
    return f"{nth(k)} {lookup_name(calls[0].name) if calls else 'lookup'}"


def past_the_limit(run, m, k, made_at, warned_at):
    """What the loop did with the replies before the kth that came with the limit of m reached,
    for the sentence about how it stopped at the kth."""
    done = sorted((j, what) for j, what in ((made_at, "made"), (warned_at, "warned"))
                  if j is not None and j < k)
    if not done:
        return f" with the limit of {m} lookups reached"
    parts = []
    for i, (j, what) in enumerate(done):
        if what == "warned":
            parts.append(f"sent back a result for the {asked(run, j)} without making it")
        else:
            parts.append(f"made the {asked(run, j)}"
                         + (f" with the limit of {m} lookups reached" if i == 0 else ""))
    return " after your loop had " + ", and ".join(parts)


def trace_problem(run, trace, asked, the_trace, when=""):
    """Every lookup asked for has its entry in the trace, in any order."""
    trace = trace if isinstance(trace, list) else []
    entries = [e for e in trace if isinstance(e, dict) and e.get("tool") in LOOKUPS]
    left = list(entries)
    for j, name, args in asked:
        want = {"tool": name, "input": args, "result": wikipedia(name, args)}
        match = next((e for e in left if has_entry([e], want)), None)
        if match is not None:
            left.remove(match)
            continue
        same_tool = [e for e in left if e.get("tool") == name]
        if same_tool:
            raise NotYet(run, f"{run.said(j)}, and the entry for the {name} in {the_trace} did "
                         f"not record that {name} and what it found{when}")
        other = [e for e in trace if not (isinstance(e, dict) and e.get("tool") in
                                          LOOKUPS + ("answer", "(reminder)", "(refusal)"))]
        if other:
            raise NotYet(run, f"{run.said(j)}, and {the_trace} held {short(other[0])}, which "
                         f"does not record a lookup and what it found{when}")
        raise NotYet(run, f"{run.said(j)}, and {the_trace} had no entry for the {name}{when}")
    if left:
        raise NotYet(run, f"{the_trace} had entries for {count(len(entries), 'lookup')}{when}, "
                     f"where your loop had made {count(len(asked))}")


def rule_5(runs):
    """Count the lookups. In the made-up check for this rule, the count and the trace are looked
    at when the loop stops, or, for a loop that does not stop yet, inside run_agent() each time it
    asks the model again; in every made-up check, the count it stops with is the number of lookups
    it made."""
    run = runs["lookups"]
    asked = [(k, call.name, call.input) for k in range(1, run.first_answer) for call in run.calls(k)]
    if run.finished():          # what the loop returned shows steps and the trace
        if run.result["steps"] != len(asked):
            raise NotYet(run, f"the model asked for {count(len(asked), 'lookup')} before its "
                         "answer, and when your loop stopped its count of lookups was "
                         f"{short(run.result['steps'])}")
        trace_problem(run, run.result["trace"], asked, "the trace your loop stopped with")
    else:                       # a loop that does not stop yet: look inside it
        for k in range(1, run.first_answer):
            so_far = [lookup for lookup in asked if lookup[0] <= k]
            steps = run.variable(k + 1, "steps")
            if steps != len(so_far):
                raise NotYet(run, f"after the model's {nth(k)} reply, your loop had made "
                             f"{count(len(so_far), 'lookup')}, and its count of lookups was "
                             f"{short(steps)} when it asked the model again")
            trace_problem(run, run.variable(k + 1, "trace"), so_far,
                          "the trace", " when your loop asked the model again")
    for other in runs.values():
        if other.finished():
            made = sum(name in LOOKUPS for name, _ in other.lookups)
            if other.result["steps"] != made:
                n = len(other.requests)
                raise NotYet(other, f"{other.said(n)}, and when your loop stopped its count of "
                             f"lookups was {short(other.result['steps'])}, where it had made "
                             f"{count(made, 'lookup')}")


# ---------- putting it together ----------

@contextlib.contextmanager
def offline():
    """No key and no network while the check runs, whatever the loop does."""
    keys = {name: os.environ.pop(name) for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN")
            if name in os.environ}
    real = {name: getattr(wiki, name) for name in LOOKUPS}

    def no_network(*args, **kwargs):
        raise RuntimeError("this check has no network, and Wikipedia was called directly")
    for name in LOOKUPS:
        setattr(wiki, name, no_network)
    try:
        yield
    finally:
        os.environ.update(keys)
        for name, function in real.items():
            setattr(wiki, name, function)


def load(path):
    """my_loop.py as a module, loaded fresh from its file."""
    spec = importlib.util.spec_from_file_location("my_loop", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def check(path=None):
    """One entry per rule, and one for the tokens if the loop counts them: None if it passes, or
    the sentence saying what happened."""
    return [problem for problem, _ in examine(path)]


def examine(path=None):
    """One (sentence, printed) pair per rule. The sentence is None if the rule passes; printed
    is what the loop printed during the made-up check the sentence is about."""
    path = Path(path or MY_LOOP).resolve()
    loop_file = str(path)
    hidden = io.StringIO()      # what my_loop.py prints while it loads is not shown
    with offline(), contextlib.redirect_stdout(hidden), contextlib.redirect_stderr(hidden):
        module, error, alive = in_thread(lambda: load(loop_file), loop_file)
        if alive or isinstance(error, DidNotStop):
            return [(f"my_loop.py did not finish loading: after {TIME_LIMIT} seconds it was "
                     "still running", "")] * len(RULES)
        if error is not None:
            line = line_in(error, loop_file)
            where = f" at line {line}" if line else ""
            return [(f"my_loop.py could not be loaded, because of an error{where}: "
                     f"{described(error)}", "")] * len(RULES)
        run_agent = getattr(module, "run_agent", None)
        if not callable(run_agent):
            return [("my_loop.py has no function called run_agent", "")] * len(RULES)
        runs, seconds = {}, TIME_LIMIT
        for key in SCENARIOS:
            runs[key] = Run(key, run_agent, loop_file, seconds)
            if runs[key].ended == "did not stop":
                seconds = AFTER_A_HANG   # so a loop that never stops is not waited for 11 times
    found = []
    rules = [rule_1, rule_2, rule_3, rule_4, rule_5]
    if reports_count(runs):
        rules.append(token_rule)
    for rule in rules:
        try:
            rule(runs)
            found.append((None, ""))
        except NotYet as not_yet:
            found.append((str(not_yet), not_yet.run.printed))
        except Exception as error:  # noqa: BLE001  something the loop made that cannot be read
            found.append((f"the check could not read what your loop did ({described(error)})",
                          ""))
    return found


def cut(output):
    """What the loop printed, at most SHOWN_LINES lines of it."""
    shown = output.rstrip("\n").splitlines()
    if len(shown) <= SHOWN_LINES:
        return "\n".join(shown)
    more = len(shown) - SHOWN_LINES
    note = f"({more} more line{'' if more == 1 else 's'} not shown)"
    return "\n".join(shown[:SHOWN_LINES] + [note])


def lines(problems):
    """The lines the check prints: one per rule, and the token line for a loop that counts."""
    titles = [f"{number}. {title}" for number, title in enumerate(RULES, 1)] + [agent.TOKEN_RULE]
    shown = []
    for title, problem in zip(titles, problems):
        if problem is None:
            shown.append(f"ok         {title}")
        else:
            shown.append(f"NOT YET    {title}: {problem}"
                         f"{'' if problem.endswith('.') else '.'}")
    return shown


def main(argv=None):
    parser = argparse.ArgumentParser(description="Check the loop in my_loop.py.")
    parser.parse_args(argv)
    saved = agent.LOOP_CHECK

    found = examine(MY_LOOP)
    problems = [problem for problem, _ in found]
    printed = lines(problems)
    print("\n".join(printed))
    if all(problem is None for problem in problems):
        print(f"\n{PASSED}")
        # The agent runs on my_loop.py once this file's first line is "yours".
        saved.parent.mkdir(parents=True, exist_ok=True)
        saved.write_text("yours\n" + "\n".join(printed) + f"\n\n{PASSED}\n")
        return 0
    number = next(n for n, problem in enumerate(problems, 1) if problem)
    if number <= len(RULES):
        print(f"\nThe rule ({number}. {RULES[number - 1]}): {rule_text(number)}")
    print(f"\n{FAILED}")
    if agent.which_loop() == "yours":
        # No agent run until the check passes again. The file stays, so step 1a stays done.
        saved.write_text(f"not passing\n{FELL_BACK}\n" + "\n".join(printed) + "\n")
        print(NOT_PASSING_NOW)
    # What the loop printed during the made-up check behind the first NOT YET line. It is
    # shown to help find the problem, and never saved.
    number, output = next((n, out) for n, (problem, out) in enumerate(found, 1) if problem)
    if output.strip():
        which = f"rule {number}" if number <= len(RULES) else "the token count"
        print(f"\nWhat your loop printed during the made-up check for {which}:")
        print(cut(output))
    return 1


if __name__ == "__main__":
    sys.exit(main())
