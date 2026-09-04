FROM python:3.10-slim

# 1. 安装系统构建工具与 libclang
RUN apt-get update && apt-get install -y \
    g++ \
    make \
    git \
    nano \
    libclang-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. 创建 libclang 软链接并配置环境变量
RUN ln -sf /usr/lib/x86_64-linux-gnu/libclang-*.so.1 /usr/lib/x86_64-linux-gnu/libclang.so
ENV LIBCLANG_PATH=/usr/lib/x86_64-linux-gnu
ENV ASPECT_INJECTOR_LIBCLANG=/usr/lib/x86_64-linux-gnu/libclang.so

WORKDIR /app

# 3. 克隆工具与依赖库
RUN git clone https://github.com/Celia2024-bit/tools.git /app/tools
RUN git clone https://github.com/Celia2024-bit/util.git /app/util

WORKDIR /app/tools

# 4. 安装 Python 依赖（含 GenAI、AST 库与 Flask 服务框架）
RUN pip install --no-cache-dir \
    flask \
    flask-cors \
    requests \
    google-genai \
    jinja2 \
    clang \
    libclang

EXPOSE 8000

CMD ["python3", "server.py"]