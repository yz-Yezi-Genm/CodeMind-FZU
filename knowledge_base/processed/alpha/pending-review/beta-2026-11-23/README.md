# Beta 四领域候选资料

青禾S4当前按[B8两包](../qinghe-b8-2026-11-23/README.md)交接，R3/R4各24片段，共48。此目录旧青禾35片段混合包只保留为核验基线，不能与新两包同时正式加载；其他7份资料不变。

入口：[manifest.json](manifest.json)。8份资料、501片段；全部`blocked`、`human_approved=false`。待组长最终人工审核，不是正式开放语料。

- [四领域核验清单](../../../../../docs/assignment-03/beta/beta-policy-verification-matrix.md)
- [原件、转换与接收说明](../../../../../docs/assignment-03/beta/beta-policy-handoff.md)
- [冲突和缺失事项](../../../../../docs/assignment-03/beta/beta-policy-gaps.md)
- [青禾完整转换Markdown](texts/qinghe.md)：当期24条实验室记录，报名截止已过，人数非实时余量。

只复制本目录无法复核原件SHA；请同步仓库内关联的11月23日原件及11月19日ZIP/RAR。字段和文件键遵循现有`DocumentPackage`，路径均相对仓库根目录。

`python -m knowledge_base.processing.build_beta_policy_review --check`离线复验全部原件、片段定位和四领域隔离。重新生成始终blocked，不自动签核或放行。
