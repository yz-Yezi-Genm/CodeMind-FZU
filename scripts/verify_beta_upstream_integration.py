"""Run the Beta upstream integration suite against a fixed main snapshot."""
from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory

from scripts.verify_alpha_upstream_integration import agent_source_state


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/assignment-03/beta/evidence"
SOURCES = (
    ("backend/services/alpha_business_rules.py", "alpha_business_rules.py"),
    ("backend/retrieval/local.py", "retrieval/local.py"),
    ("backend/retrieval/alpha_corpus.py", "retrieval/alpha_corpus.py"),
)


@contextmanager
def main_snapshot(ref: str):
    """Yield read-only source blobs from the selected merged main commit."""
    commit = subprocess.check_output(
        ["git", "rev-parse", ref],
        cwd=ROOT,
        text=True,
    ).strip()
    records = []
    with TemporaryDirectory(prefix="beta-upstream-") as temporary:
        snapshot = Path(temporary)
        for source, target in SOURCES:
            content = subprocess.check_output(
                ["git", "show", f"{commit}:{source}"],
                cwd=ROOT,
            )
            destination = snapshot / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            records.append(
                {
                    "ref": ref,
                    "commit": commit,
                    "source": source,
                    "sha256": sha256(content).hexdigest(),
                }
            )
        yield temporary, commit, records


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    before = agent_source_state()
    with main_snapshot("origin/main") as (temporary, main_commit, records):
        command = [
            sys.executable,
            "-X",
            "utf8",
            "-m",
            "unittest",
            "tests.test_agent_workflow_qwen.UpstreamRulesRetrieverIntegrationTests",
            "-v",
        ]
        process = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            encoding="utf-8",
            env=dict(
                os.environ,
                ALPHA_UPSTREAM_SNAPSHOT=temporary,
                PYTHONIOENCODING="utf-8",
            ),
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
