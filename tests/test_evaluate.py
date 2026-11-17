"""Offline tests for what the programs print and save around a run: evaluate.py's
progress lines, report.txt (which marks a finished run), run.json and --fresh;
lookup.py's --no-log; the notice when Wikipedia asks the program to wait; and
reading a verdict from a reply that is not valid JSON."""

import json
import subprocess
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

import evaluate  # noqa: E402
import wiki  # noqa: E402

ITEMS = [{"id": f"c{i}", "claim": f"claim {i}", "source": "hover", "label": "SUPPORTED", "hops": 2}
         for i in range(12)]


def always_supported(claim):
    return {"claim": claim, "verdict": "supported", "evidence": [], "explanation": "x",
            "trace": [], "steps": 1}


@pytest.fixture(autouse=True)
def a_passed_loop(monkeypatch, tmp_path):
    """evaluate.py runs the agent only once the student's loop has passed the check (the runs of
    Part 1 and later): these tests run it as if it had."""
    record = tmp_path / "runs" / "part1" / "loop-check.txt"
    record.parent.mkdir(parents=True)
    record.write_text("yours\n")
    monkeypatch.setattr(evaluate.agent, "LOOP_CHECK", record)


def run_main(monkeypatch, tmp_path):
    claims = tmp_path / "claims.jsonl"
    claims.write_text("\n".join(json.dumps(item) for item in ITEMS) + "\n")
    out_dir = tmp_path / "run"
    monkeypatch.setattr(sys, "argv", ["evaluate.py", str(claims), "--methods", "agent",
                                      "--out", str(out_dir)])
    evaluate.main()
    return claims, out_dir


def test_a_run_prints_how_far_it_has_got(monkeypatch, tmp_path, capsys):
    monkeypatch.setitem(evaluate.METHODS, "agent", always_supported)
    evaluate.run_method("agent", ITEMS, tmp_path, workers=2)
    printed = capsys.readouterr().out
    assert "agent: 0 already done, running 12" in printed
    assert "agent: 10 of 12 done" in printed
    assert "agent: 12 of 12 done" in printed


def test_a_finished_run_saves_its_report(monkeypatch, tmp_path, capsys):
    monkeypatch.setitem(evaluate.METHODS, "agent", always_supported)
    claims, out_dir = run_main(monkeypatch, tmp_path)
    printed = capsys.readouterr().out
    report = (out_dir / "report.txt").read_text()
    assert "Share of claims where the verdict matched the label" in report
    assert "12/12" in report
    assert "HoVer, supported          12/12" in report   # the count split by the dataset's label
    assert "HoVer, not supported       0/0" in report
    assert "Average per claim" in report
    assert report.strip() in printed
    assert json.loads((out_dir / "run.json").read_text()) == {"claims": str(claims)}

    # Running the same command again runs nothing and prints the same tables.
    monkeypatch.setitem(evaluate.METHODS, "agent",
                        lambda claim: pytest.fail("a saved claim was run again"))
    evaluate.main()
    assert "agent: 12 already done, running 0" in capsys.readouterr().out
    assert (out_dir / "report.txt").read_text() == report


def test_a_run_started_again_carries_on_from_where_it_stopped(monkeypatch, tmp_path, capsys):
    """2a's brief says a run that stopped, started again with the same command, carries on from where
    it stopped: the saved results are kept and only the claims still to do are run."""
    monkeypatch.setattr(evaluate, "agent_version", lambda: "v1")
    monkeypatch.setitem(evaluate.METHODS, "agent", always_supported)
    out_dir = tmp_path / "run"
    out_dir.mkdir()
    evaluate.run_method("agent", ITEMS[:7], out_dir, workers=2)  # the run stopped after 7 claims
    assert not (out_dir / "report.txt").exists()
    capsys.readouterr()

    ran = []

    def the_rest(claim):
        ran.append(claim)
        return always_supported(claim)

    monkeypatch.setitem(evaluate.METHODS, "agent", the_rest)
    run_main(monkeypatch, tmp_path)
    assert "agent: 7 already done, running 5" in capsys.readouterr().out
    assert sorted(ran) == sorted(item["claim"] for item in ITEMS[7:])
    assert len((out_dir / "agent.jsonl").read_text().splitlines()) == 12
    assert (out_dir / "report.txt").exists()


