"""Multi-modal identity fusion — combines signals from multiple sources.

Currently fuses face recognition and ReID appearance matching.
Extension points are provided for BLE badge, door access badge, and
gait recognition signals.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


@dataclass
class IdentitySignal:
    """A single identity observation from one sensor modality."""

    source: str  # "face", "reid", "ble", "badge", "gait"
    employee_id: str
    confidence: float  # 0.0 – 1.0, raw sensor confidence
    weight: float = 1.0  # source-level trust weight


# Default trust weights per source (higher = more trusted)
DEFAULT_WEIGHTS: dict[str, float] = {
    "badge": 0.99,
    "ble": 0.95,
    "face": 0.85,
    "reid": 0.70,
    "gait": 0.50,
}

# Minimum fused score to accept an identity
DEFAULT_ACCEPT_THRESHOLD = 0.40


@dataclass
class FusedIdentity:
    """Result of fusing multiple identity signals."""

    employee_id: str
    fused_score: float
    signals: list[IdentitySignal] = field(default_factory=list)
    accepted: bool = False


class IdentityFusion:
    """Weighted voting across multiple identity modalities.

    Usage
    -----
    >>> fusion = IdentityFusion()
    >>> signals = [
    ...     IdentitySignal("face", "zhangsan", 0.82),
    ...     IdentitySignal("reid", "zhangsan", 0.65),
    ... ]
    >>> result = fusion.fuse(signals)
    >>> result.employee_id
    'zhangsan'
    """

    def __init__(
        self,
        weights: dict[str, float] | None = None,
        accept_threshold: float = DEFAULT_ACCEPT_THRESHOLD,
    ):
        self._weights = weights or DEFAULT_WEIGHTS
        self._threshold = accept_threshold

    def fuse(self, signals: list[IdentitySignal]) -> FusedIdentity | None:
        """Fuse multiple signals and return the best identity (or None)."""
        if not signals:
            return None

        for sig in signals:
            if sig.weight <= 0:
                sig.weight = self._weights.get(sig.source, 0.5)

        # Group signals by employee_id
        candidates: dict[str, list[IdentitySignal]] = {}
        for sig in signals:
            candidates.setdefault(sig.employee_id, []).append(sig)

        best: FusedIdentity | None = None

        for emp_id, sigs in candidates.items():
            total_weight = sum(s.weight for s in sigs)
            if total_weight == 0:
                continue
            weighted_sum = sum(s.confidence * s.weight for s in sigs)
            fused_score = weighted_sum / total_weight

            result = FusedIdentity(
                employee_id=emp_id,
                fused_score=fused_score,
                signals=sigs,
                accepted=fused_score >= self._threshold,
            )

            if best is None or fused_score > best.fused_score:
                best = result

        if best is not None and not best.accepted:
            logger.debug(
                "Fusion: best candidate %s score %.3f below threshold %.3f",
                best.employee_id, best.fused_score, self._threshold,
            )
            return None

        return best

    def fuse_for_track(
        self,
        face_id: str | None = None,
        face_confidence: float = 0.0,
        reid_id: str | None = None,
        reid_confidence: float = 0.0,
        ble_id: str | None = None,
        badge_id: str | None = None,
    ) -> FusedIdentity | None:
        """Convenience method to fuse common signal types."""
        signals: list[IdentitySignal] = []

        if face_id and face_id != "unknown":
            signals.append(IdentitySignal(
                source="face",
                employee_id=face_id,
                confidence=face_confidence,
                weight=self._weights.get("face", 0.85),
            ))

        if reid_id and reid_id != "unknown":
            signals.append(IdentitySignal(
                source="reid",
                employee_id=reid_id,
                confidence=reid_confidence,
                weight=self._weights.get("reid", 0.70),
            ))

        if ble_id:
            signals.append(IdentitySignal(
                source="ble",
                employee_id=ble_id,
                confidence=0.95,
                weight=self._weights.get("ble", 0.95),
            ))

        if badge_id:
            signals.append(IdentitySignal(
                source="badge",
                employee_id=badge_id,
                confidence=0.99,
                weight=self._weights.get("badge", 0.99),
            ))

        return self.fuse(signals)
