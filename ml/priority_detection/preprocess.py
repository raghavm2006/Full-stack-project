"""
Builds the priority-detection training set: walks every email in the
Enron "with categories" corpus (regardless of its .cats genre label —
priority doesn't need that), computes engineered features, and assigns a
HIGH/MEDIUM/LOW pseudo-label via the heuristic in feature_engineering.py.

Run: python -m ml.priority_detection.preprocess
"""

import csv
import os

from ml.common.text_cleaning import clean_for_vectorizer, parse_raw_email_file
from ml.priority_detection.feature_engineering import extract_features, heuristic_priority_label

ENRON_ROOT = os.path.join("data", "raw", "enron", "enron_with_categories", "enron_with_categories")
OUTPUT_PATH = os.path.join("data", "processed", "priority.csv")

FEATURE_COLUMNS = [
    "urgency_keyword_count", "has_deadline_phrase", "exclamation_count",
    "question_mark_count", "is_reply_or_forward", "subject_is_shouting",
    "sender_is_internal", "body_length",
]

MIN_BODY_LENGTH = 20


def iter_priority_records(root_dir: str = ENRON_ROOT):
    if not os.path.isdir(root_dir):
        raise FileNotFoundError(
            f"Enron corpus not found at {root_dir!r}. Make sure you extracted "
            f"'enron_with_categories' into data/raw/enron/ before running this script."
        )

    for entry in sorted(os.listdir(root_dir)):
        subfolder = os.path.join(root_dir, entry)
        if not os.path.isdir(subfolder):
            continue

        for filename in sorted(os.listdir(subfolder)):
            if not filename.endswith(".txt"):
                continue

            parsed = parse_raw_email_file(os.path.join(subfolder, filename))
            if len(parsed["body"]) < MIN_BODY_LENGTH:
                continue

            text = clean_for_vectorizer(f"{parsed['subject']}\n{parsed['body']}")
            if not text:
                # clean_for_vectorizer can strip a body down to nothing (e.g.
                # a message that was almost entirely a URL) even when the
                # raw body passed MIN_BODY_LENGTH — an empty string here
                # becomes NaN on CSV round-trip and crashes TfidfVectorizer,
                # so it must never reach the output file.
                continue

            features = extract_features(parsed["subject"], parsed["body"], parsed["sender"])
            label = heuristic_priority_label(features)

            yield text, features, label


def main():
    records = list(iter_priority_records())
    if not records:
        raise RuntimeError("No records produced — check data/raw/enron/ contents.")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", *FEATURE_COLUMNS, "label"])
        for text, features, label in records:
            writer.writerow([text, *(features[col] for col in FEATURE_COLUMNS), label])

    counts = {}
    for _, _, label in records:
        counts[label] = counts.get(label, 0) + 1

    print(f"Wrote {len(records)} emails to {OUTPUT_PATH}")
    print("Priority distribution (heuristic pseudo-labels):", counts)


if __name__ == "__main__":
    main()
