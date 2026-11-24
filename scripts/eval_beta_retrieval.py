"""Repeatable Beta S1-S4 BM25 retrieval evaluation over synthetic test packages.

Uses clearly marked synthetic packages (example.invalid) to verify:
- Formal approved-corpus loading & filtering (blocked / review_only / unapproved skipped)
- S1-S4 four-domain BM25 retrieval (Chinese + English, title + content, multi-direction)
- Retriever metadata & parsed-chunk traceability on the same instance
- Hit@1, Hit@3, and MRR metrics

Run from repository root:
    python -X utf8 -m scripts.eval_beta_retrieval
    python -X utf8 -m scripts.eval_beta_retrieval --corpus-dir knowledge_base/processed/alpha/approved
"""
from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from datetime import date
from hashlib import sha256
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

from backend.contracts import (
    DocumentMetadata,
    DocumentPackage,
    FileProcessingStatus,
    ParsedChunk,
    ParsedFile,
    RetrievalRequest,
)
from backend.retrieval.alpha_corpus import PROJECT_ROOT, load_approved_alpha_retriever


@dataclass(frozen=True)
class EvalQuery:
    query_id: str
    scenario: str
    query: str
    expected_record_code: str
    expected_chunk_no: int | None = None
    business_direction_code: str | None = None
    top_k: int = 3
    note: str = ""


