"""Capture actual test/demo outputs, exit codes and local environment metadata."""
from datetime import datetime, timedelta, timezone
from importlib import metadata
import json
import os
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/assignment-03/alpha/evidence"


def main() -> int:
    OUTPUT.mkdir(parents=True, exist_ok=True)
    env = {**os.environ, "PYTHONIOENCODING": "utf-8"}
    started = datetime.now(timezone(timedelta(hours=8))).isoformat()
    packages = sorted(f"{dist.metadata['Name']}=={dist.version}" for dist in metadata.distributions())
    (OUTPUT / "requirements-tested.txt").write_text("\n".join(packages) + "\n", encoding="utf-8")
    results = []
    for name, args in [
        ("unittest", ["-m", "unittest", "discover", "-s", "tests", "-v"]),
        ("demo", ["-m", "examples.agent_workflow_demo"]),
    ]:
        process = subprocess.run(
            [sys.executable, *args], cwd=ROOT, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8",
        )
        (OUTPUT / f"{name}.txt").write_text(process.stdout, encoding="utf-8")
        results.append({"name": name, "args": [sys.executable, *args], "exit_code": process.returncode})
        print(f"{name}: exit_code={process.returncode}")
    info = {
        "started_at_asia_shanghai": started,
        "finished_at_asia_shanghai": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "python": sys.version,
        "platform": platform.platform(),
        "base_commit": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        "branch": subprocess.check_output(["git", "branch", "--show-current"], cwd=ROOT, text=True).strip(),
        "scope": "Offline fake Retriever/LLM only; no real Qwen or KB integration.",
        "runs": results,
    }
    (OUTPUT / "environment.json").write_text(json.dumps(info, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return 1 if any(result["exit_code"] for result in results) else 0


if __name__ == "__main__":
    raise SystemExit(main())
