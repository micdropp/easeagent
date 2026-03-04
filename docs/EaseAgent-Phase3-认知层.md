# EaseAgent Phase 3 — 认知层实现文档

## 概述

Phase 3 实现了 EaseAgent 的"大脑"——认知层。该层基于多模态大模型 (qwen3.5-plus 云端 / qwen3.5:9b 本地) 实现场景理解、行为分析和智能决策，通过 Function Calling 工具调用控制办公环境设备。两个通道均通过 OpenAI 兼容 API 统一接入。

## 架构

```
事件总线 EventBus
    │
    ├── face_arrived      ──┐
    ├── person_entered    ──┤
    ├── co2_high          ──┼── EaseAgent (agent_loop.py)
    ├── scene_patrol      ──┤   │
    └── scene_change      ──┘   ├── Observe: PromptBuilder 组装多模态输入
                                ├── Think:   LLMClient 调用大模型
                                ├── Act:     ToolExecutor 执行工具调用
                                └── Reflect: 记录 DecisionLog + Redis 缓存
```

## 模块说明

### 1. LLM 客户端 (`agent/llm_client.py`)

统一 OpenAI 兼容 API 的双通道多模态 LLM 客户端：

| 通道       | 模型            | API 端点                                            | 用途              | 延迟    |
|-----------|-----------------|-----------------------------------------------------|-------------------|---------|
| DashScope | qwen3.5-plus    | `https://dashscope.aliyuncs.com/compatible-mode/v1` | 云端主通道（能力最强） | 2-5 秒  |
| Ollama    | qwen3.5:9b      | `http://localhost:11434/v1`                         | 本地降级 / 离线运行  | 1-3 秒  |

- **统一接口**: 两个通道都使用 `openai.AsyncOpenAI` 客户端，代码统一简洁
- 自动降级：DashScope 不可用时切换到 Ollama
- 指数退避重试：最多 `max_retries` 次
- 统一返回 `LLMResponse` 数据类

### 2. Agent 主循环 (`agent/agent_loop.py`)

Observe -> Think -> Act -> Reflect 循环：

1. **Observe**: 从 PerceptionPipeline 获取当前画面 + 在场人员，从 SensorCollector 获取传感器数据，从 DB 获取偏好
2. **Think**: 将以上信息组装为多模态 Prompt 发送给 LLM，接收 Function Calling 响应
3. **Act**: 通过 ToolExecutor 执行工具调用（MQTT 控制设备）
4. **Reflect**: 记录到 DecisionLog 表 + 缓存到 Redis (2 小时 TTL)

关键特性：
- **事件驱动**: 仅在收到触发事件时启动决策，不轮询
- **异步非阻塞**: 使用 `asyncio.create_task` 避免阻塞事件循环
- **去重**: 同类事件正在处理时跳过重复事件
- **缓存命中**: Redis 有缓存时直接 replay 工具调用，不调 LLM

### 3. Function Calling 工具定义 (`agent/tools.py`)

7 个工具：

| 工具名                     | 功能           | 状态     |
|---------------------------|----------------|----------|
| `control_light`           | 灯光控制       | 可用     |
| `control_ac`              | 空调控制       | 可用     |
| `control_screen`          | 屏幕内容控制   | 可用     |
| `control_fresh_air`       | 新风系统控制   | 可用     |
| `get_employee_preference` | 查询偏好       | 可用     |
| `notify_feishu`           | 飞书通知       | 占位(P6) |
| `update_preference_memory`| 更新偏好记忆   | 占位(P4) |

### 4. 工具执行器 (`agent/tool_executor.py`)

LLM 输出 → 解析 JSON → 路由到对应 handler → MQTT 发布设备控制命令。

### 5. Prompt 构建器 (`agent/prompt_builder.py`)

动态组装多模态输入：

- System Prompt (从 `config/agent_prompt.yaml` 加载)
- 当前场景图像 (base64 JPEG)
- 在场人员及身份
- 传感器数据 (温度/湿度/CO2)
- 设备状态
- 员工偏好
- 多人偏好协调建议

### 6. 偏好冲突协调 (`agent/conflict_resolver.py`)

多人在场时自动计算折中方案：
- 数值型偏好 (温度/亮度/色温): 取平均值
- 优先级型偏好 (新风档位): 取最高优先级

### 7. 场景巡检调度器 (`agent/scene_patrol.py`)

混合触发策略：

