"""
Layer 2: Text abbreviation compression.

Replaces multi-word phrases and long words with standard abbreviations
that are cheaper in BPE tokens. Every substitution is validated by a
token-aware floor guard: if the replacement costs >= the original, it's skipped.

Key design rule: YAML keys are NEVER modified. Only values and list items
are touched. This prevents parse failures in structured output.
"""

import re
from collections import Counter
from .tokenizer import estimate_tokens


# ── Expansion dictionary ────────────────────────────────────────────────────
# Maps every abbreviation back to its full human-readable form.
# Used for reverse lookup, UI tooltips, and debugging.

ABBREV_EXPANSIONS = {
    # Multi-word phrase -> acronym (validated token savings)
    "KPI": "Key Performance Indicator(s)",     # 3 tok -> 2 = save 1
    "ROI": "Return on Investment",              # 3 tok -> 1 = save 2
    "SEO": "Search Engine Optimization",        # 3 tok -> 2 = save 1
    "UX": "User Experience",                    # 2 tok -> 1 = save 1
    "UI": "User Interface",                     # 2 tok -> 1 = save 1
    "CTA": "Call to Action",                    # 3 tok -> 2 = save 1
    "ICP": "Ideal Client/Customer Profile",     # 3 tok -> 1 = save 2
    "TAM": "Total Addressable Market",          # 4 tok -> 2 = save 2
    "GTM": "Go-to-Market",                      # 5 tok -> 2 = save 3
    "B2B": "Business to Business",              # 3 tok -> 3 = save 0
    "B2C": "Business to Consumer",              # 3 tok -> 3 = save 0
    "SLA": "Service Level Agreement",           # 3 tok -> 2 = save 1
    "NDA": "Non-Disclosure Agreement",          # 5 tok -> 2 = save 3
    "MVP": "Minimum Viable Product",            # 3 tok -> 2 = save 1
    "OKR": "Objectives and Key Results",        # 5 tok -> 2 = save 3
    "KG": "Knowledge Graph",                    # 2 tok -> 1 = save 1
    # Long-word abbreviations (validated token savings only)
    "conf": "confidentiality",                  # 3 tok -> 1 = save 2
    "certs": "certifications",                  # 2 tok -> 1 = save 1
    "infra": "infrastructure",                  # 2 tok -> 1 = save 1
    "demo": "demographics",                     # 2 tok -> 1 = save 1
    # Structural
    "\u00a7": "Section",                        # 1 tok -> 1 = save 0 (chars only)
}


# ── Substitution vocabulary ─────────────────────────────────────────────────
# Each tuple: (regex_pattern, replacement, flags)
# Flags: "vi" = values-only + case-insensitive, "a" = anywhere

ABBREV_VOCAB = [
    # Frozen identifiers (never substitute)
    (r"\buser[_\s]?knowledge\b", "user_knowledge", "a"),

    # Multi-word phrase collapses (highest savings)
    (r"\bkey[_\s](?:performance[_\s])?indicators?\b", "KPI", "vi"),
    (r"\breturn[_\s]on[_\s]investment\b", "ROI", "vi"),
    (r"\bsearch[_\s]engine[_\s]optimization\b", "SEO", "vi"),
    (r"\bcall[_\s]to[_\s]action\b", "CTA", "vi"),
    (r"\buser[_\s]experience\b", "UX", "vi"),
    (r"\buser[_\s]interface\b", "UI", "vi"),
    (r"\bideal[_\s](?:client|customer)(?:[_\s]profiles?)?\b", "ICP", "vi"),
    (r"\btotal[_\s]addressable[_\s]market\b", "TAM", "vi"),
    (r"\bgo[_\s-]to[_\s-]market\b", "GTM", "vi"),
    (r"\bbusiness[_\s]to[_\s]business\b", "B2B", "vi"),
    (r"\bbusiness[_\s]to[_\s]consumer\b", "B2C", "vi"),
    (r"\bservice[_\s]level[_\s]agreements?\b", "SLA", "vi"),
    (r"\bnon[_\s-]disclosure[_\s]agreements?\b", "NDA", "vi"),
    (r"\bminimum[_\s]viable[_\s]products?\b", "MVP", "vi"),
    (r"\bobjectives?[_\s](?:and[_\s])?key[_\s]results?\b", "OKR", "vi"),
    (r"\bknowledge[_\s]graph\b", "KG", "vi"),

    # Long words -> short abbreviations (only validated token-savers)
    (r"\bconfidentiality\b", "conf", "vi"),       # 3 tokens -> 1 = save 2
    (r"\bcertifications\b", "certs", "vi"),        # 2 tokens -> 1 = save 1
    (r"\binfrastructure\b", "infra", "vi"),        # 2 tokens -> 1 = save 1
    (r"\bdemographics?\b", "demo", "vi"),          # 2 tokens -> 1 = save 1

    # Structural shorthand
    (r"\bSection\b", "\u00a7", "a"),
    (r"\bsection\b", "\u00a7", "a"),
]


