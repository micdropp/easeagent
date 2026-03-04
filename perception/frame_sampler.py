from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Callable, Coroutine

import cv2
import numpy as np

logger = logging.getLogger(__name__)

DetectionCallback = Callable[[str, np.ndarray], Coroutine[Any, Any, None]]


class FrameSampler:
    """Decides which frames get sent to the detection pipeline.

    Two triggers:
    1. Time-based: at least ``interval`` seconds since the last sample.
    2. Change-based: structural difference between consecutive frames exceeds
       ``change_threshold``, allowing immediate detection even before the
       interval elapses.

    Detection is dispatched as a background task so camera reads are never
    blocked by inference.
    """

    def __init__(
        self,
        detection_callback: DetectionCallback,
        interval: float = 1.0,
        change_threshold: float = 0.03,
    ):
        self._detection_callback = detection_callback
        self._interval = interval
        self._change_threshold = change_threshold
        self._last_sample_time: dict[str, float] = {}
        self._prev_gray: dict[str, np.ndarray] = {}
        self._detecting: dict[str, bool] = {}

    async def on_frame(self, camera_id: str, frame: np.ndarray) -> None:
        """Called by CameraManager for every frame read from a camera."""
        if self._detecting.get(camera_id, False):
            return

        now = time.monotonic()
        elapsed = now - self._last_sample_time.get(camera_id, 0.0)
        time_trigger = elapsed >= self._interval

        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        change_trigger = False
        prev = self._prev_gray.get(camera_id)
        if prev is not None and prev.shape == gray.shape:
            diff = cv2.absdiff(prev, gray)
            change_ratio = float(np.count_nonzero(diff > 25)) / diff.size
            if change_ratio > self._change_threshold:
                change_trigger = True
        self._prev_gray[camera_id] = gray

        if time_trigger or change_trigger:
            self._last_sample_time[camera_id] = now
            self._detecting[camera_id] = True
            asyncio.create_task(self._run_detection(camera_id, frame))

    async def _run_detection(self, camera_id: str, frame: np.ndarray) -> None:
        try:
            await self._detection_callback(camera_id, frame)
        except Exception:
            logger.exception("Detection error for %s", camera_id)
        finally:
            self._detecting[camera_id] = False
