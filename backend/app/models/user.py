from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.db import Base


class User(Base):
    """操作员，隶属于某个部门。"""

    __tablename__ = "user"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, nullable=False)
    password = Column(String(100), default="123456")
    department_id = Column(Integer, ForeignKey("department.id"), nullable=False)
    role = Column(String(20), default="operator")
    created_at = Column(DateTime, default=datetime.now)

    department = relationship("Department", back_populates="users")
    policies = relationship("Policy", back_populates="user")