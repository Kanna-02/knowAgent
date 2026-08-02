# 本地开发

## 1. 前置条件

- Python 3.11.x
- Node.js 24.x
- PostgreSQL 与 Redis 测试实例
- 数据库账号具有目标 Schema 的建表和迁移权限

本地 HTTP 调试可设置 `KNOWAGENT_COOKIE_SECURE=false`；类生产和生产环境必须使用 HTTPS，并保持 `true`。

## 2. 后端

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[dev]"
Copy-Item .env.example .env
```

将 `.env` 中的数据库和 Redis 地址改为本地测试实例，再把变量加载到当前终端。应用不会自动读取 `.env`，可使用公司统一的环境加载方式或在 PowerShell 中显式设置。

文档解析和切分参数统一使用 `KNOWAGENT_DOCUMENT_*` 环境变量。默认值已列在 `backend/.env.example`，包括上传字节数、Office 展开大小/压缩比/归档条目数、PDF 页数与块数、Word/Markdown 块数、Excel 工作表/行/列/单元格上限，以及 chunk token 预算和块重叠数。所有上限必须为正整数，只有 `KNOWAGENT_DOCUMENT_CHUNK_OVERLAP_BLOCKS` 可以为 `0`；无效值会在配置加载时失败，不应在生产环境静默回退。

parser 是同步的 CPU/内存密集端口，只能由后续独立文档 worker 调用，不得直接放入 FastAPI `async` 请求链。目标 worker 还需在任务层配置软/硬超时和进程内存边界。

应用数据库迁移并启动 API：

```powershell
alembic upgrade head
uvicorn knowagent.api.app:app --reload --host 127.0.0.1 --port 8000
```

健康检查：`GET http://127.0.0.1:8000/health/live`。

## 3. 首个管理员

首个管理员只能通过一次性命令初始化；已有管理员后，命令会拒绝再次创建。

```powershell
knowagent-bootstrap-admin --username root.admin --display-name "平台管理员"
```

密码通过隐藏输入读取，不进入命令历史。新管理员首次从 `/admin/login` 登录后必须改密。

## 4. 批量导入用户

先为临时密码生成 Argon2id 摘要：

```powershell
knowagent-hash-password
```

按 `backend/examples/users-import.csv` 准备 UTF-8 CSV。列为：

```text
username,display_name,password_hash,role,credential_batch
```

- `password_hash` 必须是 `$argon2id$` 摘要；包含逗号时必须按 CSV 标准加双引号。
- `role` 只允许 `USER` 或 `SYSTEM_OWNER`；批量导入不能创建管理员。
- 同批账号重复、数据库已有账号或任意一行无效时，整批事务回滚。
- 所有导入账号固定设置 `must_change_password=true`。

执行导入：

```powershell
knowagent-import-users .\examples\users-import.csv
```

## 5. 前端

```powershell
cd frontend
npm ci
npm run dev -- --host 127.0.0.1 --port 5173
```

页面地址：

- 用户登录：`http://127.0.0.1:5173/login`
- 用户问答首页与系统选择：`http://127.0.0.1:5173/app`
- 管理员登录：`http://127.0.0.1:5173/admin/login`
- 业务系统管理：`http://127.0.0.1:5173/admin/systems`

Vite 将 `/api` 代理到 `http://127.0.0.1:8000`。

## 6. 验证

```powershell
cd backend
$env:PYTHONPATH = "src"
pytest tests -v

cd ..\frontend
npm test
npm run typecheck
npm run lint
npm run build
```

SSO 端点已保留适配边界，但在公司协议确认前返回 `FEATURE_DISABLED`，不应作为可用登录方式展示。
