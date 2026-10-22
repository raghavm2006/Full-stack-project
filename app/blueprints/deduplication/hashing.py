"""
Phase 10: content hashing for exact-duplicate detection.

Deliberately exact-match (normalized subject+body -> one hash), not
fuzzy/near-duplicate matching — a hash comparison is instant, needs no
extra dependency, and is trivial to explain and test, at the cost of
missing near-duplicates that differ by a signature line or a re-quoted
thread. Worth stating as a scope limitation in the project report, same
as Phase 6's 3-class categorization decision.
"""

import hashlib
import re

_NON_ALNUM = re.compile(r"[^a-z0-9\s]")
_WHITESPACE = re.compile(r"\s+")


def compute_content_hash(subject, body):
    """
    Returns a stable hash of `subject`+`body` after lowercasing, dropping
    punctuation, and collapsing whitespace — so trivial formatting
    differences (extra blank lines, punctuation) don't prevent two
    otherwise-identical emails from matching. Returns None for
    effectively empty input (nothing meaningful to hash).
    """
    normalized = f"{subject or ''} {body or ''}".lower()
    normalized = _NON_ALNUM.sub(" ", normalized)
    normalized = _WHITESPACE.sub(" ", normalized).strip()

    if not normalized:
        return None

    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()
