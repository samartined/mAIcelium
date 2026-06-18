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
        # norm('proj') in norm('my-project') → 'proj' in 'myproject'? No.
        # norm('my') in norm('my-project') → 'my' in 'myproject' → True
        match, ambiguous = fuzzy_match("my", ["my-project", "other-thing"])
        assert match == "my-project"
        assert ambiguous == []


class TestFuzzyMatchBigram:
    """Branch 3: bigram similarity scoring."""

    def test_bigram_single_match_above_threshold(self):
        # Only one candidate has score >= 0.4 → clear winner via len(top)==1
        match, ambiguous = fuzzy_match("pytho", ["python-tool", "other-thing"])
        assert match == "python-tool"
        assert ambiguous == []

    def test_bigram_clear_winner_delta_above_015(self):
        # fastapi-proj vs fastapi-project: ~0.77, vs ruby-app: ~0.07 → delta > 0.15
        match, ambiguous = fuzzy_match(
            "fastapi-proj", ["fastapi-project", "ruby-app"]
        )
        assert match == "fastapi-project"
        assert ambiguous == []

    def test_bigram_tie_delta_at_or_below_015(self):
        # 'project' vs 'project-alpha' and 'project-beta' are very close scores
        # (delta ≈ -0.05, so both top[0][1] - top[1][1] ≤ 0.15)
        candidates = ["project-alpha", "project-beta"]
        match, ambiguous = fuzzy_match("project", candidates)
        assert match is None
        assert set(ambiguous) == {"project-alpha", "project-beta"}

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