def test_saved_results_from_an_earlier_agent_are_pointed_out(monkeypatch, tmp_path, capsys):
    monkeypatch.setitem(evaluate.METHODS, "agent", always_supported)
    monkeypatch.setattr(evaluate, "agent_version", lambda: "v1")
    _, out_dir = run_main(monkeypatch, tmp_path)
    assert "earlier version" not in capsys.readouterr().out

    # The student changes instructions.md and runs the same command: nothing runs,
    # and the program says the saved results are from the earlier agent.
    monkeypatch.setattr(evaluate, "agent_version", lambda: "v2")
    monkeypatch.setitem(evaluate.METHODS, "agent",
                        lambda claim: pytest.fail("ran again without --fresh"))
    evaluate.main()
    printed = capsys.readouterr().out
    assert "earlier version of your agent" in printed and "--fresh" in printed

    # With --fresh every claim runs again with the agent as it is now.
    monkeypatch.setitem(evaluate.METHODS, "agent", always_supported)
    monkeypatch.setattr(sys, "argv", sys.argv + ["--fresh"])
    evaluate.main()
    printed = capsys.readouterr().out
    assert "agent: 0 already done, running 12" in printed
    assert "earlier version" not in printed
    rows = [json.loads(line) for line in (out_dir / "agent.jsonl").read_text().splitlines()]
    assert len(rows) == 12 and {row["agent_version"] for row in rows} == {"v2"}
    assert (out_dir / "report.txt").exists()


def test_old_and_new_results_are_not_mixed(monkeypatch, tmp_path, capsys):
    def two_fail(claim):  # a run that stopped before it finished
        if claim in ("claim 10", "claim 11"):
            raise wiki.RateLimited("too many requests")
        return always_supported(claim)

    monkeypatch.setattr(evaluate, "agent_version", lambda: "v1")
    monkeypatch.setitem(evaluate.METHODS, "agent", two_fail)
    _, out_dir = run_main(monkeypatch, tmp_path)

    monkeypatch.setattr(evaluate, "agent_version", lambda: "v2")  # then the agent changed
    monkeypatch.setitem(evaluate.METHODS, "agent",
                        lambda claim: pytest.fail("mixed old and new results"))
    with pytest.raises(SystemExit) as stopped:
        evaluate.main()
    assert "earlier version of your agent" in str(stopped.value)
    assert "--fresh" in str(stopped.value)
    assert len((out_dir / "agent.jsonl").read_text().splitlines()) == 10


# ---- the homework page's Update, which can change agent.py or the loop's file ----
# A real git repository in a temporary folder stands for the student's fork; the run folder is
# outside it, as runs/part2 is in no way part of what the fingerprint reads.

HUNDRED = [{"id": f"e{i}", "claim": f"claim e{i}", "source": "hover", "label": "SUPPORTED", "hops": 2}
           for i in range(100)]


def git(repo, *args):
    return subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@example.edu",
                           "-c", "commit.gpgsign=false", *args], check=True, capture_output=True,
                          text=True).stdout


def a_fork(tmp_path, monkeypatch):
    """The student's folder under git, which evaluate.py reads: the agent's files as the class
    repository gave them, on the student's branch, and a branch for the class repository."""
    repo = tmp_path / "fork"
    repo.mkdir()
    for name, text in (("instructions.md", "Check the claim.\n"), ("agent.py", "# the agent\nX = 1\n"),
                       ("wiki.py", "# the tools\n"), ("my_loop.py", "# the loop\nY = 2\n")):
        (repo / name).write_text(text)
    git(repo, "init", "-q", "-b", "student")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "The homework")
    git(repo, "branch", "class")
    git(repo, "worktree", "add", "-q", str(tmp_path / "class"), "class")   # the class repository's side
    monkeypatch.setattr(evaluate, "HERE", repo)
    return repo


