"""ReID feature extractor — extracts appearance embeddings from person crops.

Uses a lightweight OSNet model (via torchreid) to produce a 512-dim feature
vector for each cropped person image.  Features are L2-normalised so that
cosine similarity equals the dot product.
"""

from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import cv2
import numpy as np

logger = logging.getLogger(__name__)

_reid_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="reid")

FEATURE_DIM = 512


class ReIDExtractor:
    """Extracts appearance feature vectors from cropped person images."""

    def __init__(self, model_name: str = "osnet_x0_25", device: str = "auto"):
        self._model_name = model_name
        self._device_hint = device
        self._model: Any = None
        self._device: str = "cpu"
        self._input_size = (256, 128)  # H x W expected by OSNet

    async def load(self) -> None:
        loop = asyncio.get_running_loop()
        await loop.run_in_executor(_reid_pool, self._load_model)

    def _load_model(self) -> None:
        try:
            import torch
            from torchreid.utils import FeatureExtractor

            device = "cuda" if torch.cuda.is_available() else "cpu"
            if self._device_hint != "auto":
                device = self._device_hint
            self._device = device

            self._model = FeatureExtractor(
                model_name=self._model_name,
                model_path="",
                device=device,
            )
            logger.info(
                "ReID model loaded: %s on %s (feature_dim=%d)",
                self._model_name, device, FEATURE_DIM,
            )
        except ImportError:
            logger.warning(
                "torchreid not installed — ReID disabled. "
                "Install with: pip install torchreid"
            )
            self._model = None
        except Exception:
            logger.exception("Failed to load ReID model")
            self._model = None

    @property
    def available(self) -> bool:
        return self._model is not None

    async def extract(
        self, frame: np.ndarray, bboxes: list[list[int]]
    ) -> list[np.ndarray]:
        """Extract feature vectors for each person bbox in *frame*.

        Returns a list of L2-normalised feature vectors (one per bbox).
        If the model is not available, returns empty list.
        """
        if not self.available or not bboxes:
            return []
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(
            _reid_pool, self._extract_sync, frame, bboxes
        )

    def _extract_sync(
        self, frame: np.ndarray, bboxes: list[list[int]]
    ) -> list[np.ndarray]:
        import torch

        crops: list[np.ndarray] = []
        for bbox in bboxes:
            x1, y1, x2, y2 = bbox
            h, w = frame.shape[:2]
            x1, y1 = max(0, x1), max(0, y1)
            x2, y2 = min(w, x2), min(h, y2)
            if x2 <= x1 or y2 <= y1:
                crops.append(np.zeros((self._input_size[0], self._input_size[1], 3), dtype=np.uint8))
                continue
            crop = frame[y1:y2, x1:x2]
            crop = cv2.resize(crop, (self._input_size[1], self._input_size[0]))
            crops.append(crop)

        if not crops:
            return []

        features = self._model(crops)
        if isinstance(features, torch.Tensor):
            features = features.cpu().numpy()

        norms = np.linalg.norm(features, axis=1, keepdims=True)
        norms = np.clip(norms, 1e-8, None)
        features = features / norms

        return [features[i] for i in range(len(features))]

    async def unload(self) -> None:
        self._model = None
        logger.info("ReID model unloaded")
