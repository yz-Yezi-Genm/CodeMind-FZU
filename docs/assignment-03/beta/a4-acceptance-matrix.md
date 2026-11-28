# A4 学院资源导航 · 验收矩阵

> 负责人：林彦翔、雷葭雨　｜　版本：v1.4（2026-11-28）　｜　依据：`resource-navigation-design.md` §3.7、§4.1、`business-rules.md` §7
> 状态：矩阵已定稿；**B1—B17 待 #59 完成接口集成、#60 已合并（`4713117`）后执行**。依赖未满足记 BLOCKED，不算失败。

---

## 1. 前置条件

| 编号 | 前置条件 | 当前状态 |
| --- | --- | --- |
| P1 | 青禾 R3、R4 两包通过人工审核并入 `approved/`，`retrieval_status=enabled` | 未满足 |
| P2 | 工作流放行无年度历史资料（仅公开名录/研究介绍、单一批次） | 业务口径已确认，实现待吴诗莹完成 |
| P60 | 检索层提供批次枚举可选方法 | 已满足（#60 合并 `4713117`） |
| P3 | R1 通知栏目目录入库并开放检索 | 未满足 |
| P4 | R6 学院公开信息入库并开放检索 | 未满足 |

---

## 2. 场景矩阵（23 个）

| 编号 | 学生问句 | 目标结果 | 当前可运行 | 前置 |
| --- | --- | --- | --- | --- |
| S4-01 | 学院有哪些实验室？ | `answered` / `historical`，只用 R4 片段 | `insufficient_evidence` | P1 + P2 |
| S4-02 | EDA 实验室研究什么？ | `answered` / `historical` | `insufficient_evidence` | P1 + P2 |
| S4-03 | 我大二能进 EDA 实验室吗？ | `insufficient_evidence` / `insufficient_data` | 同目标 | 无 |
| S4-04 | 学院有什么资源？ | `needs_clarification` | 同目标 | 无 |
| S4-05 | EDA 实验室怎么样？ | `needs_clarification` | 同目标 | 无 |
| S4-06 | 培养方案在哪看？ | `needs_clarification` | 同目标 | 无 |
| S4-07 | EDA 实验室怎么报名？ | `answered` / `historical` | `insufficient_evidence` | P1；#59 单一批次流程放行 |
| S4-08 | 2026 年青禾计划报名截止了吗？ | `answered` / `historical`，说明 2026-10-31 已截止 | `insufficient_evidence` | P1（显式 2026 年度） |
| S4-09 | 这个实验室现在还招几个？ | `insufficient_evidence` / `insufficient_data` | 同目标 | 无 |
| S4-10 | 某实验室（库内无资料）研究什么？ | `insufficient_evidence` / `insufficient_data` | 同目标 | 无 |
| S4-11 | 学院办公室电话或办公地点在哪？ | `insufficient_evidence` / `insufficient_data` | 同目标 | P4 |
| S4-12 | 只有历史介绍，问现在招人吗 | `insufficient_evidence` / `insufficient_data` | 同目标 | P1 |
| S4-13 | 2026 年青禾计划怎么报名？ | `answered` / `historical` | `insufficient_evidence` | P1（显式 2026 年度） |
| S4-14 | 2025 年青禾计划怎么报名？ | `insufficient_evidence` / `insufficient_data` | 同目标 | 无 |
| S4-15 | 2027 年青禾计划招几人？ | `insufficient_evidence` / `insufficient_data` | 同目标 | 无 |
| S4-16 | 公众号文章名称是学院号但 ID 是 `ifzu1958` | `insufficient_evidence` / `insufficient_data` | 同目标 | 无 |
| S4-17 | 学院的通知在哪看？ | `answered` / `procedure_reference` | `insufficient_evidence` | P3 |
| S4-18 | 2026 年青禾通知里写的联系人是谁？ | `answered` / `historical`，须标年度 | `insufficient_evidence` | P1；#59 联系人独立判断 |
| S4-19 | 现在该联系哪个实验室负责人？ | `insufficient_evidence` / `insufficient_data` | 同目标 | 无 |
| S4-20 | 青禾计划现在还剩几个名额？ | `insufficient_evidence` / `insufficient_data` | 同目标 | 无 |
| S4-22 | 2026 年我大二能进 EDA 实验室吗？ | `answered` / `historical`，检查年级专业 | `insufficient_evidence` | P1（显式 2026 年度） |
| S4-23 | 现在能进 EDA 实验室吗？ | `insufficient_evidence` / `insufficient_data`（无当前通知） | 同目标 | 无 |
| S4-24 | 这个实验室现在还招吗？ | `insufficient_evidence` / `insufficient_data`，`citations` 为空 | 同目标 | 有已截止历史 R3、无当前 R3 |

S4-08 只回答「2026 年是否已截止」；S4-24 问「现在是否还招」，必须构造「已截止历史 R3 存在、当前 R3 不存在」两个条件，预期证据不足、`citations` 为空、不引用历史通知。P2 只服务 S4-01、S4-02，不覆盖 S4-24。

---

## 3. 批次判定矩阵（B1—B17）

