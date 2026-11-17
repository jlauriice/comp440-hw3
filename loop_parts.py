"""The parts your loop is built from, in step 1a.

Each part does one mechanical job: the exact call to the Claude API, the shape
of what is sent back for a tool call, the trace entries (every lookup, every
answer, every reminder), what finish() is given.
Your loop in my_loop.py decides when each part is used, and in what order. That
order, and what the loop counts and remembers, is the agent's logic, and it is
what you write.

    talk = Conversation(claim, client, system, messages, trace, read_so_far, lookup)
    reply = talk.ask()            # the model's next step
    reply.answer                  # the answer it gave, or None if it gave none
    reply.lookups                 # the lookups it asked for (empty if none)
    reply.calls                   # every tool call in the reply, lookups and answer alike
    reply.usage                   # the tokens it used: .input_tokens, .output_tokens
    call.is_answer, call.is_lookup, call.name
    talk.run(call)                # make a lookup; returns what it found
    talk.give(call, result)       # the result the model will be sent for this call
    talk.send_results()           # send the model every result given since its last reply
    talk.accept(call, steps)      # what the loop returns for an answer
    talk.stop(why, steps)         # what the loop returns with no verdict
                                  # (both take a token count last, once the loop keeps one: 3b)

ask() always gives back a next step. If a reply asks for nothing, ask() sends
the model a reminder to answer and asks once more. If the model still asks for
nothing, or if it refuses to check the claim, ask() gives back an answer with
no verdict, which talk.accept() turns into a stop with no verdict. The trace
records the reminder and the refusal.

ask() also stops a loop that does not stop by itself. Once it has called the
model 3 * MAX_STEPS + 10 times for one claim (46, with the limit of 12 lookups),
it calls the model no more and gives back an answer with no verdict, and the
trace records why. An answer sent back is not a lookup, so a loop that sends
answers back needs a stop of its own.

For a loop that does more than this (a change in step 3b, for example):

    talk.problem_with(call)       # check an answer's quotes: None if each one is in
                                  # something the agent read, or else what to send back
    talk.remind()                 # send the model the reminder to answer
    reply.refused                 # True if the model refused to check the claim
"""

from types import SimpleNamespace

import agent
from agent import (ACCEPTED, DECLINED, MODEL, NO_ANSWER, REJECTED, REMINDED, REMINDER, TOO_MANY_ASKS,
                   TOOLS, clean_answer, finish)


class Call:
    """One tool call in a reply. Every call that is not an answer is a lookup."""

    def __init__(self, block):
        self.name = block.name          # "search", "read", "wikidata" or "answer"
        self.input = block.input        # what the model gave the tool, as a dictionary
        self.id = block.id              # marks the result that answers this call
        self.is_answer = block.name == "answer"
        self.is_lookup = not self.is_answer
        # Set only on the answer ask() gives back for a model that refused or would not take a
        # step, or once the model has been asked too often: why there is no verdict (DECLINED,
        # NO_ANSWER or TOO_MANY_ASKS in agent.py).
        self.why = None


def no_verdict(why):
    """The answer with no verdict that ask() gives back, with why there is none."""
    call = Call(SimpleNamespace(name="answer", input={}, id=None))
    call.why = why
    return call


class Reply:
    """One reply from the model: its next step."""

    def __init__(self, response, usage=None, why=None):
        self.refused = response.stop_reason == "refusal"
        self.calls = [Call(block) for block in response.content if block.type == "tool_use"]
        if why is not None:             # a refusal, or nothing asked for twice running
            self.calls = [no_verdict(why)]
        self.lookups = [call for call in self.calls if call.is_lookup]
        self.answer = next((call for call in self.calls if call.is_answer), None)
        # The tokens this reply used, as the Claude API reports them: .usage.input_tokens and
        # .usage.output_tokens (both of ask()'s calls to the model, when it asked twice). Nothing
        # here counts them: that is step 3b's first task.
        self.usage = usage or response.usage


def asks_for_nothing(response):
    return not any(block.type == "tool_use" for block in response.content)


