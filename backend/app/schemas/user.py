from typing import Optional

from pydantic import BaseModel


class UserResponse(BaseModel):
    id: int
    username: str
    department_id: int
    department_name: Optional[str] = None
    role: str

    class Config:
        from_attributes = True


class DepartmentResponse(BaseModel):
    id: int
    name: str
    parent_id: Optional[int] = None

    class Config:
        from_attributes = True