SYNTHETIC_PACKAGES: tuple[dict[str, Any], ...] = (
    {
        "filename": "s1-competition-synthetic.json",
        "record_code": "BETA-SYN-S1-2026",
        "title": "【合成测试】2026年大学生学科竞赛认定与创新学分管理办法",
        "category_name": "竞赛与创新创业",
        "business_direction_codes": ["COMPETITION_RESEARCH", "POLICY_AFFAIRS"],
        "deadline_on": date(2026, 12, 15),
        "applicability_raw": {
            "适用年级": "全日制本科各年级",
            "适用专业": None,
            "适用对象": "本科生",
            "学院": "计算机与大数据学院",
            "适用届别": None,
        },
        "temporal_notes": {"human_approved": True, "synthetic_fixture": True},
        "retrieval_status": "enabled",
        "chunks": [
            (
                "第 1 章 第 3 条",
                '{"heading": "一、A类学科竞赛目录（ACM-ICPC/蓝桥杯）"}',
                "PDF 第 2 页",
                "ACM-ICPC 国际大学生程序设计竞赛与蓝桥杯全国软件和信息技术专业人才大赛列入学院A类重点竞赛目录，获国家级一等奖可认定创新创业学分4分。",
            ),
            (
                "第 2 章 第 7 条",
                '{"heading": "二、竞赛综测加分与认定流程"}',
                "PDF 第 4 页",
                "学生凭官方获奖证书原件在教务系统提交竞赛认定申请，审核通过后同步计入本学年综合测评科创加分。",
            ),
        ],
    },
    {
        "filename": "s2-scholarship-synthetic.json",
        "record_code": "BETA-SYN-S2-2026",
        "title": "【合成测试】2026年本科生国家奖学金与院级奖学金评选通知",
        "category_name": "综评与奖学金",
        "business_direction_codes": ["POLICY_AFFAIRS"],
        "deadline_on": date(2026, 10, 20),
        "applicability_raw": {
            "适用年级": "二年级及以上",
            "适用专业": None,
            "适用对象": "全日制本科生",
            "学院": "计算机与大数据学院",
            "适用届别": None,
        },
        "temporal_notes": {"human_approved": True, "synthetic_fixture": True},
        "retrieval_status": "enabled",
        "chunks": [
            (
                "第 1 节",
                '{"heading": "一、评选基本条件与GPA要求"}',
                "PDF 第 1 页",
                "申请国家奖学金须学习成绩GPA排名位列本专业前10%，且综合测评成绩排名同样位列前10%，无违纪记录。",
            ),
            (
                "第 2 节",
                '{"heading": "二、材料提交与截止时间"}',
                "PDF 第 2 页",
                "申请人须在2026年10月20日前提交奖学金申请表、加盖公章的成绩单以及竞赛获奖或社会实践证明材料。",
            ),
        ],
    },
    {
        "filename": "s3-recommendation-synthetic.json",
        "record_code": "BETA-SYN-S3-2027",
        "title": "【合成测试】2027届免试攻读研究生（推免）资格遴选细则",
        "category_name": "推免与升学",
        "business_direction_codes": ["EDUCATION_CAREER"],
        "deadline_on": date(2026, 9, 15),
        "applicability_raw": {
            "适用年级": "2023级",
            "适用专业": None,
            "适用对象": "全日制应届本科毕业生",
            "学院": "计算机与大数据学院",
            "适用届别": "2027届",
        },
        "temporal_notes": {"human_approved": True, "synthetic_fixture": True},
        "retrieval_status": "enabled",
        "chunks": [
            (
                "第 3 条",
                '{"heading": "一、推免基本学业与外语条件"}',
                "PDF 第 1 页",
                "申请推免研究生资格须前三年必修课程无不及格记录，全国大学英语六级 CET-6 成绩达到425分及以上。",
            ),
            (
                "第 8 条",
                '{"heading": "二、学术专长与竞赛加分说明"}',
                "PDF 第 3 页",
                "在CCF推荐会议发表论文或获A类竞赛国家级奖项的学生，可按学院细则申请推免学术专长综合加分。",
            ),
        ],
    },
    {
        "filename": "s4-lab-synthetic.json",
        "record_code": "BETA-SYN-S4-R3-2026",
        "title": "【合成测试】计算机与大数据学院实验室与科研团队导航指南",
        "category_name": "实验室与科研团队",
        "business_direction_codes": ["COLLEGE_RESOURCES"],
        "deadline_on": None,
        "applicability_raw": {
            "适用年级": "高年级本科生",
            "适用专业": None,
            "适用对象": "本科生与研究生",
            "学院": "计算机与大数据学院",
            "适用届别": None,
        },
        "temporal_notes": {"human_approved": True, "synthetic_fixture": True},
        "retrieval_status": "enabled",
        "chunks": [
            (
                "第 1 部分",
                '{"heading": "一、人工智能与大数据实验室及GPU算力申请"}',
                "网页 第 1 节",
                "人工智能与大数据实验室位于学院3号楼402室，面向高年级本科生开放科研实习，校内GPU算力集群通过实验中心门户提交课题申请表预约。",
            ),
        ],
    },
    {
        "filename": "s4-study-synthetic.json",
        "record_code": "BETA-SYN-S4-R2-2026",
        "title": "【合成测试】计算机与大数据学院本科培养方案与教务办理指南",
        "category_name": "培养方案与课程",
        "business_direction_codes": ["COLLEGE_RESOURCES"],
        "deadline_on": None,
        "applicability_raw": {
            "适用年级": "全日制本科各年级",
            "适用专业": "计算机类",
            "适用对象": "本科生",
            "学院": "计算机与大数据学院",
            "适用届别": None,
        },
        "temporal_notes": {"human_approved": True, "synthetic_fixture": True},
        "retrieval_status": "enabled",
        "chunks": [
            (
                "第 2 部分",
                '{"heading": "一、本科培养方案与教务办办事渠道"}',
                "网页 第 2 节",
                "2026版计算机类本科培养方案可在学院官网教务专栏下载；选课异动与成绩单盖章请联系教务办201室窗口办理。",
            ),
        ],
    },
    # Unopened / unapproved decoys that must NEVER appear in retrieval results.
    {
        "filename": "decoy-blocked.json",
        "record_code": "BETA-DECOY-BLOCKED",
        "title": "【合成拦截测试】未开放秘密奖学金内部草案",
        "category_name": "综评与奖学金",
        "business_direction_codes": ["POLICY_AFFAIRS"],
        "deadline_on": None,
        "applicability_raw": {
            "适用年级": None,
            "适用专业": None,
            "适用对象": "本科生",
            "学院": "计算机与大数据学院",
            "适用届别": None,
        },
        "temporal_notes": {"human_approved": True, "synthetic_fixture": True},
        "retrieval_status": "blocked",
        "chunks": [
            ("第 1 条", '{"heading": "草案"}', "草案 第 1 页", "未开放草案包含特殊奖学金神秘暗号X999。"),
        ],
    },
    {
        "filename": "decoy-unapproved.json",
        "record_code": "BETA-DECOY-UNAPPROVED",
        "title": "【合成拦截测试】缺人工审核标记的实验室通知",
        "category_name": "实验室与科研团队",
        "business_direction_codes": ["COLLEGE_RESOURCES"],
        "deadline_on": None,
        "applicability_raw": {
            "适用年级": None,
            "适用专业": None,
            "适用对象": "本科生",
            "学院": "计算机与大数据学院",
            "适用届别": None,
        },
        "temporal_notes": {"synthetic_fixture": True},
        "retrieval_status": "enabled",
        "chunks": [
            ("第 1 条", '{"heading": "未签核"}', "网页 第 1 节", "未通过人工签核的实验室暗号Y888。"),
        ],
    },
)


