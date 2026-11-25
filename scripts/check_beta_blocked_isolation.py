"""Read-only verification that all 9 Beta candidate packages (514 chunks) remain isolated.

Unlike legacy check_beta_policy_handoff.py (which assumes human_approved=False for all
pending-review items), this script reflects PR #56 (1060688) where 6 pending-review
packages carry scoped human_approved=True while retrieval_status stays blocked.

It verifies without modifying any policy files or approval flags:
1. All 9 packages / 514 chunks index cleanly offline via LocalBM25Retriever.
2. Every blocked package returns None for get_document_metadata() and get_parsed_chunk().
3. Formal retrieve() returns 0 hits across all 4 Beta business directions.
4. load_approved_alpha_retriever() loads 0 packages from pending-review/ and approved/.

Run from repository root:
    python -X utf8 -m scripts.check_beta_blocked_isolation
"""
from __future__ import annotations

import asyncio
import json

from backend.contracts import DocumentPackage, RetrievalRequest
from backend.retrieval.alpha_corpus import PROJECT_ROOT, load_approved_alpha_retriever
from backend.retrieval.local import LocalBM25Retriever

SELECTION: tuple[tuple[str, str, int], ...] = (
    ("S1", "knowledge_base/processed/alpha/pending-review/beta-2026-11-23/competition.json", 224),
    ("S1", "knowledge_base/processed/alpha/pending-review/beta-2026-11-23/innovation.json", 86),
    ("S2", "knowledge_base/processed/alpha/pending-review/beta-2026-11-23/scholarship.json", 59),
    ("S2", "knowledge_base/processed/alpha/pending-review/beta-2026-11-23/college-scholarship.json", 33),
    ("S2", "knowledge_base/processed/alpha/pending-review/beta-2026-11-23/xinghuo.json", 35),
    ("S3", "knowledge_base/processed/alpha/pending-review/beta-2026-11-23/recommendation.json", 20),
    ("S3", "knowledge_base/processed/alpha/pending-review/beta-2026-11-23/retest.json", 9),
    ("S4", "knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23/qinghe-r3.json", 24),
    ("S4", "knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23/qinghe-r4.json", 24),
)

DIRECTIONS: tuple[str, ...] = (
    "COMPETITION_RESEARCH",
    "POLICY_AFFAIRS",
    "EDUCATION_CAREER",
    "COLLEGE_RESOURCES",
)

LOADER_DIRS: tuple[str, ...] = (
    "knowledge_base/processed/alpha/pending-review/beta-2026-11-23",
    "knowledge_base/processed/alpha/pending-review/qinghe-b8-2026-11-23",
    "knowledge_base/processed/alpha/approved",
)


async def run_isolation_check() -> dict[str, object]:
    store = LocalBM25Retriever(file_root=PROJECT_ROOT)
    totals = {"S1": 0, "S2": 0, "S3": 0, "S4": 0}
    human_approved_true = 0

    for domain, rel, expected_chunks in SELECTION:
        pkg = DocumentPackage.model_validate_json((PROJECT_ROOT / rel).read_bytes())
        if pkg.metadata.retrieval_status.value != "blocked":
            raise RuntimeError(f"Expected blocked retrieval_status for {rel}")
        if (pkg.metadata.temporal_notes or {}).get("human_approved") is True:
            human_approved_true += 1

        result = await store.index_document(pkg)
        if result.status.value != "indexed" or result.warnings or result.indexed_count != expected_chunks:
            raise RuntimeError(f"Incomplete offline index for {rel}: {result}")

        chunk_ids = [cid for cid, (vid, _) in store._chunk_index.items() if vid == result.version_id]
        if len(chunk_ids) != expected_chunks:
            raise RuntimeError(f"Chunk count mismatch for {rel}: {len(chunk_ids)} != {expected_chunks}")
        if store.get_document_metadata(result.version_id) is not None:
            raise RuntimeError(f"Blocked metadata leaked for {rel}")
        if any(store.get_parsed_chunk(cid) is not None for cid in chunk_ids):
            raise RuntimeError(f"Blocked chunk leaked for {rel}")
        totals[domain] += len(chunk_ids)

    hits: dict[str, int] = {}
    for direction in DIRECTIONS:
        hits[direction] = len(
            await store.retrieve(
                RetrievalRequest(
                    query="竞赛 奖学金 推免 青禾 实验室",
                    business_direction_code=direction,
                )
            )
        )
    if any(hits.values()):
        raise RuntimeError(f"Blocked packages leaked into formal retrieval: {hits}")

    loader_checks = []
    for rel_dir in LOADER_DIRS:
        _, report = await load_approved_alpha_retriever(
            corpus_dir=PROJECT_ROOT / rel_dir,
            file_root=PROJECT_ROOT,
            allow_missing=False,
        )
        if report.loaded_packages or report.total_indexed_chunks != 0:
            raise RuntimeError(f"Formal loader accepted unapproved/blocked packages in {rel_dir}")
        loader_checks.append({
            "directory": rel_dir,
            "loaded": 0,
            "indexed_chunks": 0,
            "skipped": len(report.skipped_packages),
        })

    return {
        "packages": len(SELECTION),
        "chunks": sum(totals.values()),
        "domain_chunks": totals,
        "scoped_human_approved_true_but_blocked": human_approved_true,
        "enabled_packages": 0,
        "all_metadata_lookups_none": True,
        "all_chunk_lookups_none": True,
        "formal_hits": hits,
        "loader_checks": loader_checks,
    }


def main() -> None:
    print(json.dumps(asyncio.run(run_isolation_check()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