| 编号 | 测试条件 | 预期结果 | 执行阶段 |
| --- | --- | --- | --- |
| B1 | 只开放一个历史批次（如 2024），其余批次置为 blocked 或移除；问「学院有哪些实验室」 | `answered` / `historical`，声明该年度，不追问 | #59 集成后 |
| B2 | 同时开放 2024、2025、2026 三个历史批次；无年度问名录或研究介绍 | `needs_clarification`，追问年度，不擅自选年 | #59 集成后 |
| B3 | EDA 联系人在 2024 与 2025/2026 不同；无年度问联系人 | `needs_clarification`，追问年度 | #59 集成后 |
| B4 | 数据智能实验室联系人 2025、2026 相同；无年度问联系人 | 不误追问；`answered` / `historical`，列出所引用的 2025、2026 两个年度资料并逐条给 citation，标明历史属性，不得表述为当前联系人 | #59 集成后 |
| B5 | 同一批次的两种情形：① 2026 同一 `record_code` 有 `import-1`、`import-2`；② 同一年度的 R3、R4 分属不同 `record_code`，且原始资料**没有明确标注不同公开批次** | 两种都归并为同一年度批次，不触发多批次追问；若原文明确标注了不同批次，则按 B11 拆分；与 §3.7 口径一致，并与 #59 实现对齐 | #59 集成后 |
| B6 | 2023 批次为 `review_only` / `blocked`，`human_approved` 不为 true | 不参与批次判断；结果等同未挂该批次 | #59 集成后 |
| B7 | 用不带枚举方法的 stub 检索器；再用带方法但返回 `[]` 的 stub | 前者「无法判断」→ 证据不足；后者「没有资料」→ 无资料说明；两者可区分 | 现在（stub） |
| B8 | 查询名称含空格、大小写、全半角差异（如 `ＥＤＡ 实验室`、`eda实验室`） | 归一化后命中，不漏批次 | #59 集成后 |
| B9 | 使用别名（EDA / EDA 实验室 / EDA创新实验室）检索 | 命中其他年度的相关批次，不漏 | #59 集成后 |
| B10 | 分别只挂 R3 或只挂 R4；问研究方向 / 问报名 | 类别不匹配时证据不足，不混用 R3 与 R4 | 现在（规则侧） |
| B11 | 同一年度原文明确标注「第一批」「第二批」两批资料，用户未指定批次问名录 | `needs_clarification`，追问是第几批，不擅自选批 | #59 集成后 |
| B12 | 同 B11，用户明确问「2026 年第二批」 | `answered` / `historical`，只答第二批并声明年度与批次 | #59 集成后 |
| B13 | 同一年度存在多个 `record_code` 或多个 `version_no`，但原文没有任何批次标注 | 归并为同一年度批次，不追问；不得按包或版本数量拆分 | #59 集成后 |
| B14 | 仅凭 `record_code`、`version_no` 或 R3/R4 包编号推断批次 | 负向断言：不得据此拆成多批；未标注即视为同一批次 | #59 集成后 |
| B15 | 同一年度原文标注第一批、第二批，两批联系人不同；未指定批次问联系人 | `needs_clarification`，追问第几批，不擅自选批 | #59 集成后 |
| B16 | 同 B15，用户明确问「2026 年第二批」的联系人 | `answered` / `historical`，只用第二批资料，声明年度与批次，不得表述为当前联系人 | #59 集成后 |
| B17 | 同一年度原文标注第一批、第二批，两批联系人相同；用户未指定批次问「2026 年通知里的联系人是谁？」 | `answered` / `historical`，合并回答第一批与第二批；声明两批均为历史资料，每个批次各提供一条 citation，不得表述为当前联系人 | #59 集成后 |

B1—B17 的合成数据由验收负责人按《A4测试数据设计》在本地维护，不入库、不进入 `approved/`；测试时显式加载。B11、B12、B15、B16、B17 需要合成「同年度第一批/第二批」两套标注数据，其中 B15、B16 两批联系人不同，B17 两批联系人相同；B13、B14 用同年度多包、多版本但无批次标注的数据。

---

## 4. S4-03 边界三例

| 用例 | 输入 | 预期 |
| --- | --- | --- |
| C1 | 我大二能进 EDA 实验室吗？（无年度） | `insufficient_evidence` / `insufficient_data`，不追问年度，不用历史 R3 |
| C2 | 2026 年我大二能进 EDA 实验室吗？ | `answered` / `historical`，检查年级专业，不判能否进入 |
| C3 | 现在能进 EDA 实验室吗？ | `insufficient_evidence` / `insufficient_data`（无当前通知） |

---

## 5. 学生端展示检查

对每个 `answered` 场景：

1. `Citation` 显示标题、发布单位、发布日期、定位、原文摘录、来源链接，`source_url` 与 `excerpt` 非空。
2. `answer` 每项以实验室名称开头，项间空行，末行写「共 24 条实验室记录，本次展示 K 条，完整表见来源」。
3. `answer_mode=historical` 显示历史标签；正文含具体学年与「报名已截止」。
4. `warnings` 去重：`HISTORICAL_POLICY` 与正文同句只展示一次，补充性警告保留。

---

## 6. 执行顺序与记录

1. **现在**：B7、B10、C1、C3，以及 S4-03/04/05/06/10/17/19/20/23/24。
2. **#59 集成后**：B1—B6、B8、B9、B11—B17，S4-01/02/12/14/15。
3. **P1 审核后**：S4-07/08/13/18/22 与真实资料版 S4-01/02。

S4-24 的负向回归需要先构造「历史 R3 已审核已开放且已截止 + 无当前 R3」，断言 `insufficient_evidence` / `insufficient_data`、`citations` 为空、不引用历史通知。

| 用例 | 时间 | status | answer_mode | citations | 文本要点 | 结论 | 证据 |
| --- | --- | --- | --- | --- | --- | --- | --- |
|  |  |  |  |  |  | 通过 / 失败 / BLOCKED |  |
