"""
Risk prediction ML service.

Uses ElasticNet regression (L1+L2 regularization) to handle many correlated
features with limited historical data. When not enough completed projects
exist to train the model, falls back to a deterministic burndown rule.

Features used:
  - velocity_last_week     scrum points completed in the last 7 days
  - velocity_avg           avg scrum points per week across the project's history
  - velocity_trend         week-over-week velocity change rate
  - sprint_consistency     std dev of weekly velocities (lower = more predictable)
  - points_remaining       total scrum points still open
  - days_remaining         calendar days until project end_date
  - completion_rate        0-1, fraction of tasks completed
  - tasks_in_progress      count of open tasks

scrum_number is a future column on the task table. It's read with COALESCE so
that NULL values default to 1 point per task, keeping everything working until
the column is populated.
"""

import logging
import os
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import joblib
import numpy as np
from sklearn.linear_model import ElasticNetCV
from sklearn.preprocessing import StandardScaler
from sqlalchemy import text
from sqlalchemy.orm import Session

logger = logging.getLogger(__name__)

MODEL_DIR = Path(__file__).parent.parent / "ml_models"
MODEL_PATH = MODEL_DIR / "elasticnet_risk.joblib"
SCALER_PATH = MODEL_DIR / "scaler.joblib"

MIN_TRAINING_PROJECTS = 3

# Project lifecycle statuses (Django's Project.STATUS_CHOICES) that count as "completed" for
# training. Cancelled/Retired are excluded on purpose: their real end date doesn't reflect a
# delivery delay, so they would only add label noise.
_COMPLETED_PROJECT_STATUSES: tuple[str, ...] = ("Finished",)

# Predicted delays within this many days of the deadline are treated as on-track: a regression
# output of "+1 day" is well inside the model's error bar and must not raise an alarm.
_AT_RISK_GRACE_DAYS = 2.0

# Upper bound for the burndown projection (10 years). A near-zero velocity with many points
# remaining would otherwise overflow date.fromordinal() and 500 the endpoint.
_MAX_PROJECTED_DAYS = 3650

# In-process cache of the loaded (model, scaler) keyed by the files' modification times, so we
# don't joblib.load() from disk on every prediction. Invalidated automatically when the mtimes
# change (e.g. after train_model rewrites the files) and explicitly via train_model().
_MODEL_CACHE: tuple | None = None
_MODEL_CACHE_KEY: tuple[float, float] | None = None


# ─────────────────────────────────────────────────────────────────────────────
# Feature extraction
# ─────────────────────────────────────────────────────────────────────────────

