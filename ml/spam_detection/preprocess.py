"""
Builds the spam-detection training set from the SpamAssassin public
corpus (data/raw/spamassassin/20030228_easy_ham/easy_ham/,
20030228_hard_ham/hard_ham/, 20030228_spam/spam/) — each a flat folder of
raw RFC822 email files, no headers/labels file needed since the folder
itself IS the label (ham vs spam).

"hard_ham" is legitimate email that LOOKS spammy (heavy formatting,
marketing-style language) — including it in the ham class is what forces
the model to learn real spam signal instead of just "looks promotional",
which is exactly why the corpus ships it separately.

Run: python -m ml.spam_detection.preprocess
"""

import csv
import os

from ml.common.text_cleaning import clean_for_vectorizer, parse_raw_email_file

SPAMASSASSIN_ROOT = os.path.join("data", "raw", "spamassassin")
OUTPUT_PATH = os.path.join("data", "processed", "spam.csv")

# (subfolder name, label) — 0 = ham, 1 = spam. Supports both the 3-folder
# and 5-folder (with _2 suffixes) releases of the corpus transparently.
SOURCE_FOLDERS = [
    ("20030228_easy_ham/easy_ham", 0),
    ("20030228_easy_ham_2/easy_ham_2", 0),
    ("20030228_hard_ham/hard_ham", 0),
    ("20030228_spam/spam", 1),
    ("20030228_spam_2/spam_2", 1),
]

MIN_BODY_LENGTH = 10


def iter_spamassassin_records(root_dir: str = SPAMASSASSIN_ROOT):
    found_any_folder = False

    for relative_path, label in SOURCE_FOLDERS:
        folder = os.path.join(root_dir, relative_path)
        if not os.path.isdir(folder):
            continue
        found_any_folder = True

        for filename in sorted(os.listdir(folder)):
            file_path = os.path.join(folder, filename)
            if not os.path.isfile(file_path):
                continue

            parsed = parse_raw_email_file(file_path)
            text = f"{parsed['subject']}\n{parsed['body']}"
            text = clean_for_vectorizer(text)
            if len(text) < MIN_BODY_LENGTH:
                continue

            yield text, label

    if not found_any_folder:
        raise FileNotFoundError(
            f"No SpamAssassin folders found under {root_dir!r}. Expected at least "
            f"20030228_easy_ham/easy_ham, 20030228_hard_ham/hard_ham, "
            f"20030228_spam/spam."
        )


def main():
    records = list(iter_spamassassin_records())
    if not records:
        raise RuntimeError("No spam/ham records found — check data/raw/spamassassin/ contents.")

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["text", "label"])
        writer.writerows(records)

    ham_count = sum(1 for _, label in records if label == 0)
    spam_count = sum(1 for _, label in records if label == 1)
    print(f"Wrote {len(records)} emails to {OUTPUT_PATH}")
    print(f"Class distribution: ham={ham_count}, spam={spam_count}")


if __name__ == "__main__":
    main()
