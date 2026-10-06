"""初始化演示数据：部门 / 用户 / 近两周历史保单。

用途：本地开发与看板演示。重复执行安全（已有数据自动跳过）。

运行（项目根目录）：
    .venv/bin/python backend/scripts/seed.py
"""

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

_BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.models import Department, Policy, PolicyField, User  # noqa: E402

COMPANIES = ["中国平安", "中国人保", "太平洋保险", "中国人寿", "太平保险", "大地保险"]
MODELS_COMBUSTION = ["丰田凯美瑞", "宝马530Li", "奔驰C200", "本田雅阁", "大众帕萨特", "奥迪A4L"]
MODELS_EV = ["特斯拉Model 3", "特斯拉Model Y", "比亚迪汉EV", "比亚迪唐EV", "蔚来ET5", "小鹏P7", "理想L7"]
PROVINCES = ["粤", "京", "沪", "浙", "苏", "川", "鄂"]

# 车型 → 品牌，避免用空格切分导致「比亚迪唐EV」被截成「比亚」
BRANDS = [
    "丰田", "宝马", "奔驰", "本田", "大众", "奥迪",
    "特斯拉", "比亚迪", "蔚来", "小鹏", "理想", "极氪", "欧拉",
]


def brand_of(model: str) -> str:
    for brand in BRANDS:
        if model.startswith(brand):
            return brand
    return model.split(" ")[0] if " " in model else model


def seed_departments_and_users(db) -> None:
    departments_data = [
        ("总公司", None),
        ("深圳分公司", 1),
        ("上海分公司", 1),
        ("北京分公司", 1),
        ("广州分公司", 1),
    ]
    for name, parent_id in departments_data:
        if not db.query(Department).filter(Department.name == name).first():
            db.add(Department(name=name, parent_id=parent_id))
    db.commit()

    department_map = {d.name: d.id for d in db.query(Department).all()}

    users_data = [
        ("张三", "深圳分公司", "operator"),
        ("李四", "深圳分公司", "operator"),
        ("王五", "上海分公司", "operator"),
        ("赵六", "北京分公司", "operator"),
        ("孙七", "广州分公司", "operator"),
        ("周八", "总公司", "admin"),
    ]
    for username, dept, role in users_data:
        if not db.query(User).filter(User.username == username).first():
            db.add(User(username=username, department_id=department_map[dept], role=role))
    db.commit()


def seed_policies(db) -> None:
    existing = db.query(Policy).count()
    if existing:
        print(f"已有保单数据 {existing} 条，跳过生成")
        return

    print("生成历史保单数据...")
    users = db.query(User).all()
    now = datetime.now()
    plate_counter = 10000
    surnames = ["张", "李", "王", "赵", "陈", "刘", "杨", "黄", "周", "吴"]
    given = ["伟", "芳", "娜", "敏", "静", "强", "磊"]

    for days_ago in range(14):
        day_start = now - timedelta(days=days_ago)
        # 越接近今天，保单量越大，体现增长势头
        growth = 14 - days_ago
        count = 10 + growth * 2 + random.randint(-2, 2)

        for _ in range(count):
            user = random.choice(users)
            is_ev = random.random() < 0.35
            model = random.choice(MODELS_EV if is_ev else MODELS_COMBUSTION)
            plate = f"{random.choice(PROVINCES)}{random.choice('ABCDEFG')}{plate_counter:05d}"
            plate_counter += 1

            policy = Policy(
                user_id=user.id,
                image_path=None,
                source_filename=None,
                ocr_raw_text=f"MOCK OCR TEXT for {plate}",
                status="completed",
                quality_score=round(random.uniform(70, 100), 1),
                created_at=day_start.replace(
                    hour=random.randint(8, 20), minute=random.randint(0, 59)
                ),
            )
            db.add(policy)
            db.flush()

            db.add(
                PolicyField(
                    policy_id=policy.id,
                    plate_number=plate,
                    owner_name=random.choice(surnames) + random.choice(given),
                    vehicle_model=model,
                    vehicle_brand=brand_of(model),
                    insurance_company=random.choice(COMPANIES),
                    premium=round(random.uniform(2500, 12000), 2),
                    is_new_energy=is_ev,
                    insurance_date=(
                        day_start - timedelta(days=random.randint(0, 30))
                    ).strftime("%Y-%m-%d"),
                    coverage=random.choice(
                        ["交强险+车损险", "全险", "交强险+第三者责任险"]
                    ),
                )
            )

    db.commit()
    print(f"完成，保单总数：{db.query(Policy).count()}")


def main() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        print("=== 初始化种子数据 ===")
        seed_departments_and_users(db)
        seed_policies(db)
        print("=== 完成 ===")
    finally:
        db.close()


if __name__ == "__main__":
    main()