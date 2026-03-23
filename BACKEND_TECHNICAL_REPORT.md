# 后端系统技术报告

## 1. API 接口文档

本系统基于 RESTful 风格设计，采用 OpenAPI 3.0 标准。所有接口均通过 HTTP/HTTPS 协议访问。

### 1.1 通用说明

- **基础路径**: `/`
- **认证方式**: Bearer Token (Header: `Authorization: Bearer <token>`)
- **数据格式**: 请求体支持 `multipart/form-data` (用于文件上传) 和 `application/json`。响应体默认为 `application/json`。

### 1.2 核心接口详解

#### 1.2.1 图生图任务 (Image to Image)

- **路径**: `/comfy_img2img`
- **方法**: `POST`
- **描述**: 上传一张参考图和提示词，生成新的图像。（注：如果上传的图片最长边超过 768 像素，系统会自动等比缩放到 768 像素，并调整长宽为 4 的倍数。）
- **请求参数 (multipart/form-data)**:
  - `image` (File, 必填): 参考图像文件。
  - `prompt` (String, 必填): 生成提示词。
  - `priority` (Integer, 选填): 任务优先级，默认 0。系统内部采用公式 `score = time.time() - (priority * 60)` 作为排序分数，即每提升 1 个优先级等级，相当于在队列中提前排队了 60 秒。数字越大优先级越高。
- **响应示例**:
  ```json
  {
    "task_id": "d633584f-10ac-4683-86e4-8a044f3cb2f8"
  }
  ```

#### 1.2.2 人脸替换任务 (Face Swap)

- **路径**: `/face_swap`
- **方法**: `POST`
- **描述**: 将源人脸替换到目标身体图像上。
- **请求参数 (multipart/form-data)**:
  - `face_image` (File, 必填): 提供人脸的源图像。
  - `body_image` (File, 必填): 提供身体的目标图像。
  - `priority` (Integer, 选填): 优先级。
- **响应示例**:
  ```json
  {
    "task_id": "9107570e-cf35-4d42-8ea2-9c4070e9811b"
  }
  ```

#### 1.2.3 视频植入任务 (Video Insert)

- **路径**: `/perfect_video_insert`
- **方法**: `POST`
- **描述**: 将图像植入到视频生成流程中。
- **请求参数 (multipart/form-data)**:
  - `image` (File, 必填): 输入图像。
  - `prompt` (String, 必填): 提示词。
  - `width` (Integer, 默认 512): 视频宽度。
  - `height` (Integer, 默认 512): 视频高度。
  - `length` (Integer, 默认 81): 视频帧数/长度。
  - `priority` (Integer, 选填): 优先级。
- **响应示例**: 同上。

#### 1.2.4 视频编辑任务 (Video Edit)

- **路径**: `/perfect_video_edit`
- **方法**: `POST`
- **描述**: 基于图像和提示词编辑生成视频。
- **请求参数**: 同 "视频植入任务"。
- **响应示例**: 同上。

#### 1.2.5 文生图 Turbo 任务 (T2I Pornmaster Turbo)

- **路径**: `/api/v1/workflows/t2i-pornmaster-turbo`
- **方法**: `POST`
- **描述**: 文生图工作流，集成 Double checkpoints 与现实增强器。
- **请求参数 (application/json)**:
  - `prompt` (String, 必填): 生成提示词，长度 1-512。
- **查询参数**:
  - `async` (Boolean, 默认 true): 是否异步执行。若为 `false`，则同步阻塞等待结果（超时 60s）。
- **响应示例**:
  ```json
  {
    "task_id": "893c8340-96f3-469a-9e22-861f60049f57",
    "image_url": "http://192.168.1.115:9000/comfyui-temp/comfyui_00001_.png"
  }
  ```
- **cURL 示例**:
  ```bash
  curl -X POST "http://localhost:8000/api/v1/workflows/t2i-pornmaster-turbo?async=false" \
       -H "Authorization: Bearer <token>" \
       -H "Content-Type: application/json" \
       -d '{"prompt": "一張來自日本90年代Tokyo-Hot色情片中的一位可愛18歲日本女性照片"}'
  ```
- **前端调用示例 (JavaScript)**:
  ```javascript
  const response = await fetch('/api/v1/workflows/t2i-pornmaster-turbo', {
    method: 'POST',
    headers: {
      'Authorization': `Bearer ${token}`,
      'Content-Type': 'application/json'
    },
    body: JSON.stringify({ prompt: 'your prompt here' })
  });
  const data = await response.json();
  console.log('Task ID:', data.task_id);
  ```

#### 1.2.6 查询任务状态 (V1)

- **路径**: `/api/v1/tasks/{task_id}`
- **方法**: `GET`
- **描述**: 获取任务详情，包括生成图片的 URL。
- **响应示例**:
  ```json
  {
    "status": "done",
    "queue_pos": null,
    "progress": 1.0,
    "result_path": "comfyui_00001_.png",
    "image_url": "http://192.168.1.115:9000/comfyui-temp/comfyui_00001_.png"
  }
  ```

#### 1.2.7 查询任务状态 (Legacy)

