"""ML models: severity classifier, traffic, hospital-capacity and resource-demand regressors.

Every model is optional. Until a model is trained, callers fall back to transparent
rule-based estimates and label the result source="RULE_BASED" with no confidence, so
the UI never presents a heuristic as a learned prediction. Synthetic datasets are
generated from documented formulas plus noise and are always labelled SYNTHETIC.
"""
from __future__ import annotations

import math
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import models as m
from app.config import get_settings

INCIDENT_TYPES = ["FIRE", "ACCIDENT", "MEDICAL", "FLOOD", "EARTHQUAKE", "CHEMICAL_HAZARD", "CRIME", "MISSING_PERSON", "OTHER"]
SEVERITIES = ["LOW", "MEDIUM", "HIGH", "CRITICAL"]
DEMAND_TARGETS = ["ambulances", "fire_trucks", "police", "rescue"]

SPECS: dict[str, dict] = {
    "severity": {
        "display_name": "Incident Severity Classifier", "task": "classification", "default_algorithm": "random_forest",
        "features": [{"name": "incident_type", "type": "categorical", "values": INCIDENT_TYPES},
                     {"name": "people_affected", "type": "int"}, {"name": "injured", "type": "int"},
                     {"name": "exits_blocked", "type": "int"}, {"name": "hazard_count", "type": "int"},
                     {"name": "hour", "type": "int"}],
        "target": "severity",
    },
    "traffic": {
        "display_name": "Traffic Congestion Regressor", "task": "regression", "default_algorithm": "gradient_boosting",
        "features": [{"name": "hour", "type": "int"}, {"name": "day_of_week", "type": "int"},
                     {"name": "speed_limit_kmh", "type": "float"}, {"name": "rain_mm", "type": "float"},
                     {"name": "event_nearby", "type": "int"}],
        "target": "traffic_factor",
    },
    "hospital_capacity": {
        "display_name": "Hospital Occupancy Forecaster", "task": "regression", "default_algorithm": "random_forest",
        "features": [{"name": "hour", "type": "int"}, {"name": "day_of_week", "type": "int"},
                     {"name": "current_occupancy_pct", "type": "float"}, {"name": "incidents_last_hour", "type": "int"},
                     {"name": "beds_total", "type": "int"}],
        "target": "occupancy_next_hour_pct",
    },
    "resource_demand": {
        "display_name": "Resource Demand Predictor", "task": "multi_regression", "default_algorithm": "random_forest",
        "features": [{"name": "incident_type", "type": "categorical", "values": INCIDENT_TYPES},
                     {"name": "severity", "type": "categorical", "values": SEVERITIES},
                     {"name": "people_affected", "type": "int"}, {"name": "injured", "type": "int"},
                     {"name": "exits_blocked", "type": "int"}],
        "target": DEMAND_TARGETS,
    },
}


class MLError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code, self.message, self.status = code, message, status


def _targets(name: str) -> list[str]:
    t = SPECS[name]["target"]
    return t if isinstance(t, list) else [t]


def required_columns(name: str) -> list[str]:
    return [f["name"] for f in SPECS[name]["features"]] + _targets(name)


def schema(name: str) -> dict:
    spec = _spec(name)
    return {"features": spec["features"], "target": spec["target"], "required_columns": required_columns(name)}


def _spec(name: str) -> dict:
    if name not in SPECS:
        raise MLError("UNKNOWN_MODEL", f"Unknown model '{name}'. Known: {list(SPECS)}", 404)
    return SPECS[name]


# ------------------------------------------------------------------ rule-based fallbacks
def rule_severity(incident_type: str, people: int, injured: int = 0, exits_blocked: int = 0, hazards: int = 0) -> str:
    score = math.log10(max(people, 1) + 1) * 1.2 + injured * 0.15 + exits_blocked * 0.6 + hazards * 0.4
    score += {"FIRE": 1.0, "CHEMICAL_HAZARD": 1.4, "EARTHQUAKE": 1.5, "FLOOD": 0.8, "ACCIDENT": 0.4}.get(incident_type, 0.0)
    if score >= 4.2:
        return "CRITICAL"
    if score >= 3.0:
        return "HIGH"
    if score >= 1.8:
        return "MEDIUM"
    return "LOW"


