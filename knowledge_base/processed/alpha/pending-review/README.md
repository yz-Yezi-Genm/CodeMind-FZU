# 政策复核候选资料

本目录顶层由 `python -m knowledge_base.processing.build_policy_review` 生成 Alpha 阶段5份公共 `DocumentPackage`。读取入口为 [manifest.json](manifest.json)；`texts/` 保存被切片的提取/整理稿。

这里不是已人工审核通过的正式语料。当前3份 `review_only`、2份 `blocked`，没有 enabled；重新生成不会扩大检索权限。

- [核验清单](../../../../docs/assignment-03/alpha/policy-verification-matrix.md)
- [交接说明及接收代码](../../../../docs/assignment-03/alpha/policy-review-handoff.md)
- [原件与片段映射](../../../processing/policy-review/2026-11-19/chunk-source-map.json)

所有文件键相对于仓库根目录；需要连同引用的快照/原件一起交付，不能只复制JSON。原始44条登记和旧3份blocked样例保持不变。

## Beta 2026-11-23 候选批次

[beta-2026-11-23/](beta-2026-11-23/)保存四领域8份重新核验/新增处理的候选包，共501片段，全部blocked、未人工签核。它包含上面5份资料的新处理版本，不能将两批相加声称收集了13份独立资料。

- [Beta核验清单](../../../../docs/assignment-03/alpha/beta-policy-verification-matrix.md)
- [Beta资料交接](../../../../docs/assignment-03/alpha/beta-policy-handoff.md)
- [Beta待确认项](../../../../docs/assignment-03/alpha/beta-policy-gaps.md)

生成命令为`python -m knowledge_base.processing.build_beta_policy_review`，不会覆盖顶层Alpha包，也不会写approved。两批manifest分别加载；正式问答加载器不应读取待审核目录。
