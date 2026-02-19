# Compression Playbook

A step-by-step operational guide for compressing complex multi-document prompt systems using Token Alchemy's three-stage model.

This guide encodes the methodology validated across 6 iterative tests on a production system — 8 documents, ~62,000 tokens compressed to ~24,000 tokens (61% reduction) with zero quality regression.

## Before you start

### What compresses well

Large prompt systems with multiple documents: behavioral profiles, workflow instructions, editorial guidelines, voice/style profiles, company context. The more verbose prose your system uses, the higher the compression ratio.

### What you need

- Original (uncompressed) prompt set with known-good output examples
- A quality evaluator — either a human expert or a model instance deeply familiar with expected output
- Token Alchemy’s `compress` and `Codebook` for Layer 2 (abbreviation)
- Token Alchemy’s `ValidationTracker` for prompt-level quality tracking
- A persistent memory system (like [The Librarian](https://github.com/PRDicta/The-Librarian)) for WARM-stage backstops — or any key-value store that loads entries at boot

## The three stages

### COLD — Structural compression

**Goal:** Maximum token reduction through format transformation.

**Process:**

1. **YAML restructuring (Layer 1).** Prompt an LLM to convert each document from prose to structured YAML. This eliminates transition words, redundant framing, and paragraph glue. Typical savings: 40–50% per document.

2. **Programmatic abbreviation (Layer 2).** Run `compress()` on the YAML output. The token-aware floor guard ensures every substitution actually saves tokens — no character-level illusions.

3. **Emoji semantic injection (Layer 3).** Prompt an LLM to inject emoji as semantic anchors into the compressed YAML. See [Emoji as Compliance Architecture](#emoji-as-compliance-architecture) below — this is not cosmetic.

4. **Measure.** Use `measure()` to compare original vs compressed token counts per document.

**What to preserve (non-negotiable):**
- All quantitative benchmarks (word counts, percentages, counts)
- Format signatures (punctuation rules, spacing requirements, structural patterns)
- Anti-patterns (explicit "never do X" rules)
- Emoji binding constraints (specific emoji at specific positions — these are Tier 1 rules)
- Platform-specific format profiles

**What to cut:**
- Synthetic examples (calibration aids) — largest single source of savings in voice/style profiles
- Changelogs and version histories
- Verbose descriptions that restate what binding rules already encode
- Rejected-output verbatim blocks (preserve the failure analysis as a rule, cut the full text)
- Redundant explanations across documents

### Identifying Tier 1 vs Tier 2 rules

This is the most important step. After COLD compression, classify every rule in your prompt set:

**Tier 1 — Binary/structural rules.** These survive COLD compression with zero loss.

Characteristics:
- Has a clear pass/fail test (e.g., "max 150 words" — either it’s under 150 or it isn’t)
- Self-contained — the rule’s meaning doesn’t depend on surrounding context
- Can be expressed as a single line of YAML without ambiguity
- Examples: format suppression, length limits, punctuation rules, anti-patterns, emoji signatures, CTA rules, platform format requirements

**Tier 2 — Judgment-heavy rules.** These show drift after COLD compression.

Characteristics:
- Requires weighing multiple factors (e.g., "match the energy register to the story mood")
- Depends on hierarchical context that YAML flattening removes
- Involves conditional activation/suppression (e.g., "use this pattern when challenging a belief, suppress it for straightforward explainers")
- The original prose spent multiple paragraphs building a decision framework
- Examples: energy calibration, conditional register shifts, editorial voice matching, hook strategy, X-factor lead patterns

**Use `classify_rule_tier()` to help identify candidates**, but always validate with a quality evaluator. The function flags likely Tier 2 rules based on structural markers (conditional language, multi-factor dependencies, subjective terms), but the final call requires domain knowledge.

### Running your first validation

After COLD compression, run a quality evaluation:

1. Generate output using the compressed prompt set (cold context — no prior exposure)
2. Compare against known-good output from the original prompts
3. Score each rule: did it activate correctly? Was the output compliant?
4. Any rule that shows drift is a Tier 2 candidate

Use `ValidationTracker.record_test()` to log results. This builds the evidence base for WARM backstop creation.

### WARM — Quality recovery via backstops

**Goal:** Recover Tier 2 fidelity without inflating prompt tokens.

For each Tier 2 rule that showed drift:

1. **Write a backstop.** A concise statement (1–3 sentences) that restores the decision framework the COLD compression flattened. Focus on the *judgment logic*, not the original verbose description.

2. **Store the backstop externally.** In The Librarian, use `project-remember`. In any other system, store it as a key-value entry that loads at boot alongside the compressed prompts.

3. **Validate.** Run another quality evaluation with backstops loaded. The drifted rules should now activate correctly.

4. **Track activation.** Use `ValidationTracker.record_backstop_activation()` to log whether each backstop fired during the test. A backstop that doesn’t activate may not be needed — but give it at least 3 tests before considering retirement.

**Key principle: backstops are earned, not assumed.** Don’t preemptively create backstops for every rule. Compress first, test, identify actual drift, *then* backstop.

### HOT — Self-contained prompts

**Goal:** Eliminate boot-time dependencies by baking validated backstops into the prompts.

**Prerequisites:**
- Backstop has activated correctly across multiple validation runs
- 100% hit rate (it fires every time the relevant pattern appears)
- No quality regression in any test

**Process:**

1. **Identify insertion points.** Each backstop maps to a functional location in the compressed prompt. A backstop about energy calibration goes near the core principle section. A backstop about conditional patterns goes in the voice matching reference. A backstop about named-individual handling goes in the compliance checklist.

2. **Mark with `[HOT]` tags.** Insert the backstop text at the identified location, marked with `[HOT]` so you can trace which lines came from backstop integration.

3. **Retire the external backstop.** Remove it from the boot-time loading path. The prompt is now self-contained.

4. **Validate.** Run another quality evaluation with zero external entries loaded. Quality should match or exceed the WARM configuration.

Use `ValidationTracker.promote_to_hot()` to record the transition and its validation results.

## Emoji as Compliance Architecture

**This section is critical.** Emoji in Token Alchemy are not decorative, not a compression trick, and not primarily about saving tokens. They are **semantic anchors that enforce compliance with binding constraints**.

### Why emoji work as compliance tools

LLMs have learned emoji semantics from training data. When a model encounters 🔒 in an instruction context, it doesn’t see "lock emoji" — it activates a semantic cluster around *mandatory, non-negotiable, must-comply*. This activation is stronger and more reliable than the equivalent prose instruction.

The mechanism is **distributional compression**: the emoji’s meaning comes from the statistical distribution of contexts it appeared in during training, which is far richer than its surface form. A text abbreviation like "SEO" maps 1:1 to "Search Engine Optimization." An emoji like 🔒 maps 1:many — activating an entire behavioral cluster.

In our validation testing, 249 emoji tokens encoded approximately 800 tokens of recoverable meaning — a **3.2x semantic expansion ratio**. Five instruction sets were tested, including a novel compound instruction. All five decoded perfectly (5/5 accuracy).

### The emoji compliance patterns

These patterns were validated across 6 production tests:

**Binding constraint markers:**
- 🔒 = Mandatory / non-negotiable rule (the model treats what follows as inviolable)
- ❌ = Prohibited / never-do-this (stronger than prose "avoid" or "don’t")
- ✗ = Failure marker in anti-pattern lists (signals "this is what bad looks like")

**Behavioral anchors:**
- 🎯 = Target / goal / this-is-what-success-looks-like
- ⚡ = Emphasis / high-energy / attention-required
- 🔍 = Inspect / verify / quality-check-this

**Semantic priming:**
- 🎓 = Expertise / credibility / authority signals
- 📊 = Analysis / data / measurement context
- 🔧 = Tooling / technical / implementation detail

**Tonal calibration by exclusion:**
- 🚫 = Exclusion zone (defines behavior by what NOT to do)
- Combined patterns like `🚫 jargon, 🚫 filler, 🚫 hedging` create a behavioral fence that’s more effective than "write clearly and directly"

**Visual pipelines:**
- → for process flow / sequential steps
- Spatial arrangement of emoji creates visual structure that models parse as workflow

### Token cost vs compliance value

Emoji cost 2–4 tokens each (vs 1 token for most common English words). In a compressed prompt, emoji typically account for **~1–2% of total token budget**. This is not where your savings come from.

The value of emoji shows up as **errors that didn’t happen**. In 6 validation tests across a production pipeline, binding constraints marked with emoji achieved 100% compliance. The same constraints expressed in prose showed occasional drift after COLD compression.

This means emoji are a Tier 1 compression element — they survive every compression stage with zero loss, and they *strengthen* compliance rather than just preserving it.

### When to use emoji anchoring

- **Always** on binding constraints (🔒, ❌) — these are your safety net
- **Always** on anti-patterns (✗, 🚫) — exclusion patterns benefit most from visual distinctiveness
- **Selectively** on behavioral anchors (🎯, ⚡) — use where emphasis matters, not everywhere
- **Never** on YAML keys — keys are structural identifiers, emoji belong in values only
- **Never** as decoration — every emoji must carry semantic weight

### Emoji signatures in voice/style profiles

Some profiles define specific emoji at specific positions with specific counts. These are **binding format constraints** and fall squarely into Tier 1. They must survive compression intact — same emoji, same positions, same counts. Voice profile compression should preserve emoji signatures completely, even when cutting surrounding prose.

## Compression by document type

### Workflow/pipeline prompts
- Highest structural redundancy, excellent COLD compression candidates
- Watch for Tier 2 drift in energy calibration and conditional logic sections
- HOT insertion points map naturally to existing sections (core principles, voice matching, compliance checklist)

### Voice/style profiles
- **Highest compression ratios** (50–70%) due to verbose descriptive prose
- Synthetic examples are the largest single cut (~25% of compressed budget)
- **Risk:** removing examples saves tokens but loses gestalt calibration. Rules encode *what to do*; examples encode *what it feels like*. Restore selectively as WARM backstops if drift appears.
- Emoji signatures are sacred — Tier 1, zero loss tolerance
- Anti-patterns compress well (verbose explanations → single-line rules with ✗ markers)

### Company/context documents
- Usually the smallest, compress moderately
- Safe to cut: mission statement prose, verbose history, redundant value descriptions
- Preserve: specific names, numbers, dates, relationships

### Editorial guidelines
- Heavy Tier 2 content (editorial judgment doesn’t compress to binary rules)
- Plan for more WARM backstops than other document types
- Conditional patterns ("do X when Y, suppress when Z") need careful backstop design

## Validation framework

### Test progression

Run tests in order. Each stage builds evidence for the next:

| Test | What you’re checking | Pass criteria |
|------|---------------------|---------------|
| 1 | COLD baseline | Identify which rules show drift (these are your Tier 2 candidates) |
| 2 | WARM (+backstops) | All drifted rules recovered. No new regressions. |
| 3 | WARM (expanded) | Quality meets or exceeds uncompressed baseline |
| 4 | Backstop hit rate | 100% activation on all backstops (proves they’re load-bearing) |
| 5 | HOT (baked in) | No regression vs WARM. Zero external dependencies. |
| 6 | HOT + profile compression | No regression after additional document compression |

### What to evaluate per test

For each rule in your prompt set:
- **Activated correctly?** (the rule fired when it should have)
- **Suppressed correctly?** (the rule stayed silent when it should have)
- **Output compliant?** (the generated content meets the rule’s requirements)
- **Backstop needed?** (if drift detected, flag for WARM backstop creation)

### Red flags

- A rule that was fine in test N but drifts in test N+1 → possible interaction effect with a new backstop
- A backstop that never activates across 3+ tests → may not be needed, but investigate before removing
- Output that’s *longer* than baseline → compression may have disrupted length discipline (this is a regression even if content quality is fine)
- Emoji constraints that partially activate (right emoji, wrong count or position) → check that the emoji signature survived compression intact

## Design principles

1. **Source = CONTENT, profile = FORM.** Compression changes how prompts encode instructions, never what they instruct.
2. **Binding constraints are sacred.** Quantitative benchmarks, format rules, anti-patterns, and emoji signatures survive every stage untouched.
3. **Emoji are compliance architecture, not decoration.** Every emoji carries semantic weight. Their value is compliance rate, not token savings.
4. **Tier 2 rules need backstops until proven stable.** Don’t assume judgment-heavy rules compress cleanly — validate, then promote.
5. **Backstops are earned, not assumed.** Each backstop must demonstrate activation in testing before HOT integration.
6. **Dense source ≠ longer output.** Compression must preserve length discipline, not just content accuracy.
7. **Originals are always preserved.** Compressed versions live in a dedicated folder. Originals are never overwritten.

## Quick reference

```
COLD: Compress everything → Test → Identify Tier 2 drift
WARM: Write backstops for drifted rules → Test → Verify recovery
HOT:  Bake validated backstops into prompts → Test → Verify self-contained
```

```
Tier 1 (binary):    format, length, anti-patterns, emoji signatures → survives COLD
Tier 2 (judgment):  energy, conditionals, voice matching, hook strategy → needs WARM backstops
```

```
Emoji budget: ~1-2% of tokens, ~100% of compliance enforcement
🔒 = mandatory    ❌ = prohibited    🎯 = target    🔍 = verify
```