def apply_abbreviation(text: str, extra_vocab=None):
    """Apply programmatic text abbreviation to YAML-compressed text.

    Replaces multi-word phrases and long words with standard abbreviations.
    A token-aware floor guard ensures every substitution actually saves tokens.

    Args:
        text: Input text (typically YAML-compressed prompt)
        extra_vocab: Optional list of (pattern, replacement, flags) tuples
                     to extend the built-in vocabulary

    Returns:
        CompressResult with compressed text and stats
    """
    vocab = list(ABBREV_VOCAB)
    if extra_vocab:
        vocab = list(extra_vocab) + vocab

    result = text
    total_subs = 0
    skipped_floor = 0
    abbrev_set = set()

    for pattern, replacement, flags in vocab:
        case_flag = re.IGNORECASE if 'i' in flags else 0

        # Floor guard: skip if replacement costs >= matched text in tokens
        sample_match = re.search(pattern, result, flags=case_flag)
        if sample_match:
            matched_tokens = estimate_tokens(sample_match.group())
            replacement_tokens = estimate_tokens(replacement)
            if replacement_tokens >= matched_tokens:
                skipped_floor += 1
                continue

        if 'v' in flags:
            # Values only: apply to value portions of YAML lines, not keys
            lines = result.split('\n')
            new_lines = []
            for line in lines:
                stripped = line.lstrip()
                if stripped.startswith('#'):
                    new_lines.append(line)
                    continue

                if stripped.startswith('- '):
                    indent = line[:len(line) - len(stripped)]
                    new_stripped, count = re.subn(pattern, replacement, stripped, flags=case_flag)
                    total_subs += count
                    if count > 0:
                        abbrev_set.add(replacement)
                    new_lines.append(indent + new_stripped)
                else:
                    colon_idx = line.find(':')
                    if colon_idx > 0:
                        key_part = line[:colon_idx + 1]
                        val_part = line[colon_idx + 1:]
                        new_val, count = re.subn(pattern, replacement, val_part, flags=case_flag)
                        total_subs += count
                        if count > 0:
                            abbrev_set.add(replacement)
                        new_lines.append(key_part + new_val)
                    else:
                        new_lines.append(line)
            result = '\n'.join(new_lines)
        else:
            new_result, count = re.subn(pattern, replacement, result, flags=case_flag)
            total_subs += count
            if count > 0:
                abbrev_set.add(replacement)
            result = new_result

    return result, total_subs, len(abbrev_set), skipped_floor


def expand_abbreviation(text: str):
    """Reverse abbreviation compression for display/debugging.

    Reconstructs readable text from abbreviation-compressed YAML using
    the expansion dictionary. Not a perfect inverse (some casing may differ),
    but sufficient for human review.
    """
    result = text
    for abbrev, expansion in sorted(ABBREV_EXPANSIONS.items(), key=lambda x: len(x[0]), reverse=True):
        result = re.sub(r'\b' + re.escape(abbrev) + r'\b', expansion, result)
    result = re.sub(r"  +", " ", result)
    return result


