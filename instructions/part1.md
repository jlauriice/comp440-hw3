# COMP 440 HW3 Part 1: How the agent works

In this part you build and study the agent. You design its loop, check one claim yourself, watch it work
on your 12 development claims, write its instructions, and then start the full run on your 100
evaluation claims. It should take a little under 3 hours.

Back to the [assignment page](../README.md).

## 1a. Design the loop

In this step you design the agent's loop. You write an outline of its logic in plain words, and Claude
translates your outline into Python. The loop asks the model for lookups, runs the lookups it chooses,
sends back what they return, and stops.

**Words in this step:** A *tool* is one of the four things the agent can call: `search`, `read`,
`wikidata` and `answer`. A *lookup* is a call to one of the first three. A *reply* is what the model sends
back each time it is asked. A *result* is what the loop sends the model for one tool call. *The check*,
`check_loop.py`, runs your loop in eleven made-up cases, with a stand-in for the model and for
Wikipedia, at no cost. *The reference loop*, `reference_loop.py`, is a loop I wrote that the agent uses
only in Part 0; do not open it before your loop passes the check.

**Actions:**

1. Read the Background. It does not say how to arrange the loop: that is your job.
2. In your editor, write your outline in the block under 1a in `WRITEUP.md`.
3. Ask Claude to translate your outline into `my_loop.py`. Claude adds nothing of its own.
4. Ask Claude to run the check. For the first `NOT YET` line, work out what your outline does in that
   made-up case; Claude coaches you. Then change your outline, not the Python.
5. When every rule passes, open `reference_loop.py` in your editor and compare it with your loop.
6. Type your answers to the two other questions in `WRITEUP.md`, in your editor, under 1a.

**Background:** The model cannot look anything up by itself, and it remembers nothing between calls:
each time it is asked, it sees only what it is sent. All it can do is reply. A reply can ask for one or
more lookups (`search`, `read`, `wikidata`), or give an `answer`. If it does neither, the parts in
`loop_parts.py` remind the model to answer, so your loop does not have to.

Your loop should repeatedly call the model with the message history so far, and ask for its next step.
It should check whether the model has given an answer yet. If not, it should make the lookups that step
asks for, and add what they return to the history. It should also pay attention to whether the loop has
reached its limit: a claim that runs out of lookups cannot be decided.

One limit is set for you: 12 lookups for a claim.

You will not know every detail of the rules when you start. The check runs your loop in made-up cases,
and when your design breaks a rule, the check states that rule. Meeting the rules this way is how this
step is meant to go.

**Writing your outline:**

- Write what the loop does, in order, one thing on each line. Indent what happens inside a repeat or an
  if.
- Say what the loop remembers from one turn to the next, and where each thing it remembers is set and
  changed.
- Say every way the loop stops, and what it stops with: an answer, or no verdict.
- Write in plain words. Claude translates each line into one or two lines of Python, with the parts in
  `loop_parts.py`, which do the mechanical work.
- For example, this is an outline of grading a stack of quizzes, to show the style:

  ```
  Remember: the total of the scores (none yet), and how many quizzes have been graded (none yet).
  For each quiz in the stack:
      If it has no name on it: put it aside, and go on to the next quiz.
      Score its answers, add the score to the total, and count the quiz.
  When the stack is done: say the average score (the total divided by the count), and stop.
  ```

**Interpreting output:** Claude runs this command, or you run it yourself:

```
uv run python check_loop.py
```

It prints `ok` or `NOT YET` for each of five rules, and under them, after "The rule", it states the rule
behind the first `NOT YET` line. A `NOT YET` line says what the stand-in model did and what your loop
did, as in this run partway through:

```
ok         1. Ask the model
ok         2. Make its lookups
NOT YET    3. Stop with the answer: the model's second reply gave an answer that quotes the page it had read, and your loop ran the answer as a lookup.
```

