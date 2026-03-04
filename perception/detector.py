from __future__ import annotations

import asyncio
import logging
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

PERSON_CLASS_ID = 0  # COCO class index for "person"

_inference_pool = ThreadPoolExecutor(max_workers=2, thread_name_prefix="yolo")


def _resolve_device_name() -> str:
    try:
        import torch
        if torch.cuda.is_available():
            return torch.cuda.get_device_name(0)
    except Exception:
        pass
    return "CPU"


class PersonDetector:
    """YOLOv8-based person detector with FP16 inference on GPU."""

    def __init__(
        self,
        model_path: str = "yolov8n.pt",
        confidence: float = 0.5,
    ):
        self._model_path = model_path
        self._confidence = confidence
        self._model: Any = None
        self._device: str = "cpu"
        self._use_half: bool = False
        self.last_inference_ms: float = 0.0
        self.device_name: str = "CPU"

    @property
    def detect_fps(self) -> float:
        if self.last_inference_ms > 0:
            return 1000.0 / self.last_inference_ms
        return 0.0

    async def load(self) -> None:
        loop = asyncio.get_running_loop()
        self._model, self._device, self._use_half = await loop.run_in_executor(
            _inference_pool, self._load_model,
        )
        self.device_name = await loop.run_in_executor(None, _resolve_device_name)
        if self._device != "cpu":
            self.device_name += f" ({self._device})"
        logger.info("YOLOv8 model loaded: %s on %s (half=%s)",
                     self._model_path, self.device_name, self._use_half)

    def _load_model(self) -> tuple[Any, str, bool]:
        import torch
        from ultralytics import YOLO

        device = "cuda:0" if torch.cuda.is_available() else "cpu"
        use_half = device != "cpu"
        model = YOLO(self._model_path)
        model.to(device)
        # Warm-up: 2 dummy inferences to trigger CUDA kernel compilation
        dummy = np.zeros((640, 640, 3), dtype=np.uint8)
        for _ in range(2):
            model.predict(dummy, classes=[PERSON_CLASS_ID], conf=0.5,
                          device=device, verbose=False, half=use_half, imgsz=640)
        logger.info("YOLO device set to: %s (FP16=%s, warm-up done)", device, use_half)
        return model, device, use_half

    async def detect(self, frame: np.ndarray) -> list[dict]:
        if self._model is None:
            await self.load()

        h, w = frame.shape[:2]
        frame_area = h * w
        min_area = frame_area * 0.003   # reject boxes smaller than 0.3% of frame
        max_area = frame_area * 0.65    # reject boxes larger than 65% of frame

        loop = asyncio.get_running_loop()
        t0 = time.perf_counter()
        results = await loop.run_in_executor(
            _inference_pool,
            lambda: self._model.predict(
                frame,
                classes=[PERSON_CLASS_ID],
                conf=self._confidence,
                device=self._device,
                verbose=False,
                half=self._use_half,
                imgsz=640,
            ),
        )
        self.last_inference_ms = (time.perf_counter() - t0) * 1000

        detections: list[dict] = []
        for r in results:
            for box in r.boxes:
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                box_area = (x2 - x1) * (y2 - y1)
                if box_area < min_area or box_area > max_area:
                    continue
                detections.append(
                    {
                        "bbox": [int(x1), int(y1), int(x2), int(y2)],
                        "confidence": float(box.conf[0]),
                    }
                )
        return detections

    async def unload(self) -> None:
        self._model = None
        logger.info("YOLOv8 model unloaded")
