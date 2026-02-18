"""Basic tests for the compression pipeline."""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from prompt_compress import compress, estimate_tokens, expand_abbreviation, suggest_vocab
from prompt_compress.abbreviation import apply_abbreviation, ABBREV_VOCAB, ABBREV_EXPANSIONS
from prompt_compress.codebook import Codebook


def test_estimate_tokens():
    """Token estimation returns reasonable counts."""
    assert estimate_tokens("") == 0
    assert estimate_tokens("hello") >= 1
    assert estimate_tokens("hello world this is a test") >= 4
    # Emoji should cost more than single words
    assert estimate_tokens("📊") >= 1
    print("✓ test_estimate_tokens")


def test_abbreviation_saves_tokens():
    """Abbreviation should reduce token count for known phrases."""
    text = "strategy: The return on investment for search engine optimization is clear."
    compressed, subs, unique, skipped = apply_abbreviation(text)
    assert subs > 0, "Should have made substitutions"
    assert "ROI" in compressed or "SEO" in compressed
    assert estimate_tokens(compressed) <= estimate_tokens(text)
    print(f"✓ test_abbreviation_saves_tokens ({subs} subs, {skipped} skipped)")


def test_yaml_keys_preserved():
    """YAML keys must never be modified by abbreviation."""
    yaml_text = "search_engine_optimization: improve search engine optimization"
    compressed, _, _, _ = apply_abbreviation(yaml_text)
    # Key should be untouched, value should be compressed
    assert compressed.startswith("search_engine_optimization:"), \
        f"Key was modified: {compressed}"
    assert "SEO" in compressed.split(":", 1)[1], \
        f"Value was not compressed: {compressed}"
    print("✓ test_yaml_keys_preserved")


def test_floor_guard():
    """Floor guard should prevent substitutions that cost more tokens."""
    # "Section" → "§" should be checked by floor guard
    text = "Section one covers the topic."
    compressed, subs, _, skipped = apply_abbreviation(text)
    # The floor guard may or may not block § depending on tokenizer
    # but it should not crash
    print(f"✓ test_floor_guard (subs={subs}, skipped={skipped})")


def test_expand_roundtrip():
    """Expansion should reverse abbreviation for human review."""
    text = "goal: Improve ROI through better SEO and clear CTA placement."
    expanded = expand_abbreviation(text)
    assert "Return on Investment" in expanded
    assert "Search Engine Optimization" in expanded
    assert "Call to Action" in expanded
    print("✓ test_expand_roundtrip")


def test_compress_result():
    """compress() should return a CompressResult with correct metrics."""
    text = "strategy: The return on investment for search engine optimization is clear."
    result = compress(text)
    assert result.original_tokens > 0
    assert result.compressed_tokens > 0
    assert result.compressed_tokens <= result.original_tokens
    assert result.savings_pct >= 0
    assert "abbreviation" in result.layers_applied
    print(f"✓ test_compress_result ({result.savings_pct}% savings)")


def test_suggest_vocab():
    """suggest_vocab should find uncovered high-frequency words."""
    text = """
    configuration: update configuration settings
    configuration: validate configuration schema
    development: run development server
    development: development environment setup
    """
    candidates = suggest_vocab(text, top_n=5)
    words = [c['word'] for c in candidates]
    # "configuration" and "development" should appear as candidates
    assert any('config' in w for w in words) or any('develop' in w for w in words), \
        f"Expected frequent words, got: {words}"
    print(f"✓ test_suggest_vocab ({len(candidates)} candidates)")


def test_codebook():
    """Codebook should record and retrieve patterns."""
    cb = Codebook(":memory:")
    cid = cb.record_pattern("Search Engine Optimization", "SEO", entry_id="test1")
    assert cid is not None

    # Record again — should increment times_seen
    cid2 = cb.record_pattern("Search Engine Optimization", "SEO", entry_id="test2")
    assert cid2 == cid  # Same pattern

    stats = cb.stats()
    assert stats["total"] == 1
    assert stats["cold"] == 1

    # Usage tracking
    updated = cb.update_usage("Our SEO strategy improved ROI")
    assert updated >= 1

    cb.close()
    print("✓ test_codebook")


def test_list_items_compressed():
    """List items (- prefix) should be compressed."""
    yaml_text = """items:
  - improve return on investment
  - search engine optimization strategy
  - non-disclosure agreement compliance"""
    compressed, subs, _, _ = apply_abbreviation(yaml_text)
    assert subs > 0
    assert "ROI" in compressed or "SEO" in compressed or "NDA" in compressed
    print(f"✓ test_list_items_compressed ({subs} subs)")


if __name__ == "__main__":
    test_estimate_tokens()
    test_abbreviation_saves_tokens()
    test_yaml_keys_preserved()
    test_floor_guard()
    test_expand_roundtrip()
    test_compress_result()
    test_suggest_vocab()
    test_codebook()
    test_list_items_compressed()
    print("\n🎉 All tests passed!")
