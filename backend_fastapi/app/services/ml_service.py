import hashlib
import logging
import os
import threading
from typing import Any, Dict, List, Optional
from collections import OrderedDict

import numpy as np
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


# Configuration via environment (make changable without editing code)
ML_EMBED_MODEL = os.getenv(
    "ML_EMBED_MODEL", "flax-sentence-embeddings/st-codesearch-distilroberta-base"
)
ML_TOP_K = int(os.getenv("ML_TOP_K", "3"))
ML_MIN_SIM = float(os.getenv("ML_MIN_SIM", "0.55"))
ML_HIGH_SIM = float(os.getenv("ML_HIGH_SIM", "0.75"))
ML_DISCARD_SIM = float(os.getenv("ML_DISCARD_SIM", "0.20"))
ML_CHUNK_SIZE = int(os.getenv("ML_CHUNK_SIZE_CHARS", "4000"))
ML_CHUNK_OVERLAP = int(os.getenv("ML_CHUNK_OVERLAP", "200"))
ML_STORY_EMBED_CACHE_MAX = int(os.getenv("ML_STORY_EMBED_CACHE_MAX", "500"))


# Thread-safe singleton model initialization
_MODEL_NAME = ML_EMBED_MODEL
_MODEL = None
_MODEL_LOCK = threading.Lock()


def _get_model():
    global _MODEL
    if _MODEL is None:
        with _MODEL_LOCK:
            if _MODEL is None:
                try:
                    from sentence_transformers import SentenceTransformer

                    _MODEL = SentenceTransformer(_MODEL_NAME)
                    logger.info("Loaded sentence-transformers model: %s", _MODEL_NAME)
                except Exception as exc:  # pragma: no cover - runtime environment dependent
                    logger.exception("Could not load sentence-transformers model: %s", exc)
                    raise
    return _MODEL


def embed_texts(texts: List[str]) -> np.ndarray:
    """Return numpy embeddings for a list of texts."""
    model = _get_model()
    embs = model.encode(texts, convert_to_numpy=True, show_progress_bar=False)
    return embs


def embed_text(text: str) -> np.ndarray:
    return embed_texts([text])[0]


def _cosine_sim(a: np.ndarray, b: np.ndarray) -> float:
    denom = (np.linalg.norm(a) * np.linalg.norm(b)) + 1e-10
    return float(np.dot(a, b) / denom)


# Simple thread-safe LRU-like in-memory cache for story embeddings to avoid recomputing.
# Key: story id -> (content_hash, embedding numpy array)
STORY_EMBED_CACHE = OrderedDict()
_CACHE_LOCK = threading.Lock()


def _content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def match_stories(
    db: Session,
    repo_full_name: str,
    diff: str,
    top_k: Optional[int] = None,
    min_sim: Optional[float] = None,
    chunk_size_chars: Optional[int] = None,
    chunk_overlap: Optional[int] = None,
) -> List[Dict[str, Any]]:
    """Match a push diff against active stories in the project.

    Returns a list of dicts: {story_id, title, description, similarity} sorted by similarity.

    - If `min_sim` is provided, results with similarity < min_sim will be filtered out.
    - If `top_k` is provided (int), the result will be truncated to that many items.
    """
    # Import here to avoid circular imports at package import time
    from app.services.task_service import get_project_by_repo, get_active_tasks

    project = get_project_by_repo(db, repo_full_name)
    if not project:
        logger.info("No project found for repo: %s", repo_full_name)
        return []

    tasks = get_active_tasks(db, project.id_project)
    if not tasks:
        logger.info("No active tasks for project %s", project.id_project)
        return []

    # Build textual representation for each task
    texts = [f"{t.title}. {t.description or ''}" for t in tasks]

    # Chunking parameters (allow overrides per-call)
    chunk_size = chunk_size_chars or ML_CHUNK_SIZE
    chunk_overlap = chunk_overlap if chunk_overlap is not None else ML_CHUNK_OVERLAP

    if chunk_size <= 0:
        raise ValueError("chunk_size_chars must be > 0")

    # Prepare task embeddings with caching
    pending_texts: List[str] = []
    pending_indices: List[int] = []
    task_embs_list: List[Optional[np.ndarray]] = [None] * len(tasks)

    for i, t in enumerate(tasks):
        content = texts[i]
        chash = _content_hash(content)
        with _CACHE_LOCK:
            cached = STORY_EMBED_CACHE.get(t.id_task)
            if cached and cached[0] == chash:
                task_embs_list[i] = cached[1]
                # mark as recently used
                try:
                    STORY_EMBED_CACHE.move_to_end(t.id_task)
                except Exception:
                    pass
                continue
        pending_texts.append(content)
        pending_indices.append(i)

    try:
        # Compute embeddings only for pending texts
        if pending_texts:
            new_embs = embed_texts(pending_texts)
            for idx, emb in zip(pending_indices, new_embs):
                task_embs_list[idx] = emb
                # cache by story id (thread-safe, bounded size)
                try:
                    with _CACHE_LOCK:
                        STORY_EMBED_CACHE[tasks[idx].id_task] = (_content_hash(texts[idx]), emb.copy())
                        STORY_EMBED_CACHE.move_to_end(tasks[idx].id_task)
                        # simple LRU eviction
                        if len(STORY_EMBED_CACHE) > ML_STORY_EMBED_CACHE_MAX:
                            STORY_EMBED_CACHE.popitem(last=False)
                except Exception as exc:
                    logger.debug("Failed to update STORY_EMBED_CACHE: %s", exc)

        # Stack to a numpy array
        task_embs = np.vstack([e for e in task_embs_list])
    except Exception as exc:  # pragma: no cover - user env dependent
        logger.error("Embedding failed for tasks: %s", exc)
        raise

    # Chunk the diff safely (handle short diffs)
    diff_chunks: List[str]
    diff_len = len(diff or "")
    if diff_len == 0:
        diff_chunks = []
    elif diff_len <= chunk_size:
        diff_chunks = [diff]
    else:
        step = max(1, chunk_size - chunk_overlap)
        diff_chunks = [diff[i : i + chunk_size] for i in range(0, diff_len, step)]

    try:
        diff_embs = embed_texts(diff_chunks) if diff_chunks else np.zeros((0, task_embs.shape[1]))
    except Exception as exc:  # pragma: no cover - user env dependent
        logger.error("Embedding failed for diff chunks: %s", exc)
        raise

    # Vectorized cosine similarity: normalize and compute dot product
    def _normalize(a: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(a, axis=1, keepdims=True) + 1e-10
        return a / norms

    task_norm = _normalize(task_embs)
    diff_norm = _normalize(diff_embs) if diff_embs.size else np.empty((0, task_norm.shape[1]))

    if diff_norm.size == 0:
        sims = [0.0 for _ in range(len(task_norm))]
    else:
        sims_matrix = np.dot(task_norm, diff_norm.T)
        sims = list(sims_matrix.max(axis=1))

    results: List[Dict[str, Any]] = []
    for t, s in zip(tasks, sims):
        results.append(
            {
                "story_id": t.id_task,
                "title": t.title,
                "description": t.description,
                "similarity": float(s),
            }
        )

    # sort
    results.sort(key=lambda r: r["similarity"], reverse=True)

    # optional filter by min_sim (discard threshold)
    if min_sim is not None:
        results = [r for r in results if r["similarity"] >= float(min_sim)]

    # limit by top_k if provided
    if top_k is not None:
        return results[:top_k]
    return results
