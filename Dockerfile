# 使用官方 Python 3.12 slim 镜像作为基础镜像
FROM python:3.12-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量，避免 Python 生成 .pyc 文件以及启用 stdout/stderr 缓冲
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# 安装运行时依赖（如果需要编译，可以添加构建依赖，但当前项目似乎不需要）
# 例如：apt-get update && apt-get install -y --no-install-recommends gcc && rm -rf /var/lib/apt/lists/*

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目文件
COPY tg_username_update.py .

# 创建一个目录用于挂载持久化数据（如配置文件和会话文件）
# 虽然直接在 /app 也可以，但建议用户挂载这些文件
# VOLUME ["/app/config.local.json", "/app/api_auth.session"]

# 运行脚本
ENTRYPOINT ["python", "tg_username_update.py"]
