"""用户 / 部门数据访问。"""

from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import Department, User


def get_user(db: Session, user_id: int) -> Optional[User]:
    return db.query(User).filter(User.id == user_id).first()


def list_users(db: Session, department_id: Optional[int] = None) -> List[User]:
    q = db.query(User)
    if department_id:
        q = q.filter(User.department_id == department_id)
    return q.order_by(User.id).all()


def list_departments(db: Session) -> List[Department]:
    return db.query(Department).order_by(Department.id).all()


def get_department(db: Session, dept_id: int) -> Optional[Department]:
    return db.query(Department).filter(Department.id == dept_id).first()