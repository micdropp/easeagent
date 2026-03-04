"""Scene patrol scheduler — hybrid timer + visual-change trigger.

Timer path:   Every ``patrol_interval`` seconds, grab the latest frame
              from each camera that has detected people and publish a
              ``scene_patrol`` event so the Agent can do a full VLM
              scene analysis.

Change path:  On every sampled frame, compute SSIM against the last
              patrol reference frame.  If the difference exceeds a
              threshold *and* person count has NOT changed (to avoid
              duplicating person_entered/left events), publish a
              ``scene_change`` event immediately for fast VLM analysis.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any

import cv2
import numpy as np

from core.event_bus import Event, EventBus

logger = logging.getLogger(__name__)


def _ssim_gray(a: np.ndarray, b: np.ndarray) -> float:
    """Compute simplified structural similarity (SSIM) on grayscale images.

    Returns a value in [0, 1] where 1 means identical.
    Downsamples to 320-wide for speed.
    """
    h, w = a.shape[:2]
    scale = 320.0 / max(w, 1)
    new_w, new_h = int(w * scale), int(h * scale)
    if new_w < 8 or new_h < 8:
        return 1.0

    ga = cv2.cvtColor(a, cv2.COLOR_BGR2GRAY) if len(a.shape) == 3 else a
    gb = cv2.cvtColor(b, cv2.COLOR_BGR2GRAY) if len(b.shape) == 3 else b

    ga = cv2.resize(ga, (new_w, new_h)).astype(np.float64)
    gb = cv2.resize(gb, (new_w, new_h)).astype(np.float64)

    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2

    mu1 = cv2.GaussianBlur(ga, (11, 11), 1.5)
    mu2 = cv2.GaussianBlur(gb, (11, 11), 1.5)
    mu1_sq = mu1 * mu1
    mu2_sq = mu2 * mu2
    mu1_mu2 = mu1 * mu2

    sigma1_sq = cv2.GaussianBlur(ga * ga, (11, 11), 1.5) - mu1_sq
    sigma2_sq = cv2.GaussianBlur(gb * gb, (11, 11), 1.5) - mu2_sq
    sigma12 = cv2.GaussianBlur(ga * gb, (11, 11), 1.5) - mu1_mu2

    ssim_map = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / (
        (mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2)
    )
    return float(ssim_map.mean())


class ScenePatrol:
    """Hybrid scene patrol scheduler.

    Parameters
    ----------
    event_bus : EventBus
        Used to publish ``scene_patrol`` and ``scene_change`` events.
    perception_pipeline : Any
        Reference to the running PerceptionPipeline to grab frames and
        room occupancy.
    patrol_interval : float
        Seconds between timed patrols (default 30).
    ssim_threshold : float
        Minimum SSIM change to fire a ``scene_change`` event (default
        0.85 — i.e. 15 % visual change).
    change_cooldown : float
        Minimum seconds between two ``scene_change`` events for the
        same camera (default 10).
    """

    def __init__(
        self,
        event_bus: EventBus,
        perception_pipeline: Any,
        patrol_interval: float = 30.0,
        ssim_threshold: float = 0.85,
        change_cooldown: float = 10.0,
    ):
        self._event_bus = event_bus
        self._perception = perception_pipeline
        self._interval = patrol_interval
        self._ssim_threshold = ssim_threshold
        self._change_cooldown = change_cooldown

        self._ref_frames: dict[str, np.ndarray] = {}
        self._last_change_ts: dict[str, float] = {}
        self._task: asyncio.Task | None = None
        self._running = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        self._running = True
        self._task = asyncio.create_task(self._patrol_loop())
        logger.info(
            "ScenePatrol started (interval=%ss, ssim_threshold=%.2f)",
            self._interval,
            self._ssim_threshold,
        )

    async def stop(self) -> None:
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None
        logger.info("ScenePatrol stopped")

    # ------------------------------------------------------------------
    # Timed patrol loop
    # ------------------------------------------------------------------

    async def _patrol_loop(self) -> None:
        while self._running:
            try:
                await asyncio.sleep(self._interval)
                await self._do_patrol()
            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in patrol loop")

    async def _do_patrol(self) -> None:
        """Send scene_patrol events for rooms that currently have people."""
        if self._perception is None:
            return

        all_occupants = self._perception.get_all_occupants()

        for cam_id in self._perception.get_camera_ids():
            room_id = self._perception._cam_room.get(cam_id, "unknown")
            occupants = all_occupants.get(room_id, [])
            if not occupants:
                continue

            frame = await self._perception.get_annotated_frame(cam_id)
            if frame is None:
                continue

            self._ref_frames[cam_id] = frame.copy()

            await self._event_bus.publish(
                Event(
                    type="scene_patrol",
                    data={
                        "room_id": room_id,
                        "camera_id": cam_id,
                        "occupant_count": len(occupants),
                        "trigger": "timer",
                    },
                    source="scene_patrol",
                    room_id=room_id,
                )
            )
            logger.debug(
                "scene_patrol fired for room %s (%d occupants)",
                room_id,
                len(occupants),
            )

    # ------------------------------------------------------------------
    # Visual-change trigger (called from perception pipeline)
    # ------------------------------------------------------------------

    def check_visual_change(
        self,
        camera_id: str,
        frame: np.ndarray,
        person_count_changed: bool,
    ) -> bool:
        """Check if the frame differs enough to warrant a scene_change event.

        Returns True if the event was published.  Skips when person
        count just changed (already handled by person_entered/left).
        """
        if person_count_changed:
            self._ref_frames[camera_id] = frame.copy()
            return False

        ref = self._ref_frames.get(camera_id)
        if ref is None:
            self._ref_frames[camera_id] = frame.copy()
            return False

        now = time.monotonic()
        last = self._last_change_ts.get(camera_id, 0.0)
        if now - last < self._change_cooldown:
            return False

        ssim = _ssim_gray(ref, frame)
        if ssim > self._ssim_threshold:
            return False

        self._ref_frames[camera_id] = frame.copy()
        self._last_change_ts[camera_id] = now

        room_id = "unknown"
        if self._perception:
            room_id = self._perception._cam_room.get(camera_id, "unknown")

        self._event_bus.publish_nowait(
            Event(
                type="scene_change",
                data={
                    "room_id": room_id,
                    "camera_id": camera_id,
                    "ssim": round(ssim, 3),
                    "trigger": "visual_change",
                },
                source="scene_patrol",
                room_id=room_id,
            )
        )
        logger.info(
            "scene_change fired for camera %s (SSIM=%.3f)", camera_id, ssim
        )
        return True
