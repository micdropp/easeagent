# Phase 5: 五大模块集成 + 反射层 + ReID

## 概述

Phase 5 在 Phase 1-4 的基础上实现了以下核心功能：

1. **反射层引擎 (ReflexEngine)** — 毫秒级确定性响应，无需 LLM 介入
2. **厕位传感器 MQTT 接入** — 实时厕位状态推送
3. **跨摄像头 ReID** — 基于外观特征的身份接续
4. **多模态身份融合** — 人脸识别 + ReID 加权投票框架

## 架构

```
感知层 (Perception)
  ├── YOLOv8 检测 → PersonTracker (IoU + ReID)
  ├── InsightFace 人脸识别
  ├── ReID 外观特征提取 (OSNet)
  └── 多模态身份融合引擎 (IdentityFusion)
        ↓
事件总线 (EventBus)
  ├── person_entered / person_left
  ├── face_arrived / face_left
  ├── co2_high
  └── toilet_sensor → toilet_status
        ↓                    ↓
反射层 (Reflex)          认知层 (Cognition)
  ├── 无人延时关灯/空调      └── OTAR Agent (LLM)
  ├── CO2 超标加新风
  └── 厕位状态更新
        ↓
执行层 (ToolExecutor → MQTT Devices)
```

## 新增模块

### 1. 反射层引擎 (`reflex/engine.py`)

`ReflexEngine` 独立于 Agent，直接订阅事件并执行快速响应：

| 事件 | 反射动作 | 安全等级 |
|------|---------|---------|
| `person_left` (count=0) | 启动延时计时器 → 超时关灯+关空调 | 普通 |
| `person_entered` | 取消延时计时器 | — |
| `co2_high` | 立即设新风为 HIGH | 安全（不可覆盖） |
| `toilet_sensor` | 更新厕位状态 → 发布 `toilet_status` | — |

**延时机制**：
- 每个房间独立管理一个 `asyncio.Task` 计时器
- 延时时长从 `rooms.yaml` 的 `reflex_rules.no_person_delay` 读取
- 人员返回时自动取消计时器

**与认知层协调**：
- 每次反射动作后发布 `reflex_action` 事件
- Agent 收到后记录决策日志，安全动作不可被覆盖

### 2. 厕位传感器接入

- MQTT 订阅 `easeagent/+/toilet/+/status`
- 解析 `{"occupied": true/false}` 消息
- 通过 EventBus 发布 `toilet_sensor` → `toilet_status` 事件
- 与已有的厕位 WebSocket API 集成

### 3. ReID 特征提取器 (`perception/reid_extractor.py`)

- 使用 `torchreid` 的 OSNet 模型（轻量级，~5MB）
- 从 YOLO 检测的 bbox 裁切人体图像
- 输出 512 维 L2 归一化特征向量
- GPU 推理，与 YOLO/InsightFace 共享显卡

### 4. PersonTracker 扩展

新增字段和方法：
- `TrackedPerson.appearance`: 外观特征向量
- `_lost_gallery`: 存储最近 10 分钟消失的已识别 track
- `match_by_appearance()`: 在本地 lost gallery 中余弦匹配
- `match_across_galleries()`: 跨摄像头搜索其他 tracker 的 lost gallery

### 5. 多模态身份融合 (`perception/identity_fusion.py`)

加权投票框架，支持多种身份信号源：

| 信号源 | 默认权重 | Phase 5 状态 |
|--------|---------|-------------|
| 门禁卡 | 0.99 | 预留接口 |
| BLE 工牌 | 0.95 | 预留接口 |
| 人脸识别 | 0.85 | 已实现 |
| ReID 外观 | 0.70 | 已实现 |
| 步态识别 | 0.50 | 预留接口 |

融合流程：
1. 收集每帧所有可用的身份信号
2. 按 `employee_id` 分组
3. 计算加权平均分数
4. 超过阈值即接受身份

## 配置

### rooms.yaml 设备配置示例

```yaml
rooms:
  - id: zone_a
    name: A区办公区
    devices:
      lights: [light_a1, light_a2, light_a3]
      acs: [ac_a1]
      fresh_air: [fa_a1]
      curtains: [curtain_a1, curtain_a2]
      screens: [screen_a1]
    reflex_rules:
      no_person_delay: 300     # 无人5分钟后关闭设备
      co2_high_threshold: 1000 # CO2 超 1000ppm 触发新风
```

## 测试

### MQTT 场景模拟

```bash
# 运行所有模拟场景
python scripts/simulate_scenario.py

# 仅测试 CO2 告警
python scripts/simulate_scenario.py --scene co2

# 仅测试厕位传感器
python scripts/simulate_scenario.py --scene toilet

# 设备心跳
python scripts/simulate_scenario.py --scene heartbeat
```

### 依赖安装

```bash
pip install torchreid paho-mqtt
```

如果不安装 `torchreid`，系统会优雅降级：ReID 和身份融合功能自动禁用，仅依赖人脸识别。

## 文件清单

| 操作 | 文件 | 说明 |
|------|------|------|
| 新建 | `reflex/__init__.py` | 反射层包初始化 |
| 新建 | `reflex/engine.py` | 反射层引擎 |
| 新建 | `perception/reid_extractor.py` | ReID 特征提取 |
| 新建 | `perception/identity_fusion.py` | 多模态身份融合 |
| 新建 | `scripts/simulate_scenario.py` | MQTT 场景模拟 |
| 修改 | `perception/person_tracker.py` | 外观特征 + lost gallery |
| 修改 | `perception/pipeline.py` | 集成 ReID + 身份融合 |
| 修改 | `agent/agent_loop.py` | 订阅 reflex_action 协调 |
| 修改 | `core/main.py` | 初始化 ReflexEngine |
| 修改 | `config/rooms.yaml` | 补全设备 + 反射规则 |
| 修改 | `iot/mqtt_client.py` | 添加 subscribe_topic 方法 |
| 修改 | `requirements.txt` | 添加 torchreid, paho-mqtt |
