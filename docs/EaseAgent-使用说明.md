# EaseAgent 使用说明

> 最后更新: 2026-03-04 | 版本: Phase 5 (五大模块集成+反射层+ReID) | 部署方式: GitHub

## 1. 项目简介

EaseAgent 是一个基于 AI 的智能办公环境管理系统。它通过摄像头感知人员进出与身份，结合传感器数据和员工偏好，利用多模态大模型进行场景理解和智能决策，自动控制灯光、空调、屏幕、新风等办公设备。

核心能力：

- **感知层 (Perception)**: YOLOv8 人员检测 + InsightFace 人脸识别 + ReID 跨摄像头身份接续 + 多模态身份融合
- **反射层 (Reflex)**: 无人延时关灯/关空调、CO2 超标加新风、厕位状态推送（毫秒级，无需 LLM）
- **认知层 (Cognition)**: Qwen3.5 多模态大模型场景理解、行为分析、Function Calling 设备控制
- **记忆层 (Memory)**: SQLite 显式偏好 + ChromaDB 隐式偏好向量存储 + RAG 检索 + 偏好学习器
- **通信层 (IoT)**: MQTT 协议设备通信 + EventBus 异步事件总线
- **数据层**: SQLite 持久化 + Redis 决策缓存 + ChromaDB 向量数据库

---

## 2. 环境要求


| 组件          |                    | 说明                             |                |
| ----------- | ------------------ | ------------------------------ | -------------- |
| Python      | 3.11+              | 版本要求                           | 推荐 3.11 或 3.12 |
| NVIDIA GPU  | RTX 4090 (24GB) 推荐 | YOLO + InsightFace + Ollama 推理 |                |
| CUDA        | 12.x               | 配合 onnxruntime-gpu             |                |
| Ollama      | 最新版                | 本地部署 qwen3.5:9b                |                |
| Redis       | 7.x                | 决策缓存                           |                |
| MQTT Broker | Mosquitto 2.x      | 设备通信                           |                |
| Docker (可选) | 24.x+              | 容器化部署                          |                |


---

## 3. 安装部署

### 3.1 获取源码

```powershell
# 从 GitHub 克隆（替换为实际仓库地址）
git clone https://github.com/<你的用户名>/easeagent.git
cd easeagent
```

后续更新只需：

```powershell
git pull
```

### 3.2 首次环境搭建 (一次性操作)

以下步骤只在首次部署时执行，之后日常启动跳到 **5.1**。

**Step 1: 创建虚拟环境 + 安装依赖**

```powershell
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

**Step 2: 配置环境变量**

```powershell
copy .env.example .env
# 用编辑器打开 .env，填入 DASHSCOPE_API_KEY（阿里云灵积平台获取）
```

**Step 3: 安装 Docker Desktop + 启动基础服务**

```powershell
# 安装 Docker Desktop: https://docs.docker.com/desktop/install/windows-install/
docker-compose up -d mosquitto redis chromadb
```

**Step 4: 安装 Ollama + 拉取本地模型**

```powershell
# 安装: https://ollama.com/download
ollama serve                   # 首次启动服务
ollama pull qwen3.5:9b         # 下载模型，约 6.6 GB，需耐心等待
ollama list                    # 验证模型已下载
```

### 3.3 模型说明

| 模型 | 大小 | 获取方式 | 说明 |
| --- | --- | --- | --- |
| YOLOv8n | 6 MB | 已随仓库提供 (`models/yolov8n.pt`) | 人员检测，无需额外下载 |
| InsightFace buffalo_l | ~300 MB | 首次运行自动下载 | 人脸识别，需联网，下载到 `~/.insightface/models/` |
| Qwen3.5:9b | ~6.6 GB | `ollama pull qwen3.5:9b` | 本地 LLM，需手动拉取 |
| Qwen3.5-plus | 云端 | 填写 `DASHSCOPE_API_KEY` | 云端 LLM (阿里云)，按调用计费 |

### 3.4 Docker Compose 服务

```powershell
docker-compose up -d mosquitto redis chromadb
```

| 服务 | 端口 | 说明 |
| --- | --- | --- |
| `mosquitto` | 1883, 9001 | MQTT Broker |
| `redis` | 6379 | 决策缓存 |
| `chromadb` | 8100 | 向量数据库 (记忆层) |


---

## 4. 配置说明

### 4.1 环境变量 (.env)

复制 `.env.example` 为 `.env`，填入真实值：

```bash
cp .env.example .env
```


| 变量                   | 说明                      | 示例                                        |
| -------------------- | ----------------------- | ----------------------------------------- |
| `DASHSCOPE_API_KEY`  | 阿里云 DashScope API 密钥    | `sk-xxxx`                                 |
| `MQTT_BROKER`        | MQTT Broker 地址          | `localhost`                               |
| `MQTT_PORT`          | MQTT 端口                 | `1883`                                    |
| `REDIS_HOST`         | Redis 主机                | `localhost`                               |
| `REDIS_PORT`         | Redis 端口                | `6379`                                    |
| `DATABASE_URL`       | 数据库连接串                  | `sqlite+aiosqlite:///./data/easeagent.db` |
| `FEISHU_APP_ID`      | 飞书应用 ID (Phase 6)       | `cli_xxxx`                                |
| `FEISHU_APP_SECRET`  | 飞书应用密钥 (Phase 6)        | -                                         |
| `FEISHU_BOT_WEBHOOK` | 飞书机器人 Webhook (Phase 6) | -                                         |


