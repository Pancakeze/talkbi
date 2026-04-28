# TalkBI API 契约（MVP+）

Base URL：`http://localhost:8000/api`（Docker 与本地开发一致，前端通过 `VITE_API_BASE_URL` 配置）。

## 认证

- `POST /auth/login`  
  Body JSON：`{ "username": string, "password": string }`  
  响应：`{ "access_token": string, "token_type": "bearer" }`  
  后续请求 Header：`Authorization: Bearer <token>`

- `GET /me`  
  响应：当前用户信息（含 `role`）。

## 数据源

- `GET /data-sources` — 当前用户的数据源列表  
- `POST /data-sources` — 创建记录（演示用）  
- `POST /data-sources/excel/upload` — `multipart/form-data` 字段名 `file`

## 主题库

- `GET /theme-libraries`  
- `POST /theme-libraries` — `{ name, description? }`  
- `GET /theme-libraries/{id}/fields`  
- `POST /theme-libraries/{id}/fields` — `{ table_name, field_name, alias_zh, visible }`

## 对话与图表

- `POST /chat/query` — `{ prompt, theme_ids?: number[] }`  
  响应含：`sql`, `chart_spec`, `rows`, `explanation`

- `GET /charts` / `POST /charts` — 个人图表库

## 仪表盘

- `GET /dashboards` / `POST /dashboards` — `{ name }`  
- `GET /dashboards/{id}/layout` — `{ items: [{ chart_id, position_x, position_y, width, height, title }] }`  
- `PATCH /dashboards/{id}/layout` — `{ items: [...] }`（仅允许本人拥有的图表）

## SQL 安全（MVP）

服务端 `validate_sql`：仅允许以 `SELECT` 开头的语句，并拦截常见 DML/DDL 关键字；后续迭代将加入表/字段白名单与执行超时。
