# 系统设计说明书源文件

将可编辑源文件（DOCX/Markdown/LaTeX 等）及必要素材放在这里。最终 PDF 放在上一级 system-design/，命名为 CodeMind-FZU_系统设计说明书.pdf。

## 当前已收录源文件

| 路径 | 说明 |
|---|---|
| `tools/generate_zhaozilong_diagrams.py` | 赵紫龙技术架构图、智能问答通信图和知识入库通信图的统一生成脚本；同时输出 SVG、PNG 与 Draw.io 初稿，便于后续统一修改。 |

脚本仅使用 Python 标准库和 Pillow。运行方式：

```powershell
python docs/assignment-02/system-design/source/tools/generate_zhaozilong_diagrams.py
```