def class_change(repo, name):
    """A new commit in the class repository that changes only the first line, a comment, of one
    file. It is made in the class side's own folder, so the student's files are not touched."""
    side = repo.parent / "class"
    lines = (side / name).read_text().split("\n", 1)
    (side / name).write_text(lines[0] + ", reworded\n" + lines[1])
    git(side, "commit", "-q", "-am", f"A comment in {name}")


def update(repo):
    """The page's Update button: save the student's work, then merge the class repository's commits."""
    writeup = repo / "WRITEUP.md"
    writeup.write_text((writeup.read_text() if writeup.exists() else "") + "An answer.\n")
    git(repo, "add", "-A")
    git(repo, "commit", "-q", "-m", "Save work before update")
    git(repo, "merge", "--no-edit", "-m", evaluate.UPDATE, "class")


def full_run(monkeypatch, tmp_path, method):
    """evaluate.py data/eval.jsonl --methods agent --out <part2>, with the agent replaced."""
    claims = tmp_path / "eval.jsonl"
    claims.write_text("".join(json.dumps(item) + "\n" for item in HUNDRED))
    monkeypatch.setitem(evaluate.METHODS, "agent", method)
    monkeypatch.setattr(sys, "argv", ["evaluate.py", str(claims), "--methods", "agent",
                                      "--out", str(tmp_path / "part2")])
    evaluate.main()
    return tmp_path / "part2"


def stops_at(n):
    """A run that stops after its first n claims (a laptop that slept, say)."""
    def method(claim):
        if int(claim.split("e")[-1]) >= n:
            raise wiki.RateLimited("too many requests")
        return always_supported(claim)
    return method


stops_at_40, stops_at_70 = stops_at(40), stops_at(70)


def never(claim):
    pytest.fail("ran a saved claim again, or mixed old and new results")


def a_run(monkeypatch, tmp_path, finished):
    full_run(monkeypatch, tmp_path, always_supported if finished else stops_at_40)


def as_before(monkeypatch, tmp_path, capsys, finished):
    """What a changed agent gets on main today: a stopped run stops, a finished one gets the note."""
    capsys.readouterr()
    if finished:
        full_run(monkeypatch, tmp_path, never)
        printed = capsys.readouterr().out
        assert "Note: the agent's saved results" in printed
    else:
        with pytest.raises(SystemExit) as stopped:
            full_run(monkeypatch, tmp_path, never)
        said = str(stopped.value)
        assert said.startswith("Stopped: ") and "earlier version of your agent" in said
        printed = capsys.readouterr().out
    assert "Carrying on" not in printed


def test_a_finished_run_after_an_update_prints_its_tables_and_no_note(monkeypatch, tmp_path, capsys):
    repo = a_fork(tmp_path, monkeypatch)
    a_run(monkeypatch, tmp_path, finished=True)
    class_change(repo, "agent.py")
    update(repo)
    capsys.readouterr()
    full_run(monkeypatch, tmp_path, never)
    printed = capsys.readouterr().out
    assert "Share of claims where the verdict matched the label" in printed
    assert "earlier version" not in printed and "Carrying on" not in printed


