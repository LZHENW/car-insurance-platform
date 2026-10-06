"""上传暂存：OCR 结果先落盘，用户确认后才写入正式库。

为什么用文件系统而不是内存字典 / Redis：
  ① 不引入新的中间件，部署零成本；
  ② 进程重启后暂存不丢，用户确认时不会「结果找不到」；
  ③ 暂存图片放在 uploads/pending 下，可直接走已挂载的 /uploads 静态路由预览。
暂存超过 TTL 未确认会被视为过期并自动清理，避免垃圾文件长期堆积。
"""

import json
import re
import shutil
import time
import uuid
from pathlib import Path
from typing import Optional

from app.core.config import settings

PENDING_TTL_SECONDS = 24 * 60 * 60
_TOKEN_PATTERN = re.compile(r"^[0-9a-f]{32}$")


def new_token() -> str:
    """生成暂存标识（uuid4 十六进制，天然不含路径分隔符）。"""
    return uuid.uuid4().hex


def is_valid_token(token: Optional[str]) -> bool:
    """校验 token 形态，防止 ../ 之类的路径穿越。"""
    return bool(token) and bool(_TOKEN_PATTERN.match(token))


def file_path(token: str, ext: str) -> Path:
    """暂存目录下该 token 的原始文件路径。"""
    return settings.PENDING_DIR / f"{token}{ext}"


def save(token: str, meta: dict) -> None:
    """写入暂存元数据（识别字段、原始文本、质量分、来源文件名等）。"""
    settings.PENDING_DIR.mkdir(parents=True, exist_ok=True)
    payload = {**meta, "created_at": time.time()}
    (settings.PENDING_DIR / f"{token}.json").write_text(
        json.dumps(payload, ensure_ascii=False), encoding="utf-8"
    )


def load(token: Optional[str]) -> Optional[dict]:
    """读取暂存元数据；不存在或已过期返回 None（过期时顺手清理）。"""
    if not is_valid_token(token):
        return None
    meta_path = settings.PENDING_DIR / f"{token}.json"
    if not meta_path.is_file():
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        drop(token)
        return None
    if time.time() - meta.get("created_at", 0) > PENDING_TTL_SECONDS:
        drop(token)
        return None
    return meta


def drop(token: Optional[str]) -> None:
    """删除该 token 的全部暂存产物（原始文件 / PDF 渲染页 / 元数据）。

    用前缀匹配而非 `token.*`：PDF 渲染页名为 `{token}_p0.png`，
    只按扩展名匹配会漏掉它们，导致暂存目录残留垃圾文件。
    """
    if not is_valid_token(token):
        return
    for path in settings.PENDING_DIR.glob(f"{token}*"):
        try:
            path.unlink()
        except OSError:
            pass


def promote(token: str) -> Optional[dict]:
    """确认入库：把暂存产物移入正式上传目录，并清理该 token 的残留。

    返回更新后的元数据；token 不存在或已过期返回 None。
    """
    meta = load(token)
    if not meta:
        return None

    settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    for name in (meta.get("source"), meta.get("preview")):
        if not name:
            continue
        src = settings.PENDING_DIR / name
        if src.is_file():
            shutil.move(str(src), str(settings.UPLOAD_DIR / name))

    drop(token)  # PDF 多页渲染的剩余页图一并清掉
    return meta