- **定时巡检**: 每 30 秒对有人房间进行一次 VLM 全局场景分析
- **视觉变化触发**: 帧 SSIM 差异 > 15% 且非人数变化时立即触发 VLM 分析

这使系统能捕捉行为变化（脱衣服/打哈欠/开会讨论），延迟从 30s 降到 1-2s。

## 配置

### settings.yaml

```yaml
llm:
  provider: dashscope          # 主通道: dashscope / ollama
  model: qwen3.5-plus          # DashScope 模型 (Qwen3.5 系列)
  api_key: ${DASHSCOPE_API_KEY}
  base_url: https://dashscope.aliyuncs.com/compatible-mode/v1
  max_retries: 2
  timeout: 30
  fallback_provider: ollama    # 降级通道
  fallback_model: qwen3.5:9b   # 本地模型 (RTX 4090 24GB)
  fallback_base_url: http://localhost:11434
  patrol_interval: 30.0        # 定时巡检间隔(秒)
  ssim_threshold: 0.85         # 视觉变化触发阈值
```

### .env

```
DASHSCOPE_API_KEY=sk-your-actual-key
```

### agent_prompt.yaml

系统提示词定义了 Agent 的角色、决策原则（安全优先/个性化/节能/场景感知）和默认舒适参数。

## 事件流

```
摄像头 → YOLO检测 → person_entered/face_arrived → EventBus → Agent
                                                              │
传感器 → co2_high / sensor_update → EventBus ─────────────────┘
                                                              │
巡检器 → scene_patrol / scene_change → EventBus ──────────────┘
                                                              │
Agent ──→ LLM (多模态推理) ──→ Function Calling ──→ ToolExecutor
                                                              │
                                                    ┌─────────┼─────────┐
                                                    ▼         ▼         ▼
                                               MQTT控制    DecisionLog  Redis缓存
                                              (灯/空调/    (决策审计)   (2h TTL)
                                               屏幕/新风)
```

## 降级策略

```
正常: DashScope qwen3.5-plus (云端, OpenAI 兼容 API)
  │ 失败/超时
  ▼
降级1: Ollama qwen3.5:9b (本地 RTX 4090, OpenAI 兼容 API)
  │ 失败/未部署
  ▼
降级2: 仅反射层运行 (YOLO 基础开关灯/空调)
```

## 本地模型部署

在本机 RTX 4090 (24GB) 上通过 Ollama 部署 `qwen3.5:9b`：

```bash
# 启动 Ollama
ollama serve

# 拉取模型 (约 5.5 GB)
ollama pull qwen3.5:9b

# 切换到本地模式
# settings.yaml 中修改 llm.provider: ollama
```

## 实时无感体验策略

```
0ms      张三走进办公室
50ms     灯亮了 (反射层 person_entered → MQTT)          ← 即时
2-5s     灯光从 80% 过渡到 70%/3500K (Agent 决策)      ← 自然过渡
下次     缓存命中 → 50ms 直接复用上次决策               ← 瞬间
```

## Phase 4 扩展预留

- `prompt_builder.py`: `memories` 字段预留给 ChromaDB RAG 向量检索
- `tool_executor.py`: `update_preference_memory` handler 预留给偏好学习器
- `tool_executor.py`: `notify_feishu` handler 预留给 Phase 6 飞书集成

## 文件清单

| 文件                          | 类型 | 说明                |
|-------------------------------|------|---------------------|
| `agent/__init__.py`           | 新建 | 包初始化            |
| `agent/llm_client.py`        | 新建 | 双通道 LLM 客户端   |
| `agent/tools.py`             | 新建 | Function Calling 定义|
| `agent/tool_executor.py`     | 新建 | 工具执行器          |
| `agent/prompt_builder.py`    | 新建 | Prompt 构建器       |
| `agent/conflict_resolver.py` | 新建 | 偏好冲突协调        |
| `agent/scene_patrol.py`      | 新建 | 场景巡检调度器      |
| `agent/agent_loop.py`        | 新建 | Agent 主循环        |
| `config/agent_prompt.yaml`   | 新建 | 系统提示词          |
| `core/config.py`             | 修改 | LLM 配置扩展        |
| `core/main.py`               | 修改 | 认知层集成          |
| `perception/pipeline.py`     | 修改 | 视觉变化检测挂载    |
| `config/settings.yaml`       | 修改 | LLM 配置项          |
| `requirements.txt`           | 修改 | openai              |
