# Research: YAML + Emoji Prompt Compression

**February 2026 — Dicta Technologies Inc.**

**Tested on:** Claude Opus 4.6 (Anthropic, February 2026) via Cowork and browser, on Windows and macOS.

## Summary

We compressed a complex 11,473-token heavy content-focused prompt to 5,382 tokens (53% reduction) using a three-layer pipeline: YAML restructuring, programmatic abbreviation, and emoji semantic injection. An expert evaluator found the compressed version produced functionally equivalent output — and outperformed the original on several analytical dimensions.

The most surprising finding: emoji are not token-saving tools. They cost 2-4 tokens each (vs 1 token for most common English words). But they are *semantic encoding tools* — dense carriers of behavioral intent that models reliably decode into rich instructions. 249 emoji tokens encoded approximately 800 tokens of recoverable meaning, a 3.2x semantic expansion ratio.

## The three layers

### Layer 1: YAML structure — the heavy lifter

Converting prose instructions to structured YAML accounts for **95%+ of real token savings**. This is not surprising when you look at what prose spends tokens on:

- Transition words ("Furthermore," "In addition," "It's important to note that")
- Redundant framing ("When generating output, make sure to always...")
- Paragraph glue that carries zero informational content

YAML eliminates all of that. The hierarchical key-value structure *is* the framing — a model reading `tone: conversational` doesn't need "The tone should be conversational and approachable" wrapped around it. The nesting encodes relationships that prose must spell out.

Tested savings: **40-50%** from YAML restructuring alone, across multiple prompt types.

### Layer 2: Abbreviation — the optimizer

Programmatic text-to-text substitution handles well-established acronyms and abbreviations where the BPE tokenizer confirms real savings:

| Original | Abbreviated | Token savings |
|----------|------------|---------------|
| Search Engine Optimization | SEO | 3 → 2 (save 1) |
| Non-Disclosure Agreement | NDA | 5 → 2 (save 3) |
| Go-to-Market | GTM | 5 → 2 (save 3) |
| Objectives and Key Results | OKR | 5 → 2 (save 3) |
| confidentiality | conf | 3 → 1 (save 2) |
| infrastructure | infra | 2 → 1 (save 1) |

**Critical finding: most "obvious" abbreviations don't save tokens.** Claude's BPE vocabulary already encodes common English words as single tokens. "documentation" → "docs" is 1 → 1 (zero savings). "communications" → "comms" is 1 → 2 (net *loss*). A token-aware floor guard is essential — without it, naive abbreviation inflates token count while appearing to compress at the character level.

Tested savings: **3-8%** additional on top of YAML, but only with validated vocabulary.

### Layer 3: Emoji semantic injection — the main finding

This is why this repo exists.

#### The hypothesis

Emoji are dense, visually distinct tokens that LLMs have seen millions of times in training data — always in context that encodes their meaning. A single emoji might carry the semantic weight of several words. If we inject emoji into compressed YAML as *semantic anchors*, models might decode them into richer behavioral instructions than the character count would suggest.

#### The test

We compressed a heavy content-focused prompt (11,473 tokens) that instructs an LLM to analyze a person's writing style across dimensions like tone, vocabulary patterns, rhetorical devices, and anti-patterns. The compressed version used emoji throughout:

- **Visual pipelines**: `→` for process flow, `⚡` for emphasis
- **Tonal calibration by exclusion**: `🚫` for anti-patterns, `✗` for failures
- **Semantic priming**: `🎓` for expertise, `📊` for analysis, `🔧` for tooling
- **Metaphorical anchoring**: `⚔️` for conflict patterns, `🪞` for reflection

We then ran both versions (original prose, compressed YAML+emoji) through a cold-context transfer test — a fresh model instance with no prior exposure to either version.

#### The results

**The compressed version (5,382 tokens) matched or exceeded the original (11,473 tokens) on output quality.**

Where the compressed version outperformed:

- Pattern detection completeness: identified more distinct patterns than the prose version
- Edge case capture: caught patterns the prose version missed entirely
- Multi-register analysis: distinguished between registers the original conflated
- Exclusion list thoroughness: flagged 22% more items for the exclusion criteria

Where the original was stronger:

- Structural fidelity: cleaner benchmark organization, more secondary-tier patterns
- Operational constraints: more explicit deployment rules

Expert evaluator verdict: the original was structurally more faithful; the compressed version showed better analytical nuance. The ideal would combine both.

