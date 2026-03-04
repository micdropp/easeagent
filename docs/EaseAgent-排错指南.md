# EaseAgent 排错指南

> 本文档汇总了 EaseAgent 部署与运行中可能遇到的问题，包含通用场景和开发过程中实际踩过的坑。每个问题按 **现象 -> 原因 -> 解决方案** 结构组织。

---

## 目录

- [一、环境安装类](#一环境安装类)
- [二、服务启动类](#二服务启动类)
- [三、运行时问题](#三运行时问题)
- [四、调试技巧](#四调试技巧)

---

## 一、环境安装类

### 1.1 Python 版本不兼容

**现象**：启动时报 `SyntaxError`，特别是在 f-string 中嵌套引号的行。

**原因**：项目中部分代码使用了 `f'{p["key"]}'` 这种嵌套引号的 f-string 写法。Python 3.11 不支持此语法（3.12 才支持）。

**解决方案**：
- 推荐使用 **Python 3.11**，项目代码已适配
- 如果出现类似语法错误，检查是否使用了 3.10 或更早版本
- 确认方法：`python --version`

### 1.2 CUDA / onnxruntime-gpu 版本不匹配

**现象**：GPU 可用但 YOLO 或 InsightFace 推理时报错，或回退到 CPU。

**原因**：`onnxruntime-gpu` 版本与 CUDA 版本不匹配。

**解决方案**：

```powershell
# 检查 CUDA 版本
nvidia-smi    # 右上角显示 CUDA 版本
nvcc --version

# 检查 onnxruntime-gpu
pip show onnxruntime-gpu

# CUDA 12.x 对应 onnxruntime-gpu >= 1.17.0
# 如需重装：
pip install --force-reinstall onnxruntime-gpu==1.17.0
```

确保不要同时安装 `onnxruntime` 和 `onnxruntime-gpu`，两者冲突：

```powershell
pip uninstall onnxruntime onnxruntime-gpu
pip install onnxruntime-gpu>=1.17.0
```

### 1.3 ChromaDB 客户端与服务端版本不一致

**现象**：启动日志中出现 `KeyError: '_type'`，ChromaDB 降级为不可用。

**原因**：Python 的 `chromadb` 包版本与 Docker 中运行的 ChromaDB 服务端版本不一致。例如 pip 安装了 `0.5.23` 但 Docker 运行的是 `1.4.1`，两者 API 不兼容。

**解决方案**：

```powershell
# 查看服务端版本（docker-compose.yml 中定义）
# image: chromadb/chroma:1.4.1

# 查看客户端版本
pip show chromadb

# 如果不一致，强制安装正确版本
pip install "chromadb==1.4.1"
```

> 这是开发中实际踩过的坑：`requirements.txt` 中写了 `1.4.1`，但环境中被旧版本覆盖过，导致反复出现 `KeyError`。务必确认 `pip show` 的实际版本。

### 1.4 pip install 失败（InsightFace / onnxruntime-gpu）

**现象**：`pip install -r requirements.txt` 在 `insightface` 或 `onnxruntime-gpu` 上失败。

**原因**：这些包依赖 C++ 编译工具链和 CUDA 开发包。

**解决方案**：

```powershell
# Windows 需要 Visual C++ Build Tools
# 下载: https://visualstudio.microsoft.com/visual-cpp-build-tools/
# 安装时勾选 "C++ 桌面开发"

# 如果 insightface 安装卡在编译 Cython：
pip install cython numpy
pip install insightface
```

---

## 二、服务启动类

### 2.1 Docker 容器未启动或启动失败

**现象**：EaseAgent 启动后报 Redis/MQTT/ChromaDB 连接失败。

**原因**：Docker 容器没有正确启动，或端口被其他服务占用。

**解决方案**：

```powershell
# 检查容器状态
docker-compose ps

# 如果容器状态不是 running：
docker-compose down
docker-compose up -d mosquitto redis chromadb

# 检查端口占用
netstat -ano | findstr "1883 6379 8100"

# 查看容器日志
docker-compose logs mosquitto
docker-compose logs redis
docker-compose logs chromadb
```

### 2.2 Ollama 未运行 / 模型未下载

**现象**：Agent 决策调用 LLM 失败，日志中出现连接 `localhost:11434` 超时。

**原因**：Ollama 默认安装后不会随系统自启，重启电脑后需要手动启动。

**解决方案**：

```powershell
# 检查 Ollama 是否运行
ollama ps

# 如果未运行
ollama serve         # 在新终端中运行

# 检查模型是否已下载
ollama list
# 应该能看到 qwen3.5:9b

# 如果模型不在列表中
ollama pull qwen3.5:9b
```

> Ollama 的模型在首次推理时需要 15-20 秒加载到 GPU 显存。默认 5 分钟无请求后自动卸载。设置 `OLLAMA_KEEP_ALIVE=-1` 可以保持常驻。

### 2.3 代理（Proxy）干扰本地服务连接

**现象**：手动测试 ChromaDB 时返回 `503 Service Unavailable`，响应头中包含 `proxy-connection: close`。或者 Redis/MQTT 连接异常。

**原因**：系统或企业代理拦截了 `localhost` / `127.0.0.1` 的请求。

**解决方案**：

`run.py` 启动脚本已自动设置 `NO_PROXY=localhost,127.0.0.1`，所以通过 `python run.py` 启动的主服务不受影响。但如果你单独运行 Python 脚本测试：

```powershell
# PowerShell 中手动设置
$env:NO_PROXY = "localhost,127.0.0.1"
python your_test_script.py
```

> 这是开发中发现的隐蔽问题：`docker-compose ps` 显示容器正常，`curl` 也能访问，但 Python `httpx` 客户端走了代理导致 503。

### 2.4 启动顺序不对导致功能降级

**现象**：日志中出现大量 "降级" 警告，如 `向量存储降级为不可用`、`Redis 连接失败，缓存禁用`。

**原因**：EaseAgent 在启动时检测各服务连通性。如果 Docker 容器还没就绪就启动了主服务，会进入降级模式。

**解决方案**：

正确的启动顺序：
1. `docker-compose up -d` → 等待 3-5 秒
2. `ollama serve`（新终端）
3. `python run.py`

启动后通过健康检查确认所有组件就绪：

```
GET http://localhost:8000/health?detail=true
```

返回中每个组件状态应为 `ok`。

---

## 三、运行时问题

### 3.1 Agent 决策日志不增长

**现象**：摄像头在工作、视频画面有人员检测框，但 `/api/agent-logs/` 长时间没有新记录。

**原因**：Redis 决策缓存生效。当场景（房间、人数、传感器数据）无明显变化时，Agent 命中缓存直接复用上次决策，不调用 LLM。

**解决方案**：

1. 检查 `/api/agent-logs/` 最新记录是否标记为 `[缓存命中]`
2. 订阅 WebSocket `agent_log` 频道查看实时推送（缓存命中也会推送）
3. 强制触发新决策：
   - 方法 A：清除 Redis 缓存 `redis-cli FLUSHDB`
   - 方法 B：制造场景变化（如人离开再进入）
   - 方法 C：缩短 `config/settings.yaml` 中 `redis.decision_cache_ttl`（默认 7200 秒）

### 3.2 YOLO 误检 / 幽灵框

**现象**：视频画面中某个位置持续显示人员检测框，但实际上没有人。框可能在墙角、深色物体上方。

**原因**：
1. YOLO 将深色物体误判为人（假阳性）
2. 之前有人走过，追踪器还未超时清除（IoU 追踪器依赖位置重叠判断）

**解决方案**：

- 误检通常会在几秒后随追踪器超时而消失
- 如果持续误检，可以调整配置：

```yaml
# config/settings.yaml
ai:
  yolo_model: yolov8s.pt     # 换用 small 模型，精度更高但稍慢
  detection_interval: 0.2    # 增大检测间隔
```

- `yolov8n.pt`（nano）速度快但误检率高，`yolov8s.pt`（small）是速度与精度的较好平衡

### 3.3 人脸识别精度差

**现象**：正面近距离能识别，但稍微有角度、距离远、或戴口罩就识别不了。

**原因**：InsightFace 依赖清晰的正面人脸。受限于：
- 注册照片数量（默认只有 1 张）
- 检测分辨率
- 光线和角度

**解决方案**：

1. **多角度注册**：为每位员工注册 3-5 张不同角度的照片

```bash
# 从多张照片注册
python scripts/register_faces.py --id zhangsan --image front.jpg
python scripts/register_faces.py --id zhangsan --image left45.jpg
python scripts/register_faces.py --id zhangsan --image right45.jpg
```

2. **调整识别阈值**：

```yaml
# config/settings.yaml
ai:
  face_recognition_threshold: 0.40  # 降低阈值增加召回率（默认 0.45）
```

3. **提高摄像头分辨率**：`config/rooms.yaml` 中使用 1080p RTSP 流

> 更彻底的方案（BLE 工牌定位、门禁联动等）已规划在后续阶段，详见 `docs/EaseAgent-待办优化清单.md`。

### 3.4 FPS 低 / 推理延迟高

**现象**：视频画面卡顿，OSD（画面叠加信息）显示 FPS 低于 5，或推理延迟超过 200ms。

**原因**：GPU 被多个模型同时占用（YOLO + InsightFace + Ollama），或分辨率过高。

**解决方案**：

```powershell
# 检查 GPU 显存占用
nvidia-smi

# 如果显存接近满：
# 1. 使用更小的 YOLO 模型
ai:
  yolo_model: yolov8n.pt     # nano 最快

# 2. 降低检测频率
ai:
  detection_interval: 0.2    # 200ms 一次

# 3. 限制视频流帧率
# 访问 /api/video/stream/cam_id?max_fps=10
```

RTX 4090 参考性能：
- YOLO (yolov8n, 1080p, FP16): ~5-8ms / 帧
- InsightFace 人脸检测+识别: ~15-30ms / 帧
- 整体流水线: 15-25 FPS

### 3.5 摄像头无法打开

**现象**：视频页面空白，日志中出现 `Failed to open camera` 或 `Could not read frame`。

**原因**：
1. 本地摄像头被其他程序占用（如腾讯会议、Zoom）
2. RTSP 地址错误或摄像头离线
3. OpenCV 未正确安装

**解决方案**：

```powershell
# 关闭所有使用摄像头的程序

# 测试摄像头可用性
python -c "import cv2; cap = cv2.VideoCapture(0); print(cap.isOpened()); cap.release()"

# 如果 RTSP 摄像头连不上，用 VLC 测试：
# 媒体 → 打开网络串流 → 输入 RTSP URL
```

开发模式使用 `webcam://0`，没有摄像头时可以设置 `ai.enabled: false` 跳过。

### 3.6 DashScope API 调用失败

**现象**：日志中出现 `AuthenticationError` 或 `RateLimitError`。

**原因**：API Key 无效、余额不足、或未开通 `qwen3.5-plus` 模型权限。

**解决方案**：

1. 检查 `.env` 中 `DASHSCOPE_API_KEY` 是否正确
2. 登录阿里云灵积控制台确认余额和模型权限
3. 系统会自动降级到本地 Ollama，所以即使 DashScope 不可用也不影响基本功能

---

## 四、调试技巧

### 4.1 查看 Ollama 后台状态

```powershell
ollama ps              # 当前加载在 GPU 中的模型
ollama list            # 所有已下载的模型
ollama show qwen3.5:9b # 模型详细信息
```

### 4.2 Swagger UI 交互式测试

访问 `http://localhost:8000/docs`，可以直接在浏览器中调用所有 API。

常用测试：
- `GET /health?detail=true` — 检查所有组件连通性
- `GET /api/agent-logs/?limit=5` — 查看最新决策
- `GET /api/video/stats` — 感知层性能数据

### 4.3 WebSocket 实时事件观察

在浏览器控制台中快速连接：

```javascript
const ws = new WebSocket(
  "ws://localhost:8000/ws/realtime?channels=agent_log,person_detection,face_recognition,sensor_data"
);
ws.onmessage = e => console.log(JSON.parse(e.data));
```

或使用 `wscat`（Node.js 工具）：

```powershell
npx wscat -c "ws://localhost:8000/ws/realtime?channels=agent_log"
```

### 4.4 模拟传感器数据

通过 MQTT 发布模拟数据触发 Agent 决策：

```powershell
# 需要安装 paho-mqtt
pip install paho-mqtt

# 发送温湿度 + CO2 数据
python -c "import paho.mqtt.publish as p; p.single('easeagent/zone_a/sensor/env_01/data', '{\"temperature\": 28.0, \"humidity\": 65, \"co2\": 1200}', hostname='localhost', port=1883)"
```

### 4.5 检查 ChromaDB 数据

```powershell
# 检查心跳
curl http://localhost:8100/api/v1/heartbeat

# 列出所有集合
curl http://localhost:8100/api/v1/collections

# 查看某个集合的文档数量
curl http://localhost:8100/api/v1/collections/implicit_preferences
```

### 4.6 Redis 缓存操作

```powershell
redis-cli

# 查看所有缓存键
KEYS easeagent:*

# 清除所有决策缓存（强制下次重新调用 LLM）
FLUSHDB

# 查看具体缓存值
GET easeagent:decision:zone_a:xxxx
```

### 4.7 日志级别调整

```yaml
# config/settings.yaml
server:
  debug: true    # 开启详细日志
```

关键日志关键字搜索：
- `OTAR` — Agent 决策循环
- `cache_hit` — 缓存命中
- `tool_call` — LLM 工具调用
- `降级` — 组件不可用降级
- `person_entered` / `person_left` — 人员进出事件
