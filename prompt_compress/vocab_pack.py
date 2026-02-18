"""
Domain-specific vocabulary packs.

Vocab packs are JSON files that extend the built-in abbreviation vocabulary
with domain-specific terms. They can be loaded at runtime to handle
industry jargon, project-specific terminology, or learned patterns.

Format:
    [{"pattern": "\\bregex\\b", "replacement": "abbrev", "flags": "vi"}, ...]

Flags:
    "vi" = values-only, case-insensitive (safe for YAML — never touches keys)
    "a"  = anywhere (use only for structural substitutions like Section -> §)
"""

import json
import os


def load_vocab_pack(pack_path_or_name: str, search_dirs=None):
    """Load a vocabulary pack from a JSON file.

    Args:
        pack_path_or_name: Either a full file path, or a pack name to search for.
        search_dirs: Optional list of directories to search (when using a name).
                     Defaults to ./vocab_packs/ relative to this module.

    Returns:
        list of (pattern, replacement, flags) tuples ready for use with
        apply_abbreviation(extra_vocab=...).
    """
    # Direct file path
    if os.path.isfile(pack_path_or_name):
        pack_file = pack_path_or_name
    else:
        # Search for it by name
        if search_dirs is None:
            search_dirs = [
                os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "vocab_packs"),
            ]
        pack_file = None
        for d in search_dirs:
            candidate = os.path.join(d, f"{pack_path_or_name}.json")
            if os.path.isfile(candidate):
                pack_file = candidate
                break
        if not pack_file:
            raise FileNotFoundError(
                f"Vocab pack '{pack_path_or_name}' not found in {search_dirs}"
            )

    with open(pack_file, "r", encoding="utf-8") as f:
        entries = json.load(f)

    vocab = []
    for entry in entries:
        pattern = entry.get("pattern", "")
        replacement = entry.get("replacement", "")
        flags = entry.get("flags", "vi")
        if pattern and replacement:
            vocab.append((pattern, replacement, flags))

    return vocab