EVAL_QUERIES: tuple[EvalQuery, ...] = (
    EvalQuery(
        query_id="Q1-S1-EN",
        scenario="S1 竞赛认定",
        query="ACM-ICPC 国家级一等奖 创新创业学分",
        expected_record_code="BETA-SYN-S1-2026",
        expected_chunk_no=1,
        business_direction_code="COMPETITION_RESEARCH",
        note="中英文混合查询 + 单业务方向过滤",
    ),
    EvalQuery(
        query_id="Q2-S1-ZH",
        scenario="S1 竞赛认定",
        query="竞赛认定申请 综测科创加分",
        expected_record_code="BETA-SYN-S1-2026",
        expected_chunk_no=2,
        business_direction_code="COMPETITION_RESEARCH",
        note="中文短语匹配与章节定位",
    ),
    EvalQuery(
        query_id="Q3-S2-TITLE",
        scenario="S2 奖学金申请",
        query="院级奖学金 评选通知 GPA排名",
        expected_record_code="BETA-SYN-S2-2026",
        expected_chunk_no=1,
        business_direction_code="POLICY_AFFAIRS",
        note="标题词 + 正文英文缩写混合检索",
    ),
    EvalQuery(
        query_id="Q4-S2-DEADLINE",
        scenario="S2 奖学金申请",
        query="奖学金申请表 成绩单 截止时间",
        expected_record_code="BETA-SYN-S2-2026",
        expected_chunk_no=2,
        business_direction_code="POLICY_AFFAIRS",
        note="材料与截止时间定位",
    ),
    EvalQuery(
        query_id="Q5-S3-EN",
        scenario="S3 推免条件咨询",
        query="推免研究生 CET-6 425分 无不及格",
        expected_record_code="BETA-SYN-S3-2027",
        expected_chunk_no=1,
        business_direction_code="EDUCATION_CAREER",
        note="中英文外语条件检索",
    ),
    EvalQuery(
        query_id="Q6-S3-BONUS",
        scenario="S3 推免条件咨询",
        query="CCF推荐会议 推免学术专长加分",
        expected_record_code="BETA-SYN-S3-2027",
        expected_chunk_no=2,
        business_direction_code="EDUCATION_CAREER",
        note="学术专长加分条款检索",
    ),
    EvalQuery(
        query_id="Q7-S4-LAB",
        scenario="S4 学院资源导航",
        query="人工智能与大数据实验室 GPU算力申请",
        expected_record_code="BETA-SYN-S4-R3-2026",
        expected_chunk_no=1,
        business_direction_code="COLLEGE_RESOURCES",
        note="R3 实验室与科研团队：位置与英文算力关键词",
    ),
    EvalQuery(
        query_id="Q8-S4-OFFICE",
        scenario="S4 学院资源导航",
        query="本科培养方案 教务办 成绩单盖章",
        expected_record_code="BETA-SYN-S4-R2-2026",
        expected_chunk_no=1,
        business_direction_code="COLLEGE_RESOURCES",
        note="R2 培养方案与课程：培养方案与办事渠道导航",
    ),
    EvalQuery(
        query_id="Q9-MULTI-DIR",
        scenario="多业务方向（全库检索）",
        query="竞赛获奖 综测加分 奖学金申请表",
        expected_record_code="BETA-SYN-S2-2026",
        expected_chunk_no=None,
        business_direction_code=None,
        top_k=4,
        note="不传 business_direction_code 执行全库检索，避免跨方向漏检",
    ),
)


