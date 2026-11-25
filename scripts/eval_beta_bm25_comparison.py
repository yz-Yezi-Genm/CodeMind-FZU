"""Comparative BM25 evaluation: Content-Only vs Title+Content on a larger synthetic corpus.

Stress-tests:
- Multi-chunk long documents (including boilerplate chunks: 总则/组织机构/公示/附则/联系人)
- Similar policy titles (本科生奖学金办法 vs 院级星火奖学金通知 vs 研究生学业奖学金细则)
- Same-name labs across R3 (recruitment/contact) and R4 (research intro)
- Cross-business-direction competing ranking (full-corpus search with business_direction_code=None)
- Title+content combined queries where policy name only appears in metadata.title

All data uses example.invalid synthetic fixtures; no real policy files or statuses are touched.

Run from repository root:
    python -X utf8 -m scripts.eval_beta_bm25_comparison
"""
from __future__ import annotations

import asyncio
from collections import Counter
from dataclasses import dataclass
from datetime import date
import json
from typing import Any

from backend.contracts import (
    DocumentMetadata,
    DocumentPackage,
    FileProcessingStatus,
    ParsedChunk,
    ParsedFile,
    RetrievalRequest,
)
from backend.retrieval.local import LocalBM25Retriever, _IndexedChunk, _IndexedVersion, _terms


class _ContentOnlyBM25Retriever(LocalBM25Retriever):
    """Reference baseline using chunk.content BM25 only (title weight = 0.0)."""

    _title_weight: float = 0.0


class _EqualWeightConcatBM25Retriever(LocalBM25Retriever):
    """Previous baseline concatenating title_terms and content_terms at equal 1.0x weight."""

    _title_weight: float = 0.0

    async def index_document(self, package: DocumentPackage):
        result = await super().index_document(package)
        version = self._versions.get(result.version_id)
        if version is not None:
            title_terms = _terms(version.metadata.title)
            rebuilt = []
            for chunk in version.chunks:
                combined_terms = [*title_terms, *_terms(chunk.parsed.content)]
                rebuilt.append(
                    _IndexedChunk(
                        parsed=chunk.parsed,
                        file_id=chunk.file_id,
                        chunk_id=chunk.chunk_id,
                        term_counts=Counter(combined_terms),
                        length=len(combined_terms),
                    )
                )
            self._put_version(
                _IndexedVersion(
                    metadata=version.metadata,
                    document_id=version.document_id,
                    version_id=version.version_id,
                    chunks=tuple(rebuilt),
                    title_term_counts=Counter(),
                    title_length=0,
                )
            )
        return result


@dataclass(frozen=True)
class StressQuery:
    query_id: str
    category: str
    query: str
    expected_record_code: str
    expected_chunk_no: int
    business_direction_code: str | None = None
    top_k: int = 3
    note: str = ""


@dataclass(frozen=True)
class MultiTargetQuery:
    query_id: str
    query: str
    expected_targets: tuple[tuple[str, int], ...]
    top_k: int = 5
    note: str = ""


def _build_package(
    *,
    record_code: str,
    title: str,
    category_name: str,
    business_direction_codes: list[str],
    chunks: list[tuple[str, str]],
) -> DocumentPackage:
    storage_key = f"synthetic/{record_code.lower()}.md"
    metadata = DocumentMetadata(
        title=title,
        document_type="办法",
        category_name=category_name,
        business_direction_codes=business_direction_codes,
        record_code=record_code,
        version_no="cmp-v1",
        source_url=f"https://example.invalid/cmp/{record_code.lower()}",
        published_on=date(2026, 9, 1),
        effective_on=date(2026, 9, 1),
        applicability_raw={
            "适用年级": "全日制本科各年级",
            "适用专业": None,
            "适用对象": "本科生",
            "学院": "计算机与大数据学院",
            "适用届别": None,
        },
        temporal_notes={"human_approved": True, "synthetic_fixture": True},
        source_verification_status="verified",
        timeliness_verification_status="current",
        extraction_status="extracted",
        v1_inclusion_status="included",
        retrieval_status="enabled",
    )
    return DocumentPackage(
        metadata=metadata,
        files=[
            ParsedFile(
                file_role="extracted",
                storage_key=storage_key,
                original_name=f"{record_code.lower()}.md",
                processing_status=FileProcessingStatus.EXTRACTED,
            )
        ],
        chunks=[
            ParsedChunk(
                chunk_no=idx,
                content=content,
                locator=locator,
                locator_note=json.dumps({"heading": locator}, ensure_ascii=False),
                original_locator=f"第 {idx} 页",
                source_file_key=storage_key,
            )
            for idx, (locator, content) in enumerate(chunks, start=1)
        ],
    )


