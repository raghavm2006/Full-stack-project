"""
Standalone evaluation report for already-trained priority models.

Run: python -m ml.priority_detection.evaluate
"""

import os

import joblib
from sklearn.metrics import classification_report

from ml.priority_detection.train import LABELS, MODEL_DIR, MODELS, build_combined_features, load_split


def main():
    train_df, test_df, y_train, y_test = load_split()

    vectorizer_path = os.path.join(MODEL_DIR, "vectorizer.joblib")
    scaler_path = os.path.join(MODEL_DIR, "scaler.joblib")
    if not (os.path.exists(vectorizer_path) and os.path.exists(scaler_path)):
        print("No saved vectorizer/scaler found. Run train.py first.")
        return

    vectorizer = joblib.load(vectorizer_path)
    scaler = joblib.load(scaler_path)
    X_test = build_combined_features(test_df, vectorizer, scaler, fit=False)

    for name in MODELS:
        model_path = os.path.join(MODEL_DIR, f"{name}_model.joblib")
        if not os.path.exists(model_path):
            print(f"Skipping {name} — no saved model found.")
            continue

        model = joblib.load(model_path)
        predictions = model.predict(X_test)
        print(f"\n=== {name} ===")
        print(classification_report(y_test, predictions, labels=LABELS, zero_division=0))


if __name__ == "__main__":
    main()
