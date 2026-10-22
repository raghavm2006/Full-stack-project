"""
Builds the categorization training set from the Berkeley "Enron with
categories" corpus (data/raw/enron/enron_with_categories/enron_with_categories/,
folders 1-8, each email as <id>.txt + a matching <id>.cats file).

SCOPE NOTE (read this before trusting the 9-category spec at face value):
This corpus's .cats files label each email against a hand-built academic
taxonomy — NOT EmailOrbit's 9 target categories. Its top-level "Coarse
genre" system (system 1) distinguishes business/personal/logistics/
employment/document-collaboration/empty messages. Enron is corporate
operational email, so it simply contains no real Finance, Shopping,
Travel, Social, or Promotions examples — no amount of preprocessing
manufactures signal that isn't in the data.

Decision (confirmed with the project owner): train categorization on the
3 categories Enron actually supports — Work, Personal, Other — and
document this as a deliberate, honest scope limitation rather than
silently forcing a 9-way classifier to guess at categories it never saw
a single real example of. Phase 7's inference code returns "Other" (or a
low-confidence flag) for anything a model this narrow can't speak to.

Run: python -m ml.categorization.preprocess
"""

import csv
import os

from ml.common.text_cleaning import clean_for_vectorizer, parse_raw_email_file

ENRON_ROOT = os.path.join("data", "raw", "enron", "enron_with_categories", "enron_with_categories")
OUTPUT_PATH = os.path.join("data", "processed", "categorization.csv")

# Berkeley "Coarse genre" (system 1) subcategory -> EmailOrbit category.
# See categories.txt inside the corpus for the full taxonomy definition.
GENRE_SUBCATEGORY_TO_LABEL = {
    1: "Work",       # Company Business, Strategy, etc.
    2: "Personal",   # Purely Personal
    3: "Personal",   # Personal but in professional context
    4: "Work",       # Logistic Arrangements (meeting scheduling, tech support)
    5: "Work",       # Employment arrangements (job seeking, hiring)
    6: "Work",       # Document editing/checking (collaboration)
    7: "Other",      # Empty message (missing attachment)
    8: "Other",      # Empty message
}

MIN_BODY_LENGTH = 20  # drop near-empty emails; they carry no categorization signal


def _read_cats_file(path: str):
    """
    Each line is "n1,n2,n3" (system, subcategory, frequency). We only
    care about system 1 (coarse genre) lines; if an email has more than
    one (rare — a handful of borderline emails were double-labeled), we
    take the one with the highest recorded frequency.
    """
    best = None  # (frequency, subcategory)
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            parts = line.split(",")
            if len(parts) != 3:
                continue
            system, subcategory, frequency = (int(p) for p in parts)
            if system != 1:
                continue
            if best is None or frequency > best[0]:
                best = (frequency, subcategory)

    if best is None:
        return None
    return GENRE_SUBCATEGORY_TO_LABEL.get(best[1])


def iter_enron_records(root_dir: str = ENRON_ROOT):
    """Yields (text, label) for every email that has a usable coarse-genre label."""
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
            if not filename.endswith(".cats"):
                continue

            message_id = filename[: -len(".cats")]
            cats_path = os.path.join(subfolder, filename)
            txt_path = os.path.join(subfolder, f"{message_id}.txt")
            if not os.path.isfile(txt_path):
                continue

            label = _read_cats_file(cats_path)
            if label is None:
                continue

            parsed = parse_raw_email_file(txt_path)
            text = f"{parsed['subject']}\n{parsed['body']}"
            text = clean_for_vectorizer(text)
            if len(text) < MIN_BODY_LENGTH:
                continue

            yield text, label


def main():
    records = list(iter_enron_records())
    if not records:
        raise RuntimeError("No labeled Enron records found — check data/raw/enron/ contents.")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "label"])
        writer.writerows(records)

    counts = {}
    for _, label in records:
        counts[label] = counts.get(label, 0) + 1

    print(f"Wrote {len(records)} labeled emails to {OUTPUT_PATH}")
    print("Class distribution:", counts)


if __name__ == "__main__":
    main()
