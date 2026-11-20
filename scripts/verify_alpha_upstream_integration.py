"""Run PR #35/#36 implementations against this checkout without merging them."""
from datetime import datetime, timedelta, timezone
from contextlib import contextmanager
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/assignment-03/alpha/evidence/agent-integration"
SOURCES = (
    ("origin/feat/alpha-business-rules-runtime", "backend/services/alpha_business_rules.py", "alpha_business_rules.py"),
    ("origin/feat/alpha-retrieval-loader", "backend/retrieval/local.py", "retrieval/local.py"),
    ("origin/feat/alpha-retrieval-loader", "backend/retrieval/alpha_corpus.py", "retrieval/alpha_corpus.py"),
)


def agent_source_state():
    """Content identity survives the user's later commit without inventing a SHA.

    Normalize Git text line endings so a Windows checkout and its committed
    blobs have the same fingerprint. Never inspect local .env files.
    """
    paths = subprocess.check_output(["git", "ls-files", "--cached", "--others", "--exclude-standard",
        "--", "backend", "tests", "scripts", "examples", "knowledge_base/processing"], cwd=ROOT, text=True).splitlines()
    hashes = {}
    for name in sorted(set(paths)):
        path = ROOT / name
        if path.is_file() and (path.suffix == ".py" or path.name in {"requirements.txt", "requirements-dev.txt"}):
            hashes[name] = sha256(path.read_bytes().replace(b"\r\n", b"\n")).hexdigest()
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    main = subprocess.check_output(["git", "rev-parse", "origin/main"], cwd=ROOT, text=True).strip()
    merge_head = subprocess.run(["git", "rev-parse", "-q", "--verify", "MERGE_HEAD"],
        cwd=ROOT, capture_output=True, text=True)
    requirements = {"main_with_pr35": "a87182c", "pr31": "4282ea7"}
    pending = merge_head.stdout.strip() if merge_head.returncode == 0 else None
    included = {}
    for label, ref in requirements.items():
        commit = subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True).strip()
        included[label] = {"commit": commit,
            "in_HEAD": subprocess.run(["git", "merge-base", "--is-ancestor", commit, head], cwd=ROOT).returncode == 0,
            "in_pending_merge": bool(pending and subprocess.run(
                ["git", "merge-base", "--is-ancestor", commit, pending], cwd=ROOT).returncode == 0)}
    return {"base_commit": head, "source_sha256_lf": hashes, "main_commit": main,
            "pending_merge_parent": pending, "required_merged_history": included,
            "record_scope": "Tested source contents; base_commit is not a claim that uncommitted edits are already committed"}


@contextmanager
def upstream_snapshot():
    """Yield immutable Git source snapshots and their provenance."""
    records = []
    commits = {}
    with TemporaryDirectory(prefix="alpha-upstream-") as temporary:
        snapshot = Path(temporary)
        for ref, source, target in SOURCES:
            if ref not in commits:
                commits[ref] = subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True).strip()
            commit = commits[ref]
            content = subprocess.check_output(["git", "show", f"{commit}:{source}"], cwd=ROOT)
            destination = snapshot / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            records.append({"ref": ref, "commit": commit, "source": source,
                            "sha256": sha256(content).hexdigest()})
        yield temporary, records


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    agent = agent_source_state()
    with upstream_snapshot() as (temporary, records):
        command = [sys.executable, "-X", "utf8", "-m", "unittest",
                   "tests.test_agent_workflow_qwen.UpstreamRulesRetrieverIntegrationTests", "-v"]
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            env=dict(os.environ, ALPHA_UPSTREAM_SNAPSHOT=temporary, PYTHONIOENCODING="utf-8"))
    if agent["source_sha256_lf"] != agent_source_state()["source_sha256_lf"]:
        raise RuntimeError("Agent sources changed during tests")
    output = process.stdout + process.stderr
    (OUTPUT / "upstream-integration.txt").write_text(output, encoding="utf-8")
    (OUTPUT / "upstream-integration.json").write_text(json.dumps({
        "time_asia_shanghai": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "agent_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "agent_worktree_changes_included": True,
        "agent_source_state": agent,
        "sources": records, "command": command, "exit_code": process.returncode,
        "scope": "Unmodified upstream rules, BM25 metadata lookups and approved loader; current Agent; synthetic corpus; mock Qwen HTTP. No paid model or approved real policy acceptance.",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