def suggest_vocab(text: str, top_n: int = 20):
    """Analyze text to find high-frequency words not covered by the vocabulary.

    Scans value positions in YAML, counts word frequency, and returns
    candidates ranked by potential savings.

    Returns:
        list of dicts: [{word, count, est_chars_saved, suggested_abbrev}]
    """
    # Extract only value text (after colons + list items)
    value_chunks = []
    for line in text.split('\n'):
        stripped = line.lstrip()
        if stripped.startswith('#'):
            continue
        if stripped.startswith('- '):
            value_chunks.append(stripped[2:])
        else:
            colon_idx = line.find(':')
            if colon_idx > 0:
                value_chunks.append(line[colon_idx + 1:])

    value_text = ' '.join(value_chunks).lower()
    words = re.findall(r'\b[a-z]{4,}\b', value_text)
    freq = Counter(words)

    # Words already covered
    covered_words = set()
    for pattern, _, _ in ABBREV_VOCAB:
        literals = re.findall(r'[a-z]{3,}', pattern)
        covered_words.update(literals)

    stopwords = {
        'this', 'that', 'with', 'from', 'have', 'been', 'will', 'would',
        'could', 'should', 'their', 'there', 'these', 'those', 'what',
        'when', 'where', 'which', 'about', 'after', 'before', 'between',
        'through', 'during', 'each', 'every', 'both', 'into', 'over',
        'under', 'again', 'further', 'then', 'once', 'here', 'only',
        'just', 'also', 'more', 'most', 'other', 'some', 'such', 'than',
        'very', 'same', 'does', 'doing', 'being', 'having', 'make',
        'like', 'well', 'back', 'even', 'give', 'made', 'find', 'know',
        'take', 'want', 'come', 'good', 'look', 'help', 'first', 'last',
        'long', 'great', 'little', 'right', 'still', 'must', 'name',
        'keep', 'need', 'never', 'next', 'part', 'turn', 'real', 'life',
        'many', 'feel', 'high', 'much', 'they', 'them', 'your', 'true',
        'false', 'none', 'null', 'note', 'used', 'uses', 'using',
    }

    ABBREV_SUGGESTIONS = {
        'configuration': 'config', 'development': 'dev', 'production': 'prod',
        'environment': 'env', 'application': 'app', 'management': 'mgmt',
        'information': 'info', 'performance': 'perf', 'optimization': 'opt',
        'specification': 'spec', 'requirements': 'reqs', 'repository': 'repo',
        'notification': 'notif', 'integration': 'integ', 'administration': 'admin',
        'functionality': 'func', 'architecture': 'arch', 'dependencies': 'deps',
        'approximately': 'approx', 'miscellaneous': 'misc', 'distribution': 'dist',
        'international': 'intl', 'organization': 'org', 'professional': 'pro',
        'introduction': 'intro', 'subscription': 'sub', 'comparison': 'comp',
        'alternative': 'alt', 'maximum': 'max', 'minimum': 'min',
        'reference': 'ref', 'temporary': 'temp', 'directory': 'dir',
        'description': 'desc', 'experience': 'exp', 'frequency': 'freq',
    }

    candidates = []
    for word, count in freq.most_common(top_n * 3):
        if word in covered_words or word in stopwords:
            continue
        if count < 2:
            continue
        chars_saved = count * (len(word) - 2)
        if chars_saved <= 0:
            continue
        candidates.append({
            'word': word,
            'count': count,
            'est_chars_saved': chars_saved,
            'suggested_abbrev': ABBREV_SUGGESTIONS.get(word, '?'),
        })

    candidates.sort(key=lambda x: x['est_chars_saved'], reverse=True)
    return candidates[:top_n]
