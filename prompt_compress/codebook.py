"""
Compression codebook: a learning layer that tracks which patterns
survive across compression cycles and promotes them over time.

This is the bridge to persistent memory — when connected to a system
like The Librarian, the codebook learns which abbreviations, emoji anchors,
and structural patterns are effective, and can progressively compress
more aggressively as confidence grows.

Stages:
    COLD (0) — Pattern recognized but not yet validated
    WARM (1) — Emoji-anchored / abbreviated, confirmed to decode correctly
    HOT  (2) — Single-token, high confidence, shared context established
"""

import json
import sqlite3
import re
import uuid as _uuid
from datetime import datetime
from enum import Enum

from .tokenizer import estimate_tokens


class CompressionStage(Enum):
    COLD = 0
    WARM = 1
    HOT = 2


CODEBOOK_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS compression_codebook (
    id TEXT PRIMARY KEY,
    pattern_text TEXT NOT NULL,
    warm_form TEXT NOT NULL,
    hot_form TEXT,
    stage INTEGER NOT NULL DEFAULT 0,
    token_cost_original INTEGER,
    token_cost_warm INTEGER,
    token_cost_hot INTEGER,
    times_seen INTEGER DEFAULT 1,
    times_decoded_ok INTEGER DEFAULT 0,
    confidence REAL DEFAULT 0.0,
    first_seen_at DATETIME NOT NULL,
    last_seen_at DATETIME NOT NULL,
    promoted_at DATETIME,
    source_entry_ids TEXT DEFAULT '[]',
    metadata TEXT DEFAULT '{}'
);

CREATE INDEX IF NOT EXISTS idx_codebook_stage
    ON compression_codebook(stage);
CREATE INDEX IF NOT EXISTS idx_codebook_confidence
    ON compression_codebook(confidence DESC);
CREATE INDEX IF NOT EXISTS idx_codebook_times_seen
    ON compression_codebook(times_seen DESC);
"""


class Codebook:
    """Persistent compression pattern tracker.

    Records which patterns appear in compressed prompts, how often they
    survive across cycles, and promotes them through COLD -> WARM -> HOT
    as confidence grows.

    Usage:
        cb = Codebook("codebook.db")
        cb.record_pattern("Search Engine Optimization", "SEO", entry_id="abc")
        cb.update_usage(compressed_text)
        stats = cb.stats()
    """

    def __init__(self, db_path: str = ":memory:"):
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(CODEBOOK_SCHEMA_SQL)
        self.conn.commit()

    def record_pattern(self, original: str, compressed: str, entry_id: str = "unknown",
                       token_cost_original: int = None, token_cost_warm: int = None):
        """Record or update a compression pattern."""
        now = datetime.utcnow().isoformat()
        if token_cost_original is None:
            token_cost_original = estimate_tokens(original)
        if token_cost_warm is None:
            token_cost_warm = estimate_tokens(compressed)

        existing = self.conn.execute(
            "SELECT id, times_seen, source_entry_ids FROM compression_codebook WHERE pattern_text = ?",
            (original,)
        ).fetchone()

        if existing:
            old_ids = json.loads(existing["source_entry_ids"]) if existing["source_entry_ids"] else []
            if entry_id not in old_ids:
                old_ids.append(entry_id)
            self.conn.execute(
                """UPDATE compression_codebook SET
                    times_seen = times_seen + 1, last_seen_at = ?,
                    source_entry_ids = ?, warm_form = ?, token_cost_warm = ?
                   WHERE id = ?""",
                (now, json.dumps(old_ids), compressed, token_cost_warm, existing["id"])
            )
            self.conn.commit()
            return existing["id"]
        else:
            cid = str(_uuid.uuid4())[:8]
            self.conn.execute(
                """INSERT INTO compression_codebook
                   (id, pattern_text, warm_form, stage, token_cost_original, token_cost_warm,
                    times_seen, confidence, first_seen_at, last_seen_at, source_entry_ids)
                   VALUES (?, ?, ?, ?, ?, ?, 1, 0.0, ?, ?, ?)""",
                (cid, original, compressed, CompressionStage.COLD.value,
                 token_cost_original, token_cost_warm, now, now, json.dumps([entry_id]))
            )
            self.conn.commit()
            return cid

    def extract_patterns(self, compressed_text: str, abbrev_expansions: dict = None, entry_id: str = "unknown"):
        """Extract and record patterns from a compressed prompt.

        Detects:
        1. Abbreviation substitutions (matched against expansion dict)
        2. Emoji anchors (emoji characters used as semantic markers)
        """
        from .abbreviation import ABBREV_VOCAB, ABBREV_EXPANSIONS

        if abbrev_expansions is None:
            abbrev_expansions = ABBREV_EXPANSIONS

        patterns_recorded = 0

        # Abbreviation patterns
        for pattern, replacement, flags in ABBREV_VOCAB:
            if replacement == "user_knowledge":
                continue
            if re.search(r'\b' + re.escape(replacement) + r'\b', compressed_text):
                expansion = abbrev_expansions.get(replacement)
                if expansion:
                    self.record_pattern(expansion, replacement, entry_id)
                    patterns_recorded += 1

        # Emoji anchor patterns
        emoji_pattern = re.compile(
            r'[\U0001F300-\U0001F9FF\U00002702-\U000027B0\U0000FE00-\U0000FEFF'
            r'\U0001FA00-\U0001FA6F\U0001FA70-\U0001FAFF\U00002600-\U000026FF'
            r'\U0000200D\U00002B50\U0000231A-\U0000231B\U000023E9-\U000023F3'
            r'\U000023F8-\U000023FA\U000025AA-\U000025AB\U000025B6\U000025C0'
            r'\U000025FB-\U000025FE\U00002934-\U00002935\U00002B05-\U00002B07]+'
        )

        for line in compressed_text.split('\n'):
            emojis_in_line = emoji_pattern.findall(line)
            if emojis_in_line:
                stripped = line.strip()
                if not stripped or stripped.startswith('#'):
                    continue
                for emoji in emojis_in_line:
                    self.record_pattern(stripped, emoji, entry_id)
                    patterns_recorded += 1

        return patterns_recorded

    def update_usage(self, active_text: str):
        """Increment times_seen for patterns found in active text.

        Call this at boot/load time to close the feedback loop:
        patterns that survive across cycles gain confidence toward promotion.
        """
        rows = self.conn.execute(
            "SELECT id, warm_form, hot_form, stage FROM compression_codebook"
        ).fetchall()
        if not rows:
            return 0

        now = datetime.utcnow().isoformat()
        updated = 0
        for row in rows:
            check_form = row["hot_form"] if row["hot_form"] and row["stage"] == CompressionStage.HOT.value else row["warm_form"]
            if check_form and check_form in active_text:
                self.conn.execute(
                    "UPDATE compression_codebook SET times_seen = times_seen + 1, last_seen_at = ? WHERE id = ?",
                    (now, row["id"])
                )
                updated += 1
        if updated:
            self.conn.commit()
        return updated

    def stats(self):
        """Return codebook health statistics."""
        row = self.conn.execute(
            "SELECT COUNT(*) as total, "
            "SUM(CASE WHEN stage=0 THEN 1 ELSE 0 END) as cold, "
            "SUM(CASE WHEN stage=1 THEN 1 ELSE 0 END) as warm, "
            "SUM(CASE WHEN stage=2 THEN 1 ELSE 0 END) as hot, "
            "AVG(confidence) as avg_confidence, "
            "AVG(times_seen) as avg_times_seen "
            "FROM compression_codebook"
        ).fetchone()
        return dict(row) if row else {}

    def close(self):
        self.conn.close()