def test_a_run_stopped_at_40_carries_on_after_an_update(monkeypatch, tmp_path, capsys):
    repo = a_fork(tmp_path, monkeypatch)
    a_run(monkeypatch, tmp_path, finished=False)
    before = evaluate.agent_version()
    class_change(repo, "agent.py")
    update(repo)
    assert evaluate.agent_version() != before
    assert evaluate.versions_before_updates() == {before}
    capsys.readouterr()
    ran = []
    out = full_run(monkeypatch, tmp_path, lambda claim: ran.append(claim) or always_supported(claim))
    printed = capsys.readouterr().out
    assert (f"Carrying on: the 40 saved results in {out} were made before the homework page's Update, "
            "which did not change how your agent works.\n") in printed
    assert "agent: 40 already done, running 60" in printed
    assert sorted(ran) == sorted(item["claim"] for item in HUNDRED[40:])     # nothing run again
    assert (out / "report.txt").exists() and "earlier version" not in printed
    full_run(monkeypatch, tmp_path, never)                                  # finished now: no line, no note
    printed = capsys.readouterr().out
    assert "Carrying on" not in printed and "earlier version" not in printed


def test_a_run_that_stops_again_after_an_update_says_how_many_came_before_it(monkeypatch, tmp_path, capsys):
    repo = a_fork(tmp_path, monkeypatch)
    a_run(monkeypatch, tmp_path, finished=False)
    class_change(repo, "agent.py")
    update(repo)
    full_run(monkeypatch, tmp_path, stops_at_70)          # carries on, and stops again at 70
    capsys.readouterr()
    out = full_run(monkeypatch, tmp_path, always_supported)
    assert (f"Carrying on: 40 of the 70 saved results in {out} were made before the homework page's "
            "Update") in capsys.readouterr().out


def test_two_updates_in_a_row_still_count(monkeypatch, tmp_path, capsys):
    repo = a_fork(tmp_path, monkeypatch)
    a_run(monkeypatch, tmp_path, finished=False)
    class_change(repo, "agent.py")
    update(repo)
    class_change(repo, "my_loop.py")
    update(repo)
    capsys.readouterr()
    full_run(monkeypatch, tmp_path, always_supported)
    assert "Carrying on: the 40 saved results" in capsys.readouterr().out


@pytest.mark.parametrize("finished", [False, True])
@pytest.mark.parametrize("change", ["instructions.md after the update", "my_loop.py before the update",
                                    "instructions.md between two updates"])
def test_a_change_of_the_students_own_stops_or_notes_as_before(monkeypatch, tmp_path, capsys, change,
                                                                finished):
    repo = a_fork(tmp_path, monkeypatch)
    a_run(monkeypatch, tmp_path, finished)
    if change == "my_loop.py before the update":
        (repo / "my_loop.py").write_text("# the loop\nY = 3\n")
    class_change(repo, "agent.py")
    update(repo)
    if change == "instructions.md between two updates":
        (repo / "instructions.md").write_text("Check every part of the claim.\n")
        class_change(repo, "my_loop.py")
        update(repo)
    if change == "instructions.md after the update":
        (repo / "instructions.md").write_text("Check every part of the claim.\n")
    as_before(monkeypatch, tmp_path, capsys, finished)


@pytest.mark.parametrize("finished", [False, True])
@pytest.mark.parametrize("where", ["a folder that is not a repository", "no git program",
                                   "a repository with no Update", "a detached HEAD", "a shallow clone",
                                   "a broken repository"])
def test_anything_unusual_behaves_as_before(monkeypatch, tmp_path, capsys, where, finished):
    repo = a_fork(tmp_path, monkeypatch)
    if where == "a folder that is not a repository":
        for name in ("instructions.md", "agent.py", "wiki.py", "my_loop.py"):
            (tmp_path / name).write_text((repo / name).read_text())
        repo = tmp_path
        monkeypatch.setattr(evaluate, "HERE", repo)
    a_run(monkeypatch, tmp_path, finished)
    if where == "a repository with no Update":
        (repo / "agent.py").write_text("# the agent, reworded\nX = 1\n")
        git(repo, "commit", "-q", "-am", "A comment in agent.py")
    elif where == "a folder that is not a repository":
        (repo / "agent.py").write_text("# the agent, reworded\nX = 1\n")
    else:
        class_change(repo, "agent.py")
        update(repo)
    if where == "no git program":
        monkeypatch.setenv("PATH", str(tmp_path / "nowhere"))
    elif where == "a detached HEAD":
        git(repo, "checkout", "-q", "--detach")
    elif where == "a shallow clone":
        (repo / ".git" / "shallow").write_text(git(repo, "rev-list", "--max-parents=0", "HEAD"))
    elif where == "a broken repository":
        (repo / ".git" / "HEAD").write_text("not a reference\n")
    assert evaluate.versions_before_updates() == set()
    as_before(monkeypatch, tmp_path, capsys, finished)


