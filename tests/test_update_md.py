"""UPDATE.md: what Claude reads from the class repository when the homework page's Update fails.

Its body is the update-by-hand message that was tested word for word in live sessions on November 15
(the nine numbered steps and the closing sentence). Those tests hold only for that text, so the body
is pinned here, line by line: a change to it needs new live tests before this copy is changed.
Above the body, a short header says who reads the file and how a student starts an update by hand.
"""

from pathlib import Path

ROOT = Path(__file__).parent.parent
UPDATE = ROOT / "UPDATE.md"

# The tested text, as it was run in the live tests of November 15 (merge-message.txt).
BODY_LINES = (
    "The homework page's Update button failed, or it worked and something now looks wrong. Please bring the class repository's updates into my copy by hand, without losing any of my work. Do these steps in order, and if one fails, stop and tell me.",
    '',
    "I stopped the homework page (Ctrl-C in its terminal) on purpose before I started this session: the page commits by itself, and it would close a half-done merge. Keep it stopped, and don't ask me to start it, until the last step.",
    '',
    '1. Check that the page is stopped. Read the port number in .workbench/server.json (if that file is not there, the page has never run here: go on), then run curl -s http://127.0.0.1:PORT/api/ping with that number. If anything answers, the page is still running: stop, ask me to press Ctrl-C in its terminal, and check again when I say I have.',
    '2. Run git status. If it says a merge is in progress (unmerged paths, or still merging), stop and do nothing more: tell me to post in #comp440-f26 on Slack. If it lists modified or deleted files, show me the list and ask whether to save them. If I say no, stop and do nothing more. If I say yes, first run git diff --name-only -G "sk-ant-", which prints only the names of changed files that hold something like an API key. If it names a file, stop, tell me which file, and commit nothing; do not open or show that file. If it names none, run git add -u, then git commit -m "Save work before update". Leave untracked files as they are.',
    '3. Run git branch before-merge (add a number if the name is taken). It marks my copy as it is now.',
    '4. Run git fetch upstream, then git log --oneline HEAD..upstream/main.',
    '   - If any file in my copy has conflict markers (lines that start with <<<<<<< or >>>>>>>), stop and do nothing more: tell me to post in #comp440-f26 on Slack.',
    '   - If the log printed nothing, the updates are already in my copy. Skip step 5. In step 6, compare with my copy as it was before that update: the first parent of the newest merge named "Take the class repository\'s updates" (git log --merges -1 --grep="Take the class repository\'s updates" --format="%h %p" shows it).',
    '   - Otherwise go on to step 5, and in step 6 compare with before-merge.',
    '5. Run git merge --no-commit --no-ff -m "Take the class repository\'s updates" upstream/main. Then resolve each file git lists as conflicted:',
    "   - WRITEUP.md: keep every word I wrote (my name, my answers, my tables, my outline) exactly as I wrote it, and take the class repository's version of everything else (headings, questions, instructions).",
    '   - data/dev.jsonl, data/eval.jsonl and instructions.md: keep my version, with git checkout --ours -- PATH. My runs and my answers use my claims.',
    '   - my_loop.py: keep everything below the line "your loop goes below this line" exactly as I wrote it, and take the class repository\'s version of everything above it.',
    "   - Any other file: take the class repository's version, with git checkout --theirs -- PATH.",
    '   Then run git add on each file you resolved.',
    '6. Check where my answers are, in all of WRITEUP.md, because git also moves text where it reports no conflict. Compare it with my copy from step 4 (git show COMMIT:WRITEUP.md). Move answers; never write, complete or improve one.',
    "   - Each answer of mine must sit under the same question as before, or under that question's new wording if only the wording changed.",
    '   - If an answer of mine sits under a question it does not answer, move it out and leave that question empty.',
    '   - If the class repository removed a question I answered, move that question and my answer, word for word, to the end of WRITEUP.md, under the heading "## Answers to questions the update removed" and the line "An update to the homework removed these questions. My answers to them are kept here as I wrote them." Never keep an old step\'s heading in the file.',
    "   - Never put an answer inside the outline's code block, inside a table, or under another step.",
    '7. Check that no file has conflict markers left. If my_loop.py holds my loop, run uv run python check_loop.py. If the check fails, change nothing above the line "your loop goes below this line". Show me the line that fails and the smallest change that makes it pass, placed just below that line, and make it only after I say yes. Change nothing else in my loop.',
    '8. Show me which files conflicted and what you did in each, every answer you moved (from where to where), every answer that now sits under a reworded question (old and new wording), any change to my loop, and the check\'s output. Then ask me whether to keep all this. If I say yes and step 5 ran, run GIT_EDITOR=true git merge --continue, then git log -1 --format="%s %P". If I say no, or anything went wrong: if step 5 ran, run git merge --abort; if it did not, run git checkout before-merge -- . (the dot means every file). Either one puts every file back as it was.',
    '9. List what is left for me to do: an empty outline, new questions with no answer, steps that may lose their tick because of them, and anything under "Answers to questions the update removed" that I may want to reuse. Tell me that the branch before-merge still holds my copy as it was before this session, so if something looks wrong later, I should stop and ask in #comp440-f26 before doing more work. Then tell me to start the homework page again with uv run python -m workbench; it saves what changed.',
    '',
    'Apart from the commands these steps name, run no command that changes files or history: no git commit, push, reset, stash, rebase or restore.',
)
BODY = "\n".join(BODY_LINES) + "\n"
RULE = "\n---\n\n"


