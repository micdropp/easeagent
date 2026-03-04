# EaseAgent 待办优化清单

> 本文档记录开发过程中发现的、需要在后续阶段实现的优化项。按优先级从高到低排列。

---

## 1. BLE 工牌定位（推荐 Phase 3）

**问题**

- 摄像头无法可靠跨区域追踪身份——人离开一个摄像头画面后，进入另一个摄像头时身份断链
- 戴口罩、背对摄像头等场景下人脸识别完全失效，无法确定"谁在哪个房间"

**方案**

- 每个房间部署 BLE 接收器，员工佩戴 BLE 工牌
- BLE 接收器通过 MQTT 上报定位数据：`{employee_id, room_id, rssi}`
- 系统根据信号强度判断员工当前所在房间

**与现有架构的关系**

- 完全兼容现有 MQTT + DeviceRegistry 架构
- BLE 接收器作为新的 IoT 设备类型接入，无需改动通信层
- 摄像头仍负责人数计数和动作检测，BLE 负责身份定位

**收益**

- 100% 可靠的"谁在哪个房间"，不受遮挡、光线、角度、口罩影响
- 为后续偏好联动（灯光、空调、屏幕）提供可靠的身份基础

---

## 2. 门禁刷卡联动身份绑定（推荐 Phase 3）

**问题**

- 入口处人脸识别可能因口罩、逆光等原因失败
- 员工进门时无法确认身份，导致后续追踪全部为"未识别"

**方案**

- 门禁系统通过 MQTT 发送 `badge_swipe` 事件（包含 employee_id 和时间戳）
- 系统收到事件后，自动在入口摄像头的 tracker 中找到最新出现的未识别 track
- 将员工身份绑定到该 track，后续在该摄像头内持续追踪

**实现位置**

- `perception/pipeline.py`：订阅 EventBus 的 `badge_swipe` 事件
- `perception/person_tracker.py`：新增 `bind_latest_unidentified(employee_id)` 方法

---

## 3. 跨摄像头人体 ReID（推荐 Phase 5）

**问题**

- 人从摄像头 A 走到摄像头 B 时，tracker 创建新的 track_id，身份丢失
- 即使在同一摄像头，人离开画面超过 10 秒后重新出现也会丢失身份

**方案**

- 引入 ReID（Re-Identification）模型（如 OSNet），提取人体外观特征向量
- 当摄像头 B 出现新的未识别 track 时，与摄像头 A 最近消失的已识别 track 做外观特征匹配
- 匹配成功则继承身份

**局限**

- 换衣服后失效，仅适合当天内使用
- 需要额外的 ReID 模型，增加约 200MB 显存和 5-10ms 推理开销

**依赖**

- `torchreid` 或 `fast-reid` 库
- 预训练的 OSNet / BoT 模型

---

## 4. 口罩场景下的降级识别策略（推荐 Phase 3）

**问题**

- InsightFace buffalo_l 对口罩场景识别率从 99% 骤降到约 70-80%
- 当前固定阈值 0.45 在口罩场景下可能过高（漏识别）或过低（误识别）

**方案**

- **投票机制**：连续 N 帧（如 5 帧）识别结果一致才确认身份，过滤单帧噪声
- **分级阈值**：正常场景 0.45，检测到口罩（可通过人脸关键点遮挡程度判断）时降到 0.35
- **交叉验证**：结合 BLE 定位数据，如果 BLE 显示"张三在 A 区"且摄像头在 A 区识别到一个低置信度匹配，可以提高确认概率

**实现位置**

- `perception/face_recognizer.py`：投票逻辑和动态阈值
- `perception/pipeline.py`：融合 BLE 数据的交叉验证

---

## 5. 多模态融合识别（Phase 5+）

**问题**

- 单一传感器（摄像头）在各种边缘场景下都有盲区
- 没有任何单一方案能覆盖所有场景（口罩 + 背身 + 跨区域 + 换衣服）

**方案**

- 融合多种身份信号：人脸识别 + 人体外观 ReID + BLE 定位 + 门禁刷卡 + 步态识别
- 设计统一的身份融合引擎，每种信号提供一个置信度，加权投票确定最终身份
- 信号冲突时按可靠度排序：门禁刷卡 > BLE 定位 > 人脸识别 > ReID > 步态

**实现阶段**

- 作为系统成熟后的增强功能，依赖前述各项的逐步落地

---

## 已完成的优化（本轮）

以下优化已在当前阶段实现：

| 优化项 | 涉及文件 | 状态 |
|---|---|---|
| YOLO 与 InsightFace 并行执行 | `perception/pipeline.py` | 已完成 |
| InsightFace det_size 提升到 960x960 | `perception/face_recognizer.py` | 已完成 |
| 多 embedding 注册（多角度照片） | `perception/face_recognizer.py` | 已完成 |
| 识别阈值从 0.6 降到 0.45 | `config/settings.yaml` | 已完成 |
| 未识别人脸红色框可视化 | `perception/pipeline.py` | 已完成 |
| 轻量级 IoU 人体追踪器 | `perception/person_tracker.py` | 已完成 |
| 追踪器身份持久化（转身不丢名字） | `perception/pipeline.py` | 已完成 |
| 房间在场状态机（face_arrived/face_left） | `perception/pipeline.py` | 已完成 |
| 可查询的房间在场接口 | `perception/pipeline.py` + `api/routes/video.py` | 已完成 |
