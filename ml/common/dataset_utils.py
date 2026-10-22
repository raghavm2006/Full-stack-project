"""
Shared training/evaluation plumbing so categorization, spam_detection,
and priority_detection don't each reimplement "train 3 models, compare
them, save the best, plot a confusion matrix."
"""

import json
import os

import joblib
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)


def _to_native(value):
    """
    Recursively converts numpy scalars/arrays to plain Python types.
    Needed because sklearn metrics and pandas Series (e.g. y.unique())
    hand back numpy.int64/float64, which json.dump() cannot serialize —
    this bit us immediately when spam_detection's labels are 0/1 (numpy
    ints) rather than categorization's string labels, which is exactly
    why this is factored out here instead of casted ad hoc per call site.
    """
    if isinstance(value, dict):
        return {key: _to_native(v) for key, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_native(v) for v in value]
    if hasattr(value, "item"):  # numpy scalar (int64, float64, bool_, ...)
        return value.item()
    return value


def evaluate_predictions(y_true, y_pred, labels) -> dict:
    """Rule: every model comparison reports accuracy/precision/recall/F1 (weighted, for imbalanced classes) + confusion matrix."""
    return _to_native({
        "accuracy": accuracy_score(y_true, y_pred),
        "precision_weighted": precision_score(y_true, y_pred, average="weighted", zero_division=0),
        "recall_weighted": recall_score(y_true, y_pred, average="weighted", zero_division=0),
        "f1_weighted": f1_score(y_true, y_pred, average="weighted", zero_division=0),
        "f1_macro": f1_score(y_true, y_pred, labels=labels, average="macro", zero_division=0),
        "recall_per_class": dict(zip(map(str, labels), recall_score(y_true, y_pred, labels=labels, average=None, zero_division=0))),
        "confusion_matrix": confusion_matrix(y_true, y_pred, labels=labels).tolist(),
        "labels": list(labels),
    })


def plot_confusion_matrix(cm, labels, title, output_path):
    """Saves a confusion matrix as a PNG. Skips quietly if matplotlib isn't installed —
    the JSON metrics are what evaluate.py's numbers come from either way."""
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError:
        print(f"  (matplotlib not installed — skipping {output_path})")
        return

    fig, ax = plt.subplots(figsize=(1.4 * len(labels) + 2, 1.2 * len(labels) + 2))
    im = ax.imshow(cm, cmap="Blues")
    ax.set_xticks(range(len(labels)))
    ax.set_yticks(range(len(labels)))
    ax.set_xticklabels(labels, rotation=45, ha="right")
    ax.set_yticklabels(labels)
    ax.set_xlabel("Predicted")
    ax.set_ylabel("Actual")
    ax.set_title(title)

    max_val = cm.max() if hasattr(cm, "max") else max(max(row) for row in cm)
    for i in range(len(labels)):
        for j in range(len(labels)):
            value = cm[i][j]
            color = "white" if value > max_val / 2 else "black"
            ax.text(j, i, str(value), ha="center", va="center", color=color)

    fig.colorbar(im, ax=ax)
    fig.tight_layout()
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    fig.savefig(output_path, dpi=120)
    plt.close(fig)


def save_metrics_report(results: dict, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(_to_native(results), f, indent=2)
    print(f"Saved metrics report to {output_path}")


def save_model_bundle(model, vectorizer, model_dir: str, name: str):
    """Saves one trained model + the vectorizer it was trained with, as a matched pair."""
    os.makedirs(model_dir, exist_ok=True)
    model_path = os.path.join(model_dir, f"{name}_model.joblib")
    vectorizer_path = os.path.join(model_dir, f"{name}_vectorizer.joblib")
    joblib.dump(model, model_path)
    joblib.dump(vectorizer, vectorizer_path)
    print(f"Saved {model_path} and {vectorizer_path}")


def copy_as_production_model(model_dir: str, best_name: str, alias: str):
    """
    Copies the best-performing model/vectorizer to fixed filenames
    (e.g. production_model.joblib) so Phase 7's inference code can load
    a stable path without knowing which algorithm won the comparison.
    """
    import shutil

    for suffix in ("model", "vectorizer"):
        src = os.path.join(model_dir, f"{best_name}_{suffix}.joblib")
        dst = os.path.join(model_dir, f"{alias}_{suffix}.joblib")
        shutil.copyfile(src, dst)
    print(f"Copied '{best_name}' artifacts to '{alias}_*.joblib' for inference use.")
