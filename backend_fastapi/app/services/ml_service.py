import logging
from typing import Any, Dict, List

import numpy as np
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)


_MODEL_NAME = "all-MiniLM-L6-v2"
_MODEL = None


def _get_model():
    global _MODEL
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


def match_stories(
    db: Session, repo_full_name: str, diff: str, top_k: int = 3, min_sim: float = 0.55
) -> List[Dict[str, Any]]:
    """Match a push diff against active stories in the project.

    Returns a list of dicts: {story_id, title, description, similarity}
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

    texts = [f"{t.title}. {t.description or ''}" for t in tasks]

    # Process the full diff by chunking into batches so we don't lose information
    # chunk_size_chars controls how large each chunk is; overlap helps preserve context
    chunk_size_chars = 4000
    chunk_overlap = 200

    if chunk_size_chars <= 0:
        raise ValueError("chunk_size_chars must be > 0")
    step = max(1, chunk_size_chars - chunk_overlap)
    diff_chunks: List[str] = [
        diff[i : i + chunk_size_chars] for i in range(0, max(0, len(diff)), step)
    ]

    try:
        task_embs = embed_texts(texts)
        # embed all diff chunks at once
        diff_embs = embed_texts(diff_chunks) if diff_chunks else np.zeros((0, task_embs.shape[1]))
    except Exception as exc:  # pragma: no cover - user env dependent
        logger.error("Embedding failed: %s", exc)
        raise

    # Vectorized cosine similarity: normalize and compute dot product
    # task_embs: (n_tasks, dim), diff_embs: (n_chunks, dim)
    def _normalize(a: np.ndarray) -> np.ndarray:
        norms = np.linalg.norm(a, axis=1, keepdims=True) + 1e-10
        return a / norms

    task_norm = _normalize(task_embs)
    diff_norm = _normalize(diff_embs) if diff_embs.size else np.empty((0, task_norm.shape[1]))

    if diff_norm.size == 0:
        sims = [0.0 for _ in range(len(task_norm))]
    else:
        # sims_matrix shape: (n_tasks, n_chunks)
        sims_matrix = np.dot(task_norm, diff_norm.T)
        # For each task, take the maximum similarity across chunks
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

    # sort and filter
    results.sort(key=lambda r: r["similarity"], reverse=True)
    filtered = [r for r in results if r["similarity"] >= min_sim]
    return filtered[:top_k]
