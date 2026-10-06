"""接口层共享依赖：数据库 Session 等。"""

from app.core.db import get_db

__all__ = ["get_db"]