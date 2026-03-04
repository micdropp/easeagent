from __future__ import annotations

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

import numpy as np

logger = logging.getLogger(__name__)

_face_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="face")

FACES_DIR = Path("data/faces")


class FaceRecognizer:
    """InsightFace-based face recognition.

    Embedding vectors of registered employees are stored as ``.npy`` files
    under ``data/faces/<employee_id>.npy``.
    """

    def __init__(
        self,
        model_name: str = "buffalo_l",
        threshold: float = 0.6,
    ):
        self._model_name = model_name
        self._threshold = threshold
        self._app: Any = None
        self._known_faces: dict[str, np.ndarray] = {}

    async def load(self) -> None:
        FACES_DIR.mkdir(parents=True, exist_ok=True)
        loop = asyncio.get_running_loop()
        self._app = await loop.run_in_executor(_face_pool, self._init_model)
        self._load_known_faces()
        logger.info(
            "InsightFace loaded (model=%s), %d registered faces",
            self._model_name,
            len(self._known_faces),
        )

    def _init_model(self) -> Any:
        import insightface

        app = insightface.app.FaceAnalysis(
            name=self._model_name,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        app.prepare(ctx_id=0, det_size=(960, 960))
        return app

    def _load_known_faces(self) -> None:
        self._known_faces.clear()
        for npy_path in FACES_DIR.glob("*.npy"):
            employee_id = npy_path.stem
            arr = np.load(str(npy_path))
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            self._known_faces[employee_id] = arr
        logger.info("Loaded %d face embeddings from disk", len(self._known_faces))

    def reload_faces(self) -> None:
        """Reload face embeddings from disk (call after registering a new face)."""
        self._load_known_faces()

    async def recognize(
        self, frame: np.ndarray, bboxes: list[dict] | None = None
    ) -> list[dict]:
        """Detect faces in *frame* and match against known embeddings.

        Returns a list of dicts: ``{employee_id, confidence, bbox}``.
        Unmatched faces are returned with ``employee_id="unknown"``.
        """
        if self._app is None:
            await self.load()

        loop = asyncio.get_running_loop()
        faces = await loop.run_in_executor(_face_pool, self._app.get, frame)

        results: list[dict] = []
        for face in faces:
            embedding = face.normed_embedding
            best_id, best_sim = self._match(embedding)
            bbox = face.bbox.astype(int).tolist()
            if best_id is not None:
                results.append(
                    {
                        "employee_id": best_id,
                        "confidence": round(best_sim, 4),
                        "bbox": bbox,
                    }
                )
            else:
                results.append(
                    {
                        "employee_id": "unknown",
                        "confidence": round(best_sim, 4),
                        "bbox": bbox,
                    }
                )
        return results

    def _match(self, embedding: np.ndarray) -> tuple[str | None, float]:
        best_id: str | None = None
        best_sim = -1.0
        for emp_id, known_embs in self._known_faces.items():
            sims = known_embs @ embedding
            max_sim = float(sims.max())
            if max_sim > best_sim:
                best_sim = max_sim
                best_id = emp_id
        if best_sim >= self._threshold:
            return best_id, best_sim
        return None, best_sim

    async def register_face(self, employee_id: str, frame: np.ndarray) -> bool:
        """Extract face embedding from *frame* and append for *employee_id*.

        Multiple photos can be registered per employee (different angles).
        Returns ``True`` if a face was found and registered, ``False`` otherwise.
        """
        if self._app is None:
            await self.load()

        loop = asyncio.get_running_loop()
        faces = await loop.run_in_executor(_face_pool, self._app.get, frame)

        if not faces:
            logger.warning("No face detected for employee %s", employee_id)
            return False

        face = max(faces, key=lambda f: (f.bbox[2] - f.bbox[0]) * (f.bbox[3] - f.bbox[1]))
        embedding = face.normed_embedding.reshape(1, -1)

        FACES_DIR.mkdir(parents=True, exist_ok=True)
        save_path = FACES_DIR / f"{employee_id}.npy"

        existing = self._known_faces.get(employee_id)
        if existing is not None:
            combined = np.vstack([existing, embedding])
        else:
            combined = embedding

        np.save(str(save_path), combined)
        self._known_faces[employee_id] = combined
        logger.info(
            "Registered face for employee %s (%d embeddings) -> %s",
            employee_id, combined.shape[0], save_path,
        )
        return True

    async def unload(self) -> None:
        self._app = None
        self._known_faces.clear()
        logger.info("InsightFace model unloaded")
