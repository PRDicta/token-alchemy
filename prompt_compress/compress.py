"""
Top-level compression interface.

Orchestrates the three-layer pipeline:
    Layer 1: YAML structure (LLM-guided — prose -> structured YAML)
    Layer 2: Abbreviation (programmatic — multi-word phrases -> acronyms)
    Layer 3: Emoji semantic injection (LLM-guided — emoji as dense meaning carriers)

Layer 1 and Layer 3 require an LLM. This module handles Layer 2 programmatically
and provides measurement/reporting across all layers.
"""

from dataclasses import dataclass, field
from typing import Optional

from .tokenizer import estimate_tokens
from .abbreviation import apply_abbreviation, expand_abbreviation


@dataclass
class CompressResult:
    """Result of a compression operation with full metrics."""
    text: str
    original_tokens: int
    compressed_tokens: int
    savings_pct: float
    substitutions: int = 0
    unique_abbrevs: int = 0
    skipped_floor_guard: int = 0
    layers_applied: list = field(default_factory=list)

    @property
    def tokens_saved(self) -> int:
        return self.original_tokens - self.compressed_tokens


def compress(text: str, abbreviate: bool = True, extra_vocab=None) -> CompressResult:
    """Apply programmatic compression layers to text.

    This handles Layer 2 (abbreviation). Layers 1 (YAML) and 3 (emoji)
    are LLM-guided and should be applied before calling this function.

    Args:
        text: Input text (ideally already YAML-compressed by an LLM)
        abbreviate: Whether to apply abbreviation compression
        extra_vocab: Additional (pattern, replacement, flags) tuples

    Returns:
        CompressResult with compressed text and full metrics
    """
    original_tokens = estimate_tokens(text)
    layers = []

    if abbreviate:
        text, subs, unique, skipped = apply_abbreviation(text, extra_vocab=extra_vocab)
        layers.append("abbreviation")
    else:
        subs, unique, skipped = 0, 0, 0

    compressed_tokens = estimate_tokens(text)
    savings = round((1 - compressed_tokens / original_tokens) * 100, 1) if original_tokens else 0

    return CompressResult(
        text=text,
        original_tokens=original_tokens,
        compressed_tokens=compressed_tokens,
        savings_pct=savings,
        substitutions=subs,
        unique_abbrevs=unique,
        skipped_floor_guard=skipped,
        layers_applied=layers,
    )


def measure(original_prose: str, compressed_yaml: str) -> dict:
    """Measure compression ratio between original prose and compressed YAML.

    Useful for benchmarking: pass in the original verbose prompt and the
    YAML+emoji compressed version to get detailed metrics.

    Returns:
        dict with token counts, savings percentage, and per-layer breakdown
    """
    orig_tokens = estimate_tokens(original_prose)
    comp_tokens = estimate_tokens(compressed_yaml)

    # Try abbreviation layer on the compressed version
    abbrev_result = compress(compressed_yaml, abbreviate=True)

    return {
        "original_tokens": orig_tokens,
        "yaml_tokens": comp_tokens,
        "yaml_savings_pct": round((1 - comp_tokens / orig_tokens) * 100, 1) if orig_tokens else 0,
        "yaml_plus_abbrev_tokens": abbrev_result.compressed_tokens,
        "total_savings_pct": round((1 - abbrev_result.compressed_tokens / orig_tokens) * 100, 1) if orig_tokens else 0,
        "abbrev_substitutions": abbrev_result.substitutions,
        "abbrev_skipped_floor": abbrev_result.skipped_floor_guard,
    }
