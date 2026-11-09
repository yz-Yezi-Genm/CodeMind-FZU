# 系统设计说明书源文件

本目录存放《AgentX 系统设计说明书》的可编辑源文件。最终 PDF 放在上一级 `system-design/`，命名为 `AgentX_系统设计说明书.pdf`；正文以 Markdown 主稿为准，DOCX 与 PDF 由 `build/` 脚本生成。

## 源文件清单

| 路径 | 说明 |
|---|---|
| `系统设计说明书.md` | 系统设计说明书 Markdown 主稿（正文唯一来源） |
| `AgentX_系统设计说明书.docx` | 由主稿生成的 Word 版本（编辑/分发用） |
| `build/build.ps1` | 一键构建：pandoc → docx → Word 导出 PDF，含产物校验 |
| `build/make_reference.py` | 生成/维护中文样式模板 `reference.docx` |
| `build/postprocess.py` | 补充封面、目录域、页眉页脚与 A4 版面 |
| `build/export_pdf.ps1` | 调用 Word 将 docx 导出为 PDF |
| `../diagrams/uml/class/*.puml` | 领域类图（2 张）与服务类图（2 张）的 PlantUML 源文件 |
| `tools/generate_zhaozilong_diagrams.py` | 赵紫龙架构图与通信图的可复现生成脚本 |

## 重新构建

```powershell
powershell -ExecutionPolicy Bypass -File "docs/assignment-02/system-design/source/build/build.ps1"
```

依赖：pandoc、python-docx、Microsoft Word。
