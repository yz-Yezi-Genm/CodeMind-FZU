"""Run Beta integration tests with the checked-out rules and Retriever."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys

from scripts.verify_alpha_upstream_integration import agent_source_state


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/assignment-03/beta/evidence"
SOURCES = (
    "backend/services/alpha_business_rules.py",
    "backend/retrieval/local.py",
    "backend/retrieval/alpha_corpus.py",
)


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    before = agent_source_state()
    ref = "origin/main"
    main_commit = before["main_commit"]
    records = []
    for source in SOURCES:
        content = subprocess.check_output(["git", "show", f"{main_commit}:{source}"], cwd=ROOT)
        expected = content.replace(b"\r\n", b"\n")
        checked_out = (ROOT / source).read_bytes().replace(b"\r\n", b"\n")
        if checked_out != expected:
            raise RuntimeError(f"Checked-out module differs from {ref}: {source}")
        records.append({
            "ref": ref,
            "commit": main_commit,
            "source": source,
            "sha256": sha256(expected).hexdigest(),
        })

    command = [
        sys.executable,
        "-X",
        "utf8",
        "-m",
        "unittest",
        "tests.test_agent_workflow_qwen.MergedRulesRetrieverIntegrationTests",
        "-v",
    ]
    process = subprocess.run(
        command,
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=dict(os.environ, PYTHONIOENCODING="utf-8"),
    )
    if before["source_sha256_lf"] != agent_source_state()["source_sha256_lf"]:
        raise RuntimeError("Agent sources changed during Beta upstream tests")

    output = process.stdout + process.stderr
    (OUTPUT / "upstream-integration.txt").write_text(output, encoding="utf-8")
    (OUTPUT / "upstream-integration.json").write_text(
        json.dumps(
            {
                "time_asia_shanghai": datetime.now(
                    timezone(timedelta(hours=8))
                ).isoformat(),
                "agent_commit": subprocess.check_output(
                    ["git", "rev-parse", "HEAD"],
                    cwd=ROOT,
                    text=True,
                ).strip(),
                "agent_worktree_changes_included": True,
                "main_commit": main_commit,
                "agent_source_state": before,
                "sources": records,
                "command": command,
                "exit_code": process.returncode,
                "scope": (
                    "Beta regression against latest merged main business rules, "
                    "approved loader and BM25 metadata contract; synthetic corpus; "
                    "mock Qwen HTTP. No real model or formal policy acceptance."
                ),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    print(output)
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
