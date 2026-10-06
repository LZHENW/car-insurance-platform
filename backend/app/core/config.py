"""全局配置：集中读取 .env / 环境变量与项目路径，供各层引用。"""

import os
from pathlib import Path

# backend/app/core/config.py -> backend/app/core -> backend/app -> backend -> <project root>
BACKEND_DIR = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_DIR.parent
DATA_DIR = PROJECT_ROOT / "data"
UPLOAD_DIR = PROJECT_ROOT / "uploads"
# 上传暂存：识别结果先落在这里，用户确认后才移入 UPLOAD_DIR 并写入数据库
PENDING_DIR = UPLOAD_DIR / "pending"
FRONTEND_DIR = PROJECT_ROOT / "frontend"


def _load_dotenv(path: Path) -> None:
    """极简 .env 加载：支持 KEY=VALUE 与 # 注释；已存在的环境变量优先。"""
    if not path.is_file():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


_load_dotenv(PROJECT_ROOT / ".env")


class Settings:
    APP_NAME = "车险市场信息收集平台"
    APP_VERSION = "1.0.0"

    # 路径
    DATA_DIR = DATA_DIR
    UPLOAD_DIR = UPLOAD_DIR
    PENDING_DIR = PENDING_DIR
    FRONTEND_DIR = FRONTEND_DIR

    # 数据库：默认 SQLite 落在 data/ 目录；设置 DATABASE_URL 即可切库，代码零改动
    DATABASE_URL = os.getenv("DATABASE_URL") or f"sqlite:///{DATA_DIR / 'data.db'}"

    # 上传
    MAX_UPLOAD_MB = int(os.getenv("MAX_UPLOAD_MB", "20"))


settings = Settings()