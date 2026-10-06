"""pytest 共享夹具：内存库 Session，测试之间互不污染。"""

import sys
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

# 让 tests/ 能 import app.*（backend/ 目录）
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

import app.models  # noqa: F401,E402  确保所有模型注册到 Base.metadata
from app.core.db import Base  # noqa: E402


@pytest.fixture()
def db_session():
    """每个用例一个独立的内存 SQLite，用完即销毁。

    必须配 StaticPool：内存库的所有连接要指向同一份数据，
    否则 TestClient 在子线程里发请求时会拿到另一个空库（no such table）。
    """
    engine = sa.create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    session = sessionmaker(bind=engine)()
    try:
        yield session
    finally:
        session.close()
        engine.dispose()