def build_stress_packages() -> list[DocumentPackage]:
    return [
        # 1. Long 10-chunk undergraduate scholarship bylaw (with boilerplate chunks)
        _build_package(
            record_code="CMP-SCH-UG",
            title="【合成】2026年计算机与大数据学院本科生奖学金评定管理办法",
            category_name="综评与奖学金",
            business_direction_codes=["POLICY_AFFAIRS"],
            chunks=[
                ("第一章 总则", "为规范学院本科生评奖评优工作，激励学生全面发展，特制定本办法。"),
                ("第二章 组织机构", "学院成立奖学金评审领导小组，由分管学生工作副书记担任组长。"),
                ("第三章 基本条件", "参评学生须热爱祖国、遵纪守法、诚实守信，本学年无任何违纪处分记录。"),
                ("第四章 成绩要求", "优秀学生综合奖学金一等奖须学业绩点GPA位列专业前5%，且所有必修课程无不及格。"),
                ("第五章 综测权重", "综合测评总分由学业成绩占70%、德育表现占15%、科创与文体实践占15%构成。"),
                ("第六章 单项奖励", "学习进步奖面向本学年专业排名较上一学年提升超过25%的本科生。"),
                ("第七章 材料提交", "参评学生须在每学年秋季学期第4周前向辅导员提交申请表及教务成绩单。"),
                ("第八章 公示异议", "评审初审名单在学院公告栏及官网公示不少于三个工作日，接受师生监督。"),
                ("第九章 资金发放", "公示无异议后由财务处统一打卡发放至学生本人校园绑定银行卡。"),
                ("第十章 附则", "本办法由计算机与大数据学院学生工作办公室负责解释，自发布之日起施行。"),
            ],
        ),
        # 2. Similar title: Xinghuo department scholarship notice (5 chunks)
        _build_package(
            record_code="CMP-SCH-XINGHUO",
            title="【合成】2026年计算机与大数据学院院级星火奖学金评选通知",
            category_name="综评与奖学金",
            business_direction_codes=["POLICY_AFFAIRS"],
            chunks=[
                ("一、评选宗旨", "面向在学科竞赛、开源社区或科研项目中表现突出的学院在读本科生设立专项激励。"),
                ("二、奖项名额与金额", "本年度设个人特等奖3名每人8000元，优秀奖12名每人3000元。"),
                ("三、申报材料", "申请人须提交开源仓库贡献证明、论文录用通知或省级以上竞赛获奖证书扫描件。"),
                ("四、截止与答辩", "材料提交截止时间为2026年11月10日17:00，入围者须参加5分钟现场PPT答辩。"),
                ("五、联系人", "如有疑问请联系学工办陈老师，办公地点学院1号楼205室。"),
            ],
        ),
        # 3. Similar title: Graduate scholarship rules (4 chunks)
        _build_package(
            record_code="CMP-SCH-GRAD",
            title="【合成】2026年计算机与大数据学院研究生学业奖学金评定细则",
            category_name="综评与奖学金",
            business_direction_codes=["POLICY_AFFAIRS"],
            chunks=[
                ("一、适用对象", "本细则适用于纳入全国研究生招生计划的全日制非定向硕士与博士研究生。"),
                ("二、科研成果折算", "研究生以第一作者在SCI一区期刊或CCF-A类会议发表论文可计满分科研分。"),
                ("三、等级比例", "硕士一等学业奖学金比例不超过20%，二等不超过40%，三等不超过40%。"),
                ("四、附则", "本细则由学院研究生培养办公室负责解释。"),
            ],
        ),
        # 4. Long 8-chunk competition recognition bylaw
        _build_package(
            record_code="CMP-COMP-BYLAW",
            title="【合成】2026年大学生学科竞赛认定与创新创业学分管理办法",
            category_name="竞赛与创新创业",
            business_direction_codes=["COMPETITION_RESEARCH", "POLICY_AFFAIRS"],
            chunks=[
                ("第一章 总则", "为鼓励本科生积极参与高水平学科竞赛，规范创新创业学分认定，制定本办法。"),
                ("第二章 竞赛分级", "学科竞赛分为A+类、A类、B类、C类四个级别，以教务处年度公布目录为准。"),
                ("第三章 ACM与程序设计", "ACM-ICPC 国际大学生程序设计竞赛区域赛金奖及蓝桥杯国赛一等奖按A类认定，可换算4个创新学分。"),
                ("第四章 团队排序规则", "团队获奖项目中，第一完成人按100%计分，第二、第三完成人分别按70%与50%折算。"),
                ("第五章 重复获奖限制", "同一作品在不同级别赛事多次获奖的，仅按最高级别认定一次，不重复累计学分。"),
                ("第六章 认定流程", "学生持获奖证书原件登录教务系统上传佐证，经指导教师与学院教学办审核通过后入库。"),
                ("第七章 异议处理", "对认定级别有异议的，可在公示期内向教务处实践教学科提交书面复核申请。"),
                ("第八章 附则", "本办法自2026年9月起实施，原2022版办法同时废止。"),
            ],
        ),
        # 5. S3 Recommendation qualification (4 chunks)
        _build_package(
            record_code="CMP-REC-QUAL",
            title="【合成】2027届免试攻读研究生推荐资格遴选实施细则",
            category_name="推免与升学",
            business_direction_codes=["EDUCATION_CAREER"],
            chunks=[
                ("一、基本学业门槛", "申请人前三年必修课程须全部及格，无学术不端记录，外语须通过CET-6且成绩不低于425分。"),
                ("二、学术专长加分", "本科阶段在CCF推荐会议发表论文或获A+类学科竞赛国家级奖项，经答辩认定最高加5分。"),
                ("三、名额分配", "推免名额按各专业应届本科毕业生人数比例分配，并在学院官网公示。"),
                ("四、附则", "本细则由学院推免生遴选工作小组负责解释。"),
            ],
        ),
        # 6. Same-name lab R3 (recruitment & contact, 2 same-name labs in different rooms)
        _build_package(
            record_code="CMP-LAB-R3",
            title="【合成】2026年青禾计划智能感知实验室招募与联系方式汇总",
            category_name="实验室与科研团队",
            business_direction_codes=["COLLEGE_RESOURCES"],
            chunks=[
                ("序号1 智能感知实验室（视觉组）", "智能感知实验室（视觉组）位于3号楼402室，联系人林老师，邮箱vision@example.invalid，招收大二大三本科生8名，考核方式为编程机试与面试。"),
                ("序号2 智能感知实验室（语音组）", "智能感知实验室（语音组）位于2号楼305室，联系人周老师，邮箱speech@example.invalid，招收熟悉PyTorch的本科生5名，需提交简历初筛。"),
                ("序号3 报名截止说明", "本批次青禾计划实验室报名截止日期为2026年10月31日，逾期不再受理。"),
            ],
        ),
        # 7. Same-name lab R4 (research intro, same lab name!)
        _build_package(
            record_code="CMP-LAB-R4",
            title="【合成】计算机与大数据学院智能感知实验室研究方向与成果介绍",
            category_name="研究方向与公开介绍",
            business_direction_codes=["COLLEGE_RESOURCES"],
            chunks=[
                ("一、视觉组研究方向", "智能感知实验室（视觉组）长期深耕多模态目标检测、医学影像分割与三维点云重建，近三年发表CVPR与ICCV论文12篇。"),
                ("二、语音组研究方向", "智能感知实验室（语音组）聚焦低资源方言语音识别与端到端语音合成，曾获国家自然科学基金面上项目资助。"),
            ],
        ),
        # 8. S4 R2 Curriculum & academic affairs (3 chunks)
        _build_package(
            record_code="CMP-STUDY-R2",
            title="【合成】2026版计算机类本科培养方案与教务办事渠道",
            category_name="培养方案与课程",
            business_direction_codes=["COLLEGE_RESOURCES"],
            chunks=[
                ("一、毕业学分结构", "2026版计算机科学与技术本科培养方案要求修满165学分，其中专业核心必修课72学分、创新实践环节12学分。"),
                ("二、GPU算力预约", "学院实验中心GPU算力集群面向科研训练项目开放，通过算力管理平台提交导师签字的机时申请单。"),
                ("三、教务办窗口", "成绩单盖章、缓考申请与学籍证明办理请前往学院教学楼201室教务办窗口。"),
            ],
        ),
    ]


