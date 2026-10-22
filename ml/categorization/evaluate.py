"""
Standalone evaluation report for already-trained categorization models —
re-derives the identical train/test split train.py used (same
random_state), loads each saved model, and prints a full sklearn
classification_report per model. Useful for pulling numbers/plots for
your project report without re-training.

Run: python -m ml.categorization.evaluate
"""

import os

import joblib
import pandas as pd
from sklearn.metrics import classification_report
from sklearn.model_selection import train_test_split

from ml.categorization.train import DATA_PATH, MODEL_DIR, MODELS, RANDOM_STATE


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
        print(f"\n=== {name} ===")
        print(classification_report(y_test, predictions, zero_division=0))


if __name__ == "__main__":
    main()
