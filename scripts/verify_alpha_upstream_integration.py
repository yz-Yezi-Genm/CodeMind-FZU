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


@contextmanager
def upstream_snapshot():
    """Yield immutable Git source snapshots and their provenance."""
    records = []
    with TemporaryDirectory(prefix="alpha-upstream-") as temporary:
        snapshot = Path(temporary)
        for ref, source, target in SOURCES:
            commit = subprocess.check_output(["git", "rev-parse", ref], cwd=ROOT, text=True).strip()
            content = subprocess.check_output(["git", "show", f"{commit}:{source}"], cwd=ROOT)
            destination = snapshot / target
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            records.append({"ref": ref, "commit": commit, "source": source,
                            "sha256": sha256(content).hexdigest()})
        yield temporary, records


def main():
    OUTPUT.mkdir(parents=True, exist_ok=True)
    with upstream_snapshot() as (temporary, records):
        command = [sys.executable, "-X", "utf8", "-m", "unittest",
                   "tests.test_agent_workflow_qwen.UpstreamRulesRetrieverIntegrationTests", "-v"]
        process = subprocess.run(command, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
            env=dict(os.environ, ALPHA_UPSTREAM_SNAPSHOT=temporary, PYTHONIOENCODING="utf-8"))
    output = process.stdout + process.stderr
    (OUTPUT / "upstream-integration.txt").write_text(output, encoding="utf-8")
    (OUTPUT / "upstream-integration.json").write_text(json.dumps({
        "time_asia_shanghai": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "agent_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "agent_worktree_changes_included": True,
        "sources": records, "command": command, "exit_code": process.returncode,
        "scope": "Unmodified upstream rules, BM25 metadata lookups and approved loader; current Agent; synthetic corpus; mock Qwen HTTP. No paid model or approved real policy acceptance.",
    }, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(output)
    return process.returncode


if __name__ == "__main__":
    raise SystemExit(main())
