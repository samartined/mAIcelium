"""Unit tests for mesh/commands/scripts/fuzzy.py.

Covers: norm, bigrams, similarity, and all branches of fuzzy_match.
"""
import os
import sys

import pytest

# Add mesh/commands/scripts/ to sys.path so we can import fuzzy directly.
_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_SCRIPTS_DIR = os.path.join(_REPO_ROOT, "mesh", "commands", "scripts")
if _SCRIPTS_DIR not in sys.path:
    sys.path.insert(0, _SCRIPTS_DIR)

from fuzzy import norm, bigrams, similarity, fuzzy_match  # noqa: E402


# ── norm ────────────────────────────────────────────────────────────────────

def test_norm_lowercases():
    assert norm("Hello") == "hello"


def test_norm_strips_hyphens():
    assert norm("my-project") == "myproject"


def test_norm_strips_underscores():
    assert norm("my_project") == "myproject"


def test_norm_strips_spaces():
    assert norm("my project") == "myproject"


def test_norm_combined():
    assert norm("Hello-World_Test") == "helloworldtest"


def test_norm_empty():
    assert norm("") == ""


# ── bigrams ─────────────────────────────────────────────────────────────────

def test_bigrams_empty_string():
    assert bigrams("") == set()


def test_bigrams_one_char():
    assert bigrams("a") == set()


def test_bigrams_two_chars():
    assert bigrams("ab") == {"ab"}


def test_bigrams_word():
    result = bigrams("abc")
    assert result == {"ab", "bc"}


# ── similarity ──────────────────────────────────────────────────────────────

def test_similarity_empty_first():
    assert similarity("", "hello") == 0.0


def test_similarity_empty_second():
    assert similarity("hello", "") == 0.0


def test_similarity_both_empty():
    assert similarity("", "") == 0.0


def test_similarity_identical():
    assert similarity("hello", "hello") == 1.0


def test_similarity_identical_after_norm():
    # norm("my-project") == norm("my_project") == "myproject"
    assert similarity("my-project", "my_project") == 1.0


def test_similarity_partial():
    # Should be between 0 and 1 for partially similar strings
    s = similarity("hello", "help")
    assert 0.0 < s < 1.0


# ── fuzzy_match: all branches ────────────────────────────────────────────────
# Pre-sorted candidate lists are used for deterministic order in ambiguous results.

class TestFuzzyMatchExactNormalized:
    """Branch 1: exact normalized match."""

    def test_exact_normalized_hyphens_vs_underscores(self):
        # norm('my_project') == norm('my-project') == 'myproject'
        match, ambiguous = fuzzy_match("my_project", ["my-project", "other"])
        assert match == "my-project"
        assert ambiguous == []

    def test_exact_normalized_case_insensitive(self):
        match, ambiguous = fuzzy_match("MyProject", ["myproject", "other"])
        assert match == "myproject"
        assert ambiguous == []

    def test_exact_normalized_returns_first_when_multiple(self):
        # If two candidates normalize identically to the input, the first wins.
        match, ambiguous = fuzzy_match("abc", ["abc", "ABC"])
        assert match == "abc"
        assert ambiguous == []


class TestFuzzyMatchSubstring:
    """Branch 2: substring containment — single, multiple→ambiguous."""

    def test_substring_single_match(self):
        match, ambiguous = fuzzy_match("proj", ["my-project", "another"])
        assert match == "my-project"
        assert ambiguous == []

    def test_substring_multiple_returns_ambiguous(self):
        # Both 'my-project' and 'another-project' contain 'project' after norm.
        candidates = ["another-project", "my-project"]  # pre-sorted alpha order
        match, ambiguous = fuzzy_match("project", candidates)
        assert match is None
        assert set(ambiguous) == {"my-project", "another-project"}

    def test_substring_input_contained_in_candidate(self):
        # norm('proj') in norm('my-project') → 'proj' in 'myproject'? Yes.
        # norm('my') in norm('my-project') → 'my' in 'myproject' → True
        match, ambiguous = fuzzy_match("my", ["my-project", "other-thing"])
        assert match == "my-project"
        assert ambiguous == []