def materialize_synthetic_corpus(root: Path) -> Path:
    """Write synthetic S1-S4 packages and source text files under root/approved."""
    approved_dir = root / "approved"
    approved_dir.mkdir(parents=True, exist_ok=True)

    for spec in SYNTHETIC_PACKAGES:
        stem = Path(spec["filename"]).stem
        text_rel = f"texts/{stem}.md"
        text_path = root / text_rel
        text_path.parent.mkdir(parents=True, exist_ok=True)
        body = "\n\n".join(item[3] for item in spec["chunks"])
        text_bytes = body.encode("utf-8")
        text_path.write_bytes(text_bytes)
        digest = sha256(text_bytes).hexdigest()

        metadata = DocumentMetadata(
            title=spec["title"],
            document_type="通知",
            category_name=spec["category_name"],
            business_direction_codes=spec["business_direction_codes"],
            record_code=spec["record_code"],
            version_no="beta-syn-v1",
            source_url=f"https://example.invalid/beta/{stem}",
            published_on=date(2026, 9, 1),
            effective_on=date(2026, 9, 1),
            deadline_on=spec["deadline_on"],
            applicability_raw=spec["applicability_raw"],
            temporal_notes=spec["temporal_notes"],
            source_verification_status="verified",
            timeliness_verification_status="current",
            extraction_status="extracted",
            v1_inclusion_status="included",
            retrieval_status=spec["retrieval_status"],
        )
        chunks = [
            ParsedChunk(
                chunk_no=idx,
                content=content,
                locator=locator,
                locator_note=locator_note,
                original_locator=original_locator,
                source_file_key=text_rel,
            )
            for idx, (locator, locator_note, original_locator, content) in enumerate(
                spec["chunks"], start=1
            )
        ]
        package = DocumentPackage(
            metadata=metadata,
            files=[
                ParsedFile(
                    file_role="extracted",
                    storage_key=text_rel,
                    original_name=text_path.name,
                    sha256=digest,
                    processing_status=FileProcessingStatus.EXTRACTED,
                )
            ],
            chunks=chunks,
        )
        (approved_dir / spec["filename"]).write_text(
            package.model_dump_json(indent=2), encoding="utf-8"
        )
    return approved_dir


async def run_evaluation() -> dict[str, Any]:
    with TemporaryDirectory() as tmp:
        root = Path(tmp)
        approved_dir = materialize_synthetic_corpus(root)
        retriever, report = await load_approved_alpha_retriever(
            corpus_dir=approved_dir, file_root=root, allow_missing=False
        )

        rows = []
        hit1 = 0
        hit3 = 0
        mrr_sum = 0.0

        for case in EVAL_QUERIES:
            hits = await retriever.retrieve(
                RetrievalRequest(
                    query=case.query,
                    business_direction_code=case.business_direction_code,
                    top_k=case.top_k,
                )
            )
            matched_rank: int | None = None
            hit_summaries = []
            for rank, hit in enumerate(hits, start=1):
                meta = retriever.get_document_metadata(hit.version_id)
                parsed = retriever.get_parsed_chunk(hit.chunk_id)
                if meta is None or parsed is None:
                    raise RuntimeError(
                        f"Retrieved hit missing metadata/chunk lookup: version_id={hit.version_id}, chunk_id={hit.chunk_id}"
                    )
                hit_summaries.append({
                    "rank": rank,
                    "record_code": meta.record_code,
                    "version_no": meta.version_no,
                    "chunk_no": parsed.chunk_no,
                    "locator": parsed.locator,
                    "original_locator": parsed.original_locator,
                    "score": round(hit.score, 6),
                })
                if matched_rank is None and meta.record_code == case.expected_record_code:
                    if case.expected_chunk_no is None or parsed.chunk_no == case.expected_chunk_no:
                        matched_rank = rank

            if matched_rank == 1:
                hit1 += 1
            if matched_rank is not None and matched_rank <= 3:
                hit3 += 1
            if matched_rank is not None:
                mrr_sum += 1.0 / matched_rank

            rows.append({
                "query_id": case.query_id,
                "scenario": case.scenario,
                "query": case.query,
                "business_direction_code": case.business_direction_code,
                "expected": f"{case.expected_record_code}#{case.expected_chunk_no or '*'}",
                "matched_rank": matched_rank,
                "hits": hit_summaries,
                "note": case.note,
            })

        total = len(EVAL_QUERIES)
        no_match = await retriever.retrieve(RetrievalRequest(query="量子纠缠核聚变"))
        decoy_blocked = await retriever.retrieve(RetrievalRequest(query="暗号X999"))
        decoy_unapproved = await retriever.retrieve(RetrievalRequest(query="暗号Y888"))

        return {
            "corpus_type": "synthetic_beta_s1_s4_fixture",
            "loaded_packages": list(report.loaded_packages),
            "skipped_packages": list(report.skipped_packages),
            "total_indexed_chunks": report.total_indexed_chunks,
            "metrics": {
                "query_count": total,
                "hit_at_1": round(hit1 / total, 4),
                "hit_at_3": round(hit3 / total, 4),
                "mrr": round(mrr_sum / total, 4),
            },
            "negative_checks": {
                "no_match_count": len(no_match),
                "decoy_blocked_count": len(decoy_blocked),
                "decoy_unapproved_count": len(decoy_unapproved),
            },
            "results": rows,
        }


