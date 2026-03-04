# EaseAgent - AI 智能办公环境管理系统

基于多模态大模型的智能办公室 Agent，通过摄像头感知 + 传感器数据 + 员工偏好记忆，自动控制灯光、空调、窗帘等设备。

## 环境要求

- Python 3.11+
- NVIDIA GPU（推荐 RTX 4090）+ CUDA 12.x
- Docker（运行 Redis、Mosquitto、ChromaDB）
- Ollama（本地 LLM 推理）

## 快速开始

```powershell
# 1. 环境准备
copy .env.example .env           # 填入 DASHSCOPE_API_KEY
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 2. 启动基础设施
docker-compose up -d mosquitto redis chromadb
ollama serve                     # 新终端
ollama pull qwen3.5:9b           # 首次需下载

# 3. 启动服务
python run.py
# 访问 http://localhost:8000/health?detail=true 验证
```

## 文档

| 文档 | 说明 |
| --- | --- |
| [使用说明](docs/EaseAgent-使用说明.md) | 完整的安装部署、配置、API 使用指南 |
| [排错指南](docs/EaseAgent-排错指南.md) | 常见问题与解决方案 |
| [技术方案](docs/EaseAgent-技术实现方案.md) | 架构设计与技术选型 |
| [QA 问答集](docs/EaseAgent-QA问答集.md) | 设计决策问答 |
