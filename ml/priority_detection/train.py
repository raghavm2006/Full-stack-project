"""
Trains and compares Logistic Regression, Linear SVM, and Random Forest
for priority prediction (HIGH/MEDIUM/LOW), using TF-IDF text features
combined with the engineered numeric features from preprocess.py
(urgency keywords, deadline phrases, sender, etc.) — this is why priority
uses Random Forest as its third comparison model instead of Naive Bayes:
Naive Bayes assumes non-negative feature independence that fits pure
word-count text well but not a mixed text+numeric feature matrix, while
Random Forest is a natural fit for exactly this kind of mixed tabular
data (rule #12 aside: scikit-learn already ships it, nothing new
introduced).

Run: python -m ml.priority_detection.train
(after: python -m ml.priority_detection.preprocess)
"""

import os

import joblib
import pandas as pd
from scipy.sparse import hstack
from sklearn.ensemble import RandomForestClassifier
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler
from sklearn.svm import LinearSVC

from ml.common.dataset_utils import (
    evaluate_predictions,
    plot_confusion_matrix,
    save_metrics_report,
)
from ml.priority_detection.preprocess import FEATURE_COLUMNS

DATA_PATH = os.path.join("data", "processed", "priority.csv")
MODEL_DIR = os.path.join("models_store", "priority")
RANDOM_STATE = 42
LABELS = ["LOW", "MEDIUM", "HIGH"]

MODELS = {
    "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
    "linear_svm": LinearSVC(class_weight="balanced"),
    "random_forest": RandomForestClassifier(n_estimators=200, class_weight="balanced", random_state=RANDOM_STATE),
}


def load_split():
    df = pd.read_csv(DATA_PATH)
    # Defense-in-depth: an empty/NaN text cell crashes TfidfVectorizer
    # outright — drop any such rows rather than let preprocess.py be the
    # only guard (e.g. against re-running training on an older CSV).
    df = df.dropna(subset=["text"])
    df = df[df["text"].str.strip() != ""]
    return train_test_split(
        df, df["label"], test_size=0.2, random_state=RANDOM_STATE, stratify=df["label"]
    )


def build_combined_features(df_split, vectorizer, scaler, fit=False):
    text_matrix = (
        vectorizer.fit_transform(df_split["text"]) if fit else vectorizer.transform(df_split["text"])
    )
    numeric = df_split[FEATURE_COLUMNS].to_numpy()
    numeric_scaled = scaler.fit_transform(numeric) if fit else scaler.transform(numeric)
    return hstack([text_matrix, numeric_scaled]).tocsr()


def main():
    train_df, test_df, y_train, y_test = load_split()
    print(f"Train size: {len(train_df)}, Test size: {len(test_df)}")

    vectorizer = TfidfVectorizer(max_features=10000, ngram_range=(1, 2), stop_words="english")
    scaler = StandardScaler()

    X_train = build_combined_features(train_df, vectorizer, scaler, fit=True)
    X_test = build_combined_features(test_df, vectorizer, scaler, fit=False)

    results = {}
    os.makedirs(MODEL_DIR, exist_ok=True)

    for name, model in MODELS.items():
        print(f"\nTraining {name}...")
        model.fit(X_train, y_train)
        predictions = model.predict(X_test)

        metrics = evaluate_predictions(y_test, predictions, LABELS)
        results[name] = metrics
        print(
            f"  accuracy={metrics['accuracy']:.3f} "
            f"precision={metrics['precision_weighted']:.3f} "
            f"recall={metrics['recall_weighted']:.3f} "
            f"f1={metrics['f1_weighted']:.3f}"
        )

        joblib.dump(model, os.path.join(MODEL_DIR, f"{name}_model.joblib"))
        plot_confusion_matrix(
            metrics["confusion_matrix"], LABELS,
            f"Priority Detection — {name}",
            os.path.join(MODEL_DIR, f"{name}_confusion_matrix.png"),
        )

    # Vectorizer + scaler are shared across all three models (unlike
    # categorization/spam, where each model gets its own vectorizer copy)
    # since priority's feature matrix always combines both.
    joblib.dump(vectorizer, os.path.join(MODEL_DIR, "vectorizer.joblib"))
    joblib.dump(scaler, os.path.join(MODEL_DIR, "scaler.joblib"))

    best_name = max(results, key=lambda n: results[n]["f1_weighted"])
    print(f"\nBest model by weighted F1: {best_name}")
    joblib.dump(
        joblib.load(os.path.join(MODEL_DIR, f"{best_name}_model.joblib")),
        os.path.join(MODEL_DIR, "production_model.joblib"),
    )

    save_metrics_report(
        {"best_model": best_name, "results": results,
         "note": "Labels are heuristic pseudo-labels — see feature_engineering.py's docstring."},
        os.path.join(MODEL_DIR, "metrics.json"),
    )


if __name__ == "__main__":
    main()