def test_a_run_with_nothing_from_an_earlier_agent_never_asks_git(monkeypatch, tmp_path):
    a_fork(tmp_path, monkeypatch)
    a_run(monkeypatch, tmp_path, finished=False)
    monkeypatch.setattr(evaluate.subprocess, "run", lambda *a, **k: pytest.fail("asked git"))
    full_run(monkeypatch, tmp_path, always_supported)


def test_the_update_commit_is_the_one_the_page_makes():
    source = (Path(__file__).parent.parent / "workbench" / "updates.py").read_text()
    assert f'"--no-edit", "-m", "{evaluate.UPDATE}"' in source


def test_a_run_with_a_failed_claim_has_no_report(monkeypatch, tmp_path, capsys):
    def one_fails(claim):
        if claim == "claim 3":
            raise wiki.RateLimited("too many requests")
        return always_supported(claim)

    out_dir = tmp_path / "run"
    out_dir.mkdir()
    (out_dir / "report.txt").write_text("left over from an earlier run\n")
    monkeypatch.setitem(evaluate.METHODS, "agent", one_fails)
    run_main(monkeypatch, tmp_path)
    assert "run the same command again" in capsys.readouterr().out
    assert not (out_dir / "report.txt").exists()
    assert len((out_dir / "agent.jsonl").read_text().splitlines()) == 11


def test_runs_with_no_verdict_finish_the_run_and_the_line_says_where_the_viewer_lists_them(monkeypatch, tmp_path,
                                                                                          capsys):
    """The flow simulations of Nov 14: the report's last line said "out of steps" (the homework says
    lookups) and "Look for them in the saved files." It now names the section of the run's page in
    the results viewer that lists them, by its title in viewer/app.py, and the run is finished."""
    def two_without(claim):
        result = always_supported(claim)
        if claim in ("claim 2", "claim 5"):
            result["verdict"] = None
        return result

    monkeypatch.setitem(evaluate.METHODS, "agent", two_without)
    _, out_dir = run_main(monkeypatch, tmp_path)
    printed = capsys.readouterr().out
    line = ("2 runs gave no verdict (for example a refusal, or out of lookups). They count as wrong. "
            "The results viewer lists them on this run's page, under "
            "\"Claims with no verdict, or that stopped with an error\".")
    assert line in printed
    assert (out_dir / "report.txt").read_text().rstrip().endswith(line)    # finished: report.txt saved
    viewer = (Path(__file__).parent.parent / "viewer" / "app.py").read_text(encoding="utf-8")
    assert "<h3>Claims with no verdict, or that stopped with an error</h3>" in viewer
    assert "out of steps" not in printed and "saved files" not in printed


def test_lookup_with_no_log_prints_but_does_not_add_to_the_record(monkeypatch, tmp_path, capsys):
    import lookup
    monkeypatch.setattr(lookup, "load_dotenv", lambda: None)  # leave your own .env alone
    monkeypatch.setattr(lookup, "LOG", tmp_path / "lookups.jsonl")
    monkeypatch.setattr(wiki, "read", lambda title, section=None: f"Page: {title}")
    monkeypatch.setattr(sys, "argv", ["lookup.py", "--no-log", "read", "Saint Paul, Minnesota"])
    lookup.main()
    printed = capsys.readouterr().out
    assert "Page: Saint Paul, Minnesota" in printed
    assert "lookups.jsonl" not in printed
    assert not (tmp_path / "lookups.jsonl").exists()


