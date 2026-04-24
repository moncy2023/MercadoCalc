FROM python:3.10-slim

# 设置工作目录
WORKDIR /app

# 设置环境变量，防止 python 缓冲输出
ENV PYTHONUNBUFFERED=1

# 复制依赖文件并安装
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制项目所有文件到容器内
COPY . .

# 暴露 9001 端口
EXPOSE 9001

# 启动 Web 服务
CMD ["python", "main.py", "web", "--host", "0.0.0.0", "--port", "9001"]
