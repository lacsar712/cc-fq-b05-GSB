# FASTQ 质控流水线台（FASTQ QC Pipeline Console）

从零实现的全栈演示：上传/选择小型 FASTQ → **Actor 队列流水线**质控 → 查看阶段状态与指标。

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python 3.11 · FastAPI · SQLAlchemy · PostgreSQL |
| 流水线 | `ParseActor` → `QualityHistActor` → `NContentActor` → `ReportActor`（asyncio.Queue） |
| 前端 | Vue 3 · Vite · Quasar · 中文 UI · nginx `/api` 反代 |
| 基建 | docker compose（db / backend / seed / frontend） |

## 端口

| 服务 | 地址 |
|------|------|
| Frontend | http://localhost:3184 |
| Backend API | http://localhost:8184 |
| PostgreSQL | localhost:54384 |

## 账号

| 用户 | 密码 | 权限 |
|------|------|------|
| `bioops` | `fastq123456` | 可提交质控作业 |
| `auditor` | `audit123456` | 只读结果，不可提交 |

## 一键启动

```bash
cd projects/09-fastq-qc-pipeline
docker compose up --build
```

镜像源：Postgres/Node/Nginx 使用 `docker.m.daocloud.io`；npm 使用 `registry.npmmirror.com`；pip 使用清华源。

启动后 seed 会写入：

- `demo-good-r1`：合格样例（可算出 `mean_quality` / `n_rate`）
- `demo-broken-malformed`：损坏样例（`ParseActor` 失败，后续阶段 skipped）

## Verification（验收）

1. 打开 http://localhost:3184 ，用 `bioops` / `fastq123456` 登录。
2. **样例库** 看到 2 条样例 → 选合格样例 **提交质控作业**。
3. 作业详情页看到四个 Actor 阶段均为成功，指标卡出现 `reads` / `mean_quality` / `n_rate`。
4. 再跑损坏样例：`ParseActor` = failed，其余 = skipped。
5. 退出，用 `auditor` / `audit123456` 登录：可看历史与详情，提交作业接口返回 403 / 前端无提交入口。
6. 健康检查：`curl http://localhost:8184/api/health`

## API

- `POST /api/auth/login`
- `GET  /api/health`
- `GET  /api/samples`（含 `char_count` / `read_estimate` 内容规模字段）
- `POST /api/jobs` `{ "sampleId": 1 }` 或 `{ "fastqText": "..." }`
  - 可选 `saveRejectedDraft`（默认 `true`）：超限时是否留存 rejected 草稿
  - 空/纯空白 → `400`；超容量门禁 → `422`（结构化 `detail`：原因/实际值/上限/`draft_id`）
- `GET  /api/jobs`（含 `status=rejected` 草稿，`error_message` 为拒绝原因）
- `GET  /api/jobs/{id}`
- `GET  /api/jobs/{id}/stages`（rejected 草稿无阶段，返回 `[]`）
- `GET  /api/config/limits`（登录可见）
- `PUT  /api/config/limits` `{ "max_chars": 300, "max_reads": 5 }`（仅 bioops）

## 容量门禁与 rejected 草稿

- 运维可在 **门禁配置** 页（或 `PUT /api/config/limits`）配置**最大字符数**与**粗估最大读段数**，落库于 `system_config` 表，启动时缺失/损坏自动自愈为默认值（200000 字符 / 5000 读段）。
- 字符数按去除首尾空白后的长度计；读段数按非空行数 ÷ 4 向上取整**粗估**。
- 浏览器与服务端双拦：前端按当前内容实时显示 `实际/上限` 并在超限本地拦截；服务端为最终裁决。
- 选样例开跑按**样例内容长度**计量，粘贴框为空不影响样例提交。
- 超限不创建正式作业、不进入流水线；可选写入一条 `status=rejected` 草稿（含拒绝原因、实际值与上限），在历史/详情页可查。
- 空或纯空白直接 `400`，不留草稿。
- 审计员：无开跑入口（接口 403）、门禁配置页只读（PUT 403）。

## 自测（容量门禁）

1. `bioops` 登录 → 门禁配置：上限改为 **300 字符 / 5 读段**（合格样例 256 字符 / 3 读段）。
2. 提交页粘贴偏长文本（如 20 条读段 ≈ 649 字符）：浏览器即拦截；即使绕过前端，服务端返回 422 并按勾选留存 rejected 草稿。
3. 作业历史出现「已拒绝」记录，列中显示拒绝原因；详情页显示实际值/上限，且无 Actor 阶段。
4. 不切回配置，直接选合格样例 `demo-good-r1` 开跑：仍创建成功并跑完四个 Actor。
5. 空白粘贴直接提示，不产生任何记录；`auditor` 登录看不到开跑入口、配置页只读。

## 本地单测（可选）

```bash
cd backend
pip install -r requirements.txt
pytest -q
```

覆盖：畸形 FASTQ 在 `ParseActor` 失败；正常样例产出 `mean_quality`。

## 目录结构

```
09-fastq-qc-pipeline/
  PRD.md
  README.md
  docker-compose.yml
  backend/
    Dockerfile
    seed.py
    data/{good,broken}.fastq
    app/
      main.py api.py auth.py models.py schemas.py
      limits.py config_store.py
      pipeline/{actors,runner}.py
    tests/{conftest,test_actors,test_limits,test_gate_api}.py
  frontend/
    Dockerfile nginx.conf
    src/
      utils/limits.js
      pages/{Login,Samples,JobSubmit,JobDetail,JobHistory,LimitsConfig}Page.vue
```