#### Semantic density measurement

We ran a focused test: 249 emoji tokens were presented to a model in a compressed instruction block. The model decoded them into approximately 800 tokens of behavioral instructions — a **3.2x semantic expansion ratio**.

Five instruction sets were tested, including a novel compound instruction that the model had never seen in training. All five decoded perfectly (5/5 accuracy).

The key emoji patterns that drove this:

| Pattern | Mechanism | Example |
|---------|-----------|---------|
| Visual pipelines | Process flow as spatial arrangement | `input → analyze → 📊 output` |
| Tonal calibration by exclusion | Define behavior by what NOT to do | `🚫 jargon, 🚫 filler, 🚫 hedging` |
| Semantic priming | Emoji sets the interpretive frame | `🎓 expertise signals:` activates "look for credibility markers" |
| Metaphorical anchoring | Abstract concept → concrete image | `⚔️ conflict patterns` vs "identify areas of tension or disagreement" |

#### Why this works (our theory)

LLMs have a learned *emoji semantics* from training data. When they encounter `📊` in an instruction context, they don't see "bar chart emoji" — they activate a semantic cluster around *analysis, data, measurement, reporting*. This is a form of **distributional compression**: the emoji's meaning comes from the statistical distribution of contexts it appeared in during training, which is far richer than its surface form.

This means emoji operate differently from text abbreviations:

- Text abbreviation: `SEO` → model looks up "Search Engine Optimization" (1:1 expansion)
- Emoji injection: `📊` → model activates a *semantic field* around analysis (1:many expansion)

The 3.2x expansion ratio reflects this: each emoji recovers not just a word, but a *behavioral cluster* of related instructions.

## Production viability

The 53% savings are production-ready. The compressed prompt was tested on a real workflow with a real evaluator (a model with deep familiarity with the original prompt's expected output). Both versions failed on exactly the same 3 items — failures attributable to shared model behavior, not compression artifacts.

**Conclusion: YAML + emoji compression is production-viable for complex workflow prompts.** The combination preserves semantic fidelity while halving context window cost.

## The persistent-memory angle

These results are static — a one-time compression. But the technique gets *better* over time when connected to a persistent memory system.

The `Codebook` class in this library tracks:

- Which patterns appear across compression cycles (`times_seen`)
- Which patterns decode correctly in cold-context transfers (`times_decoded_ok`)
- Confidence scores that gate promotion through compression stages

A persistent memory system (like [The Librarian](https://github.com/PRDicta/The-Librarian)) can:

1. **Run `suggest_vocab()` on accumulated text** to find domain-specific terms that appear frequently but aren't in the built-in vocabulary.
2. **Promote proven patterns** from COLD → WARM → HOT as confidence grows, enabling progressively more aggressive compression.
3. **Build user-specific emoji vocabularies** — different domains and users have different semantic anchors. A legal workflow might develop `⚖️` as a high-confidence anchor for compliance, while a marketing workflow develops `📣` for campaign activity.
4. **Detect and retire stale patterns** — terms that stop appearing in active prompts get demoted, keeping the vocabulary lean.

The net effect: compression ratios improve over time without manual tuning. The system learns which shortcuts work for *your* prompts and *your* model's decoding behavior.

## Limitations and open questions

- **Single model family.** All testing was performed on Claude (Anthropic). Emoji semantic decoding may behave differently on GPT-4, Gemini, or open-weight models — the BPE vocabularies differ, and emoji training distributions vary across corpora.
- **One prompt type.** The 53% result comes from a single complex behavioral prompt. Shorter or simpler prompts may see different compression ratios, and the emoji density that works here could overwhelm a lighter prompt.
- **One evaluator.** The expert evaluation was performed by a single model instance with deep familiarity with the original prompt's expected output. A broader evaluation protocol (multiple evaluators, blind comparison) would strengthen the findings.
- **Emoji semantics are not guaranteed stable.** Model updates could shift how emoji are decoded. A pattern that works on Claude Opus 4.6 may not decode identically on future releases — the codebook's confidence tracking is designed to catch this, but it's an open risk.
- **No cross-language testing.** All testing was in English. Emoji semantics may carry different connotations in multilingual or non-English prompt contexts.

## Citation

```
Dicta Technologies Inc. (2026). Three-Layer LLM Prompt Compression:
YAML Structure, Abbreviation, and Emoji Semantic Injection.
https://github.com/PRDicta/token-alchemy
```
