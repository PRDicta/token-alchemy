"""
Token estimation using Claude's real BPE tokenizer.

Priority:
1. Real Claude tokenizer (claude.json + tiktoken) — exact counts
2. Heuristic fallback — BPE-aware estimation, ~6-10% error vs real

The real tokenizer is lazy-loaded on first call. If tiktoken is not
installed or claude.json is missing, the heuristic is used silently.
"""

import os
import re

# ── Lazy-loaded Claude BPE encoder ──────────────────────────────────────────
_claude_encoder = None
_claude_encoder_loaded = False


def _get_claude_encoder():
    """Lazy-load the real Claude BPE tokenizer. Returns encoder or None."""
    global _claude_encoder, _claude_encoder_loaded
    if _claude_encoder_loaded:
        return _claude_encoder
    _claude_encoder_loaded = True
    try:
        import tiktoken
        import json
        import base64

        vocab_path = os.path.join(os.path.dirname(__file__), "claude.json")
        if not os.path.isfile(vocab_path):
            return None

        with open(vocab_path, "r", encoding="utf-8") as f:
            config = json.load(f)

        parts = config["bpe_ranks"].split(" ")
        offset = int(parts[1])
        tokens = parts[2:]
        rank_map = {base64.b64decode(t): offset + i for i, t in enumerate(tokens)}

        _claude_encoder = tiktoken.Encoding(
            name="claude",
            pat_str=config["pat_str"],
            mergeable_ranks=rank_map,
            special_tokens=config["special_tokens"],
        )
        return _claude_encoder
    except Exception:
        return None


def estimate_tokens(text: str) -> int:
    """Count tokens using Claude's real BPE tokenizer when available.

    Falls back to a heuristic that handles emoji correctly (~3 tokens each)
    and standard BPE word splitting (~6-10% error margin).
    """
    if not text:
        return 0

    # Try real tokenizer first
    enc = _get_claude_encoder()
    if enc is not None:
        try:
            return len(enc.encode(text))
        except Exception:
            pass

    # ── Heuristic fallback ──────────────────────────────────────────────
    tokens = 0
    chunks = re.findall(
        r'[\U00010000-\U0010ffff][\ufe00-\ufe0f\u200d]*'
        r'|[\u2600-\u27bf\u2b50-\u2bff][\ufe00-\ufe0f\u200d]*'
        r'|[\u00a7\u00a9\u00ae\u203c\u2049\u2122\u2139\u2194-\u21aa]'
        r'|[\ufe00-\ufe0f\u200d]+'
        r'|[a-zA-Z_][a-zA-Z0-9_]*'
        r'|\d+'
        r'|[^\s\w]'
        r'|\s+',
        text
    )

    for chunk in chunks:
        if not chunk:
            continue
        first_char = chunk[0]
        code_point = ord(first_char)

        if code_point in range(0xFE00, 0xFE10) or code_point == 0x200D:
            continue

        if code_point > 0x1F00 or code_point in range(0x2600, 0x27C0) or code_point in range(0x2B50, 0x2C00):
            tokens += 3  # Most emoji = 2-4 tokens, avg ~3

        elif code_point in (0x00A7, 0x00A9, 0x00AE, 0x2122, 0x2139):
            tokens += 1

        elif first_char.isalpha() or first_char == '_':
            word_len = len(chunk)
            if word_len <= 7:
                tokens += 1
            elif word_len <= 12:
                tokens += 2
            else:
                tokens += max(2, word_len // 5)

        elif first_char.isdigit():
            tokens += max(1, len(chunk) // 3)

        elif first_char.isspace():
            newlines = chunk.count('\n')
            tokens += newlines
            if newlines == 0 and len(chunk) > 1:
                tokens += 1

        else:
            tokens += 1

    return max(1, tokens)
