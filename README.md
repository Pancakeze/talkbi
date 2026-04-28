# TalkBI

对话式 BI：自然语言生成图表、主题库语义层、个人图表库与仪表盘（MVP+）。

产品规格与原型见目录 `TalkBI/prd`、`TalkBI/prototype`。

## 仓库结构

- `apps/api` — FastAPI + SQLAlchemy + Alembic + JWT  
- `apps/web` — React + Vite + TypeScript + ECharts  
- `infra/docker-compose.yml` — PostgreSQL + Redis（可选）+ API + Web  
- 根目录 `package.json` — npm workspaces，聚合前端子包  

## 本地开发（SQLite，默认）

自仓库根目录安装前端依赖（推荐）：

```bash
npm install
```

或仅在 `apps/web` 下 `npm install`。

```bash
cd apps/api
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

另开终端：

```bash
cd apps/web
cp .env.example .env.development   # 可选
npm run dev
```

或自根目录：`npm run dev:web`。

### 数据库迁移（Alembic）

```bash
cd apps/api
source .venv/bin/activate   # Windows: .venv\Scripts\activate
alembic revision --autogenerate -m "describe change"
alembic upgrade head
```

当前应用启动时仍会用 `create_all` 建表；迁移文件用于后续演进与生产对齐。

浏览器打开 <http://localhost:5173>，使用演示账号：`analyst` / `analyst123` 或 `admin` / `admin123`。

## Docker（PostgreSQL + 可选 Redis）

```bash
cd infra
docker compose up --build
```

`redis` 服务已包含，API 暂未连接；需要时在配置中接入 `REDIS_URL`。

API：<http://localhost:8000/docs>  
Web：<http://localhost:5173>  

## 测试

```bash
# 后端：服务层 + SQLGuard + 接口契约 + 跨用户安全
cd apps/api && pytest -q

# 前端：组件 + 路由
cd apps/web && npm run test

# E2E：默认使用本机 Chrome（playwright.config.ts 内 channel: chrome）
cd apps/web && npx playwright install chromium   # 仅首次（也可改用本机 Chrome）
cd apps/web && npm run test:e2e
```

> E2E 启动时会同时拉起 `apps/api`（用 `talkbi.e2e.db` 作为隔离 SQLite）和 `apps/web` 开发服务器。

## 环境变量

| 变量 | 说明 |
|------|------|
| `DATABASE_URL` | 默认 `sqlite+pysqlite:///./talkbi.db`；Docker 中为 PostgreSQL |
| `VITE_API_BASE_URL` | 前端请求前缀，默认 `http://localhost:8000/api` |
