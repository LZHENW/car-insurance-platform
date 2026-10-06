"""应用入口：创建 FastAPI 实例、挂载路由与静态资源。

启动：
    cd backend && python -m app.main
或（推荐）项目根目录）：
    uvicorn app.main:app --reload --app-dir backend
"""

import sys
from pathlib import Path

# 支持 `python backend/app/main.py` 直接运行：把 backend/ 加入模块搜索路径，
# 使 `app.xxx` 绝对导入在任意工作目录下都能解析。
_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles

from app.api.main import api_router
from app.core.config import settings
from app.core.db import Base, engine

# 首次启动自动建表（生产环境建议改用 Alembic 迁移）
Base.metadata.create_all(bind=engine)

app = FastAPI(title=settings.APP_NAME, version=settings.APP_VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)


@app.middleware("http")
async def no_cache_static(request, call_next):
    """静态前端禁用缓存，避免浏览器沿用旧版 HTML 导致功能缺失。"""
    response = await call_next(request)
    if request.url.path.startswith("/static"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    return response


if settings.FRONTEND_DIR.is_dir():
    app.mount(
        "/static", StaticFiles(directory=str(settings.FRONTEND_DIR)), name="static"
    )

settings.UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
app.mount(
    "/uploads", StaticFiles(directory=str(settings.UPLOAD_DIR)), name="uploads"
)


@app.get("/")
def root():
    # 打开根路径直接进前端看板，避免只看到一段裸 JSON（接口文档在 /docs）
    return RedirectResponse(url="/static/index.html")


if __name__ == "__main__":
    import uvicorn

    # IDE 里直接 Run 本文件即可启动：
    #   前端看板  http://localhost:8000/static/index.html
    #   接口文档  http://localhost:8000/docs
    print("前端看板: http://localhost:8000/static/index.html")
    print("接口文档: http://localhost:8000/docs")

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=8000,
        reload=True,
        reload_dirs=[str(_BACKEND_DIR)],
        # SSE 为长连接，热重载时需限时强制关闭，否则会一直等待连接释放
        timeout_graceful_shutdown=3,
    )