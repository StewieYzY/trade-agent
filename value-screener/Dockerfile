FROM python:3.11-slim

WORKDIR /app

# akshare 依赖 lxml（需要 libxml2/libxslt 编译）
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libxml2-dev \
    libxslt-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

COPY . .

ENTRYPOINT ["python", "cli.py"]