- **路径**: `/status/{task_id}`
- **方法**: `GET`
- **描述**: 获取任务的当前状态、队列位置及进度。
- **响应示例**:
  ```json
  {
    "status": "done",
    "queue_pos": null,
    "queue_remaining": 0,
    "progress": 1.0,
    "error": null,
    "result_path": "ComfyUI_00001_.png"
  }
  ```
- **状态码定义**:
  - `pending`: 排队中
  - `running`: 执行中
  - `done`: 已完成
  - `error`: 失败

#### 1.2.8 获取结果文件

- **路径**: `/image/{task_id}` 或 `/video/{task_id}`
- **方法**: `GET`
- **描述**: 下载任务生成的图片或视频文件。系统会依次在本地的 `output` 目录和 `temp` 目录中寻找文件，如果本地均未找到，会自动向云端 MinIO 对象存储发起请求并下载回退（Fallback）文件。
- **错误处理**:
  - `404 Not Found`: 文件在本地和 MinIO 中均不存在或任务未完成。

#### 1.2.9 系统状态

- **路径**: `/system/status`
- **方法**: `GET`
- **响应示例**:
  ```json
  {
    "queue_size": 5,
    "queue_by_type": {
      "img2img": 2,
      "t2i-pornmaster-turbo": 3
    },
    "active_workers": 1,
    "comfy_online": true
  }
  ```

***

## 2. 系统架构设计文档

### 2.1 技术栈选型

- **编程语言**: Python 3.10
- **Web 框架**: FastAPI (高性能异步框架)
- **应用服务器**: Uvicorn (ASGI)
- **消息队列/缓存**: Redis 7.0 (用于任务队列、状态存储)
- **对象存储**: MinIO (用于图片/视频生成结果的回退下载与存储)
- **AI 引擎**: ComfyUI (基于 Stable Diffusion 的节点式工作流引擎)
- **容器化**: Docker & Docker Compose

### 2.2 架构设计 (C4 Container 模型)

```mermaid
graph TD
    User[用户/前端] -->|HTTP请求| API[API Gateway (FastAPI)]
    API -->|写入任务| Redis[(Redis Queue)]
    API -->|保存文件| FS[文件存储 (Input)]
    
    subgraph Backend Service
        Worker[异步 Worker]
        WS[WebSocket Listener]
    end
    
    Worker -->|轮询任务| Redis
    Worker -->|读取模板| WorkflowFS[Workflow Templates]
    Worker -->|提交任务 (HTTP)| ComfyUI[ComfyUI Server]
    
    ComfyUI -->|执行状态 (WS)| WS
    WS -->|更新状态| Redis
    ComfyUI -->|写入结果| FS_OUT[文件存储 (Output/Temp)]
    
    User -->|轮询状态/下载| API
    API -->|读取结果| FS_OUT
    API -.->|未命中时回退读取| MinIO[(MinIO Object Storage)]
```

### 2.3 核心机制

1. **异步任务队列**: 采用 Redis `Sorted Set` 实现优先级队列 (`comfy:queue:pending`)，确保高优先级任务优先处理。
2. **状态同步**: 通过 WebSocket 长连接实时监听 ComfyUI 的执行事件 (`execution_start`, `progress`, `executed`)，将状态实时映射回 Redis (`comfy:task:{id}`)。
3. **工作流补丁 (Patching)**: 系统维护 JSON 格式的 ComfyUI 工作流模板，Worker 根据用户输入动态替换节点参数 (Seed, Prompt, Image Path) 后提交执行。
4. **文件流转**:
   - 上传文件 -> `comfyui/input/`
   - 生成结果 -> `comfyui/output/` 或 `comfyui/temp/` (API 自动搜寻)

### 2.4 安全防护

- **认证**: 基于 HTTP Bearer Token 的简单认证机制。
- **隔离**: 后端服务与 ComfyUI 通过 Docker 网络隔离，对外仅暴露 API 端口。
- **输入校验**: Pydantic 模型严格校验请求参数类型。

***

## 3. 潜在风险与故障排查指南

### 3.1 常见错误场景

| 错误现象             | 可能原因                                     | 排查/解决策略                                                                     |
| ---------------- | ---------------------------------------- | --------------------------------------------------------------------------- |
| **任务一直 Pending** | 1. Worker 未启动2. Redis 连接失败3. 队列阻塞        | 1. 检查日志 `docker logs backend-api-1`2. 检查 Redis 服务状态3. 重启后端服务清除僵尸任务          |
| **任务 Error**     | 1. ComfyUI 离线2. 工作流 JSON 错误3. 显存不足 (OOM) | 1. 检查 ComfyUI 容器状态2. 检查 `workflows/debug_*.json` 生成的补丁文件3. 查看 ComfyUI 控制台日志 |
| **结果下载 404**     | 1. 文件生成在 Temp 目录2. 文件名解析错误3. 权限问题        | 1. 系统已自动回退查找 Temp 目录2. 检查 WebSocket `executed` 消息日志3. 确认 Docker 卷挂载权限       |
| **WebSocket 断连** | ComfyUI 重启或网络波动                          | 系统内置自动重连机制 (每 5秒 重试)，无需人工干预                                                 |

