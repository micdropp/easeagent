# EaseAgent - AI 智能办公环境管理系统

基于多模态大模型的智能办公室 Agent，通过摄像头感知 + 传感器数据 + 员工偏好记忆，自动控制灯光、空调、窗帘等设备。

## 环境要求

- Python 3.11+
- NVIDIA GPU（推荐 RTX 4090）+ CUDA 12.x
- Docker Desktop（运行 Redis、Mosquitto、ChromaDB）
- Ollama（本地 LLM 推理）

## 快速开始

### 首次部署

```powershell
# 1. 克隆 & 环境准备
git clone https://github.com/<你的用户名>/easeagent.git
cd easeagent
copy .env.example .env           # 编辑 .env，填入 DASHSCOPE_API_KEY

# 2. Python 虚拟环境
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt

# 3. 基础设施
docker-compose up -d mosquitto redis chromadb

# 4. Ollama 本地模型
ollama serve                     # 新终端
ollama pull qwen3.5:9b           # 约 6.6 GB，首次需下载

# 5. 启动
python run.py
```

### 日常启动 (每次开机后)

```powershell
docker-compose up -d mosquitto redis chromadb
ollama serve                     # 新终端
.venv\Scripts\activate
python run.py
```

访问 http://localhost:8000/health?detail=true 验证所有组件。

### 后续更新

```powershell
git pull                         # 拉取最新代码
pip install -r requirements.txt  # 如有新依赖
python run.py
```

## 模型说明

| 模型 | 大小 | 获取方式 |
| --- | --- | --- |
| YOLOv8n (人员检测) | 6 MB | 已随仓库提供 `models/yolov8n.pt` |
| InsightFace buffalo_l (人脸识别) | ~300 MB | 首次运行自动下载 |
| Qwen3.5:9b (本地 LLM) | ~6.6 GB | `ollama pull qwen3.5:9b` |
| Qwen3.5-plus (云端 LLM) | 云端 | 填写 `.env` 中的 `DASHSCOPE_API_KEY` |

## 文档

| 文档 | 说明 |
| --- | --- |
| [使用说明](docs/EaseAgent-使用说明.md) | 完整的安装部署、配置、API 使用指南 |
| [排错指南](docs/EaseAgent-排错指南.md) | 常见问题与解决方案 |
| [技术方案](docs/EaseAgent-技术实现方案.md) | 架构设计与技术选型 |
| [QA 问答集](docs/EaseAgent-QA问答集.md) | 设计决策问答 |
