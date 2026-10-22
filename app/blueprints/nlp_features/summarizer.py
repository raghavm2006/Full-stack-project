"""
Phase 8: extractive summarization.

Deliberately not a transformer/LLM call — rule #14/#15 (no training or
heavy inference inside a web request, and everything must run offline/
locally without an external API key). This is classic frequency-based
extractive summarization: score every sentence by how many
"important" (frequent, non-stopword) words it contains, then keep the
top-scoring sentences in their original order. No model file, no
training step — pure text processing, so it's trivial to unit test and
has zero cold-start cost.
"""

import re
from collections import Counter
from app.blueprints.emails.parser import clean_template_comments

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|[\r\n]+")
_WORD_PATTERN = re.compile(r"[A-Za-z']+")
_DETAIL_PATTERN = re.compile(
    r"\b(?:due|deadline|before|by|tomorrow|today|monday|tuesday|wednesday|"
    r"thursday|friday|saturday|sunday|please|must|required|confirm|submit|"
    r"send|review|cancel|changed|rescheduled|shared|permission|access|"
    r"do not|don't|cannot|can't)\b|\d", re.I
)

# A small built-in stopword list (no nltk/spacy download required) plus a
# few email-specific filler words that would otherwise dominate scoring.
_STOPWORDS = {
    "a", "an", "the", "and", "or", "but", "if", "then", "so", "of", "to",
    "in", "on", "for", "with", "is", "are", "was", "were", "be", "been",
    "being", "this", "that", "these", "those", "it", "its", "as", "at",
    "by", "from", "into", "about", "than", "also", "we", "you", "i",
    "he", "she", "they", "them", "our", "your", "their", "will", "would",
    "can", "could", "should", "not", "no", "do", "does", "did", "have",
    "has", "had", "please", "thanks", "thank", "regards", "hi", "hello",
    "dear", "best", "sincerely",
}


def summarize_text(text: str, max_sentences: int = 6, max_chars: int = 1000) -> str:
    """
    Keeps context and informative details, in their original order,
    within both the sentence and character budgets. Returns cleaned text if it's
    already at or below `max_sentences` sentences — no point summarizing
    a one-line email. Returns "" for empty input.
    """
    if not text or not text.strip() or max_sentences <= 0 or max_chars <= 0:
        return ""

    text = clean_template_comments(text)
    sentences = []
    seen = set()
    for part in _SENTENCE_SPLIT.split(text):
        sentence = " ".join(part.split())
        key = sentence.casefold().rstrip(".!?")
        if not key or key in seen:
            continue
        seen.add(key)
        sentences.append(sentence)

    def bounded(parts):
        result = " ".join(parts)
        if len(result) <= max_chars:
            return result
        prefix = result[:max_chars - 1]
        if " " in prefix:
            prefix = prefix.rsplit(" ", 1)[0]
        return prefix.rstrip(" ,;:") + "…"
    if not sentences:
        return ""
    if len(sentences) <= max_sentences:
        return bounded(sentences)

    words = [
        w.lower()
        for w in _WORD_PATTERN.findall(" ".join(sentences))
        if w.lower() not in _STOPWORDS and len(w) > 2
    ]
    if not words:
        return bounded(sentences[:max_sentences])

    frequencies = Counter(words)
    max_freq = max(frequencies.values())
    weights = {word: count / max_freq for word, count in frequencies.items()}

    scored = []
    for index, sentence in enumerate(sentences):
        sentence_words = [w.lower() for w in _WORD_PATTERN.findall(sentence)]
        if not sentence_words:
            continue
        score = sum(weights.get(w, 0.0) for w in sentence_words) / len(sentence_words)
        # Retain purpose, dates, instructions and restrictions, even when
        # their vocabulary occurs only once in the message.
        score += 0.18 if _DETAIL_PATTERN.search(sentence) else 0
        score += 0.12 if index == 0 else 0
        if len(sentence_words) < 4:
            score *= 0.5
        scored.append((index, sentence, score))

    # Prefer different information over several highly similar sentences.
    top = []
    remaining = list(scored)
    used_chars = 0
    while remaining and len(top) < max_sentences:
        def adjusted(item):
            terms = set(_WORD_PATTERN.findall(item[1].lower())) - _STOPWORDS
            overlap = max((len(terms & previous) / max(1, len(terms | previous))
                           for previous in selected_terms), default=0)
            return item[2] - 0.25 * overlap

        selected_terms = [set(_WORD_PATTERN.findall(item[1].lower())) - _STOPWORDS
                          for item in top]
        best = max(remaining, key=adjusted)
        remaining.remove(best)
        length = len(best[1]) + bool(top)
        if used_chars + length <= max_chars or not top:
            top.append(best)
            used_chars += length
    top_in_order = sorted(top, key=lambda item: item[0])
    return bounded([sentence for _, sentence, _ in top_in_order])
