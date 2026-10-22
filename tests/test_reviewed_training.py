import pandas as pd
import pytest

from ml.train_reviewed import train_candidate


def reviewed_frame(task):
    labels = {"categorization": ["Work", "Personal"], "priority": ["HIGH", "LOW"], "spam": ["0", "1"]}[task]
    column = {"categorization": "category", "priority": "priority", "spam": "spam_label"}[task]
    rows = []
    for label in labels:
        for i in range(12):
            rows.append({"subject": f"{label} {'urgent invoice' if label == labels[0] else 'family picnic'} topic {chr(97+i)}",
                         "body": f"Distinct message {chr(97+i)} {'submit today' if label == labels[0] else 'weekend invitation'}",
                         "sender": "sender@example.com", column: label})
    return pd.DataFrame(rows)


@pytest.mark.parametrize("task", ["categorization", "priority", "spam"])
def test_reviewed_candidate_is_isolated_and_inference_compatible(tmp_path, task):
    import joblib
    output = tmp_path / task
    report = train_candidate(reviewed_frame(task), task, output)
    assert report["selection_metric"] == "f1_macro"
    assert report["training_count"] + report["validation_count"] == 24
    assert (output / "production_model.joblib").exists()
    assert (output / ("vectorizer.joblib" if task == "priority" else "production_vectorizer.joblib")).exists()
    model = joblib.load(output / "production_model.joblib")
    assert len(model.classes_) == 2
    if task == "priority":
        assert (output / "scaler.joblib").exists()
    with pytest.raises(FileExistsError):
        train_candidate(reviewed_frame(task), task, output)


def test_training_rejects_insufficient_or_conflicting_labels(tmp_path):
    frame = reviewed_frame("categorization")
    with pytest.raises(ValueError, match="10 distinct"):
        train_candidate(frame.iloc[:4], "categorization", tmp_path / "few")
    frame.loc[12, ["subject", "body"]] = frame.loc[0, ["subject", "body"]]
    with pytest.raises(ValueError, match="conflicting"):
        train_candidate(frame, "categorization", tmp_path / "conflict")
