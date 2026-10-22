"""
Standalone evaluation report for already-trained spam models. Same
pattern as ml/categorization/evaluate.py.

Run: python -m ml.spam_detection.evaluate
"""

import os

import joblib
import pandas as pd
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

from ml.spam_detection.train import DATA_PATH, LABEL_NAMES, MODEL_DIR, MODELS, RANDOM_STATE


def main():
    df = pd.read_csv(DATA_PATH)
    _, X_test, _, y_test = train_test_split(
        df["text"], df["label"], test_size=0.2, random_state=RANDOM_STATE, stratify=df["label"]
    )

    for name in MODELS:
        model_path = os.path.join(MODEL_DIR, f"{name}_model.joblib")
        vectorizer_path = os.path.join(MODEL_DIR, f"{name}_vectorizer.joblib")
        if not os.path.exists(model_path):
            print(f"Skipping {name} — no saved model found. Run train.py first.")
            continue

        model = joblib.load(model_path)
        vectorizer = joblib.load(vectorizer_path)

        predictions = model.predict(vectorizer.transform(X_test))
        target_names = [LABEL_NAMES[l] for l in sorted(LABEL_NAMES)]
        print(f"\n=== {name} ===")
        print(classification_report(y_test, predictions, target_names=target_names, zero_division=0))


if __name__ == "__main__":
    main()
