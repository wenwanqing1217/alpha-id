# ── 构建阶段 ──
FROM python:3.12-slim AS builder

WORKDIR /app

# 配置 pip 镜像源和超时
RUN pip install --no-cache-dir pip==24.0 && \
    pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.timeout 120

# 复制依赖声明和源代码（ editable install 需要 src/ 存在）
COPY pyproject.toml ./
COPY src/ ./src/

# 安装全部依赖（含 mcp + fairy）并生成锁文件
RUN pip install --no-cache-dir --timeout 120 -e ".[mcp,fairy]" && \
    pip freeze --exclude-editable > /tmp/frozen-requirements.txt

# ── 运行阶段 ──
FROM python:3.12-slim

WORKDIR /app

# 配置 pip 镜像源
RUN pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple && \
    pip config set global.timeout 120

# 复制依赖声明和源代码（ editable install 需要 pyproject.toml + src/ 存在)
COPY pyproject.toml ./
COPY src/ ./src/

# 优先使用本地锁文件（有则跳过 builder 阶段）
COPY --from=builder /tmp/frozen-requirements.txt /tmp/

RUN if [ -f /tmp/requirements.txt ]; then \
        pip install --no-cache-dir --timeout 120 -r /tmp/requirements.txt; \
    else \
        pip install --no-cache-dir --timeout 120 -e ".[mcp,fairy]"; \
    fi

# 复制剩余应用代码
COPY src/ ./src/
COPY assets/ ./assets/

# 健康检查
HEALTHCHECK --interval=30s --timeout=3s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

EXPOSE 8000

# 使用与 aid-api 入口一致的完整 API（含 /health 端点）
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
