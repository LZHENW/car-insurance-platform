# 车险市场信息收集平台

保单图片关键字段识别 + 多维度报表监控的一体化系统。上传 JPG / PNG / PDF 保单，自动 OCR 抽取关键字段并结构化入库；看板按用户、部门、车型、新能源、保费区间、保险公司等维度实时统计。

## 功能

- **图片关键字段识别**：支持 JPG / PNG / PDF（PDF 逐页渲染识别）；离线 OCR 引擎（RapidOCR，必要时回退 PaddleOCR）；11 个字段正则抽取（保单号、车牌号、被保险人、投保人、厂牌型号、品牌、保险公司、保费、是否新能源、投保日期、险种）；自动校验给出可疑提示；支持人工修正并自动重算质量分。
- **多维度报表监控**
  - 用户行为监控：每个操作员上传量、平均质量分、部门汇总、活跃人数。
  - 业务数据分析：车型、新能源 vs 燃油车、保费区间、保险公司、日 / 周 / 月时间粒度与趋势图。
- **实时刷新**：SSE 推送，保单新增 / 修正后看板自动更新。

## 技术栈

| 层 | 选型 |
| --- | --- |
| Web 框架 | FastAPI + Uvicorn |
| ORM / 数据库 | SQLAlchemy 2.x；默认 SQLite，可切 MySQL / PostgreSQL |
| 校验 | Pydantic v2 |
| OCR | RapidOCR（onnxruntime，离线）/ PaddleOCR（可选） |
| PDF 解析 | PyMuPDF |
| 前端 | Vue 3 + ECharts（CDN，零构建） |
| 测试 | pytest |

## 目录结构

```
car-insurance-platform/
├── backend/
│   ├── app/
│   │   ├── api/                 # HTTP 接口层
│   │   │   ├── deps.py          # 共享依赖（DB Session）
│   │   │   ├── main.py          # 汇总路由
│   │   │   └── routes/          # 按资源拆分的路由
│   │   │       ├── policies.py
│   │   │       ├── reports.py
│   │   │       ├── stream.py
│   │   │       └── users.py
│   │   ├── core/                # 配置与数据库连接
│   │   │   ├── config.py
│   │   │   └── db.py
│   │   ├── models/              # SQLAlchemy ORM 模型
│   │   ├── schemas/             # Pydantic 请求 / 响应模型
│   │   ├── services/            # 业务逻辑（OCR / 报表计算）
│   │   ├── repositories/        # 数据访问层
│   │   ├── utils/               # 通用工具（事件广播）
│   │   └── main.py              # 应用入口
│   ├── scripts/seed.py          # 演示数据初始化
│   ├── tests/                   # pytest 单元测试
│   ├── pyproject.toml
│   └── .env.example
├── frontend/index.html          # Vue3 单页看板
├── data/                        # SQLite 数据文件（运行时生成）
├── uploads/                     # 上传原件与预览图（运行时生成）
├── Dockerfile
├── docker-compose.yml
├── Makefile
└── .gitignore
```

## 快速开始

```bash
make install     # 创建 .venv 并安装依赖
make seed        # 初始化演示数据
make run         # 启动服务
```

- 看板：http://localhost:8000/static/index.html
- 接口文档：http://localhost:8000/docs

手动启动：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install --ignore-requires-python -e "backend[dev]"
.venv/bin/python backend/scripts/seed.py
.venv/bin/python -m uvicorn app.main:app --reload --app-dir backend
```

## 测试

```bash
make test
```

## 配置

复制 `backend/.env.example` 为 `.env`（项目根目录），可配置：

| 变量 | 说明 | 默认 |
| --- | --- | --- |
| `DATABASE_URL` | 数据库连接串 | `sqlite:///data/data.db` |
| `MAX_UPLOAD_MB` | 单文件上传上限（MB） | `20` |

切换到 MySQL / PostgreSQL 只需设置 `DATABASE_URL` 并安装对应驱动（`pymysql` / `psycopg2-binary`），代码无需改动。

## 注意：Python 3.13+

`rapidocr-onnxruntime` 的元数据声明 `Python <3.13`，但在 3.13 / 3.14 上实测可用，安装时需加 `--ignore-requires-python`（Makefile 已内置）。

## Docker

```bash
docker compose up --build
```

## 部署说明

- **多 worker**：SSE 事件广播为进程内实现，`--workers N>1` 时需替换为 Redis 等跨进程方案。
- **建表**：当前启动时自动 `create_all`；正式环境建议接入 Alembic 迁移。