也可以使用 Pydantic Settings 前缀格式覆盖任意配置，例如：`EASEAGENT_LLM__API_KEY=sk-xxx`

### 4.2 主配置 (config/settings.yaml)

```yaml
server:
  host: 0.0.0.0
  port: 8000
  debug: true                    # 生产环境设为 false

ai:
  enabled: true                  # false 可禁用 AI，仅运行 API
  yolo_model: yolov8n.pt         # YOLOv8 模型 (nano/small/medium)
  face_model: buffalo_l          # InsightFace 模型
  detection_interval: 0.1        # 检测间隔(秒)
  face_recognition_threshold: 0.45  # 人脸识别阈值 (0-1)

llm:
  provider: dashscope            # 主通道: dashscope / ollama
  model: qwen3.5-plus            # 云端模型
  api_key: ${DASHSCOPE_API_KEY}
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  fallback_provider: ollama      # 降级通道
  fallback_model: qwen3.5:9b     # 本地模型
  fallback_base_url: http://localhost:11434
  patrol_interval: 30.0          # 场景巡检间隔(秒)
  ssim_threshold: 0.85           # 视觉变化检测阈值

redis:
  decision_cache_ttl: 7200       # 决策缓存 TTL (秒, 默认 2h)
```

### 4.3 房间与设备 (config/rooms.yaml)

定义房间、摄像头和设备的映射关系：

```yaml
rooms:
  - id: zone_a
    name: A区办公区
    cameras:
      - cam_zone_a
    devices:
      lights: [light_a1, light_a2]
      acs: [ac_a1]
      screens: [screen_a1]
    reflex_rules:
      no_person_delay: 300       # 无人关灯延迟(秒)
      co2_high_threshold: 1000   # CO2 报警阈值(ppm)

cameras:
  # 开发模式: 使用本地摄像头
  - id: cam_entrance
    rtsp_url: webcam://0
    room: entrance

  # 部署模式: 使用 RTSP 摄像头
  # - id: cam_zone_a
  #   rtsp_url: rtsp://192.168.1.11:554/stream1
  #   room: zone_a
```

### 4.4 Agent 提示词 (config/agent_prompt.yaml)

定义 AI Agent 的系统角色、决策原则和默认舒适参数，可根据实际场景调整。

---

## 5. 启动运行

### 5.1 日常启动 (每次开机后)

```powershell
# 1. 启动基础设施
docker-compose up -d mosquitto redis chromadb

# 2. 启动 Ollama（如未自动启动）
ollama serve                    # 新终端，保持后台运行

# 3. 激活虚拟环境 + 启动服务
.venv\Scripts\activate
python run.py
```