def test_the_agents_results_carry_the_limit_they_ran_under(monkeypatch, tmp_path, capsys):
    """A loop that does not warn the model can pass its limit within one reply (Nov 14), so the
    results viewer cannot tell the limit from the counts: each of the agent's results carries it."""
    monkeypatch.setitem(evaluate.METHODS, "agent", always_supported)
    monkeypatch.setitem(evaluate.METHODS, "no-tools", always_supported)
    monkeypatch.setattr(evaluate.agent, "MAX_STEPS", 9)
    evaluate.run_method("agent", ITEMS[:2], tmp_path, workers=1)
    evaluate.run_method("no-tools", ITEMS[:2], tmp_path, workers=1)
    rows = [json.loads(line) for line in (tmp_path / "agent.jsonl").read_text().splitlines()]
    assert [row["max_steps"] for row in rows] == [9, 9]
    rows = [json.loads(line) for line in (tmp_path / "no-tools.jsonl").read_text().splitlines()]
    assert not any("max_steps" in row for row in rows)


def test_check_setup_says_what_is_missing_and_never_prints_the_key(monkeypatch, tmp_path, capsys):
    import check_setup
    env = tmp_path / ".env"
    monkeypatch.setattr(check_setup, "ENV", env)
    monkeypatch.setattr(check_setup, "load_dotenv", lambda path: None)  # leave this process's environment alone
    monkeypatch.setattr(check_setup, "wikipedia_problem", lambda: None)
    monkeypatch.setattr(check_setup, "key_problem", lambda: None)
    saved = tmp_path / "runs" / "part0" / "setup-check.txt"  # what marks step 0a as done
    monkeypatch.setattr(check_setup, "SAVED", saved)

    assert check_setup.main() == 1  # no .env yet
    assert "There is no .env file" in capsys.readouterr().out
    assert not saved.exists()

    env.write_text("ANTHROPIC_API_KEY=sk-ant-not-a-real-key\nWIKIPEDIA_CONTACT=\n")
    assert check_setup.main() == 1  # the email is missing
    printed = capsys.readouterr().out
    assert "ok         ANTHROPIC_API_KEY is filled in" in printed
    assert "NOT READY  WIKIPEDIA_CONTACT is empty" in printed
    assert "Not ready yet" in printed
    assert "sk-ant" not in printed
    assert not saved.exists()

    env.write_text("ANTHROPIC_API_KEY=sk-ant-not-a-real-key\nWIKIPEDIA_CONTACT=student@macalester.edu\n")
    assert check_setup.main() == 0
    printed = capsys.readouterr().out
    assert "Everything is ready." in printed
    assert "sk-ant" not in printed and "student@macalester.edu" not in printed
    kept = saved.read_text()  # saved only when everything is ready, with nothing from .env in it
    assert "Everything is ready." in kept and "the Claude API accepted your key" in kept
    assert "sk-ant" not in kept and "student@macalester.edu" not in kept

    monkeypatch.setattr(check_setup, "key_problem", lambda: "the Claude API did not accept the key.")
    assert check_setup.main() == 1  # a key that the API refuses
    assert "NOT READY  the Claude API did not accept the key." in capsys.readouterr().out
    assert not saved.exists()  # an earlier "ready" does not outlive a failed check

    env.write_text("ANTHROPIC_API_KEY=\nWIKIPEDIA_CONTACT=\n")
    assert check_setup.main() == 1  # both lines empty: still five lines, one for each thing checked
    printed = capsys.readouterr().out
    status = [line for line in printed.splitlines() if line.startswith(("ok ", "NOT READY "))]
    assert len(status) == 5
    assert "NOT READY  the Claude API was not asked, because ANTHROPIC_API_KEY is empty" in printed


