# Updating the homework by hand

Version of November 16, 2026.

Claude reads this file from the class repository, with `git show upstream/main:UPDATE.md`, when the
Update button on the homework page fails. The copy of this file in your own homework folder may be
old, so Claude reads the one in the class repository instead.

You do not need to read this file. To update by hand, stop the homework page (press Ctrl-C in the
terminal where it runs), run `claude` in your homework folder, and say "update my homework".

For Claude: Everything below the line is written in the student's own words, as a request. Follow
it as if the student had typed it. If the student has not said that the homework page is stopped,
step 1 finds out.

---

The homework page's Update button failed, or it worked and something now looks wrong. Please bring the class repository's updates into my copy by hand, without losing any of my work. Do these steps in order, and if one fails, stop and tell me.

I stopped the homework page (Ctrl-C in its terminal) on purpose before I started this session: the page commits by itself, and it would close a half-done merge. Keep it stopped, and don't ask me to start it, until the last step.

1. Check that the page is stopped. Read the port number in .workbench/server.json (if that file is not there, the page has never run here: go on), then run curl -s http://127.0.0.1:PORT/api/ping with that number. If anything answers, the page is still running: stop, ask me to press Ctrl-C in its terminal, and check again when I say I have.
2. Run git status. If it says a merge is in progress (unmerged paths, or still merging), stop and do nothing more: tell me to post in #comp440-f26 on Slack. If it lists modified or deleted files, show me the list and ask whether to save them. If I say no, stop and do nothing more. If I say yes, first run git diff --name-only -G "sk-ant-", which prints only the names of changed files that hold something like an API key. If it names a file, stop, tell me which file, and commit nothing; do not open or show that file. If it names none, run git add -u, then git commit -m "Save work before update". Leave untracked files as they are.
3. Run git branch before-merge (add a number if the name is taken). It marks my copy as it is now.
4. Run git fetch upstream, then git log --oneline HEAD..upstream/main.
   - If any file in my copy has conflict markers (lines that start with <<<<<<< or >>>>>>>), stop and do nothing more: tell me to post in #comp440-f26 on Slack.
   - If the log printed nothing, the updates are already in my copy. Skip step 5. In step 6, compare with my copy as it was before that update: the first parent of the newest merge named "Take the class repository's updates" (git log --merges -1 --grep="Take the class repository's updates" --format="%h %p" shows it).
   - Otherwise go on to step 5, and in step 6 compare with before-merge.
5. Run git merge --no-commit --no-ff -m "Take the class repository's updates" upstream/main. Then resolve each file git lists as conflicted:
   - WRITEUP.md: keep every word I wrote (my name, my answers, my tables, my outline) exactly as I wrote it, and take the class repository's version of everything else (headings, questions, instructions).
   - data/dev.jsonl, data/eval.jsonl and instructions.md: keep my version, with git checkout --ours -- PATH. My runs and my answers use my claims.
   - my_loop.py: keep everything below the line "your loop goes below this line" exactly as I wrote it, and take the class repository's version of everything above it.
   - Any other file: take the class repository's version, with git checkout --theirs -- PATH.
   Then run git add on each file you resolved.
6. Check where my answers are, in all of WRITEUP.md, because git also moves text where it reports no conflict. Compare it with my copy from step 4 (git show COMMIT:WRITEUP.md). Move answers; never write, complete or improve one.
   - Each answer of mine must sit under the same question as before, or under that question's new wording if only the wording changed.
   - If an answer of mine sits under a question it does not answer, move it out and leave that question empty.
   - If the class repository removed a question I answered, move that question and my answer, word for word, to the end of WRITEUP.md, under the heading "## Answers to questions the update removed" and the line "An update to the homework removed these questions. My answers to them are kept here as I wrote them." Never keep an old step's heading in the file.
   - Never put an answer inside the outline's code block, inside a table, or under another step.
7. Check that no file has conflict markers left. If my_loop.py holds my loop, run uv run python check_loop.py. If the check fails, change nothing above the line "your loop goes below this line". Show me the line that fails and the smallest change that makes it pass, placed just below that line, and make it only after I say yes. Change nothing else in my loop.
8. Show me which files conflicted and what you did in each, every answer you moved (from where to where), every answer that now sits under a reworded question (old and new wording), any change to my loop, and the check's output. Then ask me whether to keep all this. If I say yes and step 5 ran, run GIT_EDITOR=true git merge --continue, then git log -1 --format="%s %P". If I say no, or anything went wrong: if step 5 ran, run git merge --abort; if it did not, run git checkout before-merge -- . (the dot means every file). Either one puts every file back as it was.
9. List what is left for me to do: an empty outline, new questions with no answer, steps that may lose their tick because of them, and anything under "Answers to questions the update removed" that I may want to reuse. Tell me that the branch before-merge still holds my copy as it was before this session, so if something looks wrong later, I should stop and ask in #comp440-f26 before doing more work. Then tell me to start the homework page again with uv run python -m workbench; it saves what changed.

Apart from the commands these steps name, run no command that changes files or history: no git commit, push, reset, stash, rebase or restore.
