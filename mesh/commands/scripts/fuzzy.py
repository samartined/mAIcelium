"""Shared fuzzy-matching utilities for mAIcelium project commands."""


def norm(s):
    """Normalize a string for comparison: lowercase, strip separators."""
    return s.lower().replace("-", "").replace("_", "").replace(" ", "")


def bigrams(s):
    """Return the set of character bigrams in a string."""
    return set(s[i : i + 2] for i in range(len(s) - 1))


def similarity(a, b):
    """Jaccard similarity between two strings based on bigrams."""
    ba, bb = bigrams(norm(a)), bigrams(norm(b))
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)


def fuzzy_match(user_input, candidates):
    """Return (match, ambiguous_candidates) from a list of candidate names.

    Returns a single match when confident, or a list of close candidates
    when the input is ambiguous.
    """
    inp = norm(user_input)

    # 1. Exact normalized match
    exact = [c for c in candidates if norm(c) == inp]
    if exact:
        return exact[0], []

    # 2. Substring containment
    substr = [c for c in candidates if inp in norm(c) or norm(c) in inp]
    if len(substr) == 1:
        return substr[0], []
    if len(substr) > 1:
        return None, substr

    # 3. Bigram similarity scoring
    scored = [(c, similarity(user_input, c)) for c in candidates]
    scored.sort(key=lambda x: -x[1])
    top = [(c, s) for c, s in scored if s >= 0.4]

    if not top:
        return None, []
    if len(top) == 1 or top[0][1] - top[1][1] > 0.15:
        return top[0][0], []
    return None, [c for c, _ in top[:5]]
