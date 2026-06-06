# 基础镜像
FROM python:3.11-slim

# 设置工作目录
WORKDIR /app

# 安装系统依赖（healthcheck 用 curl）
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# 安装 uv 包管理器
RUN pip install uv

# 复制依赖文件（利用缓存层）
COPY pyproject.toml uv.lock* ./

# 安装 Python 依赖
RUN uv sync --frozen --no-dev

# 复制项目源码
COPY src/ ./src/

# 暴露常用端口（具体由 compose 覆盖）
EXPOSE 8001 8011 8012 8013 8014 8501

# 默认启动命令（由 compose 覆盖）
CMD ["echo", "请通过 docker-compose 指定服务启动命令"]