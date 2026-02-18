"""
prompt-compress: YAML + Abbreviation + Emoji Semantic Injection for LLM prompts.

Three-layer prompt compression that achieves 53% token savings on complex
workflow prompts with zero information loss — and optionally learns over time.
"""

__version__ = "0.1.0"

from .tokenizer import estimate_tokens
from .abbreviation import (
    apply_abbreviation,
    expand_abbreviation,
    suggest_vocab,
    ABBREV_VOCAB,
    ABBREV_EXPANSIONS,
)
from .vocab_pack import load_vocab_pack
from .codebook import Codebook
from .compress import compress, CompressResult