启动后可以看到：

```
INFO:     Uvicorn running on http://0.0.0.0:8000
```

> 启动顺序很重要：Docker 服务 -> Ollama -> EaseAgent。如果顺序不对，系统会自动降级（如 ChromaDB 不可用时降级为仅 SQLite），但功能不完整。

### 5.1.1 同事拿到代码后的完整流程

```
git clone -> 复制 .env -> 创建 venv + pip install -> docker-compose up -d
-> ollama serve + ollama pull -> python run.py -> 访问 localhost:8000
```

首次环境搭建详见 **3.2**，之后每次只需执行 **5.1** 即可。如果代码有更新，先 `git pull` 再启动。

### 5.2 验证服务


| 地址                                         | 说明                   |
| ------------------------------------------ | -------------------- |
| `http://localhost:8000/health`             | 健康检查                 |
| `http://localhost:8000/health?detail=true` | 详细状态 (各组件连通性)        |
| `http://localhost:8000/docs`               | Swagger API 文档 (交互式) |
| `http://localhost:8000/redoc`              | ReDoc API 文档         |
| `http://localhost:8000/api/video/`         | 视频监控页面               |


### 5.3 禁用 AI 模式

如果没有 GPU 或暂不需要视觉识别功能，可以关闭 AI：

```yaml
# config/settings.yaml
ai:
  enabled: false
```

此模式下所有 API 正常工作，但不会启动摄像头、人员检测和 AI Agent。

---

## 6. 功能使用

### 6.1 视频监控

浏览器访问 `http://localhost:8000/api/video/` 查看实时监控界面。

界面显示内容：

- 摄像头实时画面 (MJPEG 流)
- YOLO 人员检测框
- 人脸识别结果 (已注册/未识别)
- 追踪 ID 和身份标签
- 性能指标 (Stream FPS, Detect FPS, 推理耗时, GPU 显存)

API 端点：

```bash
# 获取摄像头列表
GET /api/video/cameras

# 获取 MJPEG 视频流
GET /api/video/stream/{camera_id}?quality=80&max_fps=15

# 获取性能统计
GET /api/video/stats
```

### 6.2 人脸注册

使用 CLI 工具 `scripts/register_faces.py` 注册员工人脸：

```bash
# 从图片注册
python scripts/register_faces.py --id emp_001 --image photo.jpg

# 从摄像头实时采集
python scripts/register_faces.py --id emp_001 --webcam

# 批量注册 (目录下文件名即为 employee_id)
# 例如: data/face_photos/zhangsan.jpg → employee_id = zhangsan
python scripts/register_faces.py --dir data/face_photos/
```

也可以通过 API 上传人脸图片：

```bash
# 上传人脸图片
POST /api/employees/{employee_id}/face
Content-Type: multipart/form-data
file: <图片文件>
```

### 6.3 员工管理

```bash
# 获取员工列表
GET /api/employees/?is_active=true

# 创建员工
POST /api/employees/
{
  "id": "zhangsan",
  "name": "张三",
  "email": "zhangsan@example.com"
}

# 获取单个员工
GET /api/employees/{employee_id}

# 更新员工
PUT /api/employees/{employee_id}
{ "name": "张三", "email": "zhangsan@newmail.com" }

# 删除员工
DELETE /api/employees/{employee_id}
```

### 6.4 偏好管理

```bash
# 获取员工偏好（可选按 category 和 context 过滤）
GET /api/preferences/{employee_id}?category=ac&context=独自办公

# 设置偏好
POST /api/preferences/
{
  "employee_id": "zhangsan",
  "category": "ac",
  "key": "temperature",
  "value": "24",
  "context": "独自办公"
}

# 其他偏好示例
POST /api/preferences/
{ "employee_id": "zhangsan", "category": "light", "key": "brightness", "value": "60" }

POST /api/preferences/
{ "employee_id": "zhangsan", "category": "light", "key": "color_temp", "value": "4000" }

# 删除偏好（需要偏好记录的数字 ID）
DELETE /api/preferences/{preference_id}
```