def _extract_features(db: Session, project_id: int, reference_date: date | None = None) -> dict | None:
    """
    Compute the feature vector for a project.

    reference_date: the date from which to compute velocity windows.
    Defaults to today (real-time prediction). For training on historical
    projects, pass the project's actual end date so features are computed
    as-of that point in time.
    """
    ref = reference_date or date.today()
    ref_ts = datetime.combine(ref, datetime.min.time()).replace(tzinfo=timezone.utc)

    # ── Project deadline & creation date ─────────────────────────────────────
    # Both columns come from the same single-row lookup, so fetch them together
    # instead of issuing a second SELECT for created_at later.
    project_row = db.execute(
        text("SELECT end_date, created_at FROM project WHERE id_project = :pid"),
        {"pid": project_id},
    ).fetchone()

    if project_row is None:
        return None

    end_date = project_row[0]
    project_created_at = project_row[1]
    if end_date is None:
        # Without a deadline there is nothing to predict against: days_remaining would be
        # meaningless (a 0 here read as "deadline is today" and flagged healthy projects as
        # at-risk). Callers surface this as a 404 with a clear message.
        return None
    days_remaining = (end_date - ref).days

    # ── Task aggregates ───────────────────────────────────────────────────────
    # COALESCE(scrum_number, 1): defaults to 1 point when column is NULL / not yet added.
    # Only LEAF tasks (no subtasks) contribute points — a parent task's points are the
    # sum of its leaves, so counting both would double-count. The NOT EXISTS clause
    # restricts the point sums to leaves while task COUNTs still cover everything.
    # Every "completed" filter is bounded by completed_at <= :ref_ts: when training on a
    # historical snapshot, a task finished AFTER the snapshot date was still open at that
    # point in time — counting it leaked future information into the training features.
    tasks_row = db.execute(
        text("""
            SELECT
                COUNT(*)                                                        AS total_tasks,
                COUNT(*) FILTER (WHERE completed_at IS NOT NULL
                                   AND completed_at <= :ref_ts)                 AS completed_tasks,
                COALESCE(SUM(COALESCE(scrum_number, 1)) FILTER (
                    WHERE NOT EXISTS (
                        SELECT 1 FROM task c WHERE c.id_parent_task = task.id_task
                    )), 0)                                                      AS total_points,
                COALESCE(SUM(COALESCE(scrum_number, 1)) FILTER (
                    WHERE completed_at IS NOT NULL
                      AND completed_at <= :ref_ts
                      AND NOT EXISTS (
                        SELECT 1 FROM task c WHERE c.id_parent_task = task.id_task
                    )), 0)                                                      AS completed_points
            FROM task
            WHERE id_project = :pid
              AND created_at <= :ref_ts
        """),
        {"pid": project_id, "ref_ts": ref_ts},
    ).fetchone()

    if tasks_row is None or tasks_row[0] == 0:
        return None

    total_tasks, completed_tasks, total_points, completed_points = tasks_row
    points_remaining = float(total_points - completed_points)
    completion_rate = float(completed_points / total_points) if total_points > 0 else 0.0
    tasks_in_progress = int(total_tasks - completed_tasks)

    # ── Weekly velocity windows ───────────────────────────────────────────────
    velocity_row = db.execute(
        text("""
            SELECT
                COALESCE(SUM(COALESCE(scrum_number, 1))
                    FILTER (WHERE completed_at >= :week1_start
                               AND completed_at < :ref_ts), 0)    AS v_last_week,
                COALESCE(SUM(COALESCE(scrum_number, 1))
                    FILTER (WHERE completed_at >= :week2_start
                               AND completed_at < :week1_start), 0) AS v_prev_week
            FROM task
            WHERE id_project = :pid
              AND completed_at IS NOT NULL
              AND NOT EXISTS (
                  SELECT 1 FROM task c WHERE c.id_parent_task = task.id_task
              )
        """),
        {
            "pid": project_id,
            "ref_ts": ref_ts,
            "week1_start": datetime.combine(
                date.fromordinal(ref.toordinal() - 7),
                datetime.min.time(),
            ).replace(tzinfo=timezone.utc),
            "week2_start": datetime.combine(
                date.fromordinal(ref.toordinal() - 14),
                datetime.min.time(),
            ).replace(tzinfo=timezone.utc),
        },
    ).fetchone()

    v_last_week = float(velocity_row[0])
    v_prev_week = float(velocity_row[1])

    # All-time average weekly velocity. created_at was fetched above. Guard for
    # NULL and for either a datetime (has .date()) or a plain date value, so a
    # missing/odd creation timestamp falls back to a 1-week age instead of raising.
    created_date = None
    if project_created_at is not None:
        created_date = (
            project_created_at.date()
            if isinstance(project_created_at, datetime)
            else project_created_at
        )
    project_age_weeks = max(
        1,
        (ref - created_date).days / 7 if created_date is not None else 1,
    )
    velocity_avg = float(completed_points) / project_age_weeks

    # Trend: relative change from prev week to last week
    if v_prev_week > 0:
        velocity_trend = (v_last_week - v_prev_week) / v_prev_week
    else:
        velocity_trend = 0.0

    # Sprint consistency: std dev of per-week completed points over last 8 weeks
    weekly_rows = db.execute(
        text("""
            SELECT
                DATE_TRUNC('week', completed_at) AS week,
                COALESCE(SUM(COALESCE(scrum_number, 1)), 0) AS week_points
            FROM task
            WHERE id_project = :pid
              AND completed_at IS NOT NULL
              AND completed_at >= :eight_weeks_ago
              AND completed_at < :ref_ts
              AND NOT EXISTS (
                  SELECT 1 FROM task c WHERE c.id_parent_task = task.id_task
              )
            GROUP BY DATE_TRUNC('week', completed_at)
        """),
        {
            "pid": project_id,
            "ref_ts": ref_ts,
            "eight_weeks_ago": datetime.combine(
                date.fromordinal(ref.toordinal() - 56),
                datetime.min.time(),
            ).replace(tzinfo=timezone.utc),
        },
    ).fetchall()

    if len(weekly_rows) >= 2:
        sprint_consistency = float(np.std([float(r[1]) for r in weekly_rows]))
    else:
        sprint_consistency = 0.0

    return {
        "velocity_last_week": v_last_week,
        "velocity_avg": velocity_avg,
        "velocity_trend": velocity_trend,
        "sprint_consistency": sprint_consistency,
        "points_remaining": points_remaining,
        "days_remaining": float(days_remaining),
        "completion_rate": completion_rate,
        "tasks_in_progress": float(tasks_in_progress),
    }


