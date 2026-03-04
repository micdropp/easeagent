from __future__ import annotations

import abc
import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Coroutine

import cv2
import numpy as np

logger = logging.getLogger(__name__)


class CameraSource(abc.ABC):
    """Abstract base for all camera frame providers."""

    @abc.abstractmethod
    async def open(self) -> None: ...

    @abc.abstractmethod
    async def read_frame(self) -> np.ndarray | None: ...

    @abc.abstractmethod
    async def close(self) -> None: ...

    @abc.abstractmethod
    def is_opened(self) -> bool: ...


class _CV2Source(CameraSource):
    """OpenCV VideoCapture wrapper running blocking I/O in a thread pool."""

    def __init__(self, source: str | int, reconnect_delay: float = 5.0,
                 width: int = 1280, height: int = 720):
        self._source = source
        self._reconnect_delay = reconnect_delay
        self._width = width
        self._height = height
        self._cap: cv2.VideoCapture | None = None

    async def open(self) -> None:
        loop = asyncio.get_running_loop()
        self._cap = await loop.run_in_executor(None, cv2.VideoCapture, self._source)
        if self._cap.isOpened():
            self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, self._width)
            self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self._height)
            logger.info("Camera %s opened at %dx%d", self._source, self._width, self._height)
        else:
            logger.warning("Failed to open camera source: %s", self._source)

    async def read_frame(self) -> np.ndarray | None:
        if self._cap is None or not self._cap.isOpened():
            return None
        loop = asyncio.get_running_loop()
        ok, frame = await loop.run_in_executor(None, self._cap.read)
        if not ok:
            return None
        return frame

    async def close(self) -> None:
        if self._cap is not None:
            self._cap.release()
            self._cap = None

    def is_opened(self) -> bool:
        return self._cap is not None and self._cap.isOpened()


class RTSPSource(_CV2Source):
    def __init__(self, rtsp_url: str, reconnect_delay: float = 5.0,
                 width: int = 1280, height: int = 720):
        super().__init__(rtsp_url, reconnect_delay, width, height)


class WebcamSource(_CV2Source):
    def __init__(self, device_index: int = 0, reconnect_delay: float = 5.0,
                 width: int = 1280, height: int = 720):
        super().__init__(device_index, reconnect_delay, width, height)


def _parse_camera_url(url: str, width: int = 1280, height: int = 720) -> CameraSource:
    """Parse a camera URL like ``rtsp://...`` or ``webcam://0``."""
    if url.startswith("webcam://"):
        idx = int(url.replace("webcam://", ""))
        return WebcamSource(device_index=idx, width=width, height=height)
    return RTSPSource(rtsp_url=url, width=width, height=height)


FrameCallback = Callable[[str, np.ndarray], Coroutine[Any, Any, None]]


@dataclass
class CameraStream:
    camera_id: str
    room_id: str
    source: CameraSource
    purposes: list[str] = field(default_factory=list)
    _task: asyncio.Task | None = field(default=None, init=False, repr=False)


class CameraManager:
    """Manages multiple camera streams and pushes frames via a callback."""

    def __init__(self, frame_callback: FrameCallback, fps: float = 30.0,
                 width: int = 1280, height: int = 720):
        self._frame_callback = frame_callback
        self._interval = 1.0 / max(fps, 1.0)
        self._width = width
        self._height = height
        self._streams: dict[str, CameraStream] = {}
        self._running = False

    def add_camera(
        self,
        camera_id: str,
        room_id: str,
        url: str,
        purposes: list[str] | None = None,
    ) -> None:
        source = _parse_camera_url(url, self._width, self._height)
        self._streams[camera_id] = CameraStream(
            camera_id=camera_id,
            room_id=room_id,
            source=source,
            purposes=purposes or [],
        )

    async def start(self) -> None:
        self._running = True
        for stream in self._streams.values():
            await stream.source.open()
            stream._task = asyncio.create_task(
                self._read_loop(stream), name=f"cam-{stream.camera_id}"
            )
        logger.info("CameraManager started with %d streams", len(self._streams))

    async def stop(self) -> None:
        self._running = False
        for stream in self._streams.values():
            if stream._task and not stream._task.done():
                stream._task.cancel()
        await asyncio.gather(
            *(s._task for s in self._streams.values() if s._task),
            return_exceptions=True,
        )
        for stream in self._streams.values():
            await stream.source.close()
        logger.info("CameraManager stopped")

    async def _read_loop(self, stream: CameraStream) -> None:
        reconnect_delay = 5.0
        while self._running:
            try:
                if not stream.source.is_opened():
                    logger.info("Reconnecting camera %s ...", stream.camera_id)
                    await stream.source.open()
                    if not stream.source.is_opened():
                        await asyncio.sleep(reconnect_delay)
                        continue

                frame = await stream.source.read_frame()
                if frame is None:
                    await stream.source.close()
                    await asyncio.sleep(reconnect_delay)
                    continue

                await self._frame_callback(stream.camera_id, frame)
                await asyncio.sleep(0.001)

            except asyncio.CancelledError:
                break
            except Exception:
                logger.exception("Error in camera %s read loop", stream.camera_id)
                await asyncio.sleep(reconnect_delay)