`category` 可选值：`light`（灯光）、`ac`（空调）、`fresh_air`（新风）、`screen`（屏幕）

`key` 可选值：`brightness`（亮度）、`color_temp`（色温）、`temperature`（温度）、`mode`（模式）、`level`（档位）

### 6.5 记忆系统 (Phase 4)

EaseAgent 采用三层记忆模型，让 Agent 能够记住并学习每位员工的偏好。

**三层架构：**

| 层级 | 存储 | 说明 |
| --- | --- | --- |
| 显式偏好 | SQLite `Preference` 表 | 用户通过 API 手动设置的偏好（如"灯光亮度=60"） |
| 隐式偏好 | ChromaDB `implicit_preferences` | Agent 从用户行为中学习到的偏好向量（如"张三下午喜欢暖色调"） |
| 情境记忆 | ChromaDB `context_memories` | 与特定场景绑定的记忆（如"开会时张三喜欢关窗帘"） |

**工作机制：**

1. **RAG 检索**：Agent 在做决策前，`RAGRetriever` 从三层记忆中检索相关偏好，注入到 Prompt 中。偏好按来源标注为 `[显式]`、`[学习]`、`[情境]`，帮助 LLM 判断权重。
2. **自动学习**：`PreferenceLearner` 在每次决策后自动分析决策结果，提取隐式偏好并写入 ChromaDB。当用户手动覆盖 Agent 决策时（如用户主动关灯），系统会将覆盖行为记录为更强的偏好信号。
3. **降级策略**：ChromaDB 不可用时，系统自动降级为仅使用 SQLite 显式偏好，不影响基本功能。日志中会输出 `ChromaDB 不可用，记忆未持久化` 提示。

**验证记忆功能：**

```bash
# 检查 ChromaDB 是否连接
GET http://localhost:8000/health?detail=true
# 返回中 chromadb 字段应为 "ok"

# 设置显式偏好（见 6.4 偏好管理）
# Agent 运行一段时间后，隐式偏好会自动积累到 ChromaDB
```

### 6.6 反射层 (Phase 5)

反射层实现了毫秒级的确定性响应，无需等待 LLM 决策：

| 场景 | 触发条件 | 反射动作 |
|------|---------|---------|
| 无人关灯 | 房间人数降为 0 | 延时 N 秒后关灯 + 关空调 |
| CO2 超标 | `co2_high` 事件 | 立即将新风设为 HIGH（安全动作，不可被 Agent 覆盖） |
| 厕位状态 | MQTT 门磁传感器 | 更新厕位占用状态 → WebSocket 推送 |

延时参数在 `config/rooms.yaml` 的 `reflex_rules` 中配置：
```yaml
reflex_rules:
  no_person_delay: 300  # 无人 5 分钟后关闭设备
```

### 6.7 跨摄像头 ReID (Phase 5)

当员工离开一个摄像头视野、进入另一个摄像头时，ReID 通过外观特征匹配自动继承身份，无需重新进行人脸识别。

- 基于 OSNet 模型提取 512 维外观特征
- Lost Gallery 保留最近 10 分钟消失的已识别人员
- 余弦相似度匹配，阈值 0.55

**可选依赖**：`pip install torchreid`。未安装时系统自动降级，仅使用人脸识别。

### 6.8 MQTT 场景模拟

用于测试五大模块（灯光/屏幕/空调/新风/厕位）的端到端通信：

```bash
# 运行所有场景
python scripts/simulate_scenario.py

# 可选场景：sensor, co2, toilet, heartbeat, vacancy
python scripts/simulate_scenario.py --scene co2
```

### 6.9 设备管理

```bash
# 获取设备列表
GET /api/devices/?room_id=zone_a&device_type=light

# 创建设备
POST /api/devices/
{
  "id": "light_a1",
  "name": "A区灯光1",
  "device_type": "light",
  "room_id": "zone_a",
  "protocol": "mqtt",
  "mqtt_topic": "easeagent/zone_a/light/light_a1/cmd"
}

# 更新设备
PUT /api/devices/{device_id}
{ "name": "A区主灯", "room_id": "zone_b" }

# 删除设备
DELETE /api/devices/{device_id}
```

