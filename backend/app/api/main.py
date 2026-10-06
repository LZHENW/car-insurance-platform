"""汇总所有资源路由，供应用入口统一挂载。"""

from fastapi import APIRouter

from app.api.routes import policies, reports, stream, users

api_router = APIRouter()
api_router.include_router(policies.router)
api_router.include_router(reports.router)
api_router.include_router(users.router)
api_router.include_router(stream.router)