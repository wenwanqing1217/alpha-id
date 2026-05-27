# ── 构建阶段 ──
FROM python:3.12-slim AS builder

WORKDIR /app

# 仅复制依赖声明以利用 Docker 缓存
COPY pyproject.toml ./

# ── 运行阶段 ──
FROM python:3.12-slim

WORKDIR /app

# 安装运行时依赖
RUN pip install --no-cache-dir \
    fastapi==0.115.0 \
    uvicorn[standard]==0.30.0 \
    pydantic==2.9.0 \
    sqlalchemy==2.0.35 \
    psycopg2-binary==2.9.9 \
    cryptography==42.0.0 \
    bcrypt==4.1.0

# 复制代码
COPY src/ ./src/
COPY assets/ ./assets/

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
