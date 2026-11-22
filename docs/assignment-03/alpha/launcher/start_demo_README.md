# CodeMind-FZU 一键演示启动器（Windows）

## 文件放置

将 `start_demo.bat` 和 `start_demo.ps1` 一起放在 CodeMind-FZU 仓库根目录，与 `backend/`、`frontend/`、`tests/` 同级。

## 首次运行

1. 安装 Python 3.10 或更高版本。
2. 安装 Node.js 18.18 或更高版本（建议 Node.js 20/22 LTS）。
3. 从 GitHub 完整克隆 CodeMind-FZU 仓库。
4. 双击 `start_demo.bat`。
5. 脚本会自动创建 `.venv`、安装后端依赖、按 `package-lock.json` 执行 `npm ci`，并在缺少时从 `backend/.env.example` 创建 `backend/.env`。
6. 选择演示模式：
   - `1`：真实 Qwen API + 合成测试资料。需要在 `backend/.env` 配置 `QWEN_API_KEY`，提交问题可能消耗 API 额度。
   - `2`：Mock Agent。不调用 Qwen，无需 API Key。默认选项。

## 重要的数据说明

真实 Qwen 模式使用 `tests/fixtures/alpha_approved/` 中的 `example.invalid` 合成测试资料，仅用于演示技术调用链路，不是福州大学正式政策资料。演示和录屏时必须明确说明，不得将生成内容表述为正式政策结论。

## 启动地址

- 学生端：<http://127.0.0.1:5173/>
- 管理端：<http://127.0.0.1:5173/admin/index.html>
- Swagger：<http://127.0.0.1:8000/docs>
- 健康检查：<http://127.0.0.1:8000/api/v1/health>

## 停止服务

分别切换到后端和前端终端，按 `Ctrl+C`。关闭启动器窗口不会自动关闭这两个服务终端。

## 自动检查内容

- 仓库文件结构与演示夹具是否完整。
- Python 版本及 `.venv`。
- `backend/requirements.txt` 是否变化；必要时自动安装依赖。
- Node.js 版本。
- `frontend/package-lock.json` 是否变化；必要时自动执行 `npm ci`。
- `backend/.env` 是否存在，并检查是否配置了 Qwen Key（不会显示密钥）。
- 8000/5173 端口是否被占用。
- 后端 `/api/v1/health` 与前端首页是否实际返回 HTTP 成功状态。

依赖安装需要网络。若安装失败，启动器会显示错误并保留错误信息窗口。
