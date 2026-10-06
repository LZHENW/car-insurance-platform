from datetime import datetime
from typing import List

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import relationship

from app.core.db import Base


class Policy(Base):
    """一次保单上传记录：OCR 原始文本、质量分、来源文件、处理状态。"""

    __tablename__ = "policy"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    image_path = Column(String(500), nullable=True)
    source_filename = Column(String(255), nullable=True)
    ocr_raw_text = Column(Text, nullable=True)
    status = Column(String(20), default="completed")  # completed / corrected
    quality_score = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    user = relationship("User", back_populates="policies")
    field = relationship("PolicyField", back_populates="policy", uselist=False)


class PolicyField(Base):
    """结构化识别结果：保单号 / 车辆 / 投保人 / 保险信息。"""

    __tablename__ = "policy_field"

    id = Column(Integer, primary_key=True, index=True)
    policy_id = Column(Integer, ForeignKey("policy.id"), unique=True, nullable=False)
    policy_number = Column(String(50), nullable=True)       # 保单号
    plate_number = Column(String(20), nullable=True)        # 车牌号
    owner_name = Column(String(50), nullable=True)          # 被保险人
    insured_name = Column(String(50), nullable=True)        # 投保人
    vehicle_model = Column(String(100), nullable=True)      # 厂牌型号
    vehicle_brand = Column(String(50), nullable=True)       # 品牌
    insurance_company = Column(String(100), nullable=True)  # 保险公司
    premium = Column(Float, nullable=True)                  # 保费
    is_new_energy = Column(Boolean, default=False)          # 是否新能源
    insurance_date = Column(String(20), nullable=True)      # 投保日期
    coverage = Column(String(500), nullable=True)           # 险种（表格多行险种名拼接）

    policy = relationship("Policy", back_populates="field")


# 参与质量评分的字段顺序（前后端共用同一份口径）
FIELD_NAMES: List[str] = [
    "policy_number", "plate_number", "owner_name", "insured_name",
    "vehicle_model", "vehicle_brand", "insurance_company", "premium",
    "is_new_energy", "insurance_date", "coverage",
]

FIELD_LABELS = {
    "policy_number": "保单号",
    "plate_number": "车牌号",
    "owner_name": "被保险人",
    "insured_name": "投保人",
    "vehicle_model": "厂牌型号",
    "vehicle_brand": "品牌",
    "insurance_company": "保险公司",
    "premium": "保费",
    "is_new_energy": "是否新能源",
    "insurance_date": "投保日期",
    "coverage": "险种",
}