class TestFuzzyMatchBigram:
    """Branch 3: bigram similarity scoring.

    All inputs in this class are verified NON-substrings of every candidate
    after norm(), so the substring branch (branch 2) never fires and the bigram
    scorer is the one actually exercised.
    """

    def test_bigram_single_match_above_threshold(self):
        # 'pyhtontool' is a transposition of 'python-tool' (norm: 'pythontool').
        # norm('pyhtontool') is not contained in norm('python-tool') or vice-versa,
        # so this reaches branch 3.  Score vs 'python-tool' ≈ 0.55 (>= 0.4),
        # score vs 'other-thing' ≈ 0.0 → only one candidate above threshold.
        match, ambiguous = fuzzy_match("pyhtontool", ["python-tool", "other-thing"])
        assert match == "python-tool"
        assert ambiguous == []

    def test_bigram_clear_winner_delta_above_015(self):
        # 'fastapiprj' (dropped 'o') is not a substring of 'fastapi-project' after
        # norm ('fastapiproject' does not contain 'fastapiprj' and vice-versa).
        # Score vs 'fastapi-project' ≈ 0.57, vs 'ruby-app' ≈ 0.07 → delta > 0.15.
        match, ambiguous = fuzzy_match(
            "fastapiprj", ["fastapi-project", "ruby-app"]
        )
        assert match == "fastapi-project"
        assert ambiguous == []

    def test_bigram_tie_delta_at_or_below_015(self):
        # 'pythen' is not a substring of 'python' or 'pythox' after norm, so
        # branch 2 is skipped.  Both candidates score ≈ 0.43 (delta == 0.0 ≤ 0.15)
        # → ambiguous result from branch 3.
        candidates = ["python", "pythox"]
        match, ambiguous = fuzzy_match("pythen", candidates)
        assert match is None
        assert set(ambiguous) == {"python", "pythox"}

    def test_bigram_ambiguous_tie_covers_line_51(self):
        """Explicitly cover the tie/ambiguous return path (fuzzy.py line ~51).

        When two or more candidates share the top bigram score AND the delta
        between top[0] and top[1] is <= 0.15, fuzzy_match returns (None, [top]).
        This is the branch that was previously uncovered.

        Input 'pythen' reaches this path:
          - exact match: none (norm('pythen') not in candidates)
          - substring: none ('pythen' not in 'python'/'pythox' and vice-versa)
          - bigram: python ≈ 0.4286, pythox ≈ 0.4286 → delta == 0.0 → tie → ambiguous
        """
        match, ambiguous = fuzzy_match("pythen", ["python", "pythox"])
        assert match is None, "tie must return None for match"
        assert set(ambiguous) == {"python", "pythox"}, (
            "tie must return both close candidates"
        )

    def test_bigram_just_above_04_boundary(self):
        # pyton vs python-tool has similarity ~0.44 (above 0.4), single candidate above it
        match, ambiguous = fuzzy_match("pyton", ["python-tool"])
        assert match == "python-tool"
        assert ambiguous == []

    def test_bigram_below_04_no_match(self):
        # 'zzz' shares no bigrams with 'python-tool' or 'ruby-app'
        match, ambiguous = fuzzy_match("zzz", ["python-tool", "ruby-app"])
        assert match is None
        assert ambiguous == []


class TestFuzzyMatchEdgeCases:
    """Edge cases: empty input, empty candidates."""

    def test_empty_input(self):
        # norm('') == '' which never matches candidates via exact/substring/bigram
        # but '' in norm(c) is True (empty string is substring of everything)
        # → all candidates match as substrings → ambiguous if multiple, single if one
        match, ambiguous = fuzzy_match("", ["my-project"])
        # '' in 'myproject' → True, only 1 → single match
        assert match == "my-project"
        assert ambiguous == []

    def test_empty_candidate_list(self):
        match, ambiguous = fuzzy_match("something", [])
        assert match is None
        assert ambiguous == []

    def test_empty_input_multiple_candidates_returns_ambiguous(self):
        # '' is a substring of every candidate → all match → ambiguous
        candidates = ["alpha", "beta"]
        match, ambiguous = fuzzy_match("", candidates)
        assert match is None
        assert set(ambiguous) == {"alpha", "beta"}
