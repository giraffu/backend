---
name: "docker-ai-toolkit"
description: "Manages local Docker environment for AI development. Invoke when user needs to run AI containers with GPU support, manage images, or check Docker status."
---

# Docker AI Toolkit

This skill provides a set of tools and best practices for managing a local Docker environment optimized for AI and Deep Learning development on this machine.

## 1. Environment Verification
Before running AI tasks, verify the environment is ready:
- **Check GPU Support**: `docker run --rm --gpus all nvidia/cuda:11.0.3-base-ubuntu20.04 nvidia-smi` (or simply `nvidia-smi` on host)
- **Check Docker Info**: `docker info` (Ensure `Runtimes` includes `nvidia`)
- **Check Proxy**: Verify `~/.docker/config.json` or daemon config if pulls fail.

## 2. Common AI Development Commands

### Run AI Container (GPU Enabled)
Quickly start a container with GPU support, current directory mounted, and common ports mapped.

```bash
# Template
docker run --gpus all -it --rm \
  --shm-size=8g \
  -v "$(pwd):/workspace" \
  -w /workspace \
  -p 8888:8888 -p 6006:6006 \
  <image_name> <command>

# Example: PyTorch
docker run --gpus all -it --rm --shm-size=8g -v "$(pwd):/workspace" pytorch/pytorch:latest bash
```

### Pull Images with Proxy (If needed)
Although the daemon is configured, sometimes CLI needs explicit proxy:
```bash
export HTTP_PROXY="http://127.0.0.1:7890"
export HTTPS_PROXY="http://127.0.0.1:7890"
docker pull <image>
```

### Clean Up Resources
Free up disk space often used by large AI images.
```bash
# Remove stopped containers
docker container prune -f

# Remove unused images (dangling)
docker image prune -f

# Deep clean (careful!)
docker system prune -a --volumes
```

## 3. Recommended AI Images
- **PyTorch**: `pytorch/pytorch:latest` (Official)
- **TensorFlow**: `tensorflow/tensorflow:latest-gpu` (Official)
- **Hugging Face**: `huggingface/transformers-pytorch-gpu`
- **CUDA Base**: `nvidia/cuda:12.1.0-devel-ubuntu22.04`

## 4. Troubleshooting
- **"could not select device driver"**: Ensure `nvidia-container-toolkit` is installed and `nvidia` runtime is configured in `/etc/docker/daemon.json`.
- **"pull access denied"**: Check network proxy or login status for private registries.
- **"no space left on device"**: Run cleanup commands or check Docker root dir (`/var/lib/docker`).

## 5. Local Configuration Reference
- **Daemon Config**: `/etc/docker/daemon.json`
- **Proxy**: `http://127.0.0.1:7890`
- **Registry Mirror**: `https://dockerpull.pw`