async def run_corpus_probe(
    corpus_dir: Path,
    *,
    file_root: Path = PROJECT_ROOT,
) -> dict[str, Any]:
    """Load an external/approved corpus directory and probe S1-S4 retrieval & traceability."""
    retriever, report = await load_approved_alpha_retriever(
        corpus_dir=corpus_dir, file_root=file_root, allow_missing=False
    )
    probes = []
    for case in EVAL_QUERIES:
        hits = await retriever.retrieve(
            RetrievalRequest(
                query=case.query,
                business_direction_code=case.business_direction_code,
                top_k=case.top_k,
            )
        )
        hit_summaries = []
        for rank, hit in enumerate(hits, start=1):
            meta = retriever.get_document_metadata(hit.version_id)
            parsed = retriever.get_parsed_chunk(hit.chunk_id)
            if meta is None or parsed is None:
                raise RuntimeError(
                    f"Retrieved hit missing metadata/chunk lookup: version_id={hit.version_id}, chunk_id={hit.chunk_id}"
                )
            hit_summaries.append({
                "rank": rank,
                "record_code": meta.record_code,
                "version_no": meta.version_no,
                "title": meta.title,
                "chunk_no": parsed.chunk_no,
                "locator": parsed.locator,
                "original_locator": parsed.original_locator,
                "source_file_key": parsed.source_file_key,
                "score": round(hit.score, 6),
            })
        probes.append({
            "query_id": case.query_id,
            "scenario": case.scenario,
            "query": case.query,
            "business_direction_code": case.business_direction_code,
            "hits": hit_summaries,
        })
    return {
        "corpus_type": "approved_directory_probe",
        "corpus_dir": corpus_dir.as_posix(),
        "loaded_packages": list(report.loaded_packages),
        "skipped_packages": list(report.skipped_packages),
        "total_indexed_chunks": report.total_indexed_chunks,
        "index_results": [
            {
                "version_id": str(r.version_id),
                "status": r.status.value,
                "indexed_count": r.indexed_count,
                "warnings": [w.model_dump() for w in r.warnings],
            }
            for r in report.index_results
        ],
        "probes": probes,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate Beta S1-S4 BM25 retrieval.")
    parser.add_argument(
        "--corpus-dir",
        type=Path,
        default=None,
        help="Optional approved corpus directory to probe instead of synthetic S1-S4 fixtures.",
    )
    parser.add_argument(
        "--file-root",
        type=Path,
        default=PROJECT_ROOT,
        help="Controlled repository/file root for --corpus-dir verification.",
    )
    args = parser.parse_args()
    if args.corpus_dir is not None:
        output = asyncio.run(run_corpus_probe(args.corpus_dir, file_root=args.file_root))
    else:
        output = asyncio.run(run_evaluation())
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