STRESS_QUERIES: tuple[StressQuery, ...] = (
    # A. Multi-chunk long documents: ensure exact clause wins over boilerplate chunks
    StressQuery("C01", "long_doc", "优秀学生综合奖学金一等奖 GPA 专业前5%", "CMP-SCH-UG", 4, "POLICY_AFFAIRS", 3, "长文档精准定位成绩要求"),
    StressQuery("C02", "long_doc", "综合测评总分 学业成绩 德育表现 权重比例", "CMP-SCH-UG", 5, "POLICY_AFFAIRS", 3, "长文档精准定位综测权重"),
    StressQuery("C03", "long_doc", "学习进步奖 专业排名提升 25%", "CMP-SCH-UG", 6, "POLICY_AFFAIRS", 3, "长文档精准定位单项奖励"),
    StressQuery("C04", "long_doc", "奖学金公示不少于几个工作日", "CMP-SCH-UG", 8, "POLICY_AFFAIRS", 3, "长文档精准定位公示条款"),
    StressQuery("C05", "long_doc", "学科竞赛团队获奖 第一完成人 第二完成人 折算比例", "CMP-COMP-BYLAW", 4, "COMPETITION_RESEARCH", 3, "长文档团队排序条款"),
    StressQuery("C06", "long_doc", "同一作品多次获奖 能否重复累计创新学分", "CMP-COMP-BYLAW", 5, "COMPETITION_RESEARCH", 3, "长文档重复获奖限制"),
    # B. Similar policy titles disambiguation
    StressQuery("C07", "similar_title", "星火奖学金 特等奖 8000元 现场PPT答辩", "CMP-SCH-XINGHUO", 2, "POLICY_AFFAIRS", 3, "相似标题区分星火与本科生办法"),
    StressQuery("C08", "similar_title", "研究生学业奖学金 SCI一区 CCF-A类会议 科研分", "CMP-SCH-GRAD", 2, "POLICY_AFFAIRS", 3, "相似标题区分研究生细则"),
    StressQuery("C09", "similar_title", "星火奖学金 2026年11月10日 截止答辩", "CMP-SCH-XINGHUO", 4, "POLICY_AFFAIRS", 3, "相似标题定位星火截止日期"),
    StressQuery("C10", "similar_title", "硕士一等学业奖学金 比例不超过20%", "CMP-SCH-GRAD", 3, "POLICY_AFFAIRS", 3, "相似标题定位硕士等级比例"),
    # C. Same-name labs (R3 vs R4 & room/contact disambiguation)
    StressQuery("C11", "same_name_lab", "智能感知实验室 视觉组 3号楼402室 联系人 机试面试", "CMP-LAB-R3", 1, "COLLEGE_RESOURCES", 3, "同名实验室 R3 视觉组招募"),
    StressQuery("C12", "same_name_lab", "智能感知实验室 语音组 2号楼305室 PyTorch 简历", "CMP-LAB-R3", 2, "COLLEGE_RESOURCES", 3, "同名实验室 R3 语音组招募"),
    StressQuery("C13", "same_name_lab", "智能感知实验室 视觉组 多模态目标检测 CVPR ICCV", "CMP-LAB-R4", 1, "COLLEGE_RESOURCES", 3, "同名实验室 R4 视觉组研究方向"),
    StressQuery("C14", "same_name_lab", "智能感知实验室 语音组 方言语音识别 国家自然科学基金", "CMP-LAB-R4", 2, "COLLEGE_RESOURCES", 3, "同名实验室 R4 语音组研究方向"),
    # D. Title + content combined queries (policy name ONLY appears in title!)
    StressQuery("C15", "title_plus_content", "星火奖学金 开源仓库贡献证明", "CMP-SCH-XINGHUO", 3, "POLICY_AFFAIRS", 3, "政策名仅在标题、材料名在正文"),
    StressQuery("C16", "title_plus_content", "星火奖学金 联系人 陈老师 205室", "CMP-SCH-XINGHUO", 5, "POLICY_AFFAIRS", 3, "政策名仅在标题、联系人在正文"),
    StressQuery("C19", "title_plus_content", "星火奖学金 截止时间 2026年", "CMP-SCH-XINGHUO", 4, None, 3, "跨库同名截止时间词，仅标题含星火奖学金"),
    StressQuery("C20", "title_plus_content", "研究生学业奖学金 全日制 适用对象", "CMP-SCH-GRAD", 1, "POLICY_AFFAIRS", 3, "仅标题含研究生学业奖学金、正文为通用词"),
    # E. Cross-business-direction full-corpus competing ranking (business_direction_code=None)
    StressQuery("C17", "cross_direction", "CCF推荐会议 推免学术专长 最高加5分", "CMP-REC-QUAL", 2, None, 3, "全库检索区分推免与研究生奖学金"),
    StressQuery("C18", "cross_direction", "ACM-ICPC 蓝桥杯 4个创新学分", "CMP-COMP-BYLAW", 3, None, 3, "全库检索命中竞赛创新学分"),
)

