"""Exercise the Alpha ingestion and retrieval protocols without network access."""

import argparse
import asyncio
import json
from pathlib import Path

from backend.contracts import (
    DocumentPackage, IndexingStatus, KnowledgeIndexer, RetrievalRequest, Retriever,
)
from backend.retrieval import LocalBM25Retriever

ROOT = Path(__file__).resolve().parents[1]
SYNTHETIC_PACKAGES = ROOT / "docs/assignment-03/alpha/examples/retrieval-synthetic-packages.json"
REAL_CASES = (
    ("competition-recognition-2026", "竞赛认定"),
    ("scholarship-2026", "奖学金"),
    ("recommendation-eligibility-2027", "推免"),
)


async def demo(real: bool) -> int:
    store = LocalBM25Retriever(file_root=ROOT if real else None)
    indexer: KnowledgeIndexer = store
    retriever: Retriever = store
    if real:
        directory = ROOT / "knowledge_base/processed/alpha"
        packages = [
            DocumentPackage.model_validate_json((directory / f"{stem}.json").read_bytes())
            for stem, _ in REAL_CASES
        ]
        requests = [RetrievalRequest(query=query) for _, query in REAL_CASES]
    else:
        packages = [
            DocumentPackage.model_validate(item)
            for item in json.loads(SYNTHETIC_PACKAGES.read_text(encoding="utf-8"))
        ]
        requests = [
            RetrievalRequest(query="星桥奖学金申请需要什么", category_name="综评与奖学金", top_k=2),
            RetrievalRequest(query="星桥奖学金申请需要什么", category_name="综评与奖学金", top_k=1),
            RetrievalRequest(query="云帆竞赛认定", business_direction_code="COMPETITION_RESEARCH"),
            RetrievalRequest(query="月面推免"),
            RetrievalRequest(query="量子纠缠"),
        ]

    summaries = []
    for package in packages:
        indexed = await indexer.index_document(package)
        summaries.append({
            "record_code": package.metadata.record_code,
            "retrieval_status": package.metadata.retrieval_status,
            "file_count": len(package.files),
            **indexed.model_dump(mode="json"),
        })
    queries = []
    for request in requests:
        chunks = await retriever.retrieve(request)
        queries.append({
            "request": request.model_dump(mode="json", exclude_none=True),
            "hits": [
                {**chunk.model_dump(mode="json"), "score": round(chunk.score, 6)}
                for chunk in chunks
            ],
        })
    print(json.dumps({
        "dataset": "real_blocked" if real else "synthetic",
        "index": summaries,
        "queries": queries,
    }, ensure_ascii=False, indent=2))
    return int(any(item["status"] == IndexingStatus.FAILED for item in summaries))


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--real", action="store_true", help="validate the three blocked parser packages")
    raise SystemExit(asyncio.run(demo(parser.parse_args().real)))
