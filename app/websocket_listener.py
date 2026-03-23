import json
import asyncio
import logging
import os
import websockets
from typing import Dict, Any
from minio import Minio
from app.config import settings
from app.queue_manager import QueueManager
from app.comfy_client import ComfyClient

logger = logging.getLogger(__name__)

class WebSocketListener:
    def __init__(self, queue_manager: QueueManager):
        self.queue_manager = queue_manager
        # Append clientId to avoid conflict and ensure we receive messages for our client
        # Although ComfyUI broadcasts execution status globally.
        self.client_id = "middleware_listener_v2"
        self.uri = f"{settings.comfy_ws_url}?clientId={self.client_id}"
        self.comfy_client = ComfyClient()
        
        # Init MinIO
        try:
            self.minio_client = Minio(
                settings.minio_endpoint,
                access_key=settings.minio_access_key,
                secret_key=settings.minio_secret_key,
                secure=settings.minio_secure
            )
            logger.info("WebSocket Listener MinIO client initialized")
        except Exception as e:
            logger.error(f"Failed to init MinIO in WebSocket Listener: {e}")
            self.minio_client = None

    async def connect_and_listen(self):
        while True:
            try:
                # max_size=None allows unlimited message size (for large binary previews)
                # ping_interval/timeout keeps connection alive
                async with websockets.connect(
                    self.uri, 
                    max_size=None, 
                    ping_interval=20, 
                    ping_timeout=20
                ) as websocket:
                    logger.info(f"Connected to ComfyUI WebSocket at {self.uri}")
                    while True:
                        message = await websocket.recv()
                        await self.handle_message(message)
            except Exception as e:
                logger.error(f"WebSocket connection error: {e}")
                await asyncio.sleep(5)

    async def handle_message(self, message: Any):
        try:
            # 1. Filter binary messages immediately
            if isinstance(message, bytes):
                return

            data = json.loads(message)
            msg_type = data.get("type")
            data_content = data.get("data", {})
            
            # Debug log for critical messages
            if msg_type in ["execution_start", "executed", "execution_error", "execution_success"]:
                logger.info(f"WS Received: {msg_type} - {str(data_content)[:200]}")

            if msg_type == "execution_start":
                prompt_id = data_content.get("prompt_id")
                # Map prompt_id to task_id
                task_id = await self.queue_manager.get_task_by_prompt_id(prompt_id)
                if task_id:
                    logger.info(f"Task {task_id} started execution (prompt_id: {prompt_id})")
                    # Update status to running (idempotent)
                    await self.queue_manager.redis.hset(
                        f"{self.queue_manager.task_prefix}{task_id}", 
                        "status", 
                        "running"
                    )

            elif msg_type == "progress":
                prompt_id = data_content.get("prompt_id")
                task_id = await self.queue_manager.get_task_by_prompt_id(prompt_id)
                if task_id:
                    value = data_content.get("value")
                    max_val = data_content.get("max")
                    if max_val:
                        progress = value / max_val
                        await self.queue_manager.update_progress(task_id, progress)

            elif msg_type == "executed":
                prompt_id = data_content.get("prompt_id")
                task_id = await self.queue_manager.get_task_by_prompt_id(prompt_id)
                
                if task_id:
                    output = data_content.get("output", {})
                    # Handle images/gifs/videos
                    images = output.get("images", [])
                    gifs = output.get("gifs", [])
                    videos = output.get("videos", [])
                    
                    result_path = ""
                    # Prioritize finding a valid output
                    if images:
                        img = images[0]
                        filename = img.get('filename', '')
                        subfolder = img.get('subfolder', '')
                        result_path = f"{subfolder}/{filename}" if subfolder else filename
                    elif gifs:
                        gif = gifs[0]
                        filename = gif.get('filename', '')
                        subfolder = gif.get('subfolder', '')
                        result_path = f"{subfolder}/{filename}" if subfolder else filename
                    elif videos:
                        video = videos[0]
                        filename = video.get('filename', '')
                        subfolder = video.get('subfolder', '')
                        result_path = f"{subfolder}/{filename}" if subfolder else filename
                        
                    logger.info(f"Task {task_id} executed. Result: {result_path}")
                    
                    # Upload to MinIO
                    if self.minio_client:
                        try:
                            # Construct absolute path
                            abs_path = os.path.join(settings.comfy_output_dir, result_path)
                            if not os.path.exists(abs_path):
                                abs_path = os.path.join(settings.comfy_temp_dir, result_path)
                            
                            if os.path.exists(abs_path):
                                content_type = "image/png"
                                if result_path.endswith(".mp4"):
                                    content_type = "video/mp4"
                                elif result_path.endswith(".gif"):
                                    content_type = "image/gif"
                                elif result_path.endswith(".jpg") or result_path.endswith(".jpeg"):
                                    content_type = "image/jpeg"
                                    
                                self.minio_client.fput_object(
                                    settings.minio_result_bucket,
                                    result_path,
                                    abs_path,
                                    content_type=content_type
                                )
                                logger.info(f"Uploaded {result_path} to MinIO bucket {settings.minio_result_bucket}")
                            else:
                                logger.warning(f"File {result_path} not found for upload")
                        except Exception as e:
                            logger.error(f"Failed to upload to MinIO: {e}")
                            
                    await self.queue_manager.complete_task(task_id, result_path)

            elif msg_type == "execution_error":
                prompt_id = data_content.get("prompt_id")
                task_id = await self.queue_manager.get_task_by_prompt_id(prompt_id)
                if task_id:
                    error_msg = str(data_content.get("exception_message", "Unknown error"))
                    logger.error(f"Task {task_id} failed: {error_msg}")
                    await self.queue_manager.fail_task(task_id, error_msg)

            elif msg_type == "execution_success":
                prompt_id = data_content.get("prompt_id")
                task_id = await self.queue_manager.get_task_by_prompt_id(prompt_id)
                
                if task_id:
                    # Check if task is still running (meaning we missed 'executed' or it wasn't sent)
                    task_status = await self.queue_manager.get_task_status(task_id)
                    if task_status and task_status.get("status") == "running":
                        logger.warning(f"Task {task_id} success but stuck in running. Fetching history...")
                        
                        # Fallback: Fetch history manually
                        try:
                            history = await self.comfy_client.get_history(prompt_id)
                            # History structure: {prompt_id: {"outputs": {node_id: {"images": [...]}}}}
                            if prompt_id in history:
                                outputs = history[prompt_id].get("outputs", {})
                                result_path = ""
                                for node_id, node_output in outputs.items():
                                    if "images" in node_output:
                                        img = node_output["images"][0]
                                        fname = img.get("filename")
                                        sub = img.get("subfolder", "")
                                        result_path = f"{sub}/{fname}" if sub else fname
                                        break
                                    if "videos" in node_output:
                                        vid = node_output["videos"][0]
                                        fname = vid.get("filename")
                                        sub = vid.get("subfolder", "")
                                        result_path = f"{sub}/{fname}" if sub else fname
                                        break
                                
                                if result_path:
                                    logger.info(f"Recovered result path from history: {result_path}")
                                    await self.queue_manager.complete_task(task_id, result_path)
                                else:
                                    logger.error(f"Could not find result in history for {task_id}")
                                    await self.queue_manager.complete_task(task_id, "") # Mark done anyway
                            else:
                                logger.error(f"No history found for {prompt_id}")
                                await self.queue_manager.complete_task(task_id, "")
                                
                        except Exception as e:
                            logger.error(f"Fallback history fetch failed: {e}")
                            # Force complete to unblock queue
                            await self.queue_manager.complete_task(task_id, "")

        except Exception as e:
            logger.error(f"Error handling message: {e}")
