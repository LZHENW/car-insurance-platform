FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# OpenCV / PyMuPDF 运行时所需的系统库
RUN apt-get update && apt-get install -y --no-install-recommends \
        libglib2.0-0 \
        libgl1 \
    && rm -rf /var/lib/apt/lists/*

COPY backend/ ./backend/
COPY frontend/ ./frontend/

RUN pip install --no-cache-dir "uvicorn[standard]" \
    && pip install --no-cache-dir -e ./backend

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8000"]