`device_type` 可选值：`light`、`ac`、`screen`、`fresh_air`、`sensor`、`toilet_sensor`

### 6.10 房间管理

```bash
# 获取房间列表
GET /api/rooms/

# 创建房间
POST /api/rooms/
{ "id": "zone_b", "name": "B区办公区", "floor": "3F", "capacity": 20 }

# 获取/更新/删除
GET    /api/rooms/{room_id}
PUT    /api/rooms/{room_id}
DELETE /api/rooms/{room_id}
```

### 6.11 AI Agent 决策日志

```bash
# 获取决策日志
GET /api/agent-logs/?room_id=zone_a&limit=20&offset=0

# 日期范围过滤
GET /api/agent-logs/?date_from=2026-03-01&date_to=2026-03-04

# 统计信息 (总数/成功率/平均延迟)
GET /api/agent-logs/stats

# 单条日志详情
GET /api/agent-logs/{log_id}
```

### 6.12 厕位状态

```bash
# 所有厕位状态
GET /api/toilet/status?floor=3&gender=male

# 单个厕位
GET /api/toilet/status/{stall_id}

# 楼层汇总
GET /api/toilet/summary

# 创建厕位
POST /api/toilet/stalls
{ "id": "3F_M_01", "floor": "3F", "gender": "male" }

# 更新占用状态
PUT /api/toilet/status/{stall_id}
{ "occupied": true }
```

### 6.13 WebSocket 实时推送

```javascript
// 浏览器 JavaScript 示例
const ws = new WebSocket(
  "ws://localhost:8000/ws/realtime?channels=device_status,toilet_status"
);

ws.onmessage = (event) => {
  const data = JSON.parse(event.data);
  console.log("Event:", data);
};
```

支持的频道：

| 频道 | 订阅事件 | 说明 |
| --- | --- | --- |
| `device_status` | `device_online`, `device_offline` | 设备上下线 |
| `toilet_status` | `toilet_status` | 厕位占用变化 |
| `sensor_data` | `sensor_data`, `sensor_update`, `co2_high` | 传感器数据及报警 |
| `agent_log` | `agent_decision` | Agent 决策日志（含缓存命中） |
| `person_detection` | `person_entered`, `person_left` | 人员进出检测 |
| `face_recognition` | `face_arrived`, `face_left` | 人脸识别结果 |

连接时通过 `channels` 参数指定订阅的频道，多个用逗号分隔。连接后也可以通过发送 JSON 消息动态订阅/退订：

```json
{"action": "subscribe", "channels": ["agent_log", "face_recognition"]}
{"action": "unsubscribe", "channels": ["toilet_status"]}
{"action": "ping"}
```

---

## 7. API 速查表

### 健康检查


| 方法  | 路径        | 说明                       |
| --- | --------- | ------------------------ |
| GET | `/health` | 健康检查 (`?detail=true` 详细) |


### 设备 /api/devices


| 方法     | 路径             | 说明                            |
| ------ | -------------- | ----------------------------- |
| GET    | `/`            | 列表 (`?room_id=&device_type=`) |
| GET    | `/{device_id}` | 详情                            |
| POST   | `/`            | 创建                            |
| PUT    | `/{device_id}` | 更新                            |
| DELETE | `/{device_id}` | 删除                            |


### 房间 /api/rooms


| 方法     | 路径           | 说明  |
| ------ | ------------ | --- |
| GET    | `/`          | 列表  |
| GET    | `/{room_id}` | 详情  |
| POST   | `/`          | 创建  |
| PUT    | `/{room_id}` | 更新  |
| DELETE | `/{room_id}` | 删除  |


### 员工 /api/employees


