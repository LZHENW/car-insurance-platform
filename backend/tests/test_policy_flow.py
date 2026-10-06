"""保单「上传预览 → 确认添加 → 记录/看板同步」全链路接口回归测试。

覆盖核心诉求：
  ① 预览阶段只识别、不写库；
  ② 确认后按（人工修正过的）字段写入保单记录，并带上添加时间；
  ③ 取消上传不留任何数据、暂存文件被清理；
  ④ 预览 / 确认 / 修正都会广播实时事件，供看板同步刷新。
"""

import json
from datetime import datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from app.core.config import settings
from app.core.db import get_db
from app.main import app
from app.models import Department, Policy, User
from app.services import ocr

FIELDS = {
    "policy_number": "P20250001",
    "plate_number": "晋A12345",
    "owner_name": "张三",
    "insured_name": "李四",
    "vehicle_model": "吉利美日MR6471D12多用途乘用车",
    "vehicle_brand": "吉利",
    "insurance_company": "中国平安",
    "premium": 1012.19,
    "is_new_energy": False,
    "insurance_date": "2025-03-26",
    "coverage": "机动车损失保险+机动车第三者责任保险",
}


def _fake_recognize(path, out_dir=None):
    """替身 OCR：不跑真实模型，只按真实约定产出预览图与识别结果。"""
    source = Path(path)
    out = Path(out_dir or source.parent)
    preview = out / f"{source.stem}_p0.png"
    preview.write_bytes(b"fake-preview")
    return {
        "raw_text": "保险单号：P20250001\n厂牌型号\n吉利美日MR6471D12多用途乘用车",
        "preview_image": str(preview),
        "fields": dict(FIELDS),
        "quality_score": 100.0,
        "warnings": [],
    }


@pytest.fixture()
def api(db_session, tmp_path, monkeypatch):
    """把上传目录指向临时目录、OCR 换成替身，并注入内存库。"""
    upload_dir = tmp_path / "uploads"
    (upload_dir / "pending").mkdir(parents=True)
    monkeypatch.setattr(settings, "UPLOAD_DIR", upload_dir)
    monkeypatch.setattr(settings, "PENDING_DIR", upload_dir / "pending")
    monkeypatch.setattr(ocr, "process_policy_image", _fake_recognize)

    dept = Department(name="市场部")
    user = User(username="tester", department=dept)
    db_session.add_all([dept, user])
    db_session.commit()

    app.dependency_overrides[get_db] = lambda: db_session
    try:
        with TestClient(app) as client:
            yield SimpleNamespace(
                client=client,
                user_id=user.id,
                upload_dir=upload_dir,
                pending_dir=upload_dir / "pending",
                db=db_session,
            )
    finally:
        app.dependency_overrides.clear()


def _preview(api):
    return api.client.post(
        "/api/policies/preview",
        data={"user_id": api.user_id},
        files={"file": ("policy.jpg", b"fake-bytes", "image/jpeg")},
    )


class TestPreview:
    def test_预览只识别不写库(self, api):
        r = _preview(api)
        assert r.status_code == 200

        body = r.json()
        assert body["pending_token"]
        assert body["fields"]["insurance_company"] == "中国平安"
        assert body["image_url"].startswith("/uploads/pending/")
        # 关键：此时数据库里不应有任何保单
        assert api.db.query(Policy).count() == 0
        # 暂存元数据已落盘，等待用户确认
        assert (api.pending_dir / f"{body['pending_token']}.json").is_file()

    def test_用户不存在时拒绝(self, api):
        r = api.client.post(
            "/api/policies/preview",
            data={"user_id": 99999},
            files={"file": ("policy.jpg", b"x", "image/jpeg")},
        )
        assert r.status_code == 400

    def test_不支持的文件类型被拒绝(self, api):
        r = api.client.post(
            "/api/policies/preview",
            data={"user_id": api.user_id},
            files={"file": ("policy.txt", b"x", "text/plain")},
        )
        assert r.status_code == 415
        assert api.pending_dir.exists()
        assert not list(api.pending_dir.iterdir())  # 不留垃圾文件