MULTI_TARGET_QUERIES: tuple[MultiTargetQuery, ...] = (
    MultiTargetQuery(
        query_id="M01",
        query="2026年本科生奖学金评定管理办法的一等奖GPA要求，以及本科毕业学分165学分要求？",
        expected_targets=(("CMP-SCH-UG", 4), ("CMP-STUDY-R2", 1)),
        top_k=5,
        note="复审反例1：长标题奖学金办法与毕业学分双目标跨领域召回",
    ),
    MultiTargetQuery(
        query_id="M02",
        query="2026年青禾计划智能感知实验室招募报名截止日期，以及推免申请人外语CET-6要求？",
        expected_targets=(("CMP-LAB-R3", 3), ("CMP-REC-QUAL", 1)),
        top_k=5,
        note="复审反例2：长标题实验室招募与推免外语双目标跨领域召回",
    ),
    MultiTargetQuery(
        query_id="M03",
        query="2026年大学生学科竞赛认定与创新创业学分管理办法的团队第一完成人折算比例，以及星火奖学金特等奖8000元名额？",
        expected_targets=(("CMP-COMP-BYLAW", 4), ("CMP-SCH-XINGHUO", 2)),
        top_k=5,
        note="双目标跨领域：长标题竞赛办法 + 星火奖学金名额金额",
    ),
    MultiTargetQuery(
        query_id="M04",
        query="2026年计算机与大数据学院本科生奖学金评定管理办法的综合测评总分与学业成绩比例，以及智能感知实验室视觉组CVPR论文研究方向？",
        expected_targets=(("CMP-SCH-UG", 5), ("CMP-LAB-R4", 1)),
        top_k=5,
        note="双目标跨领域：10片段长文档综合测评总分条款 + 同名实验室 R4 研究方向",
    ),
)