| 方法     | 路径                    | 说明                     |
| ------ | --------------------- | ---------------------- |
| GET    | `/`                   | 列表 (`?is_active=true`) |
| GET    | `/{employee_id}`      | 详情                     |
| POST   | `/`                   | 创建                     |
| PUT    | `/{employee_id}`      | 更新                     |
| DELETE | `/{employee_id}`      | 删除                     |
| POST   | `/{employee_id}/face` | 上传人脸图片                 |


### 偏好 /api/preferences


| 方法     | 路径                 | 说明                         |
| ------ | ------------------ | -------------------------- |
| GET    | `/{employee_id}`   | 查询 (`?category=&context=`) |
| POST   | `/`                | 设置                         |
| DELETE | `/{preference_id}` | 删除                         |


### Agent 日志 /api/agent-logs


| 方法  | 路径          | 说明                                                           |
| --- | ----------- | ------------------------------------------------------------ |
| GET | `/`         | 列表 (`?room_id=&date_from=&date_to=&success=&limit=&offset=`) |
| GET | `/stats`    | 统计                                                           |
| GET | `/{log_id}` | 详情                                                           |


### 厕位 /api/toilet


| 方法   | 路径                   | 说明                       |
| ---- | -------------------- | ------------------------ |
| GET  | `/status`            | 所有厕位 (`?floor=&gender=`) |
| GET  | `/status/{stall_id}` | 单个厕位                     |
| POST | `/stalls`            | 创建厕位                     |
| PUT  | `/status/{stall_id}` | 更新占用状态                   |
| GET  | `/summary`           | 楼层汇总                     |


### 视频 /api/video


| 方法  | 路径                    | 说明                                 |
| --- | --------------------- | ---------------------------------- |
| GET | `/`                   | 监控页面 (HTML)                        |
| GET | `/cameras`            | 摄像头列表                              |
| GET | `/stats`              | 性能统计                               |
| GET | `/stream/{camera_id}` | MJPEG 流 (`?quality=80&max_fps=15`) |


### WebSocket


| 类型  | 路径             | 说明                                   |
| --- | -------------- | ------------------------------------ |
| WS  | `/ws/realtime` | 实时推送 (`?channels=device_status,...`) |


---

## 8. 项目结构

