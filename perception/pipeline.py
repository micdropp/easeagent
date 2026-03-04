from __future__ import annotations

import asyncio
import base64
import logging
import time
from dataclasses import dataclass, field
from typing import Any

import cv2
import numpy as np

from core.config import load_rooms_config, get_settings
from core.event_bus import Event, EventBus
from perception.camera_manager import CameraManager
from perception.detector import PersonDetector
from perception.face_recognizer import FaceRecognizer
from perception.frame_sampler import FrameSampler
from perception.person_tracker import PersonTracker, TrackedPerson

logger = logging.getLogger(__name__)


@dataclass
class Occupant:
    """An identified employee currently present in a room."""

    employee_id: str
    room_id: str
    first_seen: float = field(default_factory=time.monotonic)
    last_seen: float = field(default_factory=time.monotonic)
    confidence: float = 0.0

    def touch(self, confidence: float = 0.0) -> None:
        self.last_seen = time.monotonic()
        if confidence > self.confidence:
            self.confidence = confidence


class PerceptionPipeline:
    """Orchestrates cameras -> sampler -> detector -> recognizer -> tracker."""

    def __init__(self, event_bus: EventBus):
        self._event_bus = event_bus
        settings = get_settings()

        self._detector = PersonDetector(
            model_path=settings.ai.yolo_model,
            confidence=0.6,
        )
        self._recognizer = FaceRecognizer(
            model_name=settings.ai.face_model,
            threshold=settings.ai.face_recognition_threshold,
        )
        self._sampler = FrameSampler(
            detection_callback=self._on_sampled_frame,
            interval=settings.ai.detection_interval,
        )
        self._camera_mgr = CameraManager(
            frame_callback=self._on_raw_frame,
            width=settings.ai.camera_width,
            height=settings.ai.camera_height,
        )

        self._room_count: dict[str, int] = {}
        self._cam_room: dict[str, str] = {}
        self._cam_purposes: dict[str, list[str]] = {}

        self._latest_frames: dict[str, np.ndarray] = {}
        self._latest_detections: dict[str, list[dict]] = {}
        self._latest_faces: dict[str, list[dict]] = {}

        self._frame_times: dict[str, list[float]] = {}
        self._fps: dict[str, float] = {}

        self._gpu_mem_cache: str = "N/A"
        self._gpu_mem_ts: float = 0.0

        self._jpeg_cache: dict[str, tuple[float, bytes]] = {}

        # Per-camera person tracker
        self._trackers: dict[str, PersonTracker] = {}

        # Room occupancy: room_id -> {employee_id -> Occupant}
        self._room_occupants: dict[str, dict[str, Occupant]] = {}

        # ScenePatrol reference (set by main.py after construction)
        self._scene_patrol: Any = None

    @property
    def face_recognizer(self) -> FaceRecognizer:
        return self._recognizer

    def get_camera_ids(self) -> list[str]:
        return list(self._cam_room.keys())

    def get_room_occupants(self, room_id: str) -> list[dict]:
        """Return current occupants of *room_id* as a list of dicts.

        Each dict has: employee_id, first_seen, last_seen, confidence.
        """
        occupants = self._room_occupants.get(room_id, {})
        return [
            {
                "employee_id": o.employee_id,
                "first_seen": o.first_seen,
                "last_seen": o.last_seen,
                "confidence": o.confidence,
            }
            for o in occupants.values()
        ]

    def get_all_occupants(self) -> dict[str, list[dict]]:
        """Return occupants for all rooms."""
        return {
            room_id: self.get_room_occupants(room_id)
            for room_id in self._room_occupants
        }

    # ------------------------------------------------------------------
    # GPU memory (cached)
    # ------------------------------------------------------------------

    def _get_gpu_mem(self) -> str:
        now = time.perf_counter()
        if now - self._gpu_mem_ts < 2.0:
            return self._gpu_mem_cache
        try:
            import torch
            if torch.cuda.is_available():
                allocated = torch.cuda.memory_allocated() / 1024**3
                reserved = torch.cuda.memory_reserved() / 1024**3
                total = torch.cuda.get_device_properties(0).total_memory / 1024**3
                used = max(allocated, reserved)
                self._gpu_mem_cache = f"{used:.1f}/{total:.1f} GB"
            else:
                self._gpu_mem_cache = "N/A (CPU)"
        except Exception:
            self._gpu_mem_cache = "N/A"
        self._gpu_mem_ts = now
        return self._gpu_mem_cache

    # ------------------------------------------------------------------
    # FPS tracking
    # ------------------------------------------------------------------

    def _update_fps(self, camera_id: str) -> None:
        now = time.perf_counter()
        times = self._frame_times.setdefault(camera_id, [])
        times.append(now)
        cutoff = now - 2.0
        while times and times[0] < cutoff:
            times.pop(0)
        if len(times) >= 2:
            self._fps[camera_id] = (len(times) - 1) / (times[-1] - times[0])
        else:
            self._fps[camera_id] = 0.0

    # ------------------------------------------------------------------
    # Overlay drawing
    # ------------------------------------------------------------------

    def _draw_perf_overlay(self, frame: np.ndarray, camera_id: str) -> None:
        h, w = frame.shape[:2]
        stream_fps = self._fps.get(camera_id, 0.0)
        detect_fps = self._detector.detect_fps
        inference_ms = self._detector.last_inference_ms
        device_name = self._detector.device_name
        gpu_mem = self._get_gpu_mem()

        tracker = self._trackers.get(camera_id)
        tracks = tracker.active_tracks if tracker else []
        identified = sum(1 for t in tracks if t.employee_id is not None)
        total_tracks = len(tracks)

        room_id = self._cam_room.get(camera_id, "unknown")
        occupants = self._room_occupants.get(room_id, {})

        lines = [
            f"Device: {device_name}",
            f"Stream FPS: {stream_fps:.1f}",
            f"Detect FPS: {detect_fps:.1f}",
            f"Inference: {inference_ms:.1f}ms",
            f"Tracked: {total_tracks} ({identified} identified)",
            f"Room: {len(occupants)} occupants",
            f"Resolution: {w}x{h}",
            f"GPU Mem: {gpu_mem}",
        ]

        color = (0, 255, 0)
        font = cv2.FONT_HERSHEY_SIMPLEX
        scale = 0.65
        thickness = 2
        line_h = 30
        pad = 10
        box_w = 380
        box_h = len(lines) * line_h + pad * 2

        x2_box = min(pad + box_w, w)
        y2_box = min(pad + box_h, h)

        roi = frame[pad:y2_box, pad:x2_box]
        dark = (roi >> 2).astype(np.uint8)
        np.copyto(roi, dark)

        for i, text in enumerate(lines):
            y = pad + pad + (i + 1) * line_h - 6
            cv2.putText(frame, text, (pad + 10, y), font, scale, color, thickness)

    async def get_annotated_frame(self, camera_id: str) -> np.ndarray | None:
        """Return the latest frame with tracked person boxes and overlay."""
        raw = self._latest_frames.get(camera_id)
        if raw is None:
            return None
        frame = raw.copy()

        tracker = self._trackers.get(camera_id)
        tracks = tracker.active_tracks if tracker else []

        for track in tracks:
            x1, y1, x2, y2 = track.bbox
            if track.employee_id is not None:
                # Identified person — cyan box with name
                color = (255, 200, 0)
                label = f"{track.employee_id} ({track.confidence:.0%})"
            else:
                # Unidentified person — green box
                color = (0, 255, 0)
                label = f"Person #{track.track_id}"
            cv2.rectangle(frame, (x1, y1), (x2, y2), color, 2)
            cv2.putText(frame, label, (x1, y1 - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, color, 2)

        # Draw face detection results (smaller boxes around faces)
        faces = self._latest_faces.get(camera_id, [])
        for f in faces:
            x1, y1, x2, y2 = f["bbox"]
            emp_id = f.get("employee_id", "unknown")
            if emp_id == "unknown":
                face_color = (0, 0, 255)
                face_label = "?"
            else:
                face_color = (0, 200, 255)
                face_label = emp_id
            cv2.rectangle(frame, (x1, y1), (x2, y2), face_color, 1)
            cv2.putText(frame, face_label, (x1, y2 + 16),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, face_color, 1)

        self._draw_perf_overlay(frame, camera_id)
        return frame

    def get_cached_jpeg(self, camera_id: str) -> bytes | None:
        entry = self._jpeg_cache.get(camera_id)
        if entry is None:
            return None
        return entry[1]

    def set_cached_jpeg(self, camera_id: str, data: bytes) -> None:
        self._jpeg_cache[camera_id] = (time.perf_counter(), data)

    # ------------------------------------------------------------------
    # Frame callbacks
    # ------------------------------------------------------------------

    async def _on_raw_frame(self, camera_id: str, frame: np.ndarray) -> None:
        self._update_fps(camera_id)
        self._latest_frames[camera_id] = frame
        await self._sampler.on_frame(camera_id, frame)

    # ------------------------------------------------------------------
    # Camera loading
    # ------------------------------------------------------------------

    def _load_cameras(self) -> None:
        rooms_cfg = load_rooms_config()
        cameras = rooms_cfg.get("cameras", [])
        for cam in cameras:
            cam_id = cam["id"]
            url = cam.get("rtsp_url", "")
            room_id = cam.get("room", "unknown")
            purposes = cam.get("purpose", [])
            self._cam_room[cam_id] = room_id
            self._cam_purposes[cam_id] = purposes
            self._camera_mgr.add_camera(cam_id, room_id, url, purposes)
            self._trackers[cam_id] = PersonTracker(
                iou_threshold=0.3, max_missing_seconds=3.0,
            )
            if room_id not in self._room_occupants:
                self._room_occupants[room_id] = {}
        logger.info("Loaded %d cameras from config", len(cameras))

    async def start(self) -> None:
        self._load_cameras()
        if not self._cam_room:
            logger.warning("No cameras configured, perception pipeline idle")
            return
        await self._detector.load()
        await self._recognizer.load()
        await self._camera_mgr.start()
        logger.info("Perception pipeline started")

    async def stop(self) -> None:
        await self._camera_mgr.stop()
        await self._detector.unload()
        await self._recognizer.unload()
        logger.info("Perception pipeline stopped")

    # ------------------------------------------------------------------
    # Core sampled-frame processing
    # ------------------------------------------------------------------

    async def _on_sampled_frame(self, camera_id: str, frame: np.ndarray) -> None:
        room_id = self._cam_room.get(camera_id, "unknown")
        purposes = self._cam_purposes.get(camera_id, [])

        do_face = "face_recognition" in purposes

        # Stage 1: YOLO detection (fast, ~3-5ms on GPU with FP16)
        detections = await self._detector.detect(frame)

        # Stage 2: face recognition only when people are detected
        recognized: list[dict] = []
        if do_face and detections:
            recognized = await self._recognizer.recognize(frame)

        self._latest_detections[camera_id] = detections
        self._latest_faces[camera_id] = recognized

        # --- Person tracking ---
        tracker = self._trackers.get(camera_id)
        if tracker is None:
            return

        active_tracks, lost_tracks = tracker.update(detections)

        # Bind face identities to tracked persons
        tracker.bind_faces_to_tracks(recognized)

        # --- Room occupancy state machine ---
        occupants = self._room_occupants.setdefault(room_id, {})

        # Collect currently identified employees from active tracks
        currently_identified: dict[str, TrackedPerson] = {}
        for track in active_tracks:
            if track.employee_id is not None:
                currently_identified[track.employee_id] = track

        # Arrivals: employee in tracks but not in occupants → face_arrived
        for emp_id, track in currently_identified.items():
            if emp_id not in occupants:
                occupants[emp_id] = Occupant(
                    employee_id=emp_id,
                    room_id=room_id,
                    confidence=track.confidence,
                )
                logger.info("face_arrived: %s in room %s", emp_id, room_id)
                await self._event_bus.publish(
                    Event(
                        type="face_arrived",
                        data={
                            "employee_id": emp_id,
                            "confidence": track.confidence,
                            "room_id": room_id,
                        },
                        source="perception",
                        room_id=room_id,
                    )
                )
            else:
                occupants[emp_id].touch(track.confidence)

        # Departures: check lost tracks for identified persons
        for track in lost_tracks:
            if track.employee_id is not None:
                emp_id = track.employee_id
                # Only remove if no other active track carries this identity
                if emp_id not in currently_identified and emp_id in occupants:
                    del occupants[emp_id]
                    logger.info("face_left: %s from room %s", emp_id, room_id)
                    await self._event_bus.publish(
                        Event(
                            type="face_left",
                            data={
                                "employee_id": emp_id,
                                "room_id": room_id,
                            },
                            source="perception",
                            room_id=room_id,
                        )
                    )

        # --- Person count events (unchanged logic) ---
        count = len(detections)
        prev_count = self._room_count.get(room_id, 0)

        if count != prev_count:
            if count > prev_count:
                _, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 60])
                frame_b64 = base64.b64encode(buf).decode()
                await self._event_bus.publish(
                    Event(
                        type="person_entered",
                        data={
                            "room_id": room_id,
                            "count": count,
                            "prev_count": prev_count,
                            "frame_base64": frame_b64,
                        },
                        source="perception",
                        room_id=room_id,
                    )
                )
            else:
                await self._event_bus.publish(
                    Event(
                        type="person_left",
                        data={
                            "room_id": room_id,
                            "count": count,
                            "prev_count": prev_count,
                        },
                        source="perception",
                        room_id=room_id,
                    )
                )
            self._room_count[room_id] = count

        # --- Visual change detection for scene patrol ---
        if self._scene_patrol is not None:
            person_count_changed = count != prev_count
            self._scene_patrol.check_visual_change(
                camera_id, frame, person_count_changed
            )
