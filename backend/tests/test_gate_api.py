"""API tests for the capacity gate, rejected drafts, and role checks."""

import pytest
from fastapi.testclient import TestClient

from app.database import Base, SessionLocal, engine
from app.main import app
from app.models import Sample


GOOD_FASTQ = """@SEQ1
ACGTACGT
+
IIIIHHHH
@SEQ2
NNNNACGT
+
IIIIIIII
"""

LONGER_FASTQ = "\n".join(
    [f"@R{i}\nACGTACGTACGT\n+\nIIIIIIIIIIII" for i in range(20)]
) + "\n"


@pytest.fixture(scope="module")
def client():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    db.add(
        Sample(
            name="unit-good",
            description="合格样例",
            is_broken=False,
            fastq_content=GOOD_FASTQ,
        )
    )
    db.add(
        Sample(
            name="unit-broken",
            description="损坏样例",
            is_broken=True,
            fastq_content="@X\nAC\nNO+\nII\n",
        )
    )
    db.commit()
    db.close()
    with TestClient(app) as c:
        yield c


def _login(client, username, password):
    resp = client.post("/api/auth/login", json={"username": username, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


def test_limits_defaults_visible_to_auditor(client):
    token = _login(client, "auditor", "audit123456")
    resp = client.get("/api/config/limits", headers=_auth(token))
    assert resp.status_code == 200
    data = resp.json()
    assert data["max_chars"] > 0 and data["max_reads"] > 0


def test_auditor_cannot_update_limits(client):
    token = _login(client, "auditor", "audit123456")
    resp = client.put(
        "/api/config/limits",
        headers=_auth(token),
        json={"max_chars": 100, "max_reads": 10},
    )
    assert resp.status_code == 403


def test_auditor_cannot_create_job(client):
    token = _login(client, "auditor", "audit123456")
    resp = client.post(
        "/api/jobs", headers=_auth(token), json={"fastqText": GOOD_FASTQ}
    )
    assert resp.status_code == 403


def test_blank_paste_rejected_400_no_draft(client):
    token = _login(client, "bioops", "fastq123456")
    resp = client.post(
        "/api/jobs", headers=_auth(token), json={"fastqText": "   \n\t "}
    )
    assert resp.status_code == 400
    # 空白拒绝不留草稿：最新一条 rejected 记录数应不增加（后续用历史校验）
    history = client.get("/api/jobs", headers=_auth(token)).json()
    assert all(j["status"] != "rejected" for j in history)


def test_gate_reject_creates_visible_draft_then_sample_still_works(client):
    """自测主线：调小上限 → 偏长粘贴被拒且历史可见原因 → 合格样例仍成功。"""
    token = _login(client, "bioops", "fastq123456")
    headers = _auth(token)

    # 1) 把上限调小：200 字符 / 5 读段（合格样例 ~51 字符 / 2 读段，仍达标）
    small = client.put(
        "/api/config/limits",
        headers=headers,
        json={"max_chars": 200, "max_reads": 5},
    )
    assert small.status_code == 200, small.text
    assert small.json()["max_chars"] == 200

    # 2) 粘贴偏长文本（~620 字符 / 20 读段）→ 422 + rejected 草稿
    resp = client.post(
        "/api/jobs", headers=headers, json={"fastqText": LONGER_FASTQ}
    )
    assert resp.status_code == 422, resp.text
    detail = resp.json()["detail"]
    assert isinstance(detail, dict)
    assert "字符数" in detail["reason"] or "读段数" in detail["reason"]
    assert detail["char_count"] > 200 or detail["read_estimate"] > 5
    assert detail["draft_saved"] is True
    draft_id = detail["draft_id"]
    assert draft_id is not None

    # 3) 历史可见 rejected 草稿及拒绝原因
    history = client.get("/api/jobs", headers=headers).json()
    draft = next(j for j in history if j["id"] == draft_id)
    assert draft["status"] == "rejected"
    assert draft["error_message"] == detail["reason"]
    assert draft["metrics"]["char_count"] == detail["char_count"]
    assert draft["metrics"]["max_chars"] == 200

    # 4) 草稿详情可见，且无任何 Actor 阶段
    detail_resp = client.get(f"/api/jobs/{draft_id}", headers=headers)
    assert detail_resp.status_code == 200
    assert detail_resp.json()["status"] == "rejected"
    stages = client.get(f"/api/jobs/{draft_id}/stages", headers=headers).json()
    assert stages == []

    # 5) 同一门禁下选合格样例仍可成功——按样例内容长度，不受粘贴框空值误伤
    sample = next(
        s for s in client.get("/api/samples", headers=headers).json()
        if s["name"] == "unit-good"
    )
    assert sample["char_count"] <= 200 and sample["read_estimate"] <= 5
    job_resp = client.post(
        "/api/jobs", headers=headers, json={"sampleId": sample["id"]}
    )
    assert job_resp.status_code == 201, job_resp.text
    job = job_resp.json()
    assert job["status"] in ("pending", "running", "success")
    assert job["sample_name"] == "unit-good"

    # 6) 后台任务在 TestClient 下同步执行完成
    final = client.get(f"/api/jobs/{job['id']}", headers=headers).json()
    assert final["status"] == "success"
    assert final["metrics"]["reads"] == 2

    # 恢复默认上限
    client.put(
        "/api/config/limits",
        headers=headers,
        json={"max_chars": 200_000, "max_reads": 5_000},
    )


def test_sample_that_exceeds_gate_is_rejected_too(client):
    token = _login(client, "bioops", "fastq123456")
    headers = _auth(token)
    # 紧门禁：样例内容也受门禁约束
    client.put(
        "/api/config/limits",
        headers=headers,
        json={"max_chars": 10, "max_reads": 1},
    )
    sample = next(s for s in client.get("/api/samples", headers=headers).json()
                  if s["name"] == "unit-good")
    resp = client.post(
        "/api/jobs", headers=headers, json={"sampleId": sample["id"]}
    )
    try:
        assert resp.status_code == 422
        assert resp.json()["detail"]["draft_saved"] is True
    finally:
        client.put(
            "/api/config/limits",
            headers=headers,
            json={"max_chars": 200_000, "max_reads": 5_000},
        )


def test_no_draft_when_flag_false(client):
    token = _login(client, "bioops", "fastq123456")
    headers = _auth(token)
    client.put(
        "/api/config/limits",
        headers=headers,
        json={"max_chars": 10, "max_reads": 1},
    )
    try:
        before = len(client.get("/api/jobs", headers=headers).json())
        resp = client.post(
            "/api/jobs",
            headers=headers,
            json={"fastqText": GOOD_FASTQ, "saveRejectedDraft": False},
        )
        assert resp.status_code == 422
        detail = resp.json()["detail"]
        assert detail["draft_saved"] is False
        assert detail["draft_id"] is None
        after = client.get("/api/jobs", headers=headers).json()
        # 未留存草稿：历史条数不变
        assert len(after) == before
    finally:
        client.put(
            "/api/config/limits",
            headers=headers,
            json={"max_chars": 200_000, "max_reads": 5_000},
        )
