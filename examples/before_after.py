"""
Before/after compression example.

Demonstrates the three-layer pipeline on a sample prompt excerpt.
"""

from prompt_compress import compress, estimate_tokens
from prompt_compress.compress import measure

# ── BEFORE: Verbose prose prompt (excerpt) ──────────────────────────────────
ORIGINAL_PROSE = """
When analyzing the speaker's content, you should pay careful attention to their
use of key performance indicators and return on investment language. The tone
should be conversational but professional, suitable for a business to business
audience of decision makers. Search engine optimization alignment is critical
for all content generation tasks.

In terms of anti-patterns, watch out for the following issues that should be
suppressed in the output: excessive use of call to action phrases, overly
aggressive go-to-market language, and any non-disclosure agreement references
that might appear in the source material.

The analysis should cover the speaker's infrastructure for content delivery,
their approach to confidentiality in client communications, and their
certifications and demographics targeting strategy. Each section of the
analysis should be clearly labeled and organized.

Furthermore, it is important to note that the ideal client profile should be
derived from the speaker's own language patterns, not imposed externally.
The total addressable market references should be preserved verbatim when
they appear in the source material, and any objectives and key results
framework language should be flagged as high-value content.
"""

# ── AFTER: YAML + emoji compressed version ──────────────────────────────────
COMPRESSED_YAML = """
content_analysis:
  focus:
    - KPI + ROI language patterns
    - tone: conversational, professional
    - audience: B2B decision makers
    - SEO alignment: critical for all content
  anti_patterns:  # 🚫
    - excessive CTA phrases
    - aggressive GTM language
    - NDA references from source
  coverage:
    - infra for content delivery
    - conf in client comms
    - certs + demo targeting
    - § labels: clear, organized
  constraints:
    - ICP: derive from speaker's language, not external
    - TAM references: preserve verbatim
    - OKR language: flag as ⚡ high-value
"""

if __name__ == "__main__":
    print("=" * 60)
    print("PROMPT COMPRESSION — BEFORE / AFTER")
    print("=" * 60)

    orig_tokens = estimate_tokens(ORIGINAL_PROSE)
    comp_tokens = estimate_tokens(COMPRESSED_YAML)

    print(f"\n📝 Original prose:     {orig_tokens:,} tokens")
    print(f"📦 YAML + emoji:       {comp_tokens:,} tokens")
    print(f"💰 Savings:            {round((1 - comp_tokens/orig_tokens) * 100, 1)}%")

    # Now apply Layer 2 (abbreviation) to the compressed version
    result = compress(COMPRESSED_YAML)
    print(f"\n📦 + abbreviation:     {result.compressed_tokens:,} tokens")
    print(f"💰 Total savings:      {round((1 - result.compressed_tokens/orig_tokens) * 100, 1)}%")
    print(f"   Substitutions:      {result.substitutions}")
    print(f"   Floor-guarded:      {result.skipped_floor_guard}")

    # Full measurement
    print("\n" + "-" * 60)
    stats = measure(ORIGINAL_PROSE, COMPRESSED_YAML)
    print("Full pipeline measurement:")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    print("\n" + "=" * 60)
    print("COMPRESSED OUTPUT:")
    print("=" * 60)
    print(result.text)