```
easeagent/
├── run.py                    # 入口脚本
├── requirements.txt          # Python 依赖
├── docker-compose.yml        # Docker 编排
├── .env                      # 环境变量 (不入库)
├── .env.example              # 环境变量模板
├── Dockerfile
│
├── models/                   # 预置模型
│   └── yolov8n.pt            # YOLOv8n 人员检测 (随仓库提供)
│
├── config/                   # 配置文件
│   ├── settings.yaml         # 主配置
│   ├── rooms.yaml            # 房间/摄像头/设备
│   ├── agent_prompt.yaml     # Agent 系统提示词
│   └── mosquitto.conf        # MQTT Broker 配置
│
├── core/                     # 核心框架
│   ├── main.py               # FastAPI 应用 + lifespan
│   ├── config.py             # 配置加载 (Pydantic Settings)
│   ├── database.py           # SQLAlchemy 异步引擎
│   ├── dependencies.py       # FastAPI 依赖注入
│   ├── event_bus.py          # 异步事件总线
│   └── models.py             # ORM 模型
│
├── api/                      # REST API
│   ├── schemas.py            # Pydantic 请求/响应模型
│   ├── routes/               # 路由模块
│   │   ├── agent_log.py
│   │   ├── devices.py
│   │   ├── employees.py
│   │   ├── preferences.py
│   │   ├── rooms.py
│   │   ├── toilet.py
│   │   └── video.py
│   └── websocket/
│       └── realtime.py       # WebSocket 实时推送
│
├── agent/                    # 认知层 (Phase 3)
│   ├── llm_client.py         # 双通道 LLM 客户端 (OpenAI 兼容 API)
│   ├── agent_loop.py         # OTAR 决策循环
│   ├── tools.py              # Function Calling 工具定义
│   ├── tool_executor.py      # 工具执行器 (MQTT 设备控制)
│   ├── prompt_builder.py     # 多模态 Prompt 构建器
│   ├── conflict_resolver.py  # 多人偏好冲突协调
│   └── scene_patrol.py       # 场景巡检 (定时 + SSIM)
│
├── memory/                   # 记忆层 (Phase 4)
│   ├── __init__.py           # MemorySystem 聚合门面
│   ├── explicit_store.py     # 显式偏好 (SQLite CRUD)
│   ├── implicit_store.py     # 隐式偏好 (ChromaDB 向量)
│   ├── context_memory.py     # 情境记忆 (ChromaDB 向量)
│   ├── rag_retriever.py      # RAG 统一检索
│   └── preference_learner.py # 偏好学习器
│
├── reflex/                   # 反射层 (Phase 5)
│   ├── __init__.py
│   └── engine.py             # 反射层引擎 (无人关灯/CO2/厕位)
│
├── perception/               # 感知层 (Phase 2+5)
│   ├── pipeline.py           # 感知管线 (总调度+身份融合)
│   ├── camera_manager.py     # 摄像头管理
│   ├── frame_sampler.py      # 智能帧采样
│   ├── detector.py           # YOLOv8 人员检测
│   ├── face_recognizer.py    # InsightFace 人脸识别
│   ├── person_tracker.py     # IoU 人员追踪 + ReID 外观匹配
│   ├── reid_extractor.py     # ReID 特征提取 (OSNet)
│   ├── identity_fusion.py    # 多模态身份融合引擎
│   └── sensor_collector.py   # 传感器数据采集
│
├── iot/                      # IoT 通信层 (Phase 1)
│   ├── mqtt_client.py        # MQTT 异步客户端
│   ├── device_registry.py    # 设备注册表
│   └── protocols/
│       └── base.py           # 协议基类
│
├── monitor/
│   └── health_check.py       # 健康检查
│
├── scripts/
│   ├── register_faces.py     # 人脸注册 CLI
│   └── simulate_scenario.py  # MQTT 场景模拟脚本
│
├── data/                     # 运行时数据 (自动创建)
│   ├── easeagent.db          # SQLite 数据库
│   ├── faces/                # 人脸特征向量
│   └── chromadb/             # ChromaDB 数据
│
└── docs/                     # 文档
    ├── EaseAgent-使用说明.md
    ├── EaseAgent-排错指南.md
    ├── EaseAgent-技术实现方案.md
    ├── EaseAgent-Phase1执行计划.md
    ├── EaseAgent-Phase2执行计划.md
    ├── EaseAgent-Phase3-认知层.md
    ├── EaseAgent-Phase4-记忆层.md
    ├── EaseAgent-Phase5-集成联调.md
    ├── EaseAgent-待办优化清单.md
    └── EaseAgent-QA问答集.md
```

---

## 9. 常见问题

> 更详细的排错指南（含开发中踩过的坑和调试技巧）请参见 [EaseAgent-排错指南.md](EaseAgent-排错指南.md)。

### GPU 不可用

```bash
# 检查 NVIDIA 驱动
nvidia-smi

# 检查 CUDA 版本
nvcc --version

# 确认 onnxruntime-gpu 已安装
pip show onnxruntime-gpu
```

如果没有 GPU，系统会自动降级为 CPU 推理，但速度会明显变慢。可以在 `settings.yaml` 中设置 `ai.enabled: false` 跳过视觉处理。

### Ollama 模型加载慢

首次运行时需要将模型从磁盘加载到 GPU 显存，耗时约 15-20 秒。后续推理每次约 1-3 秒。如果模型已经卸载（默认 5 分钟无请求后卸载），可以预热：

```bash
# 预热模型
ollama run qwen3.5:9b "ping" --verbose
```

### MQTT 连接失败

```bash
# 检查 Mosquitto 是否运行
# Windows
netstat -an | findstr 1883

# Linux
ss -tlnp | grep 1883

# Docker
docker-compose ps mosquitto
```

确保 `config/settings.yaml` 中 `mqtt.broker` 和 `mqtt.port` 与实际一致。

### 摄像头无法连接

