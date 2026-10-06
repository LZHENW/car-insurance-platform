"""多维度报表接口：用户行为监控 + 业务数据分析。"""

from datetime import date, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.repositories import report_repo
from app.services import reports

router = APIRouter(prefix="/api/reports", tags=["报表监控"])

_DIMENSION = Query("day", pattern="^(day|week|month)$")


def _time_params(dimension: str, date_str: Optional[str]):
    return reports.get_time_range(dimension, date_str)


@router.get("/user_stats")
def user_upload_stats(
    dimension: str = _DIMENSION,
    date: Optional[str] = None,
    department_id: Optional[int] = None,
    db: Session = Depends(get_db),
):
    """每个操作员的上传量与平均质量分。"""
    start, end = _time_params(dimension, date)
    results = report_repo.user_upload_stats(db, start, end, department_id)
    return [
        {
            "user_id": r.user_id,
            "username": r.username,
            "department_name": r.department_name,
            "upload_count": r.upload_count,
            "avg_quality": round(r.avg_quality or 0, 1),
        }
        for r in results
    ]


@router.get("/department_stats")
def department_upload_stats(
    dimension: str = _DIMENSION,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """部门维度汇总：上传量 / 平均质量分 / 活跃人数。"""
    start, end = _time_params(dimension, date)
    results = report_repo.department_upload_stats(db, start, end)
    return [
        {
            "department_id": r.department_id,
            "department_name": r.department_name,
            "upload_count": r.upload_count,
            "avg_quality": round(r.avg_quality or 0, 1),
            "active_users": r.active_users,
        }
        for r in results
    ]


@router.get("/vehicle_model")
def vehicle_model_report(
    dimension: str = _DIMENSION,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    start, end = _time_params(dimension, date)
    results = report_repo.vehicle_model_stats(db, start, end)
    return [
        {
            "vehicle_model": r.vehicle_model,
            "policy_count": r.policy_count,
            "total_premium": round(r.total_premium or 0, 2),
            "avg_premium": round(r.avg_premium or 0, 2),
        }
        for r in results
    ]


@router.get("/new_energy")
def new_energy_report(
    dimension: str = _DIMENSION,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """新能源 vs 燃油车：保单量 / 保费总额 / 市场占比。"""
    start, end = _time_params(dimension, date)
    results = report_repo.new_energy_stats(db, start, end)
    total = sum(r.policy_count for r in results)
    return [
        {
            "is_new_energy": bool(r.is_new_energy),
            "label": "新能源" if r.is_new_energy else "燃油车",
            "policy_count": r.policy_count,
            "total_premium": round(r.total_premium or 0, 2),
            "market_share": round(r.policy_count / total * 100, 1) if total > 0 else 0,
        }
        for r in results
    ]


@router.get("/premium_segment")
def premium_segment_report(
    dimension: str = _DIMENSION,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """保费区间分布。"""
    start, end = _time_params(dimension, date)
    return report_repo.premium_segment_stats(db, start, end)


@router.get("/insurance_company")
def insurance_company_report(
    dimension: str = _DIMENSION,
    date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """保险公司维度：保单量 / 保费 / 市场占比。"""
    start, end = _time_params(dimension, date)
    results = report_repo.insurance_company_stats(db, start, end)
    total = sum(r.policy_count for r in results)
    return [
        {
            "insurance_company": r.insurance_company,
            "policy_count": r.policy_count,
            "total_premium": round(r.total_premium or 0, 2),
            "avg_premium": round(r.avg_premium or 0, 2),
            "market_share": round(r.policy_count / total * 100, 1) if total > 0 else 0,
        }
        for r in results
    ]


@router.get("/time_series")
def time_series_report(
    dimension: str = _DIMENSION,
    days: int = Query(14),
    db: Session = Depends(get_db),
):
    """趋势图：近 N 个时间桶的保单量与保费总额。"""
    output = []
    for i in range(days):
        target = (date.today() - timedelta(days=days - 1 - i)).isoformat()
        start, end = reports.get_time_range(dimension, target)
        output.append(
            {
                "period": target,
                "count": report_repo.count_policies_in_range(db, start, end),
                "total_premium": round(
                    report_repo.sum_premium_in_range(db, start, end), 2
                ),
            }
        )
    return output