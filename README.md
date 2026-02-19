# Token Alchemy

Three-layer LLM prompt compression that dramatically reduces token cost on complex workflow prompts — with zero information loss and, in some cases, *improved* model output.

If Token Alchemy was useful to you, please consider [buying me a drink](https://buymeacoffee.com/chief_librarian).

**Example result** on a production multi-document prompt system (8 documents, token counts verified via Anthropic's `count_tokens` API):

```
Original:  64,669 tokens (verbose prose across 8 documents)
Compressed: 20,986 tokens (YAML + abbreviation + emoji)
Savings:    67.5% — Tier 1 rules at 100% fidelity, zero quality regression on structural compression
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

## Requirements

- **Python 3.9+**
- Optional: `tiktoken` for exact Claude BPE token counting (falls back to heuristic without it)

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

# Replace with paths to your own prompt files
original = open("my_prompt_verbose.txt").read()       # your original prose prompt
compressed = open("my_prompt_yaml.yaml").read()        # your YAML-compressed version

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

The reference integration is [The Librarian](https://github.com/PRDicta/The-Librarian), a persistent memory system for Claude on Cowork. But any system that persists the codebook SQLite database between sessions will benefit.

### Multi-document results

The three-stage model has been validated on a production system — 8 documents, 64,669 tokens, 8 iterative tests. Token counts verified via Anthropic's `count_tokens` API (claude-sonnet-4-5-20250929).

| Stage | Tokens | Reduction | Quality |
|-------|--------|-----------|---------|
| Baseline (uncompressed) | 64,669 | — | Reference |
| COLD (structural) | ~39,800 | ~38.4% | Tier 2 drift detected |
| WARM (+backstops) | ~40,000 | ~38.1% | Quality recovered, exceeds baseline |
| HOT (backstops baked in) | ~39,600 | ~38.8% | No regression, zero boot deps |
| Emoji-optimized (all docs) | 20,986 | **67.5%** | Tier 1 perfect, minor Tier 2 drift |

**Per-document breakdown:**

| Document | Original | Compressed | Comp. % | Emoji | Emoji % |
|----------|----------|------------|---------|-------|---------|
| Doc A | 20,524t | 13,680t | 33.3% | 6,884t | 66.5% |
| Doc B | 14,052t | 9,289t | 33.9% | 4,097t | 70.8% |
| Doc C | 8,549t | 6,525t | 23.7% | 3,166t | 63.0% |
| Doc D | 3,510t | 2,659t | 24.2% | 1,371t | 60.9% |
| Doc E | 5,071t | 2,570t | 49.3% | 2,044t | 59.7% |
| Doc F | 7,839t | 2,474t | 68.4% | 1,635t | 79.1% |
| Doc G | 5,124t | 2,402t | 53.1% | 1,789t | 65.1% |
| **Total** | **64,669t** | **39,599t** | **38.8%** | **20,986t** | **67.5%** |

Compressed → Emoji incremental: 47.0% further reduction.

The key finding: compression fidelity splits into two tiers. Binary rules (format, length, anti-patterns) survive COLD perfectly. Judgment-heavy rules (energy calibration, conditional logic) need WARM backstops until validated for HOT integration. Symbolic markers and emoji tokenize ~31% less efficiently per character than English prose — always verify with the actual tokenizer, not `chars/4` estimates.

See [RESEARCH.md](RESEARCH.md) for the full methodology and test progression.

### Emoji as compliance architecture

Emoji in Token Alchemy are not decorative — they are **binding compliance anchors** that enforce constraints more reliably than prose equivalents. The key patterns: 🔒 = mandatory, ❌ = prohibited, 🎯 = target, ⚡ = emphasis, 🔍 = verify, 🚫 = exclusion zone.

Emoji cost ~1–2% of the token budget but enforce ~100% of binding constraints across all compression stages. The mechanism is distributional compression: where a text abbreviation like "SEO" maps 1:1 to its expansion, an emoji like 🔒 maps 1:many — activating an entire behavioral cluster around *mandatory, non-negotiable, must-comply*. In validation testing, 249 emoji tokens encoded approximately 800 tokens of recoverable meaning (3.2x semantic expansion ratio, 5/5 decode accuracy).

See [GUIDE.md](GUIDE.md) for full emoji compliance patterns and usage guidelines.

## The three-layer approach

Layers 1 and 3 are LLM-guided steps — you prompt a model to restructure prose into YAML (Layer 1) and to inject emoji as semantic anchors (Layer 3). Layer 2 (abbreviation) is the programmatic step this library handles directly. See [RESEARCH.md](RESEARCH.md) for the theory and test results behind this pipeline.

## License

Token Alchemy is dual-licensed:

- **Open source** — [GNU Affero General Public License v3.0](LICENSE) for open-source projects, personal use, and academic research.
- **Commercial** — [Commercial License](COMMERCIAL_LICENSE.md) for proprietary products, SaaS platforms, and enterprise deployments.

If your use case requires embedding Token Alchemy in a closed-source product or distributing it without AGPL obligations, you need a commercial license.

**Pricing and inquiries:** [licensing@usedicta.com](mailto:licensing@usedicta.com) — see [COMMERCIAL_LICENSE.md](COMMERCIAL_LICENSE.md) for tier details.

© 2026 Dicta Technologies Inc.


