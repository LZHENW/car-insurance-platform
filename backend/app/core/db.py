"""数据库连接：engine / SessionLocal / get_db 依赖。"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from app.core.config import settings

# SQLite 需要目录先存在
settings.DATA_DIR.mkdir(parents=True, exist_ok=True)

# SQLite 需要允许跨线程访问；其它数据库不需要该参数
_connect_args = (
    {"check_same_thread": False} if settings.DATABASE_URL.startswith("sqlite") else {}
)

engine = create_engine(settings.DATABASE_URL, connect_args=_connect_args)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()