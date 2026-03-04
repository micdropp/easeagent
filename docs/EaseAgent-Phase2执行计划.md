---
name: EaseAgent Phase2 执行
overview: 构建反射层 - YOLOv8 人员检测 + InsightFace 人脸识别 + 摄像头管理(支持 webcam 开发模式) + 智能帧采样器 + 传感器采集器，全部集成到 Phase 1 的 EventBus。
todos:
  - id: p2-deps
    content: 更新 requirements.txt 添加 ultralytics/insightface/opencv/onnxruntime-gpu
    status: completed
  - id: p2-camera-manager
    content: 创建 perception/camera_manager.py 摄像头流管理器（支持 RTSP + webcam）
    status: completed
  - id: p2-frame-sampler
    content: 创建 perception/frame_sampler.py 智能帧采样器
    status: completed
  - id: p2-detector
    content: 创建 perception/detector.py YOLOv8 人员检测器
    status: completed
  - id: p2-face-recognizer
    content: 创建 perception/face_recognizer.py InsightFace 人脸识别
    status: completed
  - id: p2-sensor-collector
    content: 创建 perception/sensor_collector.py 传感器数据采集
    status: completed
  - id: p2-integration
    content: 集成到 main.py lifespan + 更新 settings.yaml + rooms.yaml + employees face API
    status: completed
  - id: p2-register-faces
    content: 创建 scripts/register_faces.py 人脸录入工具
    status: completed
isProject: false
---

# EaseAgent Phase 2 执行计划

## 已确认的决策

- **摄像头来源**: 开发阶段使用 webcam，部署时切换 RTSP
- **GPU**: 用户有 NVIDIA GPU，启用 CUDA 加速
- **反射层开关**: `ai.enabled` 配置项，默认关闭

## Phase 2 交付物

### perception/ 反射层 (5 个文件)

- `camera_manager.py` - 摄像头流管理器 (RTSP + webcam)
- `frame_sampler.py` - 智能帧采样器 (时间间隔 + 变化检测)
- `detector.py` - YOLOv8 人员检测器
- `face_recognizer.py` - InsightFace 人脸识别
- `sensor_collector.py` - 传感器数据采集 (MQTT)

### 事件类型 (Phase 2 新增)

| 事件 | 触发条件 | data |
|------|---------|------|
| person_entered | YOLO 人数增加 | room_id, count, prev_count |
| person_left | YOLO 人数减少 | room_id, count, prev_count |
| face_recognized | InsightFace 识别成功 | employee_id, confidence, room_id |
| sensor_update | 传感器周期上报 | room_id, temperature, humidity, co2 |
| co2_high | CO2 > 1000ppm | room_id, co2_value |
