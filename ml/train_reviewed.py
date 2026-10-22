"""Train isolated candidates from HUMAN-LABELLED emails; never replace live models.

python -m ml.train_reviewed reviewed-training.csv --task categorization --output models_store/candidates/reviewed-category
Use a DIFFERENT held-out CSV with ml.evaluate_reviewed for final validation.
"""
import argparse
import json
from collections import Counter
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from scipy.sparse import hstack
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from ml.common.dataset_utils import evaluate_predictions
from ml.common.text_cleaning import clean_for_vectorizer
from ml.priority_detection.feature_engineering import extract_features
from ml.priority_detection.preprocess import FEATURE_COLUMNS


def train_candidate(frame, task, output):
    column = {"categorization": "category", "priority": "priority", "spam": "spam_label"}[task]
    if not {"subject", "body", "sender", column}.issubset(frame.columns):
        raise ValueError(f"CSV needs subject, body, sender and {column} columns")
    frame = frame.fillna("").copy()
    frame[column] = frame[column].astype(str).str.strip()
    frame = frame[frame[column] != ""].copy()
    allowed = {"priority": {"HIGH", "MEDIUM", "LOW"}, "spam": {"0", "1"},
               "categorization": {"Work", "Personal", "Other", "Education", "Finance", "Shopping", "Travel", "Social", "Promotions"}}[task]
    if not set(frame[column]) <= allowed:
        raise ValueError("CSV contains unsupported labels")
    frame["text"] = [clean_for_vectorizer(f"{r.subject}\n{r.body}") for r in frame.itertuples()]
    frame = frame[frame["text"].str.strip() != ""]
    if (frame.groupby("text")[column].nunique() > 1).any():
        raise ValueError("Identical cleaned messages have conflicting labels; review them first")
    frame = frame.drop_duplicates("text").reset_index(drop=True)
    counts = Counter(frame[column])
    if len(counts) < 2 or min(counts.values()) < 10:
        raise ValueError("Provide at least two classes and 10 distinct reviewed emails per class; more data is strongly recommended")
    output = Path(output).resolve()
    live_root = Path(__file__).resolve().parents[1] / "models_store"
    if any(output == (live_root / name).resolve() for name in ("categorization", "spam", "priority")):
        raise ValueError("Output cannot be a live model directory")
    output.mkdir(parents=True, exist_ok=False)
    train, validation = train_test_split(frame, test_size=0.25, random_state=42, stratify=frame[column])
    vectorizer = TfidfVectorizer(max_features=20000, ngram_range=(1, 2), sublinear_tf=True)
    train_x = vectorizer.fit_transform(train["text"])
    validation_x = vectorizer.transform(validation["text"])
    scaler = None
    if task == "priority":
        def numeric(rows):
            return np.array([[extract_features(r.subject, r.body, r.sender)[c] for c in FEATURE_COLUMNS]
                             for r in rows.itertuples()])
        scaler = StandardScaler()
        train_x = hstack([train_x, scaler.fit_transform(numeric(train))]).tocsr()
        validation_x = hstack([validation_x, scaler.transform(numeric(validation))]).tocsr()
    train_y = train[column].astype(int) if task == "spam" else train[column]
    validation_y = validation[column].astype(int) if task == "spam" else validation[column]
    labels = sorted(train_y.unique())
    models = {"balanced_svm": LinearSVC(class_weight="balanced", random_state=42),
              "balanced_logistic": LogisticRegression(class_weight="balanced", max_iter=2000, random_state=42)}
    results = {}
    for name, model in models.items():
        model.fit(train_x, train_y)
        results[name] = evaluate_predictions(validation_y, model.predict(validation_x), labels)
    best = max(results, key=lambda name: results[name]["f1_macro"])
    joblib.dump(models[best], output / "production_model.joblib")
    joblib.dump(vectorizer, output / ("vectorizer.joblib" if task == "priority" else "production_vectorizer.joblib"))
    if scaler:
        joblib.dump(scaler, output / "scaler.joblib")
    report = {"task": task, "best_model": best, "selection_metric": "f1_macro",
              "class_counts": dict(counts), "training_count": len(train), "validation_count": len(validation),
              "basis": "Internal validation used for model selection; NOT independent final test performance.", "results": results}
    (output / "metrics.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path")
    parser.add_argument("--task", choices=["categorization", "priority", "spam"], required=True)
    parser.add_argument("--output", required=True, help="New candidate task directory; existing folders are refused")
    args = parser.parse_args()
    try:
        report = train_candidate(pd.read_csv(args.csv_path, dtype=str, keep_default_na=False), args.task, args.output)
    except (ValueError, FileExistsError) as exc:
        parser.error(str(exc))
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
