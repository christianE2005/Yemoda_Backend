"""Tests for the delay-risk ML service.

Two layers:
  * Pure unit tests of the rule-based fallback and feature plumbing (no DB).
  * An end-to-end integration test (feature extraction -> training -> prediction) that
    needs a real PostgreSQL (the SQL uses FILTER / DATE_TRUNC, which SQLite lacks).
    It only runs when ML_TEST_DATABASE_URL is set, e.g.:

        ML_TEST_DATABASE_URL=postgresql+psycopg2://user@localhost:5432/mltest pytest tests/test_ml_service.py
"""
import os
from datetime import date, datetime, timedelta, timezone

import pytest

from app.services import ml_service

# ─────────────────────────────────────────────────────────────────────────────
# Unit tests — rule-based fallback (no DB required)
# ─────────────────────────────────────────────────────────────────────────────

def _features(**overrides) -> dict:
    base = {
        "velocity_last_week": 5.0,
        "velocity_avg": 7.0,
        "velocity_trend": 0.0,
        "sprint_consistency": 1.0,
        "points_remaining": 10.0,
        "days_remaining": 30.0,
        "completion_rate": 0.5,
        "tasks_in_progress": 4.0,
    }
    base.update(overrides)
    return base


class TestRuleBasedPrediction:
    def test_on_time_project_is_not_at_risk(self):
        # 10 points at 1/day -> 10 days needed vs 30 remaining.
        result = ml_service._rule_based_prediction(_features(velocity_avg=7.0))
        assert result["at_risk"] is False
        assert result["days_delay_estimate"] == 0
        assert result["model_used"] == "rule_based_burndown"
        assert result["confidence"] is None

    def test_late_project_is_at_risk(self):
        # 100 points at 1/day -> 100 days needed vs 30 remaining -> ~70 days late.
        result = ml_service._rule_based_prediction(
            _features(points_remaining=100.0, velocity_avg=7.0)
        )
        assert result["at_risk"] is True
        assert result["days_delay_estimate"] == 70

    def test_grace_band_swallows_tiny_delays(self):
        # 31.5 days needed vs 30 remaining -> 1.5 days "late": inside the model's error bar.
        result = ml_service._rule_based_prediction(
            _features(points_remaining=31.5, velocity_avg=7.0)
        )
        assert result["at_risk"] is False

    def test_zero_velocity_means_at_risk_with_no_end_date(self):
        result = ml_service._rule_based_prediction(
            _features(velocity_avg=0.0, points_remaining=5.0)
        )
        assert result["at_risk"] is True
        assert result["predicted_end_date"] is None
        assert result["days_delay_estimate"] is None

    def test_tiny_velocity_does_not_overflow_date_range(self):
        # Pre-cap, this projected ~70M days and blew past date.max in date.fromordinal().
        result = ml_service._rule_based_prediction(
            _features(velocity_avg=0.001, points_remaining=10_000.0)
        )
        assert result["at_risk"] is True
        assert result["predicted_end_date"] is not None  # capped projection, valid date


class TestFeatureArray:
    def test_shape_and_order(self):
        arr = ml_service._features_to_array(_features())
        assert arr.shape == (1, 8)
        assert arr[0][0] == 5.0  # velocity_last_week first
        assert arr[0][7] == 4.0  # tasks_in_progress last


# ─────────────────────────────────────────────────────────────────────────────
# Integration — full pipeline against PostgreSQL (opt-in via ML_TEST_DATABASE_URL)
# ─────────────────────────────────────────────────────────────────────────────

_PG_URL = os.getenv("ML_TEST_DATABASE_URL", "")

_SCHEMA = """
DROP TABLE IF EXISTS task CASCADE;
DROP TABLE IF EXISTS project CASCADE;
CREATE TABLE project (
    id_project BIGSERIAL PRIMARY KEY,
    name VARCHAR(150) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    end_date DATE,
    status VARCHAR(50)
);
CREATE TABLE task (
    id_task BIGSERIAL PRIMARY KEY,
    id_project BIGINT NOT NULL REFERENCES project(id_project),
    id_parent_task BIGINT REFERENCES task(id_task),
    title VARCHAR(200) NOT NULL DEFAULT 't',
    created_at TIMESTAMPTZ NOT NULL,
    completed_at TIMESTAMPTZ,
    scrum_number INTEGER
);
"""


def _ts(d: date) -> datetime:
    return datetime.combine(d, datetime.min.time()).replace(tzinfo=timezone.utc)


@pytest.fixture()
def pg_db(monkeypatch, tmp_path):
    from sqlalchemy import create_engine, text
    from sqlalchemy.orm import sessionmaker

    # Keep trained artifacts out of the repo tree.
    monkeypatch.setattr(ml_service, "MODEL_DIR", tmp_path)
    monkeypatch.setattr(ml_service, "MODEL_PATH", tmp_path / "elasticnet_risk.joblib")
    monkeypatch.setattr(ml_service, "SCALER_PATH", tmp_path / "scaler.joblib")
    monkeypatch.setattr(ml_service, "_MODEL_CACHE", None)
    monkeypatch.setattr(ml_service, "_MODEL_CACHE_KEY", None)

    engine = create_engine(_PG_URL, future=True)
    session = sessionmaker(bind=engine, future=True)()
    session.execute(text(_SCHEMA))
    session.commit()
    yield session
    session.close()
    engine.dispose()