When every rule passes, the check saves `runs/part1/loop-check.txt`, and from then on your copy's agent
runs on your loop. In `my_loop.py`, each line of your outline is a comment, with Claude's Python for it
under it.

**Write-up:** Answer these questions in `WRITEUP.md`, under 1a:

- Write your outline of the loop in the code block: what it remembers, what it repeats, and every way it stops.
- List each thing your loop remembers from one turn to the next, and say what would go wrong without it.
- Now open `reference_loop.py` and compare it with your loop. Describe one difference in implementation and the resulting effects on agent behavior.

**Troubleshooting:**

- The Python does something your outline does not say, or the check reports an error in it. Tell Claude:
  the translation is Claude's to fix.
- You can't get a rule to pass. Ask Claude to go through the first `NOT YET` line with you; if you are
  still stuck, post that line in `#comp440-f26` on Slack.
- You wrote Python in `my_loop.py` before this step changed. You may finish it that way, and write the
  outline of your finished loop in `WRITEUP.md` all the same.

**Hint:** Start with the plainest case: the model asks for one lookup, then gives an answer. Then ask
what your outline does when the model does something else: asks for two lookups at once, asks for a
lookup and gives an answer in the same reply, keeps asking for lookups. You may also write the Python
yourself; the outline is still what I read.

## 1b. Be the agent

In this step you check one claim yourself, using only the agent's four tools.

The claim you check in this step:

> Vic & Anthony's Steakhouse is located at the American casino that was combined with the
> California Club. The casino is owned by Landry's, Inc.

**Words in this step:** A *lookup* is one call to `search`, `read` or `wikidata`. A *verdict* is one of
*supported*, *refuted* or *doesn't say*.

**Actions:**

1. Decide on one lookup: which tool, and what to ask it. `search` takes a search query; `read` takes a page
   title, and a section if you want one; `wikidata` takes an entity and a property (see Interpreting
   output). Use only the agent's tools, not your browser, so that you see only what the agent sees.
2. Ask Claude to run it. Read what comes back, and write down for yourself why you chose that lookup:
   you type these reasons into the table at the end.
3. Repeat until you have a verdict. If you have made 12 lookups without answering the claim, stop: your
   verdict is *doesn't say*, as the agent's would be.
4. Ask Claude to paste your lookups into the table under 1b in `WRITEUP.md`. Then, in your editor, type
   your reason for each in the "Why you chose it" column.
5. Type your answer to the question in `WRITEUP.md`, in your editor, under 1b.

**Interpreting output:** For each lookup, Claude runs one of these and pastes exactly what the agent would
see:

```
uv run python lookup.py search "<query>"
uv run python lookup.py read "<page title>"
uv run python lookup.py read "<page title>" "<section>"
uv run python lookup.py wikidata "<entity>" "<property>"
```

`search` returns the top five page titles, each with a short snippet. `read` returns one section of a
page, or with no section the opening paragraphs and the list of sections. `wikidata` returns one fact
for an entity (a person, a place) and a property ("place of birth", "population"). Each lookup is added
to `runs/part1/lookups.jsonl`, which the table is filled from. Your verdict goes in `WRITEUP.md`, so
there is no `answer` call.

**Write-up:** In `WRITEUP.md`, under 1b, fill in the table and answer:

- List your lookups, in order. Ask Claude to paste every column but the last from `runs/part1/lookups.jsonl`. Type "Why you chose it" yourself.
- What is your verdict on the claim, and which sentence or sentences from what you read is it based on?

**Troubleshooting:**

- A lookup finds no page, or no such section. That is a result like any other: count it, and choose your
  next lookup from what it told you.
- A title with `&` or an apostrophe must be inside double quotes, as in
  `uv run python lookup.py read "<page title>"`, or the shell misreads it. Check Claude's command.

**Hint:** I ask you to do this before you watch the agent on your development claims in 1c, because
you'll read its traces more closely once you've made the same choices. Claude will not suggest a lookup or say what a result means, because
choosing the lookups is the job you are doing here; it will explain what a tool does or how to read its
output.

