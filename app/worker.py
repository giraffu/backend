import asyncio
import json
import logging
import os
import random
from typing import Dict, Any
from app.config import settings
from app.queue_manager import QueueManager
from app.comfy_client import ComfyClient
from app.models import TaskType, TaskStatus
from PIL import Image

logger = logging.getLogger(__name__)

class Worker:
    def __init__(self, queue_manager: QueueManager, comfy_client: ComfyClient):
        self.queue_manager = queue_manager
        self.comfy_client = comfy_client
        self.running = False
        self.mappings = self.load_mappings()

    def load_mappings(self) -> Dict[str, Any]:
        mapping_path = os.path.join(settings.workflows_dir, "mappings.json")
        if os.path.exists(mapping_path):
            with open(mapping_path, "r") as f:
                return json.load(f)
        return {}

    async def start(self):
        self.running = True
        logger.info("Worker started")
        
        # Clear any stale running tasks on startup
        await self.queue_manager.clear_running_tasks()
        
        while self.running:
            try:
                # Check concurrency
                active_count = await self.queue_manager.get_active_workers_count()
                if active_count >= 1:
                    await asyncio.sleep(1)
                    continue

                # Dequeue task
                task_data = await self.queue_manager.dequeue_task()
                if not task_data:
                    await asyncio.sleep(0.5)
                    continue

                task_id, score = task_data
                logger.info(f"Processing task {task_id}")
                
                # Get task details
                task = await self.queue_manager.get_task_status(task_id)
                if not task:
                    logger.error(f"Task {task_id} data not found")
                    continue

                await self.process_task(task_id, task)

            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                await asyncio.sleep(5)

    async def process_task(self, task_id: str, task: Dict[str, Any]):
        max_retries = 3
        retry_delay = 1
        
        for attempt in range(max_retries):
            try:
                task_type = task.get("type")
                params = json.loads(task.get("params", "{}"))
                
                # Calculate image dimensions for IMG2IMG
                if task_type == TaskType.IMG2IMG and "image" in params:
                    try:
                        image_path = os.path.join(settings.comfy_input_dir, params["image"])
                        if os.path.exists(image_path):
                            with Image.open(image_path) as img:
                                w, h = img.size
                                
                            # Resize logic: max side 768 only if input is larger than 768, other side multiple of 4
                            if max(w, h) > 768:
                                scale = 768 / max(w, h)
                            else:
                                scale = 1.0
                            
                            new_w = int(round((w * scale) / 4) * 4)
                            new_h = int(round((h * scale) / 4) * 4)
                            
                            params["width"] = new_w
                            params["height"] = new_h
                            logger.info(f"Task {task_id}: Calculated dimensions {new_w}x{new_h} from original {w}x{h}")
                    except Exception as e:
                        logger.error(f"Task {task_id}: Failed to calculate image dimensions: {e}")
                
                # Load workflow
                workflow = self.load_workflow(task_type)
                if not workflow:
                    raise ValueError(f"Workflow for {task_type} not found")

                # Patch workflow
                patched_workflow = self.patch_workflow(task_type, workflow, params)

                # DEBUG: Save patched workflow to file
                debug_path = os.path.join(settings.workflows_dir, f"debug_patched_{task_type}.json")
                with open(debug_path, "w") as f:
                    json.dump(patched_workflow, f, indent=2)

                # Submit to ComfyUI
                prompt_id = await self.comfy_client.queue_prompt(patched_workflow, client_id="middleware_listener_v2")
                
                # Update Redis
                await self.queue_manager.set_prompt_id(task_id, prompt_id)
                logger.info(f"Task {task_id} submitted, prompt_id: {prompt_id} (attempt {attempt+1})")
                return # Success

            except Exception as e:
                logger.error(f"Failed to process task {task_id} (attempt {attempt+1}): {e}")
                if attempt < max_retries - 1:
                    wait_time = retry_delay * (2 ** attempt) # Exponential backoff
                    await asyncio.sleep(wait_time)
                else:
                    await self.queue_manager.fail_task(task_id, str(e))

    def strip_meta(self, data: Any) -> Any:
        if isinstance(data, dict):
            data.pop("_meta", None)
            for key, value in data.items():
                data[key] = self.strip_meta(value)
        elif isinstance(data, list):
            for i in range(len(data)):
                data[i] = self.strip_meta(data[i])
        return data

    def load_workflow(self, task_type: str) -> Dict[str, Any]:
        filename = f"{task_type}.json"
        # Map task types to filenames
        if task_type == TaskType.IMG2IMG:
            filename = "Qwen-Rapid-AIO.json"
        elif task_type == TaskType.FACE_SWAP:
            filename = "face_swap.json"
        elif task_type == TaskType.VIDEO_INSERT:
            filename = "perfect_video_insert.json"
        elif task_type == TaskType.VIDEO_EDIT:
            filename = "perfect_video_edit.json"
        elif task_type == TaskType.T2I_PORNMASTER_TURBO:
            filename = "Pornmaster Z-Image Turbo_t2i_Double checkpoints & realism enhancer_V1_2026_01_24.json"
            
        path = os.path.join(settings.workflows_dir, filename)
        if not os.path.exists(path):
            logger.error(f"Workflow file {path} not found")
            return None
            
        with open(path, "r") as f:
            data = json.load(f)
            data = self.strip_meta(data)
            
            if isinstance(data, dict) and "nodes" in data and isinstance(data["nodes"], list):
                logger.warning(f"Workflow {filename} seems to be in UI format (contains 'nodes' list). Please export in API format.")
            return data

    def patch_workflow(self, task_type: str, workflow: Dict[str, Any], params: Dict[str, Any]) -> Dict[str, Any]:
        # Deep copy to avoid modifying template
        wf = json.loads(json.dumps(workflow))
        
        # Simple heuristic patching
        # If we have mappings, use them
        mapping = self.mappings.get(task_type, {})
        
        for key, value in params.items():
            if key in mapping:
                node_id = str(mapping[key])
                input_name = mapping.get(f"{key}_input", "image") # Default input name
                if node_id in wf:
                    if "inputs" not in wf[node_id]:
                        wf[node_id]["inputs"] = {}
                    wf[node_id]["inputs"][input_name] = value
            else:
                # Heuristic search
                self.heuristic_patch(wf, key, value)
                
        return wf

    def heuristic_patch(self, workflow: Dict[str, Any], key: str, value: Any):
        # This is a best-effort patcher for API format workflows
        for node_id, node in workflow.items():
            if not isinstance(node, dict) or "inputs" not in node:
                continue
                
            inputs = node["inputs"]
            class_type = node.get("class_type", "")
            
            if key == "prompt" and ("CLIPTextEncode" in class_type or "Prompt" in class_type or "TextEncode" in class_type):
                if "text" in inputs:
                    inputs["text"] = value
                if "prompt" in inputs:
                    inputs["prompt"] = value
                    
            elif key == "seed" and ("Sampler" in class_type or "Seed" in class_type):
                if "seed" in inputs:
                    inputs["seed"] = value
                if "noise_seed" in inputs:
                    inputs["noise_seed"] = value
                    
            elif key == "steps" and "Sampler" in class_type:
                if "steps" in inputs:
                    inputs["steps"] = value
                    
            elif key == "cfg" and "Sampler" in class_type:
                if "cfg" in inputs:
                    inputs["cfg"] = value
            
            # For images, it's harder to guess which LoadImage node corresponds to which input without mapping
            # So we only patch if we find a unique match or based on simple logic
            elif key == "image" and "LoadImage" in class_type:
                inputs["image"] = value
