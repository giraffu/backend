# 后端架构升级计划：标准化 Agent 与远程扩展支持

本文档详细描述了将现有本地紧耦合的 Worker 机制升级为**标准化、主动拉取、基于 MinIO 文件解耦的 Agent 架构**的完整四个阶段计划。该架构旨在实现业务代码的彻底解耦，并为未来一键部署远程服务器 Worker 节点提供基础。

---

## 核心架构目标
1. **彻底解耦**：将 `worker.py` 和 `websocket_listener.py` 从主控 FastAPI 服务中剥离，形成独立的 `comfy_agent` 进程。
2. **主动拉取 (Pull-based)**：Agent 通过 HTTP 轮询主控节点网关获取任务，而非主控节点推送。
3. **文件流转解耦**：摒弃共享本地磁盘路径的做法，统一使用 MinIO 作为输入图片和输出结果的中转站。

---

## 阶段 1：主控节点 (Master) 网关接口升级

主控节点需要从“直接干活”转变为纯粹的“调度中心”和“文件存储中心”。现有的 FastAPI 需要暴露专供 Agent 使用的 API。

### 1.1 核心任务
在 `app/main.py`（或新建 `app/routers/agent.py`）中新增三个核心接口：
- **`GET /api/agent/task/pop`**：Agent 轮询获取任务。Master 收到请求后从 Redis 队列中 Pop 任务，并将相关信息（含图片下载链接）返回给 Agent。
- **`POST /api/agent/task/status`**：Agent 汇报执行进度（`running`, `progress`）或错误，Master 接收后更新 Redis。
- **`POST /api/agent/task/complete`**：Agent 汇报任务完成。Agent 将生成结果上传到 MinIO 后，调用此接口通知 Master 任务已完结。

### 1.2 文件流转改造
- 用户通过 API 上传的 Input 图片，主控节点接收后**直接存入 MinIO 的 `comfyui-input` 桶**，不再依赖本地 `comfy_input_dir`。
- Master 在 `/pop` 下发任务时，将 MinIO 中的 Input 文件下载 URL 注入到任务参数中，供 Agent 下载。

### 1.3 Master 端配置新增 (`.env` 示例)
```env
# 新增 Agent 认证 Token，用于验证来拉取任务的机器身份
AGENT_SECRET_TOKEN=super_secret_agent_token_2026

# MinIO 必须配置为可被外部访问的地址 (为远程 Agent 准备)
MINIO_ENDPOINT=play.min.io:9000
MINIO_ACCESS_KEY=your_key
MINIO_SECRET_KEY=your_secret
MINIO_INPUT_BUCKET=comfyui-input   # 新增：用于存原始上传图片
MINIO_RESULT_BUCKET=comfyui-output # 现有的结果桶
```

---

## 阶段 2：开发独立的标准化 Worker Agent

这是一个**完全独立于 Master** 的 Python 项目（暂定名 `comfy_agent`），它既可以部署在 Master 本机，也可以部署在远端服务器。

### 2.1 Agent 核心职责与逻辑循环
1. **拉取任务**：每隔 N 秒向 `MASTER_URL/api/agent/task/pop` 发起带 Token 的请求。
2. **下载资源**：解析任务中的 `input_url`，通过 MinIO Client 下载文件到本机的 ComfyUI `input` 目录。
3. **组装工作流**：复用原 `worker.py` 的 `patch_workflow` 逻辑，将下载好的本地文件路径、提示词等注入 JSON 模板。
4. **提交与监听**：调用同机的 ComfyUI `/prompt` 接口提交任务；通过 `websockets` 监听同机 `ws://127.0.0.1:8188/ws` 的进度事件。
5. **同步状态**：将监听到的进度实时通过 HTTP POST 发送给 Master 的 `/status` 接口。
6. **上传结果**：监听到 `executed` 完成事件后，读取生成的图片，**Agent 直接通过 MinIO SDK 将其上传到 MinIO 的 output 桶**，然后通知 Master `complete`。

### 2.2 Agent 目录结构规划
```text
comfy_agent/
├── Dockerfile
├── requirements.txt
├── .env.example
├── agent_main.py         # 主循环与 API 通信
├── comfy_client.py       # 与本地 ComfyUI 的 HTTP/WS 交互
├── workflow_patcher.py   # JSON 模板参数注入逻辑
└── workflows/            # 存放 ComfyUI API JSON 模板
```

