# 政策复核候选资料

本目录由 `python -m knowledge_base.processing.build_policy_review` 生成5份公共 `DocumentPackage`。读取入口为 [manifest.json](manifest.json)；`texts/` 保存被切片的提取/整理稿。

这里不是已人工审核通过的正式语料。当前3份 `review_only`、2份 `blocked`，没有 enabled；重新生成不会扩大检索权限。

- [核验清单](../../../../docs/assignment-03/alpha/policy-verification-matrix.md)
- [交接说明及接收代码](../../../../docs/assignment-03/alpha/policy-review-handoff.md)
- [原件与片段映射](../../../processing/policy-review/2026-11-19/chunk-source-map.json)

所有文件键相对于仓库根目录；需要连同引用的快照/原件一起交付，不能只复制JSON。原始44条登记和旧3份blocked样例保持不变。
