"""用户与部门接口。"""

from typing import List, Optional

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories import user_repo
from app.schemas import DepartmentResponse, UserResponse

router = APIRouter(prefix="/api", tags=["用户管理"])


@router.get("/users", response_model=List[UserResponse])
def list_users(department_id: Optional[int] = None, db: Session = Depends(get_db)):
    users = user_repo.list_users(db, department_id)
    out = []
    for u in users:
        d = user_repo.get_department(db, u.department_id)
        ur = UserResponse.model_validate(u)
        ur.department_name = d.name if d else None
        out.append(ur)
    return out


@router.get("/departments", response_model=List[DepartmentResponse])
def list_departments(db: Session = Depends(get_db)):
    return user_repo.list_departments(db)