### 2.3 Agent 端配置 (`.env` 示例)
```env
# --- 身份与 Master 关联 ---
AGENT_ID=worker_local_01
MASTER_API_URL=http://<master_ip>:8000
AGENT_SECRET_TOKEN=super_secret_agent_token_2026

# --- 本地 ComfyUI 关联 ---
COMFY_API_URL=http://127.0.0.1:8188
COMFY_WS_URL=ws://127.0.0.1:8188/ws
COMFY_INPUT_DIR=/home/ubantu/comfyui/input
COMFY_OUTPUT_DIR=/home/ubantu/comfyui/output

# --- MinIO 配置 (Agent直接读写MinIO) ---
MINIO_ENDPOINT=play.min.io:9000
MINIO_ACCESS_KEY=your_key
MINIO_SECRET_KEY=your_secret
MINIO_INPUT_BUCKET=comfyui-input
MINIO_RESULT_BUCKET=comfyui-output
```

---

## 阶段 3：Docker 化与部署策略

为了方便未来一键扩展到多台远程服务器，需将 `comfy_agent` 容器化。

### 3.1 Agent 的 `docker-compose.yml` 示例
```yaml
version: '3.8'
services:
  comfy-agent:
    build: ./comfy_agent
    container_name: comfy-agent
    restart: unless-stopped
    env_file:
      - .env
    volumes:
      # 挂载模板目录
      - ./workflows:/app/workflows
      # 必须挂载 ComfyUI 的目录，用于 Agent 读写输入输出文件
      - /home/ubantu/comfyui/input:/home/ubantu/comfyui/input
      - /home/ubantu/comfyui/output:/home/ubantu/comfyui/output
    network_mode: "host" # 使用 host 网络，方便直连宿主机 127.0.0.1:8188 的 ComfyUI
```

### 3.2 远程扩展能力说明
当需要增加一台远程 Worker 时，只需在新机器上执行以下操作：
1. 安装并启动标准的 ComfyUI 环境。
2. 将 `comfy_agent` 目录及其 Docker 配置文件拷贝至新机器。
3. 修改 `.env`，将 `MASTER_API_URL` 和 `MINIO_ENDPOINT` 指向主控节点的公网 IP。
4. 执行 `docker compose up -d`。此时，这台远程机器就会自动向 Master 轮询并分担任务。

---

## 阶段 4：停机重构与联调测试 (Refactor & Test Strategy)

由于本次是对老的 Worker 逻辑进行彻底的底层重构（包括文件存储从本地转向 MinIO），并且不要求线上服务无缝不中断，我们采用“停机重构”策略。

### 4.1 代码重构步骤
1. **清理旧代码**：在 `app/main.py` 中，直接删除或注释掉旧的 `Worker` 和 `WebSocketListener` 的后台启动逻辑。
2. **修改上传接口**：将现有的 `/comfy_img2img` 等接口中接收图片后存入本地的逻辑，强制改为通过 MinIO SDK 存入 `comfyui-input` 桶，并生成对应的 MinIO URL。
3. **新增网关接口**：在主控端实装 `/api/agent/task/pop`、`/api/agent/task/status` 和 `/api/agent/task/complete`。

### 4.2 联调与测试
1. **重启主控服务**：停止旧的 Backend 容器，启动更新后的 Backend 服务。此时如果有新任务进来，只会堆积在 Redis 队列中，不会被消费。
2. **启动独立 Agent**：在本地启动新的 `comfy_agent` 容器。
3. **全链路验证**：
   - 提交任务，观察 Agent 是否成功通过 `/pop` 接口拿到任务。
   - 验证 Agent 是否能从 MinIO 正确下载 Input 文件。
   - 验证 Agent 调用本地 ComfyUI 的过程及状态回传 `/status` 是否正常。
   - 验证生成结束后，Agent 是否成功将结果推送到 MinIO，并调用 `/complete`。
   - 验证前端（或 API 调用方）能否通过原有的 `/image/{task_id}` 或直接通过 MinIO 链接获取到最终图片。
