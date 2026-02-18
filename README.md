# Token Alchemy

Three-layer LLM prompt compression that dramatically reduces token cost on complex workflow prompts — with zero information loss and, in some cases, *improved* model output.

**Example result** on a heavy content-focused prompt:

```
Original:  11,473 tokens (verbose prose)
Compressed: 5,382 tokens (YAML + abbreviation + emoji)
Savings:    53% — compressed version outperformed the original on several dimensions
```

## What this does

Large, carefully-written system prompts (behavioral profiles, workflow instructions, style guides) burn context window tokens at boot. This library provides a compression pipeline that shrinks them dramatically while preserving — and in some cases *improving* — model output quality.

The pipeline has three layers:

| Layer | Method | Who does it | Savings |
|-------|--------|-------------|---------|
| **1. YAML structure** | Prose → structured YAML | LLM (you prompt it) | ~40-50% |
| **2. Abbreviation** | Multi-word phrases → acronyms | Programmatic (this library) | ~3-8% |
| **3. Emoji semantic injection** | Emoji as dense meaning carriers | LLM (you prompt it) | Semantic density, not token savings |

Layer 3 is the interesting one. See [RESEARCH.md](RESEARCH.md) for the full findings.

## Install

```bash
pip install token-alchemy

# For exact token counting (optional, falls back to heuristic):
pip install token-alchemy[tokenizer]
```

Or from source:

```bash
git clone https://github.com/PRDicta/token-alchemy
cd token-alchemy
pip install -e .
```

## Quick start

### Measure compression ratio

```python
from prompt_compress import compress, estimate_tokens
from prompt_compress.compress import measure

original = open("my_prompt_verbose.txt").read()
compressed = open("my_prompt_yaml.yaml").read()

stats = measure(original, compressed)
print(f"YAML savings: {stats['yaml_savings_pct']}%")
print(f"YAML + abbrev: {stats['total_savings_pct']}%")
```

### Apply abbreviation layer

```python
from prompt_compress import compress

yaml_text = """
content_profile:
  tone: conversational but professional
  audience: business to business decision makers
  key_performance_indicators:
    - return on investment messaging
    - search engine optimization alignment
    - call to action clarity
"""

result = compress(yaml_text)
print(result.text)
# content_profile:
#   tone: conversational but professional
#   audience: B2B decision makers
#   key_performance_indicators:
#     - ROI messaging
#     - SEO alignment
#     - CTA clarity

print(f"Tokens: {result.original_tokens} → {result.compressed_tokens} ({result.savings_pct}% saved)")
print(f"Substitutions: {result.substitutions}, Floor-guarded: {result.skipped_floor_guard}")
```

### Expand back for review

```python
from prompt_compress import expand_abbreviation

readable = expand_abbreviation(result.text)
print(readable)
# All abbreviations restored to full phrases for human review
```

### Use domain-specific vocab packs

```python
from prompt_compress import compress, load_vocab_pack

marketing_vocab = load_vocab_pack("example_marketing")
result = compress(yaml_text, extra_vocab=marketing_vocab)
```

### Suggest new vocabulary entries

```python
from prompt_compress import suggest_vocab

candidates = suggest_vocab(yaml_text, top_n=10)
for c in candidates:
    print(f"  {c['word']} (x{c['count']}) → {c['suggested_abbrev']}  "
          f"(~{c['est_chars_saved']} chars saved)")
```

### Track patterns with the codebook (learning layer)

```python
from prompt_compress import Codebook

cb = Codebook("my_patterns.db")  # or ":memory:" for ephemeral

# Record patterns from a compression operation
cb.extract_patterns(compressed_yaml_text)

# At boot/reload, update usage stats
cb.update_usage(active_compressed_text)

# Check health
print(cb.stats())
# {'total': 42, 'cold': 30, 'warm': 10, 'hot': 2, ...}
```

## The token-aware floor guard

Every abbreviation substitution is validated at runtime:

```
"Search Engine Optimization" → "SEO"
  Original: 3 tokens → Replacement: 2 tokens → APPLIED (saves 1)

"thought leadership" → "thought ldrshp"
  Original: 2 tokens → Replacement: 3 tokens → BLOCKED (costs more)
```

The floor guard uses Claude's real BPE tokenizer (via `tiktoken` + bundled `claude.json`) when available, falling back to a heuristic with ~6-10% error margin. This prevents the common trap of character-level compression that inflates token count.

## YAML keys are never modified

A hard design constraint: abbreviation and emoji substitution only touch YAML **values** and list items. Keys are structural identifiers — shortening `phase_1_gathering` to an emoji would break parsers and confuse models reading the structure. The `v` flag in the vocabulary enforces value-only matching.

## Vocab pack format

Domain-specific packs are JSON arrays:

```json
[
  {"pattern": "\\bcustomer relationship management\\b", "replacement": "CRM", "flags": "vi"},
  {"pattern": "\\bpay per click\\b", "replacement": "PPC", "flags": "vi"}
]
```

Flags: `v` = values only (YAML-safe), `i` = case-insensitive, `a` = anywhere.

## Persistent memory integration

This library is standalone, but it's designed to get better over time when connected to a persistent memory system. The `Codebook` class tracks which compression patterns survive across sessions, and a memory system can use that signal to:

1. **Learn domain vocabulary** — frequent words that aren't in the built-in vocab get surfaced by `suggest_vocab()` and can be promoted to permanent vocab entries.
2. **Promote proven patterns** — patterns that decode correctly across many cold-context transfers gain confidence and can be compressed more aggressively (COLD → WARM → HOT).
3. **Adapt to the user** — different users and domains have different high-frequency terms. The codebook learns *your* vocabulary, not a generic one.

The reference integration is [The Librarian](https://github.com/PRDicta/The-Librarian), a persistent memory system for LLM assistants. But any system that persists the codebook SQLite database between sessions will benefit.

## How to do Layer 1 (YAML compression)

Layer 1 is an LLM task, not a programmatic one. Prompt your model with something like:

> Compress the following instructions into structured YAML. Preserve all semantic content, constraints, and behavioral rules. Use nested keys for hierarchy. Keep it machine-readable — another LLM will consume this directly.

The key insight: LLMs read YAML structure faster and more reliably than prose paragraphs. The hierarchy itself carries meaning that prose has to spell out with transition words.

## How to do Layer 3 (emoji semantic injection)

Layer 3 is also LLM-guided. After YAML compression, inject emoji as semantic anchors:

> Add emoji markers to the YAML values where they serve as semantic density carriers — visual pipeline indicators (→, ⚡, ✓/✗), tonal calibrators, and domain anchors. The emoji should encode meaning a model can decode, not just decoration.

See [RESEARCH.md](RESEARCH.md) for the evidence that this works — 3.2x semantic expansion ratio confirmed across cold-context transfer tests.

## License

AGPL-3.0 / Commercial dual license — Dicta Technologies Inc., 2026