class Reply:
    """What requests.get() returns, for a scripted Wikipedia."""

    def __init__(self, status, data=None, retry_after=None):
        self.status_code = status
        self.headers = {"Retry-After": retry_after} if retry_after else {}
        self.data = data

    def json(self):
        return self.data

    def raise_for_status(self):
        pass


STEAKHOUSE = {"query": {"search": [{
    "title": "Vic & Anthony's Steakhouse",
    "snippet": 'Vic &amp; Anthony&#039;s is a <span class="searchmatch">steakhouse</span>'}]}}


def scripted_wikipedia(monkeypatch, tmp_path, replies):
    replies = list(replies)
    monkeypatch.setattr(wiki, "CACHE_DIR", tmp_path)
    monkeypatch.setattr(wiki.requests, "get", lambda url, **kwargs: replies.pop(0))
    monkeypatch.setattr(wiki.time, "sleep", lambda seconds: None)
    monkeypatch.setattr(wiki, "_warned", True)       # the warning about the contact is tested elsewhere
    monkeypatch.setattr(wiki, "_said_waiting", 0.0)  # as at the start of a run


def test_a_wait_for_wikipedia_is_announced_once(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("WIKIPEDIA_CONTACT", raising=False)
    scripted_wikipedia(monkeypatch, tmp_path, [
        Reply(429, retry_after="7"), Reply(429, retry_after="7"), Reply(200, STEAKHOUSE)])
    wiki.search("steakhouse")
    said = capsys.readouterr().err
    assert said.count("Wikipedia asked this program to slow down") == 1
    assert "waiting 7 seconds" in said
    assert "WIKIPEDIA_CONTACT" in said  # not set, so it says how to get your own allowance


def test_the_wait_notice_leaves_out_the_contact_when_it_is_set(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("WIKIPEDIA_CONTACT", "student@macalester.edu")
    scripted_wikipedia(monkeypatch, tmp_path, [Reply(429, retry_after="3"), Reply(200, STEAKHOUSE)])
    wiki.search("steakhouse")
    said = capsys.readouterr().err
    assert "Wikipedia asked this program to slow down" in said
    assert "WIKIPEDIA_CONTACT" not in said


def test_search_results_show_plain_characters(monkeypatch, tmp_path):
    scripted_wikipedia(monkeypatch, tmp_path, [Reply(200, STEAKHOUSE)])
    assert "1. Vic & Anthony's Steakhouse: Vic & Anthony's is a steakhouse" in wiki.search("steakhouse")


def test_a_reply_with_unescaped_quote_marks_keeps_its_verdict():
    import baselines
    reply = ('{"verdict": "doesn\'t say", "explanation": "The text names the composer of '
             '"Persian Surgery Dervishes" but does not give his birthday."}')
    with pytest.raises(json.JSONDecodeError):
        json.loads(reply)  # this is the kind of reply that used to lose its verdict
    verdict, explanation = baselines._parse(reply)
    assert verdict == "doesn't say"
    assert explanation == ('The text names the composer of "Persian Surgery Dervishes" '
                           "but does not give his birthday.")


def test_a_reply_that_is_valid_json_is_read_as_before():
    import baselines
    fenced = '```json\n{"verdict": "refuted", "explanation": "The page says 1940."}\n```'
    assert baselines._parse(fenced) == ("refuted", "The page says 1940.")
    other_order = '{"explanation": "The page says "1935".", "verdict": "supported"}'
    assert baselines._parse(other_order) == ("supported", 'The page says "1935".')


def test_a_reply_with_no_verdict_still_gives_none():
    import baselines
    assert baselines._parse("I can't help with that.") == (None, "I can't help with that.")
    assert baselines._parse('{"verdict": "maybe", "explanation": "x"}') == (None, "x")
