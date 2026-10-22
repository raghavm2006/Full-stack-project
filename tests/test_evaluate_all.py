"""
Phase 11 verification tests for ml/evaluate_all.py.

Run with: pytest tests/test_evaluate_all.py -v

Uses small hand-built metrics.json fixtures in a temp directory rather
than the user's real models_store/ — this script's job is to correctly
read/summarize whatever metrics.json files exist, which is testable
without any real trained model.
"""

import json
import os

import pytest

from ml import evaluate_all


def _write_metrics(tmp_path, task, best_model, results):
    task_dir = os.path.join(str(tmp_path), task)
    os.makedirs(task_dir, exist_ok=True)
    with open(os.path.join(task_dir, "metrics.json"), "w") as f:
        json.dump({"best_model": best_model, "results": results}, f)


@pytest.fixture(autouse=True)
def _point_at_tmp_models_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(evaluate_all, "MODELS_DIR", str(tmp_path))
    yield tmp_path


_SAMPLE_RESULTS = {
    "logistic_regression": {
        "accuracy": 0.80, "precision_weighted": 0.79, "recall_weighted": 0.80, "f1_weighted": 0.795,
    },
    "linear_svm": {
        "accuracy": 0.85, "precision_weighted": 0.86, "recall_weighted": 0.84, "f1_weighted": 0.85,
    },
}


def test_load_task_metrics_returns_none_when_missing(tmp_path):
    assert evaluate_all.load_task_metrics("categorization") is None


def test_load_task_metrics_reads_saved_file(tmp_path):
    _write_metrics(tmp_path, "categorization", "linear_svm", _SAMPLE_RESULTS)

    metrics = evaluate_all.load_task_metrics("categorization")
    assert metrics["best_model"] == "linear_svm"
    assert metrics["results"]["linear_svm"]["f1_weighted"] == 0.85


def test_build_summary_marks_untrained_tasks(tmp_path):
    _write_metrics(tmp_path, "categorization", "linear_svm", _SAMPLE_RESULTS)

    summary = evaluate_all.build_summary()
    assert summary["tasks"]["categorization"]["trained"] is True
    assert summary["tasks"]["spam"] == {"trained": False}
    assert summary["tasks"]["priority"] == {"trained": False}


def test_build_summary_includes_caveat_for_categorization_and_priority(tmp_path):
    _write_metrics(tmp_path, "categorization", "linear_svm", _SAMPLE_RESULTS)
    _write_metrics(tmp_path, "priority", "logistic_regression", _SAMPLE_RESULTS)
    _write_metrics(tmp_path, "spam", "linear_svm", _SAMPLE_RESULTS)

    summary = evaluate_all.build_summary()
    assert summary["tasks"]["categorization"]["caveat"] is not None
    assert summary["tasks"]["priority"]["caveat"] is not None
    assert summary["tasks"]["spam"]["caveat"] is None


def test_render_markdown_marks_the_best_model():
    summary = {
        "tasks": {
            "categorization": {
                "trained": True,
                "best_model": "linear_svm",
                "models_compared": _SAMPLE_RESULTS,
                "caveat": "some caveat",
            },
            "spam": {"trained": False},
            "priority": {"trained": False},
        }
    }

    markdown = evaluate_all.render_markdown(summary)
    assert "linear_svm **(best)**" in markdown
    assert "Not yet trained" in markdown
    assert "some caveat" in markdown


def test_main_writes_json_and_markdown_files(tmp_path):
    _write_metrics(tmp_path, "categorization", "linear_svm", _SAMPLE_RESULTS)

    evaluate_all.main()

    json_path = os.path.join(str(tmp_path), "evaluation_summary.json")
    md_path = os.path.join(str(tmp_path), "evaluation_summary.md")
    assert os.path.exists(json_path)
    assert os.path.exists(md_path)

    with open(json_path) as f:
        data = json.load(f)
    assert data["tasks"]["categorization"]["best_model"] == "linear_svm"
