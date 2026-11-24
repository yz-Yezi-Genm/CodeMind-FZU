"""Read-only check of the nine-package technical handoff (not approval).

python -m knowledge_base.processing.check_beta_policy_handoff
The legacy Qinghe mixed package remains a source baseline, not a handoff item.
"""
import asyncio
import inspect
import json

from backend.contracts import DocumentPackage, RetrievalRequest
from backend.contracts.protocols import Retriever
from backend.retrieval.alpha_corpus import load_approved_alpha_retriever
from backend.retrieval.local import LocalBM25Retriever
from backend.services.alpha_business_rules import RESOURCE_CATEGORY_MAP, RES_LAB, RES_INTRO
from knowledge_base.processing import build_beta_policy_review as baseline
from knowledge_base.processing import build_qinghe_b8 as b8

SELECTION = (
    ("S1", "competition", 224), ("S1", "innovation", 86),
    ("S2", "scholarship", 59), ("S2", "college-scholarship", 33),
    ("S2", "xinghuo", 35), ("S3", "recommendation", 20), ("S3", "retest", 9),
    ("S4", "qinghe-r3", 24), ("S4", "qinghe-r4", 24),
)


def selected_packages():
    for domain, key, count in SELECTION:
        folder = b8.OUTPUT if domain == "S4" else baseline.OUTPUT
        path = folder / (key + ".json")
        package = DocumentPackage.model_validate_json((baseline.ROOT / path).read_bytes())
        if len(package.chunks) != count:
            raise ValueError(f"Unexpected handoff chunk count: {key}")
        if (package.metadata.retrieval_status.value != "blocked"
            or (package.metadata.temporal_notes or {}).get("human_approved") is not False):
            raise ValueError(f"Handoff must remain unapproved and blocked: {key}")
        yield domain, key, path, package


async def check():
    for name in ("get_document_metadata", "get_parsed_chunk"):
        if (inspect.signature(getattr(Retriever, name)).parameters.keys()
            != inspect.signature(getattr(LocalBM25Retriever, name)).parameters.keys()
            or inspect.iscoroutinefunction(getattr(LocalBM25Retriever, name))):
            raise ValueError("Retriever lookup signature differs from merged #51 contract")
    if (RESOURCE_CATEGORY_MAP.get(b8.CATEGORIES["R3"]) != RES_LAB
        or RESOURCE_CATEGORY_MAP.get(b8.CATEGORIES["R4"]) != RES_INTRO):
        raise ValueError("Qinghe categories differ from merged #45 resource map")
    store = LocalBM25Retriever(file_root=baseline.ROOT)
    rows, totals, seen = [], {"S1": 0, "S2": 0, "S3": 0, "S4": 0}, set()
    for domain, key, path, package in selected_packages():
        result = await store.index_document(package)
        ids = [i for i, (version, _) in store._chunk_index.items() if version == result.version_id]
        if (result.version_id in seen or result.status.value != "indexed" or result.warnings
            or result.chunk_count != len(package.chunks) or result.indexed_count != len(package.chunks)
            or len(ids) != len(package.chunks)):
            raise ValueError(f"Incomplete or duplicate handoff index: {key}")
        seen.add(result.version_id)
        if store.get_document_metadata(result.version_id) is not None or any(store.get_parsed_chunk(i) is not None for i in ids):
            raise ValueError(f"Blocked lookup leaked: {key}")
        totals[domain] += len(ids)
        rows.append({"key": key, "domain": domain, "package": path.as_posix(),
                     "version_id": str(result.version_id), "chunks": len(ids),
                     "timeliness": package.metadata.timeliness_verification_status.value,
                     "retrieval_status": "blocked", "human_approved": False,
                     "metadata_lookup": None, "hidden_chunk_lookups": len(ids)})
    if totals != {"S1": 310, "S2": 127, "S3": 29, "S4": 48} or len(rows) != 9:
        raise ValueError("Handoff must be 9 packages / 514 chunks, excluding old Qinghe")
    hits = {}
    for direction in ("COMPETITION_RESEARCH", "POLICY_AFFAIRS", "EDUCATION_CAREER", "COLLEGE_RESOURCES"):
        hits[direction] = len(await store.retrieve(RetrievalRequest(query="竞赛 奖学金 推免 青禾 实验室", business_direction_code=direction)))
    if any(hits.values()):
        raise ValueError("Blocked handoff leaked into retrieval")
    loader_checks = []
    for folder in (baseline.OUTPUT, b8.OUTPUT, baseline.ROOT / "knowledge_base/processed/alpha/approved"):
        _, report = await load_approved_alpha_retriever(corpus_dir=baseline.ROOT / folder, file_root=baseline.ROOT, allow_missing=False)
        if report.loaded_packages or report.total_indexed_chunks:
            raise ValueError("Formal corpus loader accepted unapproved packages")
        loader_checks.append({"directory": (baseline.ROOT / folder).relative_to(baseline.ROOT).as_posix(),
                              "loaded_packages": 0, "indexed_chunks": 0,
                              "skipped_packages": len(report.skipped_packages)})
    approved = baseline.ROOT / "knowledge_base/processed/alpha/approved"
    if [p for p in approved.rglob("*.json") if p.name not in {"manifest.json", "summary.json"}]:
        raise ValueError("Expected zero formal approved package files")
    return {"packages": 9, "chunks": 514, "domain_chunks": totals, "enabled_packages": 0,
            "human_approved_packages": 0, "approved_packages": 0,
            "formal_hits": hits, "loader_checks": loader_checks, "index_results": rows,
            "compatibility": {"pr45_category_map": "matched", "pr51_lookup_signatures": "matched"}}


def main():
    # b8.check() owns its synchronous asyncio boundary; run it before this loop.
    print(json.dumps(run_check(), ensure_ascii=False, indent=2))


def run_check():
    # This checks the original baseline and B8 before starting the async audit.
    # No policy outputs or approval metadata are regenerated.
    b8.check()
    return asyncio.run(check())


if __name__ == "__main__":
    main()
