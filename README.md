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
5. 退出，用 `auditor` / `audit123456` 登录：可看历史与详情，提交作业接口返回 403 / 前端无提交入口，改配置接口同样 403。
6. 健康检查：`curl http://localhost:8184/api/health`

## 容量门禁（粘贴开跑）

- 运维在 **提交质控作业** 页顶部可配置 **最大字符数** 与 **粗估最大读段数**（按行数 / 4 向上取整），保存后落库（`capacity_config` 单行表），并可开关「拒绝时写入 rejected 草稿记录」。
- 空或纯空白粘贴直接 400 拒绝；超限时服务端返回 **413** 且不创建正式作业，开启记录时会写入一条 `status=rejected` 的草稿（快照仅保留前 500 字符），历史页「说明」列可查看拒绝原因。
- 浏览器与服务端双拦：提交页实时显示「当前字符 / 粗估读段 vs 上限」；**选样例开跑按样例内容长度校验**，粘贴框为空不会误伤样例开跑。
- 审计员（auditor）只读：不能开跑、不能改配置。

自测：把上限调小（如 100 字符）→ 粘贴偏长文本被拒且历史出现 `已拒绝` 记录与原因 → 再选合格样例（246 字符）恢复上限后仍可成功开跑。

## API

- `POST /api/auth/login`
- `GET  /api/health`
- `GET  /api/samples`（含 `content_length` / `est_reads`）
- `GET  /api/config/capacity`（登录即可读）
- `PUT  /api/config/capacity`（仅 bioops）`{ "max_chars": 200000, "max_reads": 50000, "record_rejected": true }`
- `POST /api/jobs` `{ "sampleId": 1 }` 或 `{ "fastqText": "..." }`（空文本 400；超上限 413，可选写入 rejected 草稿）
- `GET  /api/jobs`
- `GET  /api/jobs/{id}`
- `GET  /api/jobs/{id}/stages`

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
      main.py api.py auth.py models.py schemas.py capacity.py
      pipeline/{actors,runner}.py
    tests/{test_actors,test_capacity}.py
  frontend/
    Dockerfile nginx.conf
    src/pages/{Login,Samples,JobSubmit,JobDetail,JobHistory}Page.vue
```
