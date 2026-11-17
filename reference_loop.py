"""The reference loop. The homework uses it in Part 0, before your own loop, in
my_loop.py, has passed the check (uv run python check_loop.py), and not after.
It is built from the same parts as yours, in loop_parts.py.

Do not open this file before step 1a is done: reading it first gives the
exercise away. After that, compare it with yours (the write-up asks you to).
"""

import anthropic

from agent import INSTRUCTIONS, MAX_STEPS, RAN_OUT, run_tool
from loop_parts import Conversation


def run_agent(claim, client=None, max_steps=MAX_STEPS, lookup=run_tool):
    """Check one claim. Returns what talk.accept() or talk.stop() returns."""
    client = client or anthropic.Anthropic()
    system = INSTRUCTIONS.read_text()
    messages = [{"role": "user", "content": f"Claim: {claim}"}]
    trace, read_so_far = [], []
    talk = Conversation(claim, client, system, messages, trace, read_so_far, lookup)
    steps = 0           # lookups made so far

    while True:
        reply = talk.ask()
        if reply.answer:
            return talk.accept(reply.answer, steps)
        if steps >= max_steps:
            return talk.stop(RAN_OUT, steps)
        for call in reply.lookups:
            talk.give(call, talk.run(call))
            steps += 1
        talk.send_results()
