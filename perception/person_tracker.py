from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np


@dataclass
class TrackedPerson:
    """A person being tracked across frames."""

    track_id: int
    bbox: list[int]
    last_seen: float = field(default_factory=time.monotonic)
    employee_id: str | None = None
    confidence: float = 0.0
    appearance: np.ndarray | None = field(default=None, repr=False)

    def update_bbox(self, bbox: list[int]) -> None:
        self.bbox = bbox
        self.last_seen = time.monotonic()

    def bind_identity(self, employee_id: str, confidence: float) -> None:
        if self.employee_id is None or confidence > self.confidence:
            self.employee_id = employee_id
            self.confidence = confidence

    def set_appearance(self, feature: np.ndarray) -> None:
        self.appearance = feature


def _iou(a: list[int], b: list[int]) -> float:
    """Intersection-over-Union for two [x1, y1, x2, y2] boxes."""
    x1 = max(a[0], b[0])
    y1 = max(a[1], b[1])
    x2 = min(a[2], b[2])
    y2 = min(a[3], b[3])
    inter = max(0, x2 - x1) * max(0, y2 - y1)
    if inter == 0:
        return 0.0
    area_a = (a[2] - a[0]) * (a[3] - a[1])
    area_b = (b[2] - b[0]) * (b[3] - b[1])
    return inter / (area_a + area_b - inter)


def _center_inside(face_bbox: list[int], person_bbox: list[int]) -> bool:
    """Check if the center of *face_bbox* falls inside *person_bbox*."""
    cx = (face_bbox[0] + face_bbox[2]) / 2
    cy = (face_bbox[1] + face_bbox[3]) / 2
    return (
        person_bbox[0] <= cx <= person_bbox[2]
        and person_bbox[1] <= cy <= person_bbox[3]
    )


class PersonTracker:
    """Lightweight IoU-based multi-object tracker with ReID gallery.

    Assigns persistent ``track_id`` values to person detections across frames
    using greedy IoU matching.  Tracks are kept alive for *max_missing_seconds*
    after the last matched detection to tolerate brief occlusions.

    When a track with a known identity is lost, it is stored in the
    *lost gallery* for cross-camera or re-entry matching via appearance
    features (ReID).
    """

    def __init__(
        self,
        iou_threshold: float = 0.25,
        max_missing_seconds: float = 10.0,
        gallery_ttl: float = 600.0,
        reid_threshold: float = 0.55,
    ):
        self._iou_threshold = iou_threshold
        self._max_missing_seconds = max_missing_seconds
        self._gallery_ttl = gallery_ttl
        self._reid_threshold = reid_threshold
        self._next_id = 1
        self._tracks: dict[int, TrackedPerson] = {}
        self._lost_gallery: list[TrackedPerson] = []

    @property
    def active_tracks(self) -> list[TrackedPerson]:
        return list(self._tracks.values())

    def update(
        self, detections: list[dict]
    ) -> tuple[list[TrackedPerson], list[TrackedPerson]]:
        """Feed new YOLO detections and return (active, lost) tracks.

        *detections* is a list of dicts with at least a ``bbox`` key
        ([x1, y1, x2, y2]).

        Returns
        -------
        active : list[TrackedPerson]
            Currently tracked persons (matched + newly created).
        lost : list[TrackedPerson]
            Tracks removed this frame (person left the scene).
        """
        now = time.monotonic()
        det_bboxes = [d["bbox"] for d in detections]

        matched_track_ids: set[int] = set()
        matched_det_idxs: set[int] = set()

        # Build IoU matrix and do greedy matching (highest IoU first)
        pairs: list[tuple[float, int, int]] = []
        track_items = list(self._tracks.items())
        for ti, (tid, track) in enumerate(track_items):
            for di, det_bbox in enumerate(det_bboxes):
                score = _iou(track.bbox, det_bbox)
                if score >= self._iou_threshold:
                    pairs.append((score, ti, di))

        pairs.sort(key=lambda x: x[0], reverse=True)

        for score, ti, di in pairs:
            tid = track_items[ti][0]
            if tid in matched_track_ids or di in matched_det_idxs:
                continue
            self._tracks[tid].update_bbox(det_bboxes[di])
            matched_track_ids.add(tid)
            matched_det_idxs.add(di)

        # Create new tracks for unmatched detections
        for di, det_bbox in enumerate(det_bboxes):
            if di not in matched_det_idxs:
                new_track = TrackedPerson(
                    track_id=self._next_id, bbox=det_bbox
                )
                self._tracks[self._next_id] = new_track
                self._next_id += 1

        # Expire tracks not seen for too long
        lost: list[TrackedPerson] = []
        expired_ids = [
            tid
            for tid, t in self._tracks.items()
            if now - t.last_seen > self._max_missing_seconds
        ]
        for tid in expired_ids:
            track = self._tracks.pop(tid)
            lost.append(track)
            if track.employee_id is not None and track.appearance is not None:
                self._lost_gallery.append(track)

        # Prune stale gallery entries
        cutoff = now - self._gallery_ttl
        self._lost_gallery = [
            t for t in self._lost_gallery if t.last_seen > cutoff
        ]

        return self.active_tracks, lost

    def bind_faces_to_tracks(self, faces: list[dict]) -> None:
        """Associate recognised face results with the closest tracked person.

        For each face whose ``employee_id`` is not ``"unknown"``, find the
        tracked person whose bbox contains the face center and bind the
        identity.
        """
        for face in faces:
            emp_id = face.get("employee_id")
            if emp_id is None or emp_id == "unknown":
                continue
            face_bbox = face["bbox"]
            best_track: TrackedPerson | None = None
            best_iou = -1.0
            for track in self._tracks.values():
                if _center_inside(face_bbox, track.bbox):
                    iou_val = _iou(face_bbox, track.bbox)
                    if iou_val > best_iou:
                        best_iou = iou_val
                        best_track = track
            if best_track is not None:
                best_track.bind_identity(emp_id, face.get("confidence", 0.0))

    def get_track_for_bbox(self, bbox: list[int]) -> TrackedPerson | None:
        """Find the track whose bbox best overlaps with *bbox*."""
        best: TrackedPerson | None = None
        best_iou = self._iou_threshold
        for track in self._tracks.values():
            score = _iou(track.bbox, bbox)
            if score > best_iou:
                best_iou = score
                best = track
        return best

    # ------------------------------------------------------------------
    # ReID appearance matching
    # ------------------------------------------------------------------

    def match_by_appearance(
        self, feature: np.ndarray
    ) -> TrackedPerson | None:
        """Search the lost gallery for a matching identity via cosine similarity."""
        if not self._lost_gallery or feature is None:
            return None

        best_match: TrackedPerson | None = None
        best_score = self._reid_threshold

        for lost_track in self._lost_gallery:
            if lost_track.appearance is None:
                continue
            score = float(np.dot(feature, lost_track.appearance))
            if score > best_score:
                best_score = score
                best_match = lost_track

        return best_match

    def match_across_galleries(
        self, feature: np.ndarray, galleries: list["PersonTracker"]
    ) -> TrackedPerson | None:
        """Search lost galleries from *other* trackers (cross-camera ReID)."""
        best_match: TrackedPerson | None = None
        best_score = self._reid_threshold

        for other in galleries:
            if other is self:
                continue
            for lost_track in other._lost_gallery:
                if lost_track.appearance is None:
                    continue
                score = float(np.dot(feature, lost_track.appearance))
                if score > best_score:
                    best_score = score
                    best_match = lost_track

        return best_match

    @property
    def lost_gallery(self) -> list[TrackedPerson]:
        return list(self._lost_gallery)