def _features_to_array(features: dict) -> np.ndarray:
    return np.array([
        features["velocity_last_week"],
        features["velocity_avg"],
        features["velocity_trend"],
        features["sprint_consistency"],
        features["points_remaining"],
        features["days_remaining"],
        features["completion_rate"],
        features["tasks_in_progress"],
    ], dtype=float).reshape(1, -1)


# ─────────────────────────────────────────────────────────────────────────────
# Rule-based fallback (no trained model yet)
# ─────────────────────────────────────────────────────────────────────────────

def _rule_based_prediction(features: dict) -> dict:
    """
    Pure burndown math: how many days will it take to finish at current velocity,
    and compare to days_remaining.
    """
    effective_velocity = features["velocity_avg"] / 7  # points per day
    if effective_velocity <= 0:
        days_to_finish = float("inf")
    else:
        # Cap the projection: a tiny velocity with many points left can project centuries
        # ahead, which overflows date.fromordinal() below.
        days_to_finish = min(
            features["points_remaining"] / effective_velocity, float(_MAX_PROJECTED_DAYS)
        )

    days_remaining = features["days_remaining"]
    days_delay = days_to_finish - days_remaining
    at_risk = days_delay > _AT_RISK_GRACE_DAYS

    predicted_end = None
    if days_to_finish != float("inf"):
        predicted_days = int(days_to_finish)
        predicted_end = date.fromordinal(date.today().toordinal() + predicted_days).isoformat()

    return {
        "at_risk": at_risk,
        "confidence": None,
        "predicted_end_date": predicted_end,
        "days_delay_estimate": int(max(0, days_delay)) if days_delay != float("inf") else None,
        "model_used": "rule_based_burndown",
        "features": features,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Training
# ─────────────────────────────────────────────────────────────────────────────

def _get_training_data(db: Session) -> tuple[np.ndarray, np.ndarray] | None:
    """
    Build training dataset from completed projects.
    Label: actual_delay_days (positive = delivered late, negative = early).
    """
    # Match Django's real lifecycle values (Project.STATUS_CHOICES stores "Finished", not
    # "closed" — the old filter never matched a single row, so the model could never train).
    completed_projects = db.execute(
        text("""
            SELECT id_project, end_date, created_at
            FROM project
            WHERE end_date IS NOT NULL
              AND status = ANY(:statuses)
        """),
        {"statuses": list(_COMPLETED_PROJECT_STATUSES)},
    ).fetchall()

    if len(completed_projects) < MIN_TRAINING_PROJECTS:
        logger.info(
            "Not enough completed projects to train (%d / %d required).",
            len(completed_projects),
            MIN_TRAINING_PROJECTS,
        )
        return None

    X_rows, y_rows = [], []

    for row in completed_projects:
        project_id = row[0]
        end_date = row[1]

        # Find actual completion date (latest completed_at among all tasks)
        actual_row = db.execute(
            text("""
                SELECT MAX(completed_at)
                FROM task
                WHERE id_project = :pid AND completed_at IS NOT NULL
            """),
            {"pid": project_id},
        ).fetchone()

        if actual_row is None or actual_row[0] is None:
            continue

        actual_end = actual_row[0].date()
        actual_delay = (actual_end - end_date).days  # positive = late

        # Extract features as-of the end_date (mid-project snapshot)
        mid_date = date.fromordinal((row[2].toordinal() + end_date.toordinal()) // 2)
        features = _extract_features(db, project_id, reference_date=mid_date)
        if features is None:
            continue

        X_rows.append(_features_to_array(features).flatten())
        y_rows.append(float(actual_delay))

    if len(X_rows) < MIN_TRAINING_PROJECTS:
        return None

    return np.array(X_rows), np.array(y_rows)


def train_model(db: Session) -> dict:
    """
    Train the ElasticNet model and persist it to disk.
    Returns a status dict with training results.
    """
    data = _get_training_data(db)
    if data is None:
        return {
            "status": "skipped",
            "reason": f"Need at least {MIN_TRAINING_PROJECTS} completed projects with tasks.",
        }

    X, y = data

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    # ElasticNetCV auto-selects alpha and l1_ratio via 5-fold CV
    model = ElasticNetCV(
        l1_ratio=[0.1, 0.5, 0.7, 0.9, 0.95, 0.99, 1.0],
        cv=min(5, len(X)),
        max_iter=10000,
        random_state=42,
    )
    model.fit(X_scaled, y)

    _dump_model_atomic(model, scaler)

    # Invalidate the in-process cache so the next prediction reloads the freshly trained files.
    global _MODEL_CACHE, _MODEL_CACHE_KEY
    _MODEL_CACHE = None
    _MODEL_CACHE_KEY = None

    # r2_score is computed ON THE TRAINING SET (with this few samples it trends to 1.0 and
    # says nothing about generalization). cv_mse is the honest signal: the best mean
    # cross-validated MSE (in days²) across the alpha/l1_ratio grid ElasticNetCV searched.
    train_r2 = model.score(X_scaled, y)
    cv_mse = float(np.min(np.mean(model.mse_path_, axis=-1)))

    logger.info(
        "Model trained on %d projects. train R²=%.3f, CV MSE=%.2f days², alpha=%.4f, l1_ratio=%.2f",
        len(X),
        train_r2,
        cv_mse,
        model.alpha_,
        model.l1_ratio_,
    )

    return {
        "status": "trained",
        "samples": len(X),
        "r2_score": round(train_r2, 4),
        "cv_mse": round(cv_mse, 2),
        "alpha": round(float(model.alpha_), 6),
        "l1_ratio": round(float(model.l1_ratio_), 3),
    }


def _dump_model_atomic(model, scaler) -> None:
    """Persist model + scaler with write-to-temp + atomic rename.

    A plain joblib.dump() to the final path lets a concurrent predict read a half-written
    file, and two overlapping trains could leave a model from one run paired with the scaler
    of another (silently wrong predictions). os.replace() makes each file swap atomic.
    """
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    for obj, path in ((model, MODEL_PATH), (scaler, SCALER_PATH)):
        fd, tmp_path = tempfile.mkstemp(dir=MODEL_DIR, suffix=".tmp")
        try:
            with os.fdopen(fd, "wb") as fh:
                joblib.dump(obj, fh)
            os.replace(tmp_path, path)
        except BaseException:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass
            raise


def _load_model() -> tuple | None:
    global _MODEL_CACHE, _MODEL_CACHE_KEY
    if not (MODEL_PATH.exists() and SCALER_PATH.exists()):
        return None
    # Key the cache on both files' mtimes so a retrain (which rewrites them) is picked up
    # automatically without restarting the process.
    cache_key = (MODEL_PATH.stat().st_mtime, SCALER_PATH.stat().st_mtime)
    if _MODEL_CACHE is not None and _MODEL_CACHE_KEY == cache_key:
        return _MODEL_CACHE
    try:
        loaded = (joblib.load(MODEL_PATH), joblib.load(SCALER_PATH))
    except Exception as exc:
        logger.warning("Could not load persisted model: %s", exc)
        return None
    _MODEL_CACHE = loaded
    _MODEL_CACHE_KEY = cache_key
    return loaded


# ─────────────────────────────────────────────────────────────────────────────
# Prediction
# ─────────────────────────────────────────────────────────────────────────────

def predict_risk(db: Session, project_id: int) -> dict | None:
    """
    Predict delay risk for a project.

    Returns None if the project does not exist, has no tasks, or has no end_date
    (without a deadline there is no delay to predict).
    Otherwise returns:
      {
        at_risk: bool,
        confidence: float | None,   # None when using rule-based fallback
        predicted_end_date: str | None,
        days_delay_estimate: int | None,
        model_used: "elasticnet" | "rule_based_burndown",
        features: dict,
      }
    """
    features = _extract_features(db, project_id)
    if features is None:
        return None

    loaded = _load_model()
    if loaded is None:
        return _rule_based_prediction(features)

    model, scaler = loaded
    X = _features_to_array(features)
    X_scaled = scaler.transform(X)

    predicted_delay = float(model.predict(X_scaled)[0])
    # Grace band: a predicted delay of a day or two is inside the model's error bar — flagging
    # it as "at risk" would make the signal noisy and erode trust in real alarms.
    at_risk = predicted_delay > _AT_RISK_GRACE_DAYS

    days_remaining = features["days_remaining"]
    predicted_end_days = int(days_remaining + predicted_delay)
    predicted_end = date.fromordinal(
        date.today().toordinal() + max(0, predicted_end_days)
    ).isoformat()

    # Confidence: how far from the decision boundary (0-delay line),
    # normalized by a ±30-day window to give a 0-1 score.
    raw_confidence = min(1.0, abs(predicted_delay) / 30.0)

    return {
        "at_risk": at_risk,
        "confidence": round(raw_confidence, 3),
        "predicted_end_date": predicted_end,
        "days_delay_estimate": int(max(0, predicted_delay)),
        "model_used": "elasticnet",
        "features": features,
    }
