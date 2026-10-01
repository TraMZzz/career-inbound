import json
import subprocess

from ci_tools.check_cli import main, run_checks


def make_repo(tmp_path, *, filled=True):
    subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
    (tmp_path / "README.md").write_text("# Demo\n")
    rules = "\n".join(f"- rule {i}" for i in range(12)) if filled else "TODO(starter): describe stack\n"
    (tmp_path / "AGENTS.md").write_text(rules)
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "project.md").write_text("# Project\nProblem: x\nМетрика успіху: 80% діагнозів\nUser: on-call\n")
    (docs / "ai-log.md").write_text("# AI log\n- delegated x\n- agent broke y, caught by test\n")
    return tmp_path


def by_title(items):
    return {i.title: i for i in items}


def test_stage1_passes_for_filled_repo(tmp_path):
    repo = make_repo(tmp_path)
    items = run_checks(repo, 1, None)
    assert all(i.ok for i in items if i.kind == "REQ"), [i for i in items if i.kind == "REQ" and not i.ok]
    assert main(["--stage", "1", "--path", str(repo)]) == 0


def test_stage1_flags_starter_placeholders(tmp_path):
    repo = make_repo(tmp_path, filled=False)
    items = by_title(run_checks(repo, 1, None))
    rules = items["agent rules file, specific to the project"]
    assert rules.ok is False and "TODO(starter)" in rules.detail


def test_stage2_golden_size_and_edge(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "evals").mkdir()
    rows = [{"id": f"g{i}", "input": "x", "expect": {"contains": ["a"]}} for i in range(5)]
    (repo / "evals" / "golden.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    items = by_title(run_checks(repo, 2, None))
    assert items["evals/golden.jsonl: valid, 15-30 cases (15+ later), each with expectations"].ok is False
    assert items["edge / bad-input cases in the golden set"].ok is False
    # without --url the contract check is downgraded to a manual item, not a failure
    assert items["service answers /health and /ask per contract"].kind == "MANUAL"


def test_secret_scan_finds_tracked_key(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "config.py").write_text('KEY = "sk-ant-api03-' + "A" * 30 + '"\n')
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    items = by_title(run_checks(repo, 4, None))
    assert items["no secrets in tracked files"].ok is False
    assert "config.py" in items["no secrets in tracked files"].detail


def test_readme_story_needs_real_sections(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "README.md").write_text("# Demo\nWe talk about problems, architecture, p95, cost and evals.\n")
    item = by_title(run_checks(repo, 7, None))
    story = next(v for k, v in item.items() if k.startswith("README tells the story"))
    assert story.ok is False and "## problem" in story.detail
    (repo / "README.md").write_text(
        "# Demo\n## Проблема\nx\n## Архітектура\n```mermaid\ngraph TD; a-->b\n```\n## Рішення і компроміси\n"
        "p95 1.2 s, $/1000 = 3.1, evals 0.85\n## Безпека\nx\n"
    )
    item = by_title(run_checks(repo, 7, None))
    assert all(v.ok for k, v in item.items() if k.startswith("README"))


def test_tests_are_found_only_among_tracked_files(tmp_path):
    repo = make_repo(tmp_path)
    venv = repo / ".venv-3.12" / "lib" / "site-packages"
    venv.mkdir(parents=True)
    (venv / "test_cases.py").write_text("def test_x(): pass\n")
    (repo / ".gitignore").write_text(".venv-3.12/\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    item = by_title(run_checks(repo, 2, None))["regular tests for non-AI code"]
    assert item.ok is False
    (repo / "src").mkdir()
    (repo / "src" / "OrderServiceTest.java").write_text("class OrderServiceTest {}\n")
    subprocess.run(["git", "add", "-A"], cwd=repo, check=True)
    assert by_title(run_checks(repo, 2, None))["regular tests for non-AI code"].ok is True


def test_project_in_a_subdirectory_of_a_repo(tmp_path):
    """Monorepo: ci-check --path demo must work although demo/ has no .git of its own."""
    make_repo(tmp_path)
    sub = tmp_path / "demo"
    sub.mkdir()
    for name in ("README.md", "AGENTS.md"):
        (sub / name).write_text((tmp_path / name).read_text())
    (sub / "docs").mkdir()
    for name in ("project.md", "ai-log.md"):
        (sub / "docs" / name).write_text((tmp_path / "docs" / name).read_text())
    items = run_checks(sub, 1, None)
    assert all(i.ok for i in items if i.kind == "REQ"), [i for i in items if i.kind == "REQ" and not i.ok]


def test_golden_upper_limit_only_at_stage_2(tmp_path):
    repo = make_repo(tmp_path)
    (repo / "evals").mkdir()
    rows = [
        {"id": f"g{i}", "input": "x", "expect": {"contains": ["a"]}, "tags": ["edge"] if i < 2 else []}
        for i in range(35)
    ]
    (repo / "evals" / "golden.jsonl").write_text("\n".join(json.dumps(r) for r in rows))
    title = "evals/golden.jsonl: valid, 15-30 cases (15+ later), each with expectations"
    assert by_title(run_checks(repo, 2, None))[title].ok is False
    assert by_title(run_checks(repo, 5, None))[title].ok is True


def test_stage0_needs_a_running_service(tmp_path):
    repo = make_repo(tmp_path)
    items = by_title(run_checks(repo, 0, None))
    assert items["service answers GET /health"].ok is False  # week 0 without --url fails
    later = by_title(run_checks(repo, 1, None))
    assert later["service answers GET /health"].kind == "MANUAL"  # CI without a server: not a failure
    assert main(["--stage", "1", "--path", str(repo)]) == 0