## 1c. Watch the agent work

In this step you find out whether the agent matches the dataset's label on your 12 development claims,
and whether it got there for a good reason.

**Words in this step:** *Your development claims* are the 12 claims in `data/dev.jsonl`. *The number of
articles* is how many Wikipedia articles a claim needs (2, 3 or 4). *The dataset's label* is HoVer's
*supported* or *not supported*; a verdict of *refuted* or *doesn't say* counts as *not supported*. A
*trace* is the agent's lookups for one claim, in order, with what each returned; an *entry* is one
numbered line of it.

**Actions:**

1. Ask Claude to run the agent on your 12 development claims, and read the two tables it prints.
2. Open **Results** at the top of the homework page, then "runs/part1/before".
3. Choose three claims, one each that needs 2, 3 and 4 Wikipedia articles (see the Hint).
4. For each, read "The agent's trace", one entry at a time, and decide whether the agent got there for a
   good reason: does its quoted evidence really answer the claim?
5. Fill in one row of the table for each, and type your answer to the question, in `WRITEUP.md`, in
   your editor, under 1c.

**Interpreting output:** Claude runs this command. It takes about a minute and costs about 2 cents:

```
uv run python evaluate.py data/dev.jsonl --methods agent --out runs/part1/before
```

Its first line, "Agent loop: yours (my_loop.py)", says the agent ran on the loop you designed in 1a. The
first table shows how many claims matched the dataset's label, by number of articles and by label;
the second, the average lookups and seconds per claim. The run is saved in
`runs/part1/before`, "before" your instructions of 1d. On a claim's page, each quote under "Quoted
evidence" says "Found in entry N of the trace (read), highlighted below": click "entry N" to see it.

**Write-up:** In `WRITEUP.md`, under 1c, fill in the table and answer:

- List the three traces you read closely. At least one should be a claim the agent got wrong (if it got any wrong).
- Which trace did you find most interesting, and what did the agent do well or badly in it?

**Troubleshooting:** If the run stops partway, ask Claude to run the same command again. It keeps every
claim it already finished.

**Hint:** In "Claims", set "The number of articles" to "2" (then "3", then "4"), and set "Result" in
"The agent" box to "matches the dataset's label" or "does not match the dataset's label (any reason)".
"Next →" goes to the next claim in the filtered list. The dataset's labels were made by people from the
Wikipedia of 2017, so one may look wrong to you; if so, say so in that row. The claim you checked by hand
in 1b is one of these. You may choose it as your 3-article claim; if you do, read the agent's trace for it
as you would any other, and compare it with your own lookups: the table asks what the agent did, not what
you did.

## 1d. Write the agent's instructions

In this step you write the agent's instructions, and see how its traces change.

**Words in this step:** *`instructions.md`* holds the agent's instructions, which the program sends to
the model on every turn. It starts with three sentences that name the job, the four tools and how to
finish, and says nothing about how to look things up.

**Actions:**

1. In your editor, write your instructions in `instructions.md` and save. Add to its three sentences or
   rewrite them, but keep what they say about finishing with `answer` and the three verdict words. At a
   minimum your instructions must say:
   - how to break a claim into the pieces that have to be checked;
   - when to use `wikidata` instead of reading a page;
   - when the agent has enough evidence to stop;
   - when to answer *doesn't say*.
2. Ask Claude to run the agent on your 12 development claims again.
3. Open **Results** at the top of the homework page, click "Compare two runs", then "Step 1d:
   runs/part1/before with runs/part1/after", and read "Accuracy". A is the run before your
   instructions, B the run after.
4. Under "Claims that changed", click "Open A and B" to read a claim's two traces side by side. If it
   says "No claim changed. Every claim in both runs has the same verdict in A and B.", or to see
   whether a claim's lookups changed where its verdict did not, open the claim in `runs/part1/before`
   and the same claim in `runs/part1/after`.
