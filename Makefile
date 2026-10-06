PY := .venv/bin/python

.PHONY: help install run seed test test-verbose clean

help:
	@echo "车险市场信息收集平台 — 常用命令"
	@echo "  make install   创建虚拟环境并安装依赖"
	@echo "  make seed      初始化演示数据（部门/用户/历史保单）"
	@echo "  make run       启动服务（http://localhost:8000）"
	@echo "  make test      运行单元测试"
	@echo "  make clean     清理缓存与临时文件"

install:
	python3 -m venv .venv
	$(PY) -m pip install -U pip
	$(PY) -m pip install --ignore-requires-python -e "backend[dev]"

seed:
	$(PY) backend/scripts/seed.py

run:
	$(PY) -m uvicorn app.main:app --reload --app-dir backend --host 0.0.0.0 --port 8000

test:
	cd backend && ../$(PY) -m pytest

test-verbose:
	cd backend && ../$(PY) -m pytest -v

clean:
	find . -path ./.venv -prune -o -name '__pycache__' -type d -print -exec rm -rf {} +
	rm -rf backend/.pytest_cache .pytest_cache