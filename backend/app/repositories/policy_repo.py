"""保单数据访问：写入 / 查询 / 人工修正 / 总览统计。"""

from datetime import datetime
from typing import List, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models import Policy, PolicyField, User


def create_policy(
    db: Session,
    user_id: int,
    image_path: Optional[str],
    source_filename: Optional[str],
    ocr_raw_text: str,
    quality_score: float,
    fields: dict,
) -> Policy:
    policy = Policy(
        user_id=user_id,
        image_path=image_path,
        source_filename=source_filename,
        ocr_raw_text=ocr_raw_text,
        status="completed",
        quality_score=quality_score,
    )
    db.add(policy)
    db.flush()

    db.add(PolicyField(policy_id=policy.id, **fields))
    db.commit()
    return policy


def get_policy(db: Session, policy_id: int) -> Optional[Policy]:
    """按 id 取保单，并预加载关联字段 / 用户 / 部门，避免响应序列化时触发额外查询。"""
    p = db.query(Policy).filter(Policy.id == policy_id).first()
    if p:
        p.field
        p.user
        if p.user:
            p.user.department
    return p


def list_policies(
    db: Session,
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    limit: int = 200,
) -> List[Policy]:
    q = db.query(Policy)

    if user_id:
        q = q.filter(Policy.user_id == user_id)

    if department_id:
        user_ids = [
            u.id for u in db.query(User).filter(User.department_id == department_id).all()
        ]
        q = q.filter(Policy.user_id.in_(user_ids))

    if start_date:
        q = q.filter(Policy.created_at >= start_date)
    if end_date:
        q = q.filter(Policy.created_at <= end_date + " 23:59:59")

    policies = q.order_by(Policy.created_at.desc()).limit(limit).all()
    for p in policies:
        p.field
        p.user
        if p.user:
            p.user.department
    return policies


def update_policy_fields(
    db: Session, policy_id: int, update_data: dict, quality_score: float
) -> Optional[Policy]:
    policy = db.query(Policy).filter(Policy.id == policy_id).first()
    if not policy:
        return None

    pf = policy.field
    if not pf:
        pf = PolicyField(policy_id=policy.id)
        db.add(pf)

    for k, v in update_data.items():
        setattr(pf, k, v)

    policy.quality_score = quality_score
    policy.status = "corrected"
    db.commit()
    db.refresh(policy)
    policy.field
    return policy


def get_overview(db: Session) -> dict:
    total = db.query(func.count(Policy.id)).scalar() or 0
    # 与模型默认值、报表口径保持一致：统一用本地时间，「今日新增」才符合当地日界
    today = datetime.now().date()
    today_count = (
        db.query(func.count(Policy.id))
        .filter(func.date(Policy.created_at) == today)
        .scalar()
        or 0
    )
    avg_quality = db.query(func.avg(Policy.quality_score)).scalar() or 0
    corrected = (
        db.query(func.count(Policy.id)).filter(Policy.status == "corrected").scalar() or 0
    )
    return {
        "total": total,
        "today_count": today_count,
        "avg_quality_score": round(avg_quality, 1),
        "corrected_count": corrected,
    }