_BOILERPLATE_MARKERS = ("总则", "组织机构", "附则", "联系人")


async def _evaluate_retriever(retriever: LocalBM25Retriever, packages: list[DocumentPackage]) -> dict[str, Any]:
    for pkg in packages:
        res = await retriever.index_document(pkg)
        if res.status.value != "indexed":
            raise RuntimeError(f"Indexing failed for {pkg.metadata.record_code}: {res.warnings}")

    hit1 = 0
    hit3 = 0
    mrr_sum = 0.0
    boilerplate_in_top3 = 0
    per_category: dict[str, dict[str, float]] = {}
    details = []

    for q in STRESS_QUERIES:
        hits = await retriever.retrieve(
            RetrievalRequest(
                query=q.query,
                business_direction_code=q.business_direction_code,
                top_k=q.top_k,
            )
        )
        matched_rank: int | None = None
        top_hits = []
        for rank, hit in enumerate(hits, start=1):
            meta = retriever.get_document_metadata(hit.version_id)
            parsed = retriever.get_parsed_chunk(hit.chunk_id)
            if meta is None or parsed is None:
                raise RuntimeError("Missing metadata/chunk lookup")
            top_hits.append({
                "rank": rank,
                "record_code": meta.record_code,
                "chunk_no": parsed.chunk_no,
                "locator": parsed.locator,
                "score": round(hit.score, 4),
            })
            if matched_rank is None and meta.record_code == q.expected_record_code and parsed.chunk_no == q.expected_chunk_no:
                matched_rank = rank
            if (
                q.category == "long_doc"
                and any(marker in (parsed.locator or "") for marker in _BOILERPLATE_MARKERS)
                and not (meta.record_code == q.expected_record_code and parsed.chunk_no == q.expected_chunk_no)
            ):
                boilerplate_in_top3 += 1

        cat = per_category.setdefault(q.category, {"count": 0, "hit1": 0, "hit3": 0, "mrr": 0.0})
        cat["count"] += 1
        if matched_rank == 1:
            hit1 += 1
            cat["hit1"] += 1
        if matched_rank is not None and matched_rank <= 3:
            hit3 += 1
            cat["hit3"] += 1
        if matched_rank is not None:
            mrr_sum += 1.0 / matched_rank
            cat["mrr"] += 1.0 / matched_rank

        details.append({
            "query_id": q.query_id,
            "category": q.category,
            "expected": f"{q.expected_record_code}#{q.expected_chunk_no}",
            "matched_rank": matched_rank,
            "top_hits": top_hits,
        })

    multi_details = []
    recall5_sum = 0.0
    all_targets_hit_count = 0
    for mq in MULTI_TARGET_QUERIES:
        hits = await retriever.retrieve(
            RetrievalRequest(query=mq.query, business_direction_code=None, top_k=mq.top_k)
        )
        top_hits = []
        found_pairs: set[tuple[str, int]] = set()
        for rank, hit in enumerate(hits, start=1):
            meta = retriever.get_document_metadata(hit.version_id)
            parsed = retriever.get_parsed_chunk(hit.chunk_id)
            if meta is None or parsed is None:
                raise RuntimeError("Missing metadata/chunk lookup")
            found_pairs.add((meta.record_code, parsed.chunk_no))
            top_hits.append({
                "rank": rank,
                "record_code": meta.record_code,
                "chunk_no": parsed.chunk_no,
                "locator": parsed.locator,
                "score": round(hit.score, 4),
            })
        matched = [t for t in mq.expected_targets if t in found_pairs]
        missing = [f"{code}#{no}" for code, no in mq.expected_targets if (code, no) not in found_pairs]
        recall_at_5 = len(matched) / len(mq.expected_targets)
        recall5_sum += recall_at_5
        if not missing:
            all_targets_hit_count += 1
        multi_details.append({
            "query_id": mq.query_id,
            "query": mq.query,
            "expected": [f"{code}#{no}" for code, no in mq.expected_targets],
            "recall_at_5": round(recall_at_5, 4),
            "missing": missing,
            "top_hits": top_hits,
            "note": mq.note,
        })

    total = len(STRESS_QUERIES)
    multi_total = len(MULTI_TARGET_QUERIES)
    return {
        "document_count": len(packages),
        "chunk_count": sum(len(p.chunks) for p in packages),
        "query_count": total,
        "hit_at_1": round(hit1 / total, 4),
        "hit_at_3": round(hit3 / total, 4),
        "mrr": round(mrr_sum / total, 4),
        "long_doc_boilerplate_in_top3": boilerplate_in_top3,
        "multi_target_query_count": multi_total,
        "multi_target_recall_at_5": round(recall5_sum / multi_total, 4),
        "multi_target_full_recall_count": all_targets_hit_count,
        "by_category": {
            k: {
                "count": int(v["count"]),
                "hit_at_1": round(v["hit1"] / v["count"], 4),
                "hit_at_3": round(v["hit3"] / v["count"], 4),
                "mrr": round(v["mrr"] / v["count"], 4),
            }
            for k, v in per_category.items()
        },
        "details": details,
        "multi_target_details": multi_details,
    }