class Conversation:
    """One check of one claim: the conversation with the model, the lookups, and the trace."""

    def __init__(self, claim, client, system, messages, trace, read_so_far, lookup):
        self.claim, self.client, self.system, self.lookup = claim, client, system, lookup
        self.messages, self.trace, self.read_so_far = messages, trace, read_so_far
        self.results = []               # results given since the model's last reply, not sent yet
        self.asked = 0                  # calls to the model for this claim so far
        # The most calls to the model for one claim, read now so that a change to MAX_STEPS moves it.
        self.most_asks = 3 * agent.MAX_STEPS + 10
        self.stopped = False            # has ask() given back the answer for too many calls?

    def call_model(self):
        """Send the model the system text, the tools and the whole conversation so far. Add its
        reply to the conversation, and return the reply as the Claude API gives it."""
        self.asked += 1
        response = self.client.messages.create(model=MODEL, max_tokens=16000, system=self.system,
                                               tools=TOOLS, messages=self.messages)
        self.messages.append({"role": "assistant", "content": response.content})
        return response

    def ask(self):
        """Ask the model for its next step, sending it the whole conversation so far, and return
        its reply. A reply that asks for nothing gets the reminder to answer and one more ask; a
        reply that still asks for nothing, or a refusal, comes back as an answer with no verdict, and
        so does every ask once the model has been called self.most_asks times for this claim."""
        if self.asked >= self.most_asks:
            return self.too_many()
        reminded = bool(self.messages) and self.messages[-1] == {"role": "user", "content": REMINDER}
        response = self.call_model()
        usage = response.usage
        if response.stop_reason != "refusal" and asks_for_nothing(response) and not reminded:
            if self.asked >= self.most_asks:
                return self.too_many(usage)
            self.remind()
            again = self.call_model()
            usage = SimpleNamespace(input_tokens=usage.input_tokens + again.usage.input_tokens,
                                    output_tokens=usage.output_tokens + again.usage.output_tokens)
            response = again
        if response.stop_reason == "refusal":
            self.trace.append({"tool": "(refusal)", "input": {}, "result": DECLINED})
            return Reply(response, usage, why=DECLINED)
        if asks_for_nothing(response):
            return Reply(response, usage, why=NO_ANSWER)
        return Reply(response, usage)

    def too_many(self, usage=None):
        """ask()'s answer with no verdict once the model has been called as often as it may be for
        one claim, recorded in the trace. A loop that asks again after this answer stops with an
        error, so that no loop can go on for ever."""
        why = TOO_MANY_ASKS.format(n=self.asked)
        if self.stopped:
            raise RuntimeError(why + " The loop asked again after that.")
        self.stopped = True
        self.trace.append({"tool": "(stopped)", "input": {}, "result": why})
        nothing = SimpleNamespace(stop_reason=None, content=[],
                                  usage=usage or SimpleNamespace(input_tokens=0, output_tokens=0))
        return Reply(nothing, why=why)

    def run(self, call):
        """Make one lookup and return what it found. What read and wikidata find counts as read
        by the agent, so a check of the quotes can find them in it; what search finds does not."""
        found = self.lookup(call.name, call.input)
        if call.name != "search":
            self.read_so_far.append(found)
        return found

    def problem_with(self, call):
        """A check of an answer's quotes, which the agent does only if its loop asks for it: None
        if every quote is in something the agent read, or else the sentence to send back about its
        problem, which starts "Answer rejected.". An answer with a problem is recorded in the trace
        here, when it is checked, so the trace is complete even if the loop stops before it gives
        the answer its result. (An answer that passes is recorded by accept().)"""
        if call.why is not None:        # ask()'s answer with no verdict: nothing to check
            return None
        problem = agent.answer_problem(clean_answer(call.input), self.read_so_far)
        if problem is None:
            return None
        self.trace.append({"tool": call.name, "input": call.input, "result": REJECTED + problem})
        return REJECTED + problem

    def give(self, call, result):
        """Set the result the model will be sent for this call. A lookup's result is recorded in
        the trace here; an answer's is recorded when it is checked or accepted."""
        if not call.is_answer:
            self.trace.append({"tool": call.name, "input": call.input, "result": result})
        self.results.append({"type": "tool_result", "tool_use_id": call.id, "content": result})

    def send_results(self):
        """Add one turn to the conversation that holds every result given since the model's last
        reply. The model sees them when it is next asked."""
        self.messages.append({"role": "user", "content": self.results})
        self.results = []

    def remind(self):
        """Add the reminder to answer to the conversation, and record it in the trace."""
        self.trace.append({"tool": "(reminder)", "input": {}, "result": REMINDED})
        self.messages.append({"role": "user", "content": REMINDER})

    def accept(self, call, steps, tokens=None):
        """Return what finish() returns for an answer, and record it in the trace as accepted. For
        ask()'s answer with no verdict, return what stop() returns. A loop that counts tokens (step
        3b) passes its count last, as {"input": ..., "output": ...}."""
        if call.why is not None:
            return self.stop(call.why, steps, tokens)
        answer = clean_answer(call.input)
        self.trace.append({"tool": "answer", "input": call.input, "result": ACCEPTED})
        return finish(self.claim, answer["verdict"], answer["evidence"], answer["explanation"],
                      self.trace, steps, tokens)

    def stop(self, why, steps, tokens=None):
        """Return what finish() returns with no verdict. why is one of the ready-made sentences
        in agent.py: RAN_OUT, or, for a loop that does more, NO_ANSWER, DECLINED or
        REJECTED_TOO_OFTEN.format(n=rejected). A loop that counts tokens (step 3b) passes its
        count last."""
        return finish(self.claim, None, [], why, self.trace, steps, tokens)
