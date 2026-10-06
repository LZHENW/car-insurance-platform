from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel


class PolicyFieldBase(BaseModel):
    """保单结构化字段（提交 / 返回共用）。"""

    policy_number: Optional[str] = None
    plate_number: Optional[str] = None
    owner_name: Optional[str] = None
    insured_name: Optional[str] = None
    vehicle_model: Optional[str] = None
    vehicle_brand: Optional[str] = None
    insurance_company: Optional[str] = None
    premium: Optional[float] = None
    is_new_energy: Optional[bool] = None
    insurance_date: Optional[str] = None
    coverage: Optional[str] = None


class PolicyFieldResponse(PolicyFieldBase):
    id: int
    policy_id: int

    class Config:
        from_attributes = True


class PolicyUpdateField(PolicyFieldBase):
    """人工修正提交体：仅提交需要变更的字段。"""


class PolicyResponse(BaseModel):
    id: int
    user_id: int
    username: Optional[str] = None
    department_name: Optional[str] = None
    image_path: Optional[str] = None
    source_filename: Optional[str] = None
    ocr_raw_text: Optional[str] = None
    status: str
    quality_score: float
    created_at: datetime
    field: Optional[PolicyFieldResponse] = None

    class Config:
        from_attributes = True


class OCRResult(BaseModel):
    """识别预览响应：暂存标识 + 识别字段 + 原始文本 + 质量分 + 自动校验提示。

    该接口不写库；前端据此展示可编辑的确认表单，确认时再调 /confirm 入库。
    """

    pending_token: Optional[str] = None
    policy_id: Optional[int] = None
    image_url: Optional[str] = None
    raw_text: str
    fields: PolicyFieldBase
    quality_score: float
    warnings: List[str] = []


class PolicyConfirmRequest(BaseModel):
    """确认添加请求：暂存标识 + 操作员 + （可能已人工修正的）字段。"""

    pending_token: str
    user_id: int
    fields: PolicyFieldBase