def rule_demand(incident_type: str, severity: str, people: int, injured: int = 0) -> dict[str, int]:
    sev = SEVERITIES.index(severity) if severity in SEVERITIES else 1
    patients = injured or math.ceil(people * [0.01, 0.03, 0.06, 0.10][sev])
    amb = max(1, math.ceil(patients / 4)) if patients or incident_type in ("MEDICAL", "ACCIDENT") else 1
    fire = {"FIRE": 1 + sev, "CHEMICAL_HAZARD": 1 + sev, "EARTHQUAKE": sev, "ACCIDENT": 1 if sev >= 2 else 0}.get(incident_type, 0)
    police = 1 + (1 if sev >= 2 else 0) + (1 if people > 300 else 0)
    rescue = {"FLOOD": 1 + sev // 2, "EARTHQUAKE": 1 + sev // 2, "MISSING_PERSON": 1}.get(incident_type, 1 if sev == 3 else 0)
    return {"ambulances": min(amb, 8), "fire_trucks": min(fire, 5), "police": min(police, 4), "rescue": min(rescue, 3)}


# ------------------------------------------------------------------ synthetic data
def generate_frame(name: str, rows: int = 1500, seed: int = 42) -> pd.DataFrame:
    _spec(name)
    rng = np.random.default_rng(seed)
    if name in ("severity", "resource_demand"):
        types = rng.choice(INCIDENT_TYPES, rows)
        people = np.round(rng.lognormal(3.5, 1.4, rows)).astype(int).clip(1, 5000)
        injured = rng.binomial(people, 0.04)
        exits = rng.poisson(0.5, rows) * np.isin(types, ["FIRE", "EARTHQUAKE", "CHEMICAL_HAZARD"])
        hazards = rng.poisson(0.7, rows)
        hours = rng.integers(0, 24, rows)
        sev = []
        for t, p, i, e, h in zip(types, people, injured, exits, hazards):
            s = SEVERITIES.index(rule_severity(t, int(p), int(i), int(e), int(h)))
            if rng.random() < 0.12:  # label noise so the task is not trivially learnable
                s = int(np.clip(s + rng.choice([-1, 1]), 0, 3))
            sev.append(SEVERITIES[s])
        if name == "severity":
            return pd.DataFrame({"incident_type": types, "people_affected": people, "injured": injured,
                                 "exits_blocked": exits, "hazard_count": hazards, "hour": hours, "severity": sev})
        demand = [rule_demand(t, s, int(p), int(i)) for t, s, p, i in zip(types, sev, people, injured)]
        df = pd.DataFrame({"incident_type": types, "severity": sev, "people_affected": people, "injured": injured,
                           "exits_blocked": exits})
        for k in DEMAND_TARGETS:
            df[k] = [max(0, d[k] + int(rng.choice([-1, 0, 0, 0, 1]))) for d in demand]
        return df
    if name == "traffic":
        hour = rng.integers(0, 24, rows)
        dow = rng.integers(0, 7, rows)
        speed = rng.choice([22, 25, 30, 35, 40, 45, 50], rows)
        rain = np.where(rng.random(rows) < 0.25, rng.gamma(2, 4, rows), 0.0).round(1)
        event = (rng.random(rows) < 0.1).astype(int)
        peak = np.exp(-((hour - 9.5) ** 2) / 4) + np.exp(-((hour - 18.5) ** 2) / 5)
        factor = 1 + 0.9 * peak * np.where(dow < 5, 1.0, 0.6) + 0.025 * rain + 0.5 * event + (50 - speed) * 0.006
        return pd.DataFrame({"hour": hour, "day_of_week": dow, "speed_limit_kmh": speed, "rain_mm": rain,
                             "event_nearby": event, "traffic_factor": (factor + rng.normal(0, 0.08, rows)).round(3)})
    # hospital_capacity
    hour = rng.integers(0, 24, rows)
    dow = rng.integers(0, 7, rows)
    occ = rng.uniform(30, 98, rows).round(1)
    inc = rng.poisson(2, rows)
    beds = rng.choice([40, 45, 50, 58, 60], rows)
    nxt = occ + inc * (100 / beds) * 0.9 - 2.5 + 3 * np.sin((hour - 6) / 24 * 2 * np.pi) + rng.normal(0, 2, rows)
    return pd.DataFrame({"hour": hour, "day_of_week": dow, "current_occupancy_pct": occ, "incidents_last_hour": inc,
                         "beds_total": beds, "occupancy_next_hour_pct": nxt.clip(0, 100).round(1)})


def _datasets_dir() -> Path:
    return Path(get_settings().ml_datasets_dir)


def dataset_dict(d: m.MLDataset) -> dict:
    from app.services.serializers import iso
    return {"id": d.id, "name": d.name, "model_name": d.model_name, "rows": d.rows, "columns": d.columns,
            "source": d.source, "created_at": iso(d.created_at)}


def save_dataset(db: Session, name: str, df: pd.DataFrame, source: str, label: str) -> m.MLDataset:
    missing = [c for c in required_columns(name) if c not in df.columns]
    if missing:
        raise MLError("MISSING_COLUMNS", f"Dataset is missing required columns: {', '.join(missing)}", 422)
    if len(df) < 30:
        raise MLError("TOO_FEW_ROWS", "Dataset needs at least 30 rows", 422)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S%f")
    path = _datasets_dir() / f"{name}_{ts}.csv"
    df.to_csv(path, index=False)
    d = m.MLDataset(name=label, model_name=name, path=str(path), rows=len(df), columns=list(df.columns), source=source)
    db.add(d)
    db.commit()
    return d


# ------------------------------------------------------------------ training
def _build_estimator(name: str, algorithm: str):
    from sklearn.compose import ColumnTransformer
    from sklearn.ensemble import (GradientBoostingClassifier, GradientBoostingRegressor, RandomForestClassifier,
                                  RandomForestRegressor)
    from sklearn.linear_model import LinearRegression, LogisticRegression
    from sklearn.multioutput import MultiOutputRegressor
    from sklearn.pipeline import Pipeline
    from sklearn.preprocessing import OneHotEncoder, StandardScaler

    spec = SPECS[name]
    cat = [f["name"] for f in spec["features"] if f["type"] == "categorical"]
    num = [f["name"] for f in spec["features"] if f["type"] != "categorical"]
    pre = ColumnTransformer([("cat", OneHotEncoder(handle_unknown="ignore"), cat), ("num", StandardScaler(), num)])
    task = spec["task"]
    if task == "classification":
        est = {"random_forest": RandomForestClassifier(n_estimators=150, random_state=0),
               "gradient_boosting": GradientBoostingClassifier(random_state=0),
               "logistic_regression": LogisticRegression(max_iter=2000)}.get(algorithm)
    else:
        est = {"random_forest": RandomForestRegressor(n_estimators=150, random_state=0),
               "gradient_boosting": GradientBoostingRegressor(random_state=0),
               "linear_regression": LinearRegression()}.get(algorithm)
        if est is not None and task == "multi_regression" and algorithm == "gradient_boosting":
            est = MultiOutputRegressor(est)
    if est is None:
        raise MLError("BAD_ALGORITHM", f"Algorithm '{algorithm}' is not valid for a {task} model", 422)
    return Pipeline([("pre", pre), ("model", est)])


def _feature_importance(pipe, name: str) -> list[dict] | None:
    model = pipe.named_steps["model"]
    imp = getattr(model, "feature_importances_", None)
    if imp is None and hasattr(model, "estimators_") and hasattr(model.estimators_[0], "feature_importances_"):
        imp = np.mean([e.feature_importances_ for e in model.estimators_], axis=0)
    if imp is None and hasattr(model, "coef_"):
        imp = np.abs(np.atleast_2d(model.coef_)).mean(axis=0)
    if imp is None:
        return None
    names = pipe.named_steps["pre"].get_feature_names_out()
    agg: dict[str, float] = {}
    for n, v in zip(names, imp):
        raw = n.split("__", 1)[1]
        base = next((f["name"] for f in SPECS[name]["features"] if raw == f["name"] or raw.startswith(f["name"] + "_")), raw)
        agg[base] = agg.get(base, 0.0) + float(v)
    total = sum(agg.values()) or 1.0
    return sorted(({"feature": k, "importance": round(v / total, 4)} for k, v in agg.items()), key=lambda x: -x["importance"])


def train(db: Session, name: str, dataset_id: int, algorithm: str | None = None) -> m.MLModel:
    from sklearn import metrics as skm
    from sklearn.model_selection import train_test_split

    spec = _spec(name)
    ds = db.get(m.MLDataset, dataset_id)
    if ds is None or ds.model_name != name:
        raise MLError("BAD_DATASET", f"Dataset {dataset_id} not found for model '{name}'", 404)
    df = pd.read_csv(ds.path)
    feats = [f["name"] for f in spec["features"]]
    targets = _targets(name)
    X, y = df[feats], (df[targets[0]] if len(targets) == 1 else df[targets])
    algorithm = algorithm or spec["default_algorithm"]
    strat = y if spec["task"] == "classification" and y.value_counts().min() >= 2 else None
    X_tr, X_te, y_tr, y_te = train_test_split(X, y, test_size=0.2, random_state=0, stratify=strat)
    pipe = _build_estimator(name, algorithm)
    pipe.fit(X_tr, y_tr)
    pred = pipe.predict(X_te)
    details: dict = {"feature_importance": _feature_importance(pipe, name)}
    if spec["task"] == "classification":
        labels = [s for s in SEVERITIES if s in set(y)]
        metrics = {"accuracy": skm.accuracy_score(y_te, pred),
                   "precision": skm.precision_score(y_te, pred, average="macro", zero_division=0),
                   "recall": skm.recall_score(y_te, pred, average="macro", zero_division=0),
                   "f1": skm.f1_score(y_te, pred, average="macro", zero_division=0)}
        details["confusion_matrix"] = {"labels": labels, "matrix": skm.confusion_matrix(y_te, pred, labels=labels).tolist()}
    else:
        metrics = {"mae": skm.mean_absolute_error(y_te, pred), "rmse": math.sqrt(skm.mean_squared_error(y_te, pred)),
                   "r2": skm.r2_score(y_te, pred)}
        a = np.asarray(y_te, dtype=float).reshape(len(y_te), -1)[:, 0]
        p = np.asarray(pred, dtype=float).reshape(len(pred), -1)[:, 0]
        details["residuals"] = [{"actual": round(float(x), 3), "predicted": round(float(z), 3)} for x, z in zip(a[:200], p[:200])]
    metrics = {k: round(float(v), 4) for k, v in metrics.items()}
    version = (db.scalar(select(m.MLModel.version).where(m.MLModel.name == name).order_by(m.MLModel.version.desc())) or 0) + 1
    path = Path(get_settings().ml_artifacts_dir) / f"{name}_v{version}.joblib"
    joblib.dump(pipe, path)
    for old in db.scalars(select(m.MLModel).where(m.MLModel.name == name, m.MLModel.is_active.is_(True))):
        old.is_active = False
    row = m.MLModel(name=name, version=version, algorithm=algorithm, dataset_id=ds.id, artifact_path=str(path),
                    features=feats, target=targets, metrics=metrics, details=details, n_train=len(X_tr), n_test=len(X_te))
    db.add(row)
    db.commit()
    _cache.pop(name, None)
    return row


# ------------------------------------------------------------------ inference
_cache: dict[str, tuple[int, object]] = {}


def active_model(db: Session, name: str) -> m.MLModel | None:
    return db.scalar(select(m.MLModel).where(m.MLModel.name == name, m.MLModel.is_active.is_(True)))


def _load(row: m.MLModel):
    hit = _cache.get(row.name)
    if hit and hit[0] == row.version:
        return hit[1]
    pipe = joblib.load(row.artifact_path)
    _cache[row.name] = (row.version, pipe)
    return pipe


def model_info(db: Session, name: str) -> dict:
    from app.services.serializers import iso
    spec = _spec(name)
    row = active_model(db, name)
    ds = db.get(m.MLDataset, row.dataset_id) if row and row.dataset_id else None
    details = (row.details or {}) if row else {}
    return {"name": name, "display_name": spec["display_name"], "task": spec["task"],
            "algorithm": row.algorithm if row else spec["default_algorithm"], "version": row.version if row else None,
            "status": "TRAINED" if row else "NOT_TRAINED",
            "dataset": {"id": ds.id, "name": ds.name, "rows": ds.rows, "source": ds.source} if ds else None,
            "trained_at": iso(row.trained_at) if row else None, "features": [f["name"] for f in spec["features"]],
            "target": spec["target"], "metrics": row.metrics if row else None,
            "confusion_matrix": details.get("confusion_matrix"), "residuals": details.get("residuals"),
            "n_train": row.n_train if row else 0, "n_test": row.n_test if row else 0,
            "feature_importance": details.get("feature_importance")}


def predict(db: Session, name: str, features: dict, incident_id: str | None = None, fallback: bool = False) -> dict:
    """Predict with the active model. With fallback=True an untrained model yields the
    rule-based estimate (source RULE_BASED, confidence None); otherwise MODEL_NOT_TRAINED."""
    spec = _spec(name)
    row = active_model(db, name)
    probs, conf = None, None
    if row is None:
        if not fallback:
            raise MLError("MODEL_NOT_TRAINED", f"Model '{name}' has not been trained yet", 409)
        source, version = "RULE_BASED", None
        if name == "severity":
            value = rule_severity(features.get("incident_type", "OTHER"), int(features.get("people_affected", 0)),
                                  int(features.get("injured", 0)), int(features.get("exits_blocked", 0)),
                                  int(features.get("hazard_count", 0)))
        elif name == "resource_demand":
            value = rule_demand(features.get("incident_type", "OTHER"), features.get("severity", "MEDIUM"),
                                int(features.get("people_affected", 0)), int(features.get("injured", 0)))
        else:
            raise MLError("MODEL_NOT_TRAINED", f"Model '{name}' has not been trained yet", 409)
    else:
        source, version = "ML", row.version
        defaults = {f["name"]: (f["values"][0] if f["type"] == "categorical" else 0) for f in spec["features"]}
        X = pd.DataFrame([{k: features.get(k, defaults[k]) for k in defaults}])
        pipe = _load(row)
        raw = pipe.predict(X)
        if spec["task"] == "classification":
            value = str(raw[0])
            p = pipe.predict_proba(X)[0]
            probs = {str(c): round(float(v), 4) for c, v in zip(pipe.classes_, p)}
            conf = round(float(max(p)), 4)
        elif spec["task"] == "multi_regression":
            value = {k: max(0, int(round(float(v)))) for k, v in zip(DEMAND_TARGETS, np.atleast_1d(raw[0]))}
        else:
            value = round(float(raw[0]), 3)
    rec = m.Prediction(incident_id=incident_id, model_name=name, model_version=version, source=source,
                       features=features, prediction={"value": value}, probabilities=probs, confidence=conf)
    db.add(rec)
    db.commit()
    from app.services.serializers import prediction as ser_pred
    return ser_pred(rec)
