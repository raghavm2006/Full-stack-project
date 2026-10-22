"""
Trains and compares Logistic Regression, Linear SVM, and Naive Bayes on
TF-IDF features for spam detection (ham=0, spam=1).

Run: python -m ml.spam_detection.train
(after: python -m ml.spam_detection.preprocess)
"""

import os

import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.model_selection import train_test_split
from sklearn.naive_bayes import MultinomialNB
from sklearn.svm import LinearSVC

from ml.common.dataset_utils import (
    copy_as_production_model,
    evaluate_predictions,
    plot_confusion_matrix,
    save_metrics_report,
    save_model_bundle,
)

DATA_PATH = os.path.join("data", "processed", "spam.csv")
MODEL_DIR = os.path.join("models_store", "spam")
RANDOM_STATE = 42

MODELS = {
    "logistic_regression": LogisticRegression(max_iter=1000, class_weight="balanced"),
    "linear_svm": LinearSVC(class_weight="balanced"),
    "naive_bayes": MultinomialNB(),
}

LABEL_NAMES = {0: "ham", 1: "spam"}


def load_split():
    df = pd.read_csv(DATA_PATH)
    # Defense-in-depth: an empty/NaN text cell (from a message that
    # cleaned down to nothing) crashes TfidfVectorizer outright — drop
    # any such rows rather than let preprocess.py be the only guard.
    df = df.dropna(subset=["text"])
    df = df[df["text"].str.strip() != ""]
    return train_test_split(
        df["text"], df["label"], test_size=0.2, random_state=RANDOM_STATE, stratify=df["label"]
    )


def main():
    X_train, X_test, y_train, y_test = load_split()
    print(f"Train size: {len(X_train)}, Test size: {len(X_test)}")

    vectorizer = TfidfVectorizer(max_features=20000, ngram_range=(1, 2), stop_words="english")
    X_train_vec = vectorizer.fit_transform(X_train)
    X_test_vec = vectorizer.transform(X_test)

    labels = sorted(y_train.unique())
    label_display = [LABEL_NAMES[l] for l in labels]
    results = {}

    for name, model in MODELS.items():
        print(f"\nTraining {name}...")
        model.fit(X_train_vec, y_train)
        predictions = model.predict(X_test_vec)

        metrics = evaluate_predictions(y_test, predictions, labels)
        results[name] = metrics
        print(
            f"  accuracy={metrics['accuracy']:.3f} "
            f"precision={metrics['precision_weighted']:.3f} "
            f"recall={metrics['recall_weighted']:.3f} "
            f"f1={metrics['f1_weighted']:.3f}"
        )

        save_model_bundle(model, vectorizer, MODEL_DIR, name)
        plot_confusion_matrix(
            metrics["confusion_matrix"], label_display,
            f"Spam Detection — {name}",
            os.path.join(MODEL_DIR, f"{name}_confusion_matrix.png"),
        )

    best_name = max(results, key=lambda n: results[n]["f1_weighted"])
    print(f"\nBest model by weighted F1: {best_name}")
    copy_as_production_model(MODEL_DIR, best_name, alias="production")

    save_metrics_report(
        {"best_model": best_name, "label_names": LABEL_NAMES, "results": results},
        os.path.join(MODEL_DIR, "metrics.json"),
    )


if __name__ == "__main__":
    main()
