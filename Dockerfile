# ── 构建阶段 ──
FROM python:3.12-slim AS builder

WORKDIR /app

# 安装构建依赖
RUN pip install --no-cache-dir pip==24.0

# 复制依赖声明
COPY pyproject.toml ./

# 安装全部依赖并生成锁文件
RUN pip install --no-cache-dir -e ".[all]" && \
    pip freeze --exclude-editable > /tmp/frozen-requirements.txt

# ── 运行阶段 ──
FROM python:3.12-slim

WORKDIR /app

# 优先使用本地锁文件（有则跳过 builder 阶段）
COPY requirements.txt* /tmp/ 2>/dev/null || true
COPY --from=builder /tmp/frozen-requirements.txt /tmp/ 2>/dev/null || true

RUN if [ -f /tmp/requirements.txt ]; then \
        pip install --no-cache-dir -r /tmp/requirements.txt; \
    else \
        pip install --no-cache-dir -e ".[all]"; \
    fi

# 复制应用代码
COPY src/ ./src/
COPY assets/ ./assets/

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
