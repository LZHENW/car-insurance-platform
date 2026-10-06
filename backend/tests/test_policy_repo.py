"""数据访问层单元测试：保单写入 / 查询 / 人工修正 / 总览统计。"""

from app.repositories import policy_repo, report_repo, user_repo
from app.models import Department, User
from app.services import reports


def _seed_user(db):
    dept = Department(name="测试分公司")
    db.add(dept)
    db.flush()
    user = User(username="test_user", department_id=dept.id)
    db.add(user)
    db.flush()
    return dept, user


def _make_policy(db, user_id, **fields):
    base = {
        "plate_number": "粤B12345",
        "vehicle_model": "特斯拉Model 3",
        "insurance_company": "中国平安",
        "premium": 7200.0,
        "is_new_energy": True,
    }
    base.update(fields)
    return policy_repo.create_policy(
        db, user_id, None, "mock.png", "MOCK OCR TEXT", 88.9, base
    )


class TestUserRepo:
    def test_插入并查询用户(self, db_session):
        _, user = _seed_user(db_session)
        assert user.id is not None
        assert user_repo.get_user(db_session, user.id).username == "test_user"

    def test_部门列表(self, db_session):
        _seed_user(db_session)
        assert len(user_repo.list_departments(db_session)) >= 1


class TestPolicyRepo:
    def test_创建保单(self, db_session):
        _, user = _seed_user(db_session)
        policy = _make_policy(db_session, user.id)
        assert policy.id is not None
        assert policy.field is not None
        assert policy.field.plate_number == "粤B12345"

    def test_查询保单列表(self, db_session):
        _, user = _seed_user(db_session)
        _make_policy(db_session, user.id)
        assert len(policy_repo.list_policies(db_session)) >= 1

    def test_按用户过滤(self, db_session):
        _, user = _seed_user(db_session)
        _make_policy(db_session, user.id)
        assert len(policy_repo.list_policies(db_session, user_id=user.id)) == 1
        assert len(policy_repo.list_policies(db_session, user_id=99999)) == 0

    def test_总览统计(self, db_session):
        _, user = _seed_user(db_session)
        _make_policy(db_session, user.id)
        overview = policy_repo.get_overview(db_session)
        assert overview["total"] >= 1
        assert overview["avg_quality_score"] > 0

    def test_人工修正重算质量分并置状态(self, db_session):
        _, user = _seed_user(db_session)
        policy = _make_policy(db_session, user.id)

        updated = policy_repo.update_policy_fields(
            db_session, policy.id, {"policy_number": "P20260001"}, 100.0
        )
        assert updated.status == "corrected"
        assert updated.quality_score == 100.0
        assert updated.field.policy_number == "P20260001"


class TestReportRepo:
    def test_新能源维度聚合(self, db_session):
        _, user = _seed_user(db_session)
        _make_policy(db_session, user.id)
        start, end = reports.get_time_range("day")
        rows = report_repo.new_energy_stats(db_session, start, end)
        assert sum(r.policy_count for r in rows) >= 1