开发模式下使用 `webcam://0` 访问本地摄像头。如果笔记本没有摄像头或被占用，会在日志中看到连接失败的警告，但不会影响其他功能。

部署 RTSP 摄像头时确保：

1. 摄像头在同一网段
2. RTSP URL 格式正确
3. 摄像头未被其他程序独占

### Redis 连接失败

```bash
# 检查 Redis
redis-cli ping
# 应返回 PONG
```

Redis 不可用时 Agent 决策缓存会失效，每次都需要重新调用 LLM，但不影响系统基本运行。

### DashScope API 调用失败

1. 检查 `.env` 中 `DASHSCOPE_API_KEY` 是否正确
2. 确认 API Key 有 `qwen3.5-plus` 模型的调用权限
3. 系统会自动降级到本地 Ollama (`qwen3.5:9b`)

### ChromaDB 连接失败

**现象**：启动日志中出现 `向量存储降级为不可用` 或 `KeyError: '_type'`。

```powershell
# 检查容器是否运行
docker-compose ps chromadb

# 手动测试连通性
curl http://localhost:8100/api/v1/heartbeat

# 核查 Python 客户端版本（必须与服务端一致）
pip show chromadb
# 服务端版本: docker-compose.yml 中 chromadb/chroma:1.4.1
# 客户端版本: requirements.txt 中 chromadb==1.4.1
# 两者必须完全匹配，否则会出现 KeyError
```

如果版本不匹配：`pip install "chromadb==1.4.1"`

如果 `curl` 返回 503，检查是否有代理干扰本地连接。`run.py` 已自动设置 `NO_PROXY=localhost,127.0.0.1`，但如果你单独运行脚本测试，需要手动设置：

```powershell
$env:NO_PROXY = "localhost,127.0.0.1"
```

### Agent 决策日志不增长

**现象**：摄像头在工作、能看到人员检测，但 `/api/agent-logs/` 长时间没有新记录。

**原因**：Redis 决策缓存生效。当场景（房间、人数、环境）无明显变化时，Agent 会命中缓存直接复用上次决策，不调用 LLM，日志标记为 `[缓存命中]`。缓存 TTL 默认 2 小时。

**验证方法**：
1. 查看 `/api/agent-logs/` 最新记录的 `trigger_event` 是否为 `cache_hit`
2. WebSocket 订阅 `agent_log` 频道观察实时推送
3. 如果需要强制触发新决策，可以清除 Redis 缓存：`redis-cli FLUSHDB`
4. 或修改 `config/settings.yaml` 中 `redis.decision_cache_ttl` 缩短缓存时间

### Ollama 未自动启动

**现象**：EaseAgent 启动后日志中 LLM 调用失败，但 DashScope 云端可用时会自动降级。

Ollama 默认安装后不会随系统自启。每次重启电脑后需手动启动：

```powershell
ollama serve           # 前台运行
# 或检查是否已在后台运行
ollama ps              # 查看已加载的模型
ollama list            # 查看已下载的模型
```

模型首次加载到 GPU 显存约 15-20 秒，可以预热：`ollama run qwen3.5:9b "ping"`

---

## 10. 开发调试

### 查看日志

```bash
# 运行时日志直接输出到控制台
python run.py

# 调整日志级别
# config/settings.yaml → server.debug: true
```

### Swagger 交互测试

访问 `http://localhost:8000/docs`，可以直接在浏览器中调试所有 API 端点。

### 事件总线调试

系统内部事件通过 EventBus 传递，关键事件包括：


| 事件               | 触发条件          |
| ---------------- | ------------- |
| `person_entered` | 检测到新人员进入      |
| `person_left`    | 人员离开 (超过延迟时间) |
| `face_arrived`   | 识别到已注册人脸      |
| `face_left`      | 已识别人员离开       |
| `co2_high`       | CO2 浓度超过阈值    |
| `sensor_update`  | 传感器数据更新       |
| `scene_patrol`   | 定时巡检触发        |
| `scene_change`   | 视觉变化检测触发      |


