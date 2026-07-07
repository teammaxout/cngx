"""Optional local semantic embedding drift signal.

Opt-in via ``pip install cogscope[semantic]`` and ``--semantic`` on watch.
Uses sentence-transformers (all-MiniLM-L6-v2, ~80MB, CPU, downloaded once).

Addresses the honest limitation that heuristic regex metrics miss topical or
semantic shifts with similar surface reasoning patterns.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Optional

import numpy as np
from scipy import stats
from scipy.spatial.distance import jensenshannon

if TYPE_CHECKING:
    from cogscope.core.models import BehavioralFingerprint

DEFAULT_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
EMBEDDING_DIM = 384


@dataclass
class SemanticDriftResult:
    """Distributional distance between baseline and current embedding windows."""

    distance: float
    drift_detected: bool
    threshold: float
    n_baseline: int
    n_current: int
    summary: str


class SemanticDriftAnalyzer:
    """Lazy-loaded local embedder + Jensen-Shannon distance on PC1 bins."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL,
        distance_threshold: float = 0.25,
        n_bins: int = 30,
    ):
        self.model_name = model_name
        self.distance_threshold = distance_threshold
        self.n_bins = n_bins
        self._model = None
        self._baseline_embeddings: list[np.ndarray] = []

    def _load_model(self):
        if self._model is not None:
            return self._model
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise ImportError(
                "Semantic drift requires optional dependency. "
                "Install with: pip install cogscope[semantic]"
            ) from exc
        self._model = SentenceTransformer(self.model_name)
        return self._model

    def embed_text(self, text: str) -> np.ndarray:
        model = self._load_model()
        vec = model.encode(text or "", normalize_embeddings=True)
        return np.asarray(vec, dtype=np.float64)

    def add_baseline_text(self, text: str) -> None:
        self._baseline_embeddings.append(self.embed_text(text))

    def seed_from_fingerprints(
        self,
        fingerprints: list["BehavioralFingerprint"],
        trace_outputs: dict[str, str],
    ) -> None:
        """Seed baseline embedding store from historical trace outputs."""
        for fp in fingerprints:
            text = trace_outputs.get(fp.trace_id, "")
            if text.strip():
                self.add_baseline_text(text)

    def _pc1_project(self, embeddings: list[np.ndarray]) -> np.ndarray:
        if not embeddings:
            return np.array([])
        mat = np.vstack(embeddings)
        if mat.shape[0] == 1:
            return mat[:, 0]
        centered = mat - mat.mean(axis=0)
        u, s, _vt = np.linalg.svd(centered, full_matrices=False)
        pc1 = u[:, 0] * s[0]
        return pc1

    def _binned_distribution(self, values: np.ndarray) -> np.ndarray:
        if values.size == 0:
            return np.ones(self.n_bins) / self.n_bins
        hist, _edges = np.histogram(values, bins=self.n_bins, density=True)
        hist = hist + 1e-12
        return hist / hist.sum()

    def compare_current_text(self, text: str) -> SemanticDriftResult:
        """Compare one response embedding against baseline distribution."""
        if len(self._baseline_embeddings) < 3:
            return SemanticDriftResult(
                distance=0.0,
                drift_detected=False,
                threshold=self.distance_threshold,
                n_baseline=len(self._baseline_embeddings),
                n_current=1,
                summary="Insufficient baseline embeddings for semantic comparison.",
            )

        current_emb = self.embed_text(text)
        baseline_pc1 = self._pc1_project(self._baseline_embeddings)
        # Project current onto baseline PC1 direction for stability
        mat = np.vstack(self._baseline_embeddings)
        centered = mat - mat.mean(axis=0)
        u, s, _vt = np.linalg.svd(centered, full_matrices=False)
        direction = u[:, 0]
        current_scalar = float(np.dot(current_emb - mat.mean(axis=0), direction))

        all_baseline_scalars = baseline_pc1
        combined = np.concatenate([all_baseline_scalars, np.array([current_scalar])])

        lo, hi = combined.min(), combined.max()
        if hi - lo < 1e-9:
            return SemanticDriftResult(
                distance=0.0,
                drift_detected=False,
                threshold=self.distance_threshold,
                n_baseline=len(self._baseline_embeddings),
                n_current=1,
                summary="Degenerate semantic projection.",
            )

        baseline_bins = self._binned_distribution(all_baseline_scalars)
        current_bins = self._binned_distribution(np.array([current_scalar]))
        js_dist = float(jensenshannon(baseline_bins, current_bins))
        detected = js_dist >= self.distance_threshold

        return SemanticDriftResult(
            distance=js_dist,
            drift_detected=detected,
            threshold=self.distance_threshold,
            n_baseline=len(self._baseline_embeddings),
            n_current=1,
            summary=(
                f"Semantic JS distance {js_dist:.3f} "
                f"({'drift' if detected else 'stable'} vs threshold {self.distance_threshold})."
            ),
        )

    def wasserstein_pc1(
        self,
        current_texts: list[str],
    ) -> tuple[float, bool]:
        """Wasserstein distance on PC1 scalars (alternative corroboration)."""
        if len(self._baseline_embeddings) < 3 or not current_texts:
            return 0.0, False
        baseline_pc1 = self._pc1_project(self._baseline_embeddings)
        current_embs = [self.embed_text(t) for t in current_texts]
        mat = np.vstack(self._baseline_embeddings)
        centered = mat - mat.mean(axis=0)
        u, _s, _vt = np.linalg.svd(centered, full_matrices=False)
        direction = u[:, 0]
        current_scalars = [float(np.dot(e - mat.mean(axis=0), direction)) for e in current_embs]
        dist = float(stats.wasserstein_distance(baseline_pc1, current_scalars))
        detected = dist > np.std(baseline_pc1) * 2
        return dist, detected


_analyzer: Optional[SemanticDriftAnalyzer] = None


def get_semantic_analyzer(enabled: bool = False) -> Optional[SemanticDriftAnalyzer]:
    global _analyzer
    if not enabled:
        return None
    if _analyzer is None:
        _analyzer = SemanticDriftAnalyzer()
    return _analyzer
