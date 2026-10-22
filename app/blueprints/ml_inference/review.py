"""Local model evidence; never retrain during a request."""
from app.blueprints.ml_inference.predictors import _load_artifacts, ModelNotTrainedError
from ml.common.text_cleaning import clean_for_vectorizer


def category_evidence(email):
    if email.category_confidence is None:
        return {"terms": [], "note": "No model confidence stored; this may be a correction or an unavailable model."}
    try:
        artifacts = _load_artifacts("categorization", {
            "model": "production_model.joblib", "vectorizer": "production_vectorizer.joblib"})
        model, vectorizer = artifacts["model"], artifacts["vectorizer"]
        if not hasattr(model, "coef_"):
            return {"terms": [], "note": "Feature explanations are unavailable for this model."}
        text = clean_for_vectorizer(f"{email.subject or ''}\n{email.body or ''}")
        matrix = vectorizer.transform([text])
        predicted = model.predict(matrix)[0]
        if str(predicted) != email.category:
            return {"terms": [], "note": "Stored category differs from the current model. It may be corrected or from an earlier model."}
        index = list(model.classes_).index(predicted)
        weights = model.coef_[index] if len(model.coef_) > 1 else model.coef_[0] * (1 if index == 1 else -1)
        names = vectorizer.get_feature_names_out()
        contributions = [(names[i], float(value * weights[i])) for i, value in zip(matrix.indices, matrix.data)]
        terms = [str(word) for word, score in sorted(contributions, key=lambda x: x[1], reverse=True) if score > 0][:5]
        return {"terms": terms, "note": "These words contributed to the current model score; they do not prove the category is correct."}
    except (ModelNotTrainedError, ValueError, AttributeError, IndexError):
        return {"terms": [], "note": "Model explanation is unavailable."}
