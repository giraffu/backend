FROM python:3.10-slim

WORKDIR /app

# Set proxy to speed up pip install if needed
ENV HTTP_PROXY="http://10.137.118.157:7890"
ENV HTTPS_PROXY="http://10.137.118.157:7890"

COPY requirements.txt .
# Use a fast mirror and the proxy
RUN pip install --no-cache-dir -i https://mirrors.aliyun.com/pypi/simple/ -r requirements.txt

# Unset proxy so the running container does not route internal ComfyUI/MinIO traffic through the VPN
ENV HTTP_PROXY=""
ENV HTTPS_PROXY=""

COPY . .

CMD ["python", "agent_main.py"]
