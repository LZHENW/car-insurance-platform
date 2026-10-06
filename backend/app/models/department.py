from datetime import datetime

from sqlalchemy import Column, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import relationship

from app.core.db import Base


class Department(Base):
    """部门（parent_id 自关联，支持多级组织树）。"""

    __tablename__ = "department"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), nullable=False)
    parent_id = Column(Integer, ForeignKey("department.id"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    parent = relationship("Department", remote_side=[id])
    users = relationship("User", back_populates="department")