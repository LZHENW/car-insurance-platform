"""报表数据访问：用户行为监控 + 业务维度聚合。"""

from datetime import datetime
from typing import Optional

from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.models import Department, Policy, PolicyField, User


# ──────────────────────── 用户行为监控 ────────────────────────

def user_upload_stats(
    db: Session, start: datetime, end: datetime, department_id: Optional[int] = None
):
    q = (
        db.query(
            User.id.label("user_id"),
            User.username.label("username"),
            Department.name.label("department_name"),
            func.count(Policy.id).label("upload_count"),
            func.avg(Policy.quality_score).label("avg_quality"),
        )
        .outerjoin(
            Policy,
            and_(
                Policy.user_id == User.id,
                Policy.created_at >= start,
                Policy.created_at <= end,
            ),
        )
        .outerjoin(Department, Department.id == User.department_id)
    )
    if department_id:
        q = q.filter(User.department_id == department_id)
    return q.group_by(User.id, User.username, Department.name).all()


def department_upload_stats(db: Session, start: datetime, end: datetime):
    return (
        db.query(
            Department.id.label("department_id"),
            Department.name.label("department_name"),
            func.count(Policy.id).label("upload_count"),
            func.avg(Policy.quality_score).label("avg_quality"),
            func.count(func.distinct(Policy.user_id)).label("active_users"),
        )
        .outerjoin(User, User.department_id == Department.id)
        .outerjoin(
            Policy,
            and_(
                Policy.user_id == User.id,
                Policy.created_at >= start,
                Policy.created_at <= end,
            ),
        )
        .group_by(Department.id, Department.name)
        .all()
    )


# ──────────────────────── 业务数据分析 ────────────────────────

def vehicle_model_stats(db: Session, start: datetime, end: datetime, limit: int = 50):
    return (
        db.query(
            PolicyField.vehicle_model.label("vehicle_model"),
            func.count(Policy.id).label("policy_count"),
            func.sum(PolicyField.premium).label("total_premium"),
            func.avg(PolicyField.premium).label("avg_premium"),
        )
        .join(Policy, Policy.id == PolicyField.policy_id)
        .filter(Policy.created_at >= start, Policy.created_at <= end)
        .filter(PolicyField.vehicle_model.isnot(None))
        .group_by(PolicyField.vehicle_model)
        .order_by(func.count(Policy.id).desc())
        .limit(limit)
        .all()
    )


def new_energy_stats(db: Session, start: datetime, end: datetime):
    return (
        db.query(
            PolicyField.is_new_energy.label("is_new_energy"),
            func.count(Policy.id).label("policy_count"),
            func.sum(PolicyField.premium).label("total_premium"),
        )
        .join(Policy, Policy.id == PolicyField.policy_id)
        .filter(Policy.created_at >= start, Policy.created_at <= end)
        .group_by(PolicyField.is_new_energy)
        .all()
    )


def premium_segment_stats(db: Session, start: datetime, end: datetime):
    segments = [
        ("0-1000", PolicyField.premium < 1000),
        ("1000-3000", and_(PolicyField.premium >= 1000, PolicyField.premium < 3000)),
        ("3000-5000", and_(PolicyField.premium >= 3000, PolicyField.premium < 5000)),
        ("5000-10000", and_(PolicyField.premium >= 5000, PolicyField.premium < 10000)),
        ("10000+", PolicyField.premium >= 10000),
    ]
    output = []
    for label, cond in segments:
        count = (
            db.query(func.count(Policy.id))
            .join(PolicyField, PolicyField.policy_id == Policy.id)
            .filter(Policy.created_at >= start, Policy.created_at <= end)
            .filter(cond)
            .scalar()
            or 0
        )
        total = (
            db.query(func.coalesce(func.sum(PolicyField.premium), 0))
            .join(Policy, Policy.id == PolicyField.policy_id)
            .filter(Policy.created_at >= start, Policy.created_at <= end)
            .filter(cond)
            .scalar()
            or 0
        )
        output.append(
            {"segment": label, "policy_count": count, "total_premium": round(total, 2)}
        )
    return output


def insurance_company_stats(db: Session, start: datetime, end: datetime):
    return (
        db.query(
            PolicyField.insurance_company.label("insurance_company"),
            func.count(Policy.id).label("policy_count"),
            func.sum(PolicyField.premium).label("total_premium"),
            func.avg(PolicyField.premium).label("avg_premium"),
        )
        .join(Policy, Policy.id == PolicyField.policy_id)
        .filter(Policy.created_at >= start, Policy.created_at <= end)
        .filter(PolicyField.insurance_company.isnot(None))
        .group_by(PolicyField.insurance_company)
        .order_by(func.count(Policy.id).desc())
        .all()
    )


def count_policies_in_range(db: Session, start: datetime, end: datetime) -> int:
    return (
        db.query(func.count(Policy.id))
        .filter(Policy.created_at >= start, Policy.created_at <= end)
        .scalar()
        or 0
    )


def sum_premium_in_range(db: Session, start: datetime, end: datetime) -> float:
    return (
        db.query(func.coalesce(func.sum(PolicyField.premium), 0))
        .join(Policy, Policy.id == PolicyField.policy_id)
        .filter(Policy.created_at >= start, Policy.created_at <= end)
        .scalar()
        or 0
    )