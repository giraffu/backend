from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    redis_url: str = "redis://backend-redis-1:6379/0"
    comfy_api_base: str = "http://192.168.1.226:8188"
    comfy_ws_url: str = "ws://192.168.1.226:8188/ws"
    auth_token: str = "your_secure_token_here"
    
    # ComfyUI paths (for saving uploaded files and reading outputs)
    comfy_input_dir: str = "/home/ubantu/comfyui/input"
    comfy_output_dir: str = "/home/ubantu/comfyui/output"
    comfy_temp_dir: str = "/home/ubantu/comfyui/temp"
    
    # Workflow templates directory
    workflows_dir: str = "/app/workflows"
    
    # MinIO Configuration
    minio_endpoint: str = "192.168.1.115:9000"
    minio_access_key: str = "minioadmin"
    minio_secret_key: str = "minioadmin"
    minio_bucket: str = "bot-data"
    minio_result_bucket: str = "comfyui-temp"
    minio_template_bucket: str = "bot-template"
    minio_secure: bool = False
    
    class Config:
        env_file = ".env"

settings = Settings()
