"""Run the repository unittest suite and save a reproducible Alpha test record."""
from contextlib import redirect_stderr
from datetime import datetime, timezone
from importlib.metadata import version
import io
import json
import os
from pathlib import Path
import platform
import sys
import unittest

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "docs/assignment-03/alpha"


def main() -> int:
    previous = Path.cwd()
    stream = io.StringIO()
    try:
        os.chdir(ROOT)
        with redirect_stderr(stream):
            suite = unittest.defaultTestLoader.discover("tests")
            result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    finally:
        os.chdir(previous)
    OUTPUT.mkdir(parents=True, exist_ok=True)
    log = stream.getvalue().replace(str(ROOT), "<repository>")
    (OUTPUT / "document-processing-tests.txt").write_text(log, encoding="utf-8")
    record = {
        "command": "python -m scripts.check_document_processing",
        "tested_at": datetime.now(timezone.utc).isoformat(),
        "python": platform.python_version(), "platform": platform.system(),
        "dependencies": {name: version(name) for name in ("pydantic", "fastapi", "httpx", "starlette")},
        "tests_run": result.testsRun,
        "passed": result.testsRun - len(result.skipped) - len(result.failures) - len(result.errors),
        "failures": len(result.failures), "errors": len(result.errors),
        "skipped": [{"test": test.id(), "reason": reason} for test, reason in result.skipped],
        "successful": result.wasSuccessful(),
        "note": "实际执行全仓库unittest；解析通过不表示已做政策核验、入库或检索接入。",
    }
    (OUTPUT / "test-results.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(log)
    print(json.dumps(record, ensure_ascii=False, indent=2))
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    sys.exit(main())
