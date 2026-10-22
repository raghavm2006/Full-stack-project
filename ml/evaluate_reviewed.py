"""Evaluate frozen models on a separate, human-labeled CSV; never train here.

Run: python -m ml.evaluate_reviewed data/labeled/reviewed.csv
Columns: subject, body, sender, category, priority, spam_label.
Labels may be blank; spam_label must be 0 (ham) or 1 (spam).
Use held-out examples that were not used in training or tuning.
"""
import argparse
import csv
import json


def evaluate_rows(rows, predictors):
    from sklearn.metrics import accuracy_score, f1_score

    report = {}
    for task, column in (("category", "category"), ("priority", "priority"), ("spam", "spam_label")):
        expected, predicted = [], []
        for row in rows:
            label = (row.get(column) or "").strip()
            if not label:
                continue
            if task == "spam":
                if label not in ("0", "1"):
                    raise ValueError("spam_label must be 0 or 1")
                label = label == "1"
            elif task == "priority" and label not in ("HIGH", "MEDIUM", "LOW"):
                raise ValueError("priority must be HIGH, MEDIUM, or LOW")
            expected.append(label)
            predicted.append(predictors[task](row))
        if expected:
            report[task] = {
                "reviewed_count": len(expected),
                "accuracy": float(accuracy_score(expected, predicted)),
                "f1_macro": float(f1_score(expected, predicted, average="macro", zero_division=0)),
            }
    if not report:
        raise ValueError("CSV contains no reviewed labels")
    return {"basis": "Human labels supplied in CSV; validity depends on independent held-out review.",
            "tasks": report}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path")
    parser.add_argument("--models-dir", help="Candidate root containing categorization/, priority/, spam/ directories")
    parser.add_argument("--task", choices=["category", "priority", "spam"], help="Evaluate just one task")
    args = parser.parse_args()
    from pathlib import Path
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    from app import create_app
    from app.blueprints.ml_inference.predictors import predict_category, predict_priority, predict_spam

    with open(args.csv_path, encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)
        if not {"subject", "body", "sender"}.issubset(reader.fieldnames or []):
            parser.error("CSV must include subject, body, and sender columns")
        rows = list(reader)
    if args.task:
        keep = {"category": "category", "priority": "priority", "spam": "spam_label"}[args.task]
        for row in rows:
            for column in ("category", "priority", "spam_label"):
                if column != keep:
                    row[column] = ""
    predictors = {
        "category": lambda r: predict_category(f"{r['subject']}\n{r['body']}")[0],
        "priority": lambda r: predict_priority(r["subject"], r["body"], r["sender"])[0],
        "spam": lambda r: predict_spam(f"{r['subject']}\n{r['body']}")[0],
    }
    application = create_app()
    if args.models_dir:
        application.config["MODELS_DIR"] = str(Path(args.models_dir).resolve())
    with application.app_context():
        print(json.dumps(evaluate_rows(rows, predictors), indent=2))


if __name__ == "__main__":
    main()
