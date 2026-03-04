from __future__ import annotations

import asyncio
import time

import cv2
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, StreamingResponse

router = APIRouter()

VIEWER_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>EaseAgent - Live View</title>
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body { background: #111; color: #eee; font-family: system-ui, sans-serif; }
  header { padding: 16px 24px; background: #1a1a2e; border-bottom: 1px solid #333;
           display: flex; align-items: center; gap: 12px; }
  header h1 { font-size: 20px; font-weight: 600; }
  .status { font-size: 13px; color: #4ade80; }
  .grid { display: flex; flex-wrap: wrap; gap: 16px; padding: 20px; justify-content: center; }
  .cam-card { background: #1e1e2e; border-radius: 10px; overflow: hidden;
              box-shadow: 0 4px 20px rgba(0,0,0,.4); max-width: 960px; flex: 1 1 640px; }
  .cam-card .title { padding: 10px 16px; font-size: 14px; font-weight: 500;
                     background: #16213e; display: flex; justify-content: space-between;
                     align-items: center; }
  .cam-card .title .room { color: #94a3b8; }
  .cam-card img { width: 100%; display: block; background: #000; min-height: 360px; }
  .no-cam { text-align: center; padding: 80px 20px; color: #888; }
  .no-cam p { margin-top: 12px; font-size: 14px; }
  .controls { padding: 8px 16px; background: #16213e; display: flex; gap: 8px;
              align-items: center; border-top: 1px solid #333; }
  .controls select, .controls button { background: #2a2a3e; color: #eee; border: 1px solid #444;
              padding: 4px 10px; border-radius: 4px; font-size: 13px; cursor: pointer; }
  .controls label { font-size: 13px; color: #94a3b8; }
</style>
</head>
<body>
<header>
  <h1>EaseAgent Live View</h1>
  <span class="status" id="status">Loading...</span>
</header>
<div class="grid" id="grid"></div>
<script>
async function init() {
  const res = await fetch('/api/video/cameras');
  const data = await res.json();
  const grid = document.getElementById('grid');
  const status = document.getElementById('status');
  if (!data.cameras || data.cameras.length === 0) {
    grid.innerHTML = '<div class="no-cam"><p>No cameras active.<br>Set <code>ai.enabled: true</code> in settings.yaml and restart.</p></div>';
    status.textContent = 'No cameras';
    status.style.color = '#f87171';
    return;
  }
  status.textContent = data.cameras.length + ' camera(s) active';
  data.cameras.forEach(cam => {
    const card = document.createElement('div');
    card.className = 'cam-card';
    card.innerHTML = `
      <div class="title">
        <span>${cam.camera_id}</span>
        <span class="room">Room: ${cam.room_id}</span>
      </div>
      <img id="img-${cam.camera_id}" src="/api/video/stream/${cam.camera_id}?quality=70&max_fps=30" alt="${cam.camera_id}">
      <div class="controls">
        <label>Quality:</label>
        <select onchange="updateStream('${cam.camera_id}', this.value, document.getElementById('fps-${cam.camera_id}').value)">
          <option value="50">Low</option>
          <option value="70" selected>Medium</option>
          <option value="85">High</option>
        </select>
        <label>FPS:</label>
        <select id="fps-${cam.camera_id}" onchange="updateStream('${cam.camera_id}', this.previousElementSibling.previousElementSibling.value, this.value)">
          <option value="15">15</option>
          <option value="20">20</option>
          <option value="30" selected>30</option>
          <option value="60">60</option>
        </select>
      </div>
    `;
    grid.appendChild(card);
  });
}
function updateStream(camId, quality, fps) {
  const img = document.getElementById('img-' + camId);
  img.src = '/api/video/stream/' + camId + '?quality=' + quality + '&max_fps=' + fps;
}
init();
</script>
</body>
</html>"""


@router.get("/", response_class=HTMLResponse)
async def video_viewer():
    return VIEWER_HTML


@router.get("/cameras")
async def list_cameras(request: Request):
    pipeline = getattr(request.app.state, "perception", None)
    if pipeline is None:
        return {"cameras": []}
    cameras = []
    for cam_id in pipeline.get_camera_ids():
        room_id = pipeline._cam_room.get(cam_id, "unknown")
        cameras.append({"camera_id": cam_id, "room_id": room_id})
    return {"cameras": cameras}


@router.get("/stats")
async def video_stats(request: Request):
    """Performance stats for all cameras."""
    pipeline = getattr(request.app.state, "perception", None)
    if pipeline is None:
        return {"stats": {}}
    stats = {}
    for cam_id in pipeline.get_camera_ids():
        stats[cam_id] = {
            "stream_fps": round(pipeline._fps.get(cam_id, 0), 1),
            "detect_fps": round(pipeline._detector.detect_fps, 1),
            "inference_ms": round(pipeline._detector.last_inference_ms, 1),
            "device": pipeline._detector.device_name,
            "detections": len(pipeline._latest_detections.get(cam_id, [])),
        }
    return {"stats": stats, "room_occupants": pipeline.get_all_occupants()}


@router.get("/stream/{camera_id}")
async def video_stream(
    camera_id: str,
    request: Request,
    quality: int = 70,
    max_fps: int = 30,
):
    quality = max(20, min(95, quality))
    max_fps = max(5, min(60, max_fps))
    interval = 1.0 / max_fps
    pipeline = getattr(request.app.state, "perception", None)

    async def mjpeg_generator():
        encode_params = [cv2.IMWRITE_JPEG_QUALITY, quality]
        while True:
            if await request.is_disconnected():
                break
            if pipeline is None:
                await asyncio.sleep(1.0)
                continue
            frame = await pipeline.get_annotated_frame(camera_id)
            if frame is None:
                await asyncio.sleep(0.05)
                continue
            _, buf = cv2.imencode(".jpg", frame, encode_params)
            jpeg_bytes = buf.tobytes()
            pipeline.set_cached_jpeg(camera_id, jpeg_bytes)
            yield (
                b"--frame\r\n"
                b"Content-Type: image/jpeg\r\n\r\n"
                + jpeg_bytes
                + b"\r\n"
            )
            await asyncio.sleep(interval)

    return StreamingResponse(
        mjpeg_generator(),
        media_type="multipart/x-mixed-replace; boundary=frame",
    )