def parts():
    text = UPDATE.read_text(encoding="utf-8")
    assert text.count(RULE) == 1, "UPDATE.md needs exactly one line of --- between the header and the body"
    return text.split(RULE)


def test_the_body_is_the_tested_text_word_for_word():
    header, body = parts()
    assert body == BODY, "UPDATE.md's body has drifted from the text tested on November 15"


def test_the_body_has_nine_steps_and_its_closing_sentence():
    numbered = [line.split(".")[0] for line in BODY_LINES if line[:2].rstrip(".").isdigit() and ". " in line[:4]]
    assert numbered == [str(n) for n in range(1, 10)]
    assert BODY_LINES[-1].startswith("Apart from the commands these steps name, run no command that changes files")


def test_the_header_says_who_reads_it_and_how_a_student_starts():
    header, _ = parts()
    flat = " ".join(header.split())
    for must in ("git show upstream/main:UPDATE.md",
                 "when the Update button on the homework page fails",
                 "The copy of this file in your own homework folder may be old",
                 "You do not need to read this file.",
                 "stop the homework page (press Ctrl-C in the terminal where it runs)",
                 "run `claude` in your homework folder",
                 'say "update my homework"',
                 "Version of November 16, 2026.",
                 "Follow it as if the student had typed it.",
                 "If the student has not said that the homework page is stopped, step 1 finds out."):
        assert must in flat, must


def test_claude_md_sends_an_update_by_hand_to_the_class_repositorys_update_md():
    import sys
    sys.path.insert(0, str(ROOT))
    from workbench import claude_md, steps
    a = steps.load(ROOT / "steps.toml")
    text = " ".join(claude_md.text(a).split())
    update = ("If the student asks to update the homework, or says the Update button on the homework page "
              "failed, do only this.")
    for must in (update,
                 "Run `git fetch upstream`",
                 f"first run `git remote add upstream {a.upstream}`",
                 "then `git show upstream/main:UPDATE.md`, and follow that file exactly",
                 "Do not tell the student to start the homework page: the update needs the page stopped, "
                 "and the file's last step says when to start it again.",
                 "Read the file from the class repository every time, because the copy of UPDATE.md in this "
                 "folder may be old.",
                 "so the tutor rules below allow them",
                 "Everything else in this homework is done on the homework page",
                 "Unless the student asked for an update, tell them so before anything else"):
        assert must in text, must
    # The exception is the first thing after the title and the comment, so that nothing sending the student to the
    # page comes ahead of it; it is stated once; and the tutor rules (which page sessions also get) do not carry it.
    body = text.split("-->", 1)[1]
    assert body.lstrip().startswith(update)
    assert body.index(update) < body.index("homework page, not in a Claude session")
    assert body.index(update) < body.index("uv run python -m workbench")
    assert text.count("UPDATE.md") == 2 and text.count("git fetch upstream") == 1
    assert "One thing is done" not in text
    assert text.index(update) < text.index(" ".join(a.tutor.split())[:80])
    assert "UPDATE.md" not in a.tutor