def _seed_finished_projects(db, n: int = 4) -> None:
    from sqlalchemy import text

    today = date.today()
    for i in range(n):
        start = today - timedelta(days=180 + i * 10)
        planned_end = start + timedelta(days=90)
        actual_end = planned_end + timedelta(days=(-5, 3, 12, 0, 25)[i % 5])
        db.execute(
            text("INSERT INTO project (name, created_at, end_date, status) VALUES (:n, :c, :e, 'Finished')"),
            {"n": f"hist-{i}", "c": _ts(start), "e": planned_end},
        )
        pid = db.execute(text("SELECT max(id_project) FROM project")).scalar()
        for j in range(20):
            created = start + timedelta(days=2 + j * 3)
            completed = min(actual_end, created + timedelta(days=10 + (j % 5) * 4))
            db.execute(
                text("INSERT INTO task (id_project, created_at, completed_at, scrum_number) VALUES (:p, :c, :d, :s)"),
                {"p": pid, "c": _ts(created), "d": _ts(completed), "s": 1 + (j % 5)},
            )
    db.commit()


@pytest.mark.skipif(not _PG_URL, reason="ML_TEST_DATABASE_URL not set (needs PostgreSQL)")
class TestPipelineIntegration:
    def test_trains_on_finished_projects_and_predicts(self, pg_db):
        from sqlalchemy import text

        _seed_finished_projects(pg_db)

        result = ml_service.train_model(pg_db)
        assert result["status"] == "trained"
        assert result["samples"] >= ml_service.MIN_TRAINING_PROJECTS
        assert "cv_mse" in result

        # Active project to predict on.
        today = date.today()
        pg_db.execute(
            text("INSERT INTO project (name, created_at, end_date, status) VALUES ('act', :c, :e, 'In Progress')"),
            {"c": _ts(today - timedelta(days=60)), "e": today + timedelta(days=30)},
        )
        active_id = pg_db.execute(text("SELECT max(id_project) FROM project")).scalar()
        for j in range(10):
            created = today - timedelta(days=55 - j * 4)
            completed = _ts(created + timedelta(days=6)) if j < 6 else None
            pg_db.execute(
                text("INSERT INTO task (id_project, created_at, completed_at, scrum_number) VALUES (:p, :c, :d, 2)"),
                {"p": active_id, "c": _ts(created), "d": completed},
            )
        pg_db.commit()

        pred = ml_service.predict_risk(pg_db, active_id)
        assert pred is not None
        assert pred["model_used"] == "elasticnet"
        assert isinstance(pred["at_risk"], bool)
        assert 0.0 <= pred["confidence"] <= 1.0

    def test_does_not_train_on_cancelled_projects(self, pg_db):
        from sqlalchemy import text

        _seed_finished_projects(pg_db, n=4)
        pg_db.execute(text("UPDATE project SET status = 'Cancelled'"))
        pg_db.commit()
        result = ml_service.train_model(pg_db)
        assert result["status"] == "skipped"

    def test_project_without_end_date_returns_none(self, pg_db):
        from sqlalchemy import text

        pg_db.execute(
            text("INSERT INTO project (name, created_at, end_date, status) VALUES ('nodl', :c, NULL, 'In Progress')"),
            {"c": _ts(date.today() - timedelta(days=10))},
        )
        pid = pg_db.execute(text("SELECT max(id_project) FROM project")).scalar()
        pg_db.execute(
            text("INSERT INTO task (id_project, created_at) VALUES (:p, :c)"),
            {"p": pid, "c": _ts(date.today() - timedelta(days=5))},
        )
        pg_db.commit()
        assert ml_service.predict_risk(pg_db, pid) is None

    def test_historical_snapshot_does_not_leak_future_completions(self, pg_db):
        from sqlalchemy import text

        today = date.today()
        start = today - timedelta(days=100)
        pg_db.execute(
            text("INSERT INTO project (name, created_at, end_date, status) VALUES ('leak', :c, :e, 'Finished')"),
            {"c": _ts(start), "e": start + timedelta(days=80)},
        )
        pid = pg_db.execute(text("SELECT max(id_project) FROM project")).scalar()
        snapshot = start + timedelta(days=40)
        # Created before the snapshot, completed after it -> still OPEN at snapshot time.
        pg_db.execute(
            text("INSERT INTO task (id_project, created_at, completed_at, scrum_number) VALUES (:p, :c, :d, 3)"),
            {"p": pid, "c": _ts(start + timedelta(days=5)), "d": _ts(snapshot + timedelta(days=20))},
        )
        # Completed before the snapshot -> counts.
        pg_db.execute(
            text("INSERT INTO task (id_project, created_at, completed_at, scrum_number) VALUES (:p, :c, :d, 3)"),
            {"p": pid, "c": _ts(start + timedelta(days=5)), "d": _ts(start + timedelta(days=15))},
        )
        pg_db.commit()

        feats = ml_service._extract_features(pg_db, pid, reference_date=snapshot)
        assert feats is not None
        assert feats["completion_rate"] == pytest.approx(0.5)
        assert feats["tasks_in_progress"] == 1.0
        assert feats["points_remaining"] == 3.0
