"""保单识别与人工修正接口。"""

import os
import shutil
from typing import List, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.core.config import settings
from app.models import PolicyField
from app.repositories import policy_repo, user_repo
from app.schemas import (
    OCRResult,
    PolicyConfirmRequest,
    PolicyFieldBase,
    PolicyFieldResponse,
    PolicyResponse,
    PolicyUpdateField,
)
from app.services import ocr, pending
from app.utils import events

router = APIRouter(prefix="/api/policies", tags=["保单识别"])

settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_EXTS = ocr.IMAGE_EXTS | ocr.PDF_EXTS


def _to_policy_response(p) -> PolicyResponse:
    """ORM Policy → 响应模型，并补全用户名 / 部门名。"""
    pr = PolicyResponse.model_validate(p)
    if p.field:
        pr.field = PolicyFieldResponse.model_validate(p.field)
    if p.user:
        pr.username = p.user.username
        pr.department_name = p.user.department.name if p.user.department else None
    return pr


@router.post("/preview", response_model=OCRResult)
async def preview_policy(
    user_id: int = Form(...),
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """上传 JPG / PNG / PDF → OCR 识别 → 暂存结果（**不写库**）。

    前端拿到识别结果后先让用户核对 / 修正，确认时才调 /confirm 正式入库，
    这样未确认的草稿不会进入保单记录与看板统计。
    """
    user = user_repo.get_user(db, user_id)
    if not user:
        raise HTTPException(status_code=400, detail="用户不存在")

    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTS:
        raise HTTPException(
            status_code=415,
            detail=f"不支持的文件类型 {ext or '未知'}，仅支持 JPG / PNG / PDF 等",
        )

    settings.PENDING_DIR.mkdir(parents=True, exist_ok=True)
    token = pending.new_token()
    saved_path = pending.file_path(token, ext)
    with open(saved_path, "wb") as buffer:
        shutil.copyfileobj(file.file, buffer)

    try:
        result = ocr.process_policy_image(
            str(saved_path), out_dir=str(settings.PENDING_DIR)
        )
    except ocr.UnsupportedFileType as e:
        pending.drop(token)
        raise HTTPException(status_code=415, detail=str(e))
    except ocr.OCREngineUnavailable as e:
        pending.drop(token)
        raise HTTPException(status_code=503, detail=str(e))
    except Exception as e:
        pending.drop(token)
        raise HTTPException(status_code=500, detail=f"识别过程出错：{e}")

    # 关键字段全部为空 → 文件里没有保单信息，直接拒绝（自动校验第一道关）
    if not ocr.has_policy_info(result["fields"]):
        pending.drop(token)
        raise HTTPException(
            status_code=422,
            detail="未在文件中识别到保单信息，请确认上传的是车险保单（JPG / PNG / PDF）",
        )

    preview_name = os.path.basename(result["preview_image"])
    pending.save(
        token,
        {
            "source": saved_path.name,
            "source_filename": file.filename,
            "preview": preview_name,
            "raw_text": result["raw_text"],
            "fields": result["fields"],
            "quality_score": result["quality_score"],
            "warnings": result["warnings"],
            "user_id": user_id,
        },
    )

    return OCRResult(
        pending_token=token,
        image_url=f"/uploads/pending/{preview_name}",
        raw_text=result["raw_text"],
        fields=PolicyFieldBase(**result["fields"]),
        quality_score=result["quality_score"],
        warnings=result["warnings"],
    )


@router.post("/confirm", response_model=PolicyResponse)
def confirm_policy(payload: PolicyConfirmRequest, db: Session = Depends(get_db)):
    """确认添加：把暂存的识别结果（含人工修正）写入保单记录，并通知看板刷新。"""
    if not user_repo.get_user(db, payload.user_id):
        raise HTTPException(status_code=400, detail="用户不存在")

    meta = pending.load(payload.pending_token)
    if not meta:
        raise HTTPException(
            status_code=410, detail="上传结果已失效或已过期，请重新上传识别"
        )

    fields = payload.fields.model_dump()
    quality = ocr.calc_quality_score(fields)  # 按人工修正后的值重算质量分

    pending.promote(payload.pending_token)  # 暂存文件转正，之后走 /uploads 访问
    policy = policy_repo.create_policy(
        db,
        payload.user_id,
        meta.get("preview"),
        meta.get("source_filename"),
        meta["raw_text"],
        quality,
        fields,
    )

    # 入库成功 → 推送实时事件，看板与保单记录据此自动刷新
    events.bus.publish(
        {"type": "policy_created", "policy_id": policy.id, "user_id": payload.user_id}
    )
    return _to_policy_response(policy_repo.get_policy(db, policy.id))


@router.delete("/preview/{token}")
def discard_preview(token: str):
    """取消添加：清理本次上传的暂存文件，不产生任何记录。"""
    pending.drop(token)
    return {"message": "已取消添加，暂存文件已清理"}


@router.get("", response_model=List[PolicyResponse])
def list_policies(
    user_id: Optional[int] = None,
    department_id: Optional[int] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    policies = policy_repo.list_policies(
        db, user_id, department_id, start_date, end_date
    )
    return [_to_policy_response(p) for p in policies]


@router.get("/stats/overview")
def policies_overview(db: Session = Depends(get_db)):
    return policy_repo.get_overview(db)


@router.get("/{policy_id}", response_model=PolicyResponse)
def get_policy(policy_id: int, db: Session = Depends(get_db)):
    policy = policy_repo.get_policy(db, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="保单不存在")
    return _to_policy_response(policy)


@router.put("/{policy_id}/fields", response_model=PolicyResponse)
def update_policy_fields(
    policy_id: int,
    update: PolicyUpdateField,
    db: Session = Depends(get_db),
):
    """人工修正识别结果：仅更新提交的字段，并重算质量分。"""
    policy = policy_repo.get_policy(db, policy_id)
    if not policy:
        raise HTTPException(status_code=404, detail="保单不存在")

    update_data = update.model_dump(exclude_unset=True)
    if not update_data:
        raise HTTPException(status_code=400, detail="没有需要更新的字段")

    pf = policy.field or PolicyField(policy_id=policy.id)
    for k, v in update_data.items():
        setattr(pf, k, v)

    # 用修正后的全量字段重算质量分
    fields_dict = {
        c.name: getattr(pf, c.name)
        for c in PolicyField.__table__.columns
        if c.name not in ("id", "policy_id")
    }
    quality = ocr.calc_quality_score(fields_dict)

    updated = policy_repo.update_policy_fields(db, policy_id, update_data, quality)
    events.bus.publish({"type": "policy_updated", "policy_id": policy_id})
    return _to_policy_response(updated)