class TestConfirm:
    def test_确认后写入保单记录并带上添加时间(self, api):
        token = _preview(api).json()["pending_token"]

        r = api.client.post(
            "/api/policies/confirm",
            json={"pending_token": token, "user_id": api.user_id, "fields": FIELDS},
        )
        assert r.status_code == 200

        body = r.json()
        assert body["id"] > 0
        assert body["username"] == "tester"
        assert body["department_name"] == "市场部"
        assert body["field"]["insurance_company"] == "中国平安"
        # 添加时间：系统自动记录，前端「保单记录」据此展示
        assert body["created_at"]
        assert body["created_at"][:10] == datetime.now().date().isoformat()

        # 数据确实落库
        assert api.db.query(Policy).count() == 1
        # 暂存清空、图片转正到正式上传目录
        assert not list(api.pending_dir.glob(f"{token}*"))
        assert (api.upload_dir / f"{token}_p0.png").is_file()

    def test_按修正后的字段入库并重算质量分(self, api):
        token = _preview(api).json()["pending_token"]

        fixed = dict(FIELDS, premium=888.88, owner_name="王五", coverage=None)
        r = api.client.post(
            "/api/policies/confirm",
            json={"pending_token": token, "user_id": api.user_id, "fields": fixed},
        )
        assert r.status_code == 200

        body = r.json()
        assert body["field"]["premium"] == 888.88   # 采用人工修正值而非识别值
        assert body["field"]["owner_name"] == "王五"
        assert body["quality_score"] < 100          # 险种被清空 → 质量分下降

    def test_重复确认同一暂存返回410(self, api):
        token = _preview(api).json()["pending_token"]
        payload = {"pending_token": token, "user_id": api.user_id, "fields": FIELDS}

        assert api.client.post("/api/policies/confirm", json=payload).status_code == 200
        assert api.client.post("/api/policies/confirm", json=payload).status_code == 410
        assert api.db.query(Policy).count() == 1  # 不会重复入库

    def test_非法token被拒绝(self, api):
        r = api.client.post(
            "/api/policies/confirm",
            json={"pending_token": "../../etc/passwd", "user_id": api.user_id, "fields": FIELDS},
        )
        assert r.status_code == 410


class TestDiscard:
    def test_取消上传清理暂存且不产生记录(self, api):
        token = _preview(api).json()["pending_token"]

        r = api.client.delete(f"/api/policies/preview/{token}")
        assert r.status_code == 200
        assert api.db.query(Policy).count() == 0
        assert not list(api.pending_dir.glob(f"{token}*"))


class TestRecordsAndSync:
    def test_记录列表支持按添加时间筛选(self, api):
        token = _preview(api).json()["pending_token"]
        api.client.post(
            "/api/policies/confirm",
            json={"pending_token": token, "user_id": api.user_id, "fields": FIELDS},
        )

        today = datetime.now().date()
        tomorrow = today + timedelta(days=1)

        hit = api.client.get(f"/api/policies?start_date={today.isoformat()}&end_date={today.isoformat()}")
        assert len(hit.json()) == 1

        miss = api.client.get(f"/api/policies?start_date={tomorrow.isoformat()}")
        assert miss.json() == []

    def test_确认与修正都会广播实时事件(self, api):
        from app.utils import events

        queue = events.bus.subscribe()
        try:
            token = _preview(api).json()["pending_token"]
            confirmed = api.client.post(
                "/api/policies/confirm",
                json={"pending_token": token, "user_id": api.user_id, "fields": FIELDS},
            ).json()

            created = json.loads(queue.get_nowait())
            assert created["type"] == "policy_created"
            assert created["policy_id"] == confirmed["id"]

            api.client.put(
                f"/api/policies/{confirmed['id']}/fields",
                json={"premium": 666.66},
            )
            updated = json.loads(queue.get_nowait())
            assert updated["type"] == "policy_updated"
            assert updated["policy_id"] == confirmed["id"]
        finally:
            events.bus.unsubscribe(queue)