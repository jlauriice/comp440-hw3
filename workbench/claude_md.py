"""Write the repository's CLAUDE.md from steps.toml, for a student who starts plain `claude` here.

    uv run python -m workbench.claude_md

A session the page starts leaves this file out (its command has `--setting-sources user`), so it
reaches only a Claude started in this folder some other way. It first gives the one thing done
there instead of on the page, an update by hand (read UPDATE.md from the class repository and
follow it, with the page left stopped). For anything else it sends the student to the homework
page, helps if the page won't start, and gives the homework's tutor rules from steps.toml for a
student who keeps working there anyway. tests/test_workbench.py fails when this file and
steps.toml are out of step: run this again after changing the tutor text.
"""

from __future__ import annotations

from pathlib import Path

from .steps import Assignment, load

REPO = Path(__file__).resolve().parent.parent


def text(a: Assignment) -> str:
    url = a.upstream or "the class repository's address"
    return f"""# {a.title}

<!-- Written by `uv run python -m workbench.claude_md` from steps.toml. Change steps.toml, then
run that command again. Don't edit this file by hand. -->

If the student asks to update the homework, or says the Update button on the homework page failed,
do only this. Run `git fetch upstream` (if there is no remote named upstream, first run
`git remote add upstream {url}`),
then `git show upstream/main:UPDATE.md`, and follow that file exactly: it is the instructor's
current procedure for bringing the class repository's updates into this copy without losing the
student's work. Do not tell the student to start the homework page: the update needs the page
stopped, and the file's last step says when to start it again. Read the file from the class
repository every time, because the copy of UPDATE.md in this folder may be old. Its steps move the
student's answers and never write one, so the tutor rules below allow them.

Everything else in this homework is done on the homework page, not in a Claude session started
here. Unless the student asked for an update, tell them so before anything else, in two sentences:
run this in a terminal in this folder, and leave that terminal open while they work:

    uv run python -m workbench

It opens the homework page in the browser. The page starts each Claude session for the homework:
the command a step shows, pasted into another terminal in this folder, starts a new one, and the
prompt a step shows, pasted into that session's chat, moves it on to that step.

If the page won't start, help them get it running, and nothing else until it does:
- It must be started in this folder, the one with steps.toml.
- It needs uv. If `uv` isn't found, point them to https://docs.astral.sh/uv/ to install it. uv
  fetches the right Python (3.12) by itself the first time.
- If it says the homework page is already running, it gives the address: open that.
- It picks a free port by itself, from 8450. If every port it tries is in use, it says so; then
  start it with `--port 9000`.
- For any other error, read it with them and fix what it names. If it still won't start, they
  post the error in #comp440-f26 on Slack.

If they keep working in this session anyway, these rules apply:

{a.tutor.strip()}
"""


def main() -> None:
    out = REPO / "CLAUDE.md"
    out.write_text(text(load(REPO / "steps.toml")), encoding="utf-8")
    print(f"Wrote {out.name} from steps.toml.")


if __name__ == "__main__":
    main()
