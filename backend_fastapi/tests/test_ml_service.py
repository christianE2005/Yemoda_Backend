import numpy as np
import pytest

from types import SimpleNamespace


class DummyTask(SimpleNamespace):
    pass


def test_match_stories_simple(monkeypatch):
    # Prepare fake tasks
    tasks = [DummyTask(id_task=1, title="T1", description="desc1"), DummyTask(id_task=2, title="T2", description="desc2")]

    # Patch get_project_by_repo and get_active_tasks used inside match_stories
    def fake_get_project_by_repo(db, repo_full_name):
        return SimpleNamespace(id_project=123)

    def fake_get_active_tasks(db, project_id):
        return tasks

    # Patch both module locations to be robust regardless of import timing
    monkeypatch.setattr("app.services.task_service.get_project_by_repo", fake_get_project_by_repo, raising=False)
    monkeypatch.setattr("app.services.task_service.get_active_tasks", fake_get_active_tasks, raising=False)
    monkeypatch.setattr("app.services.ml_service.get_project_by_repo", fake_get_project_by_repo, raising=False)
    monkeypatch.setattr("app.services.ml_service.get_active_tasks", fake_get_active_tasks, raising=False)

    # Patch embed_texts to return deterministic vectors
    def fake_embed_texts(texts):
        # Return an embedding per text of dimension 2
        arr = []
        for t in texts:
            if "T1" in t or "desc1" in t:
                arr.append(np.array([1.0, 0.0]))
            elif "T2" in t or "desc2" in t:
                arr.append(np.array([0.0, 1.0]))
            else:
                # for diff chunks produce a vector closer to T1
                arr.append(np.array([0.9, 0.1]))
        return np.vstack(arr)

    monkeypatch.setattr("app.services.ml_service.embed_texts", fake_embed_texts)

    from app.services.ml_service import match_stories

    diff = "some change touching T1"
    matches = match_stories(None, "owner/repo", diff, top_k=None, min_sim=None, chunk_size_chars=1000, chunk_overlap=100)

    # Expect first match to be story 1 with high similarity
    assert matches[0]["story_id"] == 1
    assert matches[0]["similarity"] > 0.7


def test_chunking_short_diff(monkeypatch):
    # Ensure short diffs produce a single chunk and do not error
    tasks = [DummyTask(id_task=1, title="T1", description="desc1")]

    def fake_get_project_by_repo(db, repo_full_name):
        return SimpleNamespace(id_project=1)

    def fake_get_active_tasks(db, project_id):
        return tasks

    # Patch both module locations to be robust regardless of import timing
    monkeypatch.setattr("app.services.task_service.get_project_by_repo", fake_get_project_by_repo, raising=False)
    monkeypatch.setattr("app.services.task_service.get_active_tasks", fake_get_active_tasks, raising=False)
    monkeypatch.setattr("app.services.ml_service.get_project_by_repo", fake_get_project_by_repo, raising=False)
    monkeypatch.setattr("app.services.ml_service.get_active_tasks", fake_get_active_tasks, raising=False)

    def fake_embed_texts(texts):
        # Return simple embeddings
        return np.vstack([np.array([1.0, 0.0]) for _ in texts])

    monkeypatch.setattr("app.services.ml_service.embed_texts", fake_embed_texts)

    from app.services.ml_service import match_stories

    short_diff = "short diff"
    matches = match_stories(None, "owner/repo", short_diff, top_k=None, min_sim=None, chunk_size_chars=1000, chunk_overlap=900)

    assert len(matches) == 1
    assert matches[0]["story_id"] == 1


def test_story_embedding_cache_avoids_recompute(monkeypatch):
    # Prepare fake tasks
    tasks = [DummyTask(id_task=1, title="T1", description="desc1"), DummyTask(id_task=2, title="T2", description="desc2")]

    def fake_get_project_by_repo(db, repo_full_name):
        return SimpleNamespace(id_project=123)

    def fake_get_active_tasks(db, project_id):
        return tasks

    monkeypatch.setattr("app.services.task_service.get_project_by_repo", fake_get_project_by_repo, raising=False)
    monkeypatch.setattr("app.services.task_service.get_active_tasks", fake_get_active_tasks, raising=False)
    monkeypatch.setattr("app.services.ml_service.get_project_by_repo", fake_get_project_by_repo, raising=False)
    monkeypatch.setattr("app.services.ml_service.get_active_tasks", fake_get_active_tasks, raising=False)

    call_count = {"count": 0}

    def fake_embed_texts(texts):
        # Count calls; return simple 2-dim vectors
        call_count["count"] += 1
        arr = []
        for t in texts:
            if "T1" in t or "desc1" in t:
                arr.append(np.array([1.0, 0.0]))
            elif "T2" in t or "desc2" in t:
                arr.append(np.array([0.0, 1.0]))
            else:
                arr.append(np.array([0.5, 0.5]))
        return np.vstack(arr)

    monkeypatch.setattr("app.services.ml_service.embed_texts", fake_embed_texts)

    from app.services.ml_service import match_stories, clear_story_embedding_cache

    clear_story_embedding_cache()

    diff = "some change touching T1"
    # first call: should call embed_texts for tasks (1) and diff (1) => 2
    match_stories(None, "owner/repo", diff, top_k=None, min_sim=None, chunk_size_chars=1000, chunk_overlap=100)
    # second call: task embeddings come from cache; only diff is embedded => +1
    match_stories(None, "owner/repo", diff, top_k=None, min_sim=None, chunk_size_chars=1000, chunk_overlap=100)

    assert call_count["count"] == 3
