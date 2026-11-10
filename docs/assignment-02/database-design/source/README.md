# 正式说明书生成与技术源文件

## 文档生成链

1. `数据库设计说明书_正文.md`维护正式正文；`build_specification.py`读取v1.2模型与既有记录，整理完整附录
2. `render_diagrams.py`从既有模型生成文档视图，并将Mermaid渲染为PNG和SVG；源稿及渲染结果保存在`../figures/`
3. `create_word_specification.py`设置Word封面、标题样式、自动目录、图表、页眉页脚和折页
4. `update_fields_export.ps1`通过独立Microsoft Word实例更新字段和目录，并导出PDF
5. `verify_specification.py`核对目录与实际页码、图形、字段约束、技术输入校验值及实施状态
6. `finalize_acceptance.py`生成正式说明书、核对并打包，不运行数据库实验

从仓库根目录执行：

```powershell
python -m pip install -r docs/assignment-02/database-design/source/requirements-document.txt
python docs/assignment-02/database-design/source/generate_pdf.py
python docs/assignment-02/database-design/source/verify_specification.py
```

输出为`../AgentX_数据库设计说明书.pdf`及本目录下的`AgentX_数据库设计说明书.docx`。需要完整交付包时，运行`finalize_acceptance.py`。

正文可以直接修改；数据字典与约束附录由模型生成。Word稿也可人工编辑，提交前在Word中更新整个目录，再导出PDF；重新运行生成脚本将按Markdown源稿重建Word文件。

目录收录正文两级标题及附录一级标题，章标题加粗、节标题缩进。标题字体显式设置为中文黑体、英文及数字Times New Roman，清除主题字体；目录页码由Word更新。

## 图形重渲染

常规生成使用已提交的渲染缓存。修改关系视图或主动重渲染时，需要Node.js、npm及Chrome/Edge/Chromium：

```powershell
python docs/assignment-02/database-design/source/generate_pdf.py --rerender-diagrams
```

渲染器固定为`@mermaid-js/mermaid-cli@11.12.0`。可通过`CODEMIND_BROWSER_PATH`指定浏览器，或以`CODEMIND_MMDC`指定已有的Mermaid CLI。文档生成使用当前Python；需要单独的Word创作运行环境时，可设置`CODEMIND_DOCX_PYTHON`。

## 已确认的数据库源文件

`models.py`、`build_deliverables.py`、`validate_deliverables.py`及两个`test_*.py`文件继续保留v1.2技术用途。`validation_report.json`记录既有21项测试、SQLite创建23张表并向8张核心表插入资料fixture的结果。

本轮文档生成不调用上述数据库构建与测试程序。原始fixture为44条37列，未包含149个物理文件；版本级提取登记与文件级物理状态分别管理。详细设计与验证原文继续保留在对应技术目录。

`业务方向顺序修正/`为丁晓炜提交的历史输入快照，供查阅原对接链接；当前文档与图形以本生成链为准。
