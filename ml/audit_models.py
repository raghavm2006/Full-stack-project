"""Audit saved confusion matrices for hidden minority-class failures (no training)."""
import argparse
import json
from pathlib import Path


def audit(root):
    report = {}
    for task in ("categorization", "spam", "priority"):
        path = Path(root) / task / "metrics.json"
        if not path.exists():
            continue
        data = json.loads(path.read_text(encoding="utf-8"))
        result = data["results"][data["best_model"]]
        matrix, labels = result["confusion_matrix"], result["labels"]
        classes = {}
        for i, label in enumerate(labels):
            support = sum(matrix[i])
            predicted = sum(row[i] for row in matrix)
            precision = matrix[i][i] / predicted if predicted else 0
            recall = matrix[i][i] / support if support else 0
            f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0
            classes[str(label)] = {"support": support, "precision": precision, "recall": recall, "f1": f1}
        report[task] = {"model": data["best_model"], "class_metrics": classes,
                        "f1_macro": sum(item["f1"] for item in classes.values()) / max(1, len(classes)),
                        "basis": "Historical saved evaluation; not live inbox accuracy."}
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--models-dir", default="models_store")
    args = parser.parse_args()
    print(json.dumps(audit(args.models_dir), indent=2))


if __name__ == "__main__":
    main()