### 3.2 监控告警规则 (建议)

- **队列堆积**: 当 `queue_size > 20` 持续 5 分钟 -> 告警 (需扩容 ComfyUI 节点)。
- **Worker 存活**: 监听 `/system/status`，若 `active_workers == 0` 且队列不为空 -> 告警。
- **错误率**: 单位时间内 `status=error` 的任务比例超过 10% -> 告警。

***

## 4. 功能扩展规范

### 4.1 添加新功能模块流程

1. **准备工作流**: 在 ComfyUI 前端搭建并调试好工作流，导出为 **API Format (JSON)** (注意不是 Workflow 格式)。
2. **保存模板**: 将 JSON 文件命名为 `xxx.json` 放入 `backend/workflows/` 目录。
3. **配置映射 (可选)**: 在 `app/worker.py` 的 `load_workflow` 方法中添加类型映射，或更新 `mappings.json` 以精确控制参数替换逻辑。
4. **定义模型**: 在 `app/models.py` 的 `TaskType` 枚举中添加新类型。
5. **添加接口**: 在 `app/main.py` 添加对应的 `POST` 路由 endpoint。

### 4.2 数据库/缓存迁移

- 当前使用 Redis 作为临时状态存储，数据由 TTL (24小时) 自动过期，无持久化强需求。
- 若需升级为持久化存储 (MySQL/PG)，需引入 SQLAlchemy/Tortoise-ORM，并编写 Alembic 迁移脚本。

### 4.3 灰度发布

- 利用 Docker 部署多套 Backend + ComfyUI 环境 (如 `prod` 和 `stage`)。
- 通过 Nginx 反向代理基于 Header 或流量权重分发请求。

***

## 5. 运维操作手册

### 5.1 服务启停

```bash
# 启动服务 (后台运行)
cd /home/ubantu/backend
docker compose up -d

# 停止服务
docker compose down

# 重启 API 服务 (应用代码变更后)
docker compose restart api
```

### 5.2 日志查看

```bash
# 查看实时日志
docker logs -f backend-api-1

# 查看最近 100 行日志
docker logs --tail 100 backend-api-1

# 筛选特定任务日志
docker logs backend-api-1 | grep "task_id"
```

### 5.3 配置文件更新

1. 修改 `/home/ubantu/backend/.env` 文件。
2. 执行 `docker compose up -d` 重新加载配置。

### 5.4 数据备份

- **Redis 数据**: 默认挂载在 `redis_data` 卷。
- **文件数据**: 定期备份 `/home/ubantu/comfyui/output` 目录。
  ```bash
  # 备份 Output 目录
  tar -czf backup_output_$(date +%Y%m%d).tar.gz /home/ubantu/comfyui/output
  ```

***

## 6. 数据存储全景图

### 6.1 Redis 数据结构 (Schema)

| Key 模式                     | 类型     | TTL | 说明                                                          |
| -------------------------- | ------ | --- | ----------------------------------------------------------- |
| `comfy:task:{uuid}`        | Hash   | 24h | 存储任务详情 (status, params, result\_path, progress, error\_msg) |
| `comfy:queue:pending`      | ZSet   | -   | 等待队列。Member: task\_id, Score: 优先级权重 (当前时间戳减去 priority * 60 秒) |
| `comfy:queue:running`      | Set    | -   | 运行中任务集合。用于并发控制和故障恢复。                                        |
| `comfy:prompt:{prompt_id}` | String | 1h  | ComfyUI Prompt ID 到 Task ID 的反向映射。                          |

### 6.2 文件存储路径规划

| 路径            | 宿主机位置                 | 容器内挂载                         | 用途              |
| ------------- | --------------------- | ----------------------------- | --------------- |
| **Input**     | `~/comfyui/input`     | `/home/ubantu/comfyui/input`  | 用户上传的原始图片/视频    |
| **Output**    | `~/comfyui/output`    | `/home/ubantu/comfyui/output` | ComfyUI 生成的最终结果 |
| **Temp**      | `~/comfyui/temp`      | `/home/ubantu/comfyui/temp`   | 中间过程文件/预览图      |
| **Workflows** | `~/backend/workflows` | `/app/workflows`              | 业务逻辑模板文件        |
| **MinIO**     | -                     | -                             | 云端存储 (Bucket: `comfyui-temp`, `bot-data`, `bot-template`)，作为文件和结果的回退获取源 |

### 6.3 数据归档策略

- **定期清理**: 已部署自动化脚本 `/home/ubantu/backend/scripts/cleanup_files.sh`，用于清理 `Input`、`Output` 和 `Temp` 目录下超过 3 天的文件。
  - **Crontab 配置**: `0 3 * * * /bin/bash /home/ubantu/backend/scripts/cleanup_files.sh` (每天凌晨 3 点执行)
  - **日志记录**: 清理日志保存在 `/home/ubantu/backend/cleanup.log`。
- **结果保留**: 长期归档建议同步至对象存储 (S3/OSS)，或在清理脚本中排除特定重要文件。