async def run_comparison() -> dict[str, Any]:
    packages = build_stress_packages()
    content_only = await _evaluate_retriever(_ContentOnlyBM25Retriever(), packages)
    equal_weight_concat = await _evaluate_retriever(_EqualWeightConcatBM25Retriever(), packages)
    title_and_content = await _evaluate_retriever(LocalBM25Retriever(), packages)
    return {
        "corpus_type": "synthetic_stress_comparison_fixture",
        "content_only": content_only,
        "equal_weight_concat": equal_weight_concat,
        "title_and_content": title_and_content,
        "delta": {
            "hit_at_1": round(title_and_content["hit_at_1"] - content_only["hit_at_1"], 4),
            "hit_at_3": round(title_and_content["hit_at_3"] - content_only["hit_at_3"], 4),
            "mrr": round(title_and_content["mrr"] - content_only["mrr"], 4),
            "multi_target_recall_at_5": round(
                title_and_content["multi_target_recall_at_5"]
                - content_only["multi_target_recall_at_5"],
                4,
            ),
            "multi_target_recall_at_5_vs_equal_weight": round(
                title_and_content["multi_target_recall_at_5"]
                - equal_weight_concat["multi_target_recall_at_5"],
                4,
            ),
            "long_doc_boilerplate_in_top3": (
                title_and_content["long_doc_boilerplate_in_top3"]
                - content_only["long_doc_boilerplate_in_top3"]
            ),
        },
    }


def main() -> None:
    print(json.dumps(asyncio.run(run_comparison()), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