5. Type your answer to the question in `WRITEUP.md`, in your editor, under 1d.

**Interpreting output:** Claude runs this command. It takes about a minute and costs about 2 cents, or
more if your instructions make the agent do more:

```
uv run python evaluate.py data/dev.jsonl --methods agent --out runs/part1/after
```

It ends with the same two tables as the run in 1c.

**Write-up:** Answer this question in `WRITEUP.md`, under 1d:

- What changed in the agent's traces after you wrote your instructions? Give one claim as an example.

**Troubleshooting:**

- The comparison says "A and B used the same version of the agent". The second run did not have your
  change: save `instructions.md`, then ask Claude to run the command again with `--fresh`.
- You changed `instructions.md` after the run. A saved result is never checked again, so ask Claude to
  run the same command with `--fresh` at the end, which replaces this folder's saved results:

  ```
  uv run python evaluate.py data/dev.jsonl --methods agent --out runs/part1/after --fresh
  ```

**Hint:** I recommend short, direct rules. Write rules that fit any claim. A rule that names one of your
12 development claims, or a page one of them needs, gives the agent part of that claim's answer, and the
second run then tells you little about your rules. The model does not give the same answer every time, so 12
claims are too few to prove a change helped: read the traces, not only the score. Claude will not write
or suggest text for `instructions.md`, because what the agent is told is your decision.

## 1e. Start the full run, and predict

In this step you start the run on your 100 evaluation claims, and predict its results while it runs.

**Words in this step:** *The three versions* are the no-tools baseline (the model answers from memory),
the one-search baseline (one search, one page, then an answer) and the agent. *Your evaluation claims*
are the 100 claims in `data/eval.jsonl`.

**Actions:**

1. In another terminal tab in the homework's folder, start the full run:
   `uv run python evaluate.py data/eval.jsonl --out runs/part2`.
2. Leave that tab open and your laptop awake until the run ends with two tables.
3. While it runs, fill in the predictions table, and type your answer to the question, in `WRITEUP.md`,
   in your editor, under 1e.
4. Don't look at the run's results before your predictions are saved. Until it ends, it prints only
   progress lines that count claims.

**Interpreting output:** The full run takes about 10 minutes and costs about 28 cents on your key. It
runs the no-tools baseline on your 100 evaluation claims, then the one-search baseline, then the agent
with your `instructions.md` from 1d. It prints a progress line every ten claims, ends with two tables,
and is saved in `runs/part2`. You read the tables in 2a.

**Write-up:** In `WRITEUP.md`, under 1e, fill in the table and answer:

- Predict the share of claims each version will get right (its verdict matches the dataset's label), as a percentage. A guess is fine; the reasons are what I grade.
- How many lookups will the agent make per claim, on average? Why?

**Troubleshooting:**

- The run stops (you closed the tab, your laptop slept, or Wikipedia refused requests for too long). Run
  the same command again; it keeps every claim it already finished.
- It stops and says the saved results came from an earlier version of your agent. You changed
  `instructions.md` after the run started: put it back and run the command again.

**Hint:** The page ticks 1e once the run has started; once the run has ended, this is a good place to
stop for the day.

## What I look for

Part 1 is 35% of the homework. At a minimum I am looking for the following:

- Your loop: 30% - Your outline is your own design, your loop passes the check, and your answers to 1a
  say what your loop remembers and how it differs from the reference loop.
- Being the agent: 20% - Your 1b record shows each lookup and why you chose it, and your verdict names
  the sentences it is based on.
- Predictions: 15% - Each prediction in 1e has a reason. They are graded on the reasoning, not on being
  right.
- Instructions: 35% - Your `instructions.md` covers the four points in 1d, your 1c table says for each
  trace whether the agent got there for a good reason, and your 1d answer compares the traces before and
  after with a specific example.
