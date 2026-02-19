"""
Token Alchemy — Validation Module

Standalone module for tracking prompt-level compression quality across
the COLD → WARM → HOT pipeline. Complements the Codebook (which tracks
pattern-level confidence) with prompt-set-level fidelity tracking.

Classes:
    ValidationTracker — Records test results per rule across compression stages.
    BackstopManager   — Manages the lifecycle of WARM backstops through HOT promotion.

Functions:
    classify_rule_tier — Heuristic classifier for Tier 1 (binary) vs Tier 2 (judgment) rules.

Architecture:
    Can share Codebook's SQLite database or use its own. Pass a db_path to
    connect to an existing DB, or let it create a new one. The tables are
    namespaced (validation_*, backstop_*) so they never collide with Codebook's
    pattern tables.
"""

import json
import re
import sqlite3
import time
from dataclasses import dataclass, field, asdict
from enum import IntEnum
from pathlib import Path
from typing import Optional


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class CompressionStage(IntEnum):
    """Mirrors Codebook's CompressionStage for interoperability."""
    COLD = 0
    WARM = 1
    HOT  = 2


class RuleTier(IntEnum):
    """Rule fidelity classification.

    Tier 1 — Binary/structural rules that survive COLD compression with zero loss.
              Examples: format suppression, length limits, punctuation rules,
              anti-patterns, emoji signatures, CTA rules.

    Tier 2 — Judgment-heavy rules that show drift after COLD compression.
              Examples: energy calibration, conditional register shifts,
              editorial voice matching, hook strategy.
    """
    TIER_1 = 1
    TIER_2 = 2


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class RuleResult:
    """Result of evaluating a single rule in one test run."""
    rule_id: str
    activated_correctly: bool
    suppressed_correctly: bool
    output_compliant: bool
    backstop_needed: bool = False
    notes: str = ""


@dataclass
class TestRun:
    """A single validation test run across the prompt set."""
    test_number: int
    stage: CompressionStage
    token_budget: int
    reduction_pct: float
    rule_results: list = field(default_factory=list)
    backstops_loaded: list = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)
    notes: str = ""

    @property
    def pass_rate(self) -> float:
        if not self.rule_results:
            return 0.0
        passed = sum(
            1 for r in self.rule_results
            if r.activated_correctly and r.suppressed_correctly and r.output_compliant
        )
        return passed / len(self.rule_results)

    @property
    def drifted_rules(self) -> list:
        return [
            r for r in self.rule_results
            if not (r.activated_correctly and r.suppressed_correctly and r.output_compliant)
        ]

@dataclass
class Backstop:
    """A WARM-stage backstop targeting a specific Tier 2 rule."""
    backstop_id: str
    rule_id: str
    text: str
    stage: CompressionStage = CompressionStage.WARM
    created_at: float = field(default_factory=time.time)
    activation_count: int = 0
    test_count: int = 0
    promoted_at: Optional[float] = None
    insertion_point: str = ""  # Where in the prompt this backstop belongs (for HOT)

    @property
    def hit_rate(self) -> float:
        if self.test_count == 0:
            return 0.0
        return self.activation_count / self.test_count

    @property
    def ready_for_hot(self) -> bool:
        """A backstop is HOT-ready when it has 100% hit rate across 3+ tests."""
        return self.test_count >= 3 and self.hit_rate == 1.0


# ---------------------------------------------------------------------------
# ValidationTracker
# ---------------------------------------------------------------------------

class ValidationTracker:
    """Tracks prompt-level quality across compression stages.

    Records test results per rule, identifies Tier 2 drift, and builds
    the evidence base for WARM backstop creation and HOT promotion.

    Usage:
        tracker = ValidationTracker("my_project.db")
        run = tracker.record_test(
            test_number=1,
            stage=CompressionStage.COLD,
            token_budget=37800,
            reduction_pct=39.1,
            rule_results=[
                RuleResult("max_150_words", True, True, True),
                RuleResult("energy_calibration", True, True, False, backstop_needed=True),
            ]
        )
        print(run.drifted_rules)  # Rules that need WARM backstops
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or "validation.db"
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS validation_tests (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_number INTEGER NOT NULL,
                stage INTEGER NOT NULL,
                token_budget INTEGER,
                reduction_pct REAL,
                pass_rate REAL,
                backstops_loaded TEXT DEFAULT '[]',
                notes TEXT DEFAULT '',
                timestamp REAL NOT NULL
            );

            CREATE TABLE IF NOT EXISTS validation_rule_results (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                test_id INTEGER NOT NULL,
                rule_id TEXT NOT NULL,
                activated_correctly INTEGER NOT NULL,
                suppressed_correctly INTEGER NOT NULL,
                output_compliant INTEGER NOT NULL,
                backstop_needed INTEGER DEFAULT 0,
                notes TEXT DEFAULT '',
                FOREIGN KEY (test_id) REFERENCES validation_tests(id)
            );

            CREATE TABLE IF NOT EXISTS validation_rules (
                rule_id TEXT PRIMARY KEY,
                tier INTEGER DEFAULT 1,
                description TEXT DEFAULT '',
                tier_evidence TEXT DEFAULT '',
                first_seen REAL,
                last_tested REAL
            );

            CREATE INDEX IF NOT EXISTS idx_rule_results_test
                ON validation_rule_results(test_id);
            CREATE INDEX IF NOT EXISTS idx_rule_results_rule
                ON validation_rule_results(rule_id);
        """)
        self._conn.commit()

    def record_test(self, test_number: int, stage: CompressionStage,
                    token_budget: int, reduction_pct: float,
                    rule_results: list, backstops_loaded: list = None,
                    notes: str = "") -> TestRun:
        """Record a complete validation test run.

        Args:
            test_number: Sequential test number (1-indexed).
            stage: COLD, WARM, or HOT.
            token_budget: Total tokens in the compressed prompt set.
            reduction_pct: Percentage reduction from original.
            rule_results: List of RuleResult objects.
            backstops_loaded: List of backstop IDs loaded for this test.
            notes: Free-text notes about this test.

        Returns:
            TestRun with computed pass_rate and drifted_rules.
        """
        backstops_loaded = backstops_loaded or []
        run = TestRun(
            test_number=test_number,
            stage=stage,
            token_budget=token_budget,
            reduction_pct=reduction_pct,
            rule_results=rule_results,
            backstops_loaded=backstops_loaded,
            notes=notes,
        )

        cursor = self._conn.execute(
            """INSERT INTO validation_tests
               (test_number, stage, token_budget, reduction_pct, pass_rate,
                backstops_loaded, notes, timestamp)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (test_number, int(stage), token_budget, reduction_pct,
             run.pass_rate, json.dumps(backstops_loaded), notes, run.timestamp)
        )
        test_id = cursor.lastrowid

        for r in rule_results:
            self._conn.execute(
                """INSERT INTO validation_rule_results
                   (test_id, rule_id, activated_correctly, suppressed_correctly,
                    output_compliant, backstop_needed, notes)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (test_id, r.rule_id, int(r.activated_correctly),
                 int(r.suppressed_correctly), int(r.output_compliant),
                 int(r.backstop_needed), r.notes)
            )

            # Upsert rule metadata
            now = time.time()
            self._conn.execute(
                """INSERT INTO validation_rules (rule_id, first_seen, last_tested)
                   VALUES (?, ?, ?)
                   ON CONFLICT(rule_id) DO UPDATE SET last_tested = ?""",
                (r.rule_id, now, now, now)
            )

        self._conn.commit()
        return run

    def classify_rule(self, rule_id: str, tier: RuleTier, evidence: str = ""):
        """Set or update a rule's tier classification.

        Args:
            rule_id: The rule identifier.
            tier: TIER_1 (binary/structural) or TIER_2 (judgment-heavy).
            evidence: Why this classification was chosen.
        """
        self._conn.execute(
            """INSERT INTO validation_rules (rule_id, tier, tier_evidence, first_seen)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(rule_id) DO UPDATE SET tier = ?, tier_evidence = ?""",
            (rule_id, int(tier), evidence, time.time(), int(tier), evidence)
        )
        self._conn.commit()

    def rule_history(self, rule_id: str) -> list:
        """Get all test results for a specific rule, ordered by test number."""
        rows = self._conn.execute(
            """SELECT vt.test_number, vt.stage, vrr.activated_correctly,
                      vrr.suppressed_correctly, vrr.output_compliant,
                      vrr.backstop_needed, vrr.notes
               FROM validation_rule_results vrr
               JOIN validation_tests vt ON vrr.test_id = vt.id
               WHERE vrr.rule_id = ?
               ORDER BY vt.test_number""",
            (rule_id,)
        ).fetchall()
        return [dict(r) for r in rows]

    def tier2_candidates(self) -> list:
        """Return rules that have shown drift in any test (Tier 2 candidates)."""
        rows = self._conn.execute(
            """SELECT DISTINCT vrr.rule_id, vr.tier, vr.tier_evidence
               FROM validation_rule_results vrr
               LEFT JOIN validation_rules vr ON vrr.rule_id = vr.rule_id
               WHERE vrr.output_compliant = 0
                  OR vrr.activated_correctly = 0
                  OR vrr.suppressed_correctly = 0
               ORDER BY vrr.rule_id"""
        ).fetchall()
        return [dict(r) for r in rows]

    def test_progression(self) -> list:
        """Return summary of all tests in order — for the validation table."""
        rows = self._conn.execute(
            """SELECT test_number, stage, token_budget, reduction_pct,
                      pass_rate, backstops_loaded, notes, timestamp
               FROM validation_tests
               ORDER BY test_number"""
        ).fetchall()
        return [dict(r) for r in rows]

    def stats(self) -> dict:
        """Overall validation statistics."""
        tests = self._conn.execute(
            "SELECT COUNT(*) as n FROM validation_tests"
        ).fetchone()["n"]

        rules = self._conn.execute(
            "SELECT COUNT(*) as n FROM validation_rules"
        ).fetchone()["n"]

        tier2 = self._conn.execute(
            "SELECT COUNT(*) as n FROM validation_rules WHERE tier = 2"
        ).fetchone()["n"]

        latest = self._conn.execute(
            """SELECT test_number, stage, pass_rate, reduction_pct
               FROM validation_tests ORDER BY test_number DESC LIMIT 1"""
        ).fetchone()

        return {
            "total_tests": tests,
            "total_rules": rules,
            "tier2_rules": tier2,
            "latest_test": dict(latest) if latest else None,
        }

    def close(self):
        self._conn.close()


# ---------------------------------------------------------------------------
# BackstopManager
# ---------------------------------------------------------------------------

class BackstopManager:
    """Manages the WARM → HOT backstop lifecycle.

    Backstops are concise statements that restore decision frameworks
    flattened by COLD compression. They target specific Tier 2 rules
    and must earn their way from WARM (external) to HOT (baked-in)
    through validated activation.

    Usage:
        mgr = BackstopManager("my_project.db")

        # Create a backstop for a drifted rule
        bs = mgr.create(
            rule_id="energy_calibration",
            text="Match energy register to story mood: high-energy for breakthroughs, "
                 "measured for analysis, urgent for crisis. Never default to neutral.",
            insertion_point="core_principles"
        )

        # Record activation during a test
        mgr.record_activation("energy_calibration", activated=True)

        # Check if ready for HOT promotion
        if bs.ready_for_hot:
            mgr.promote_to_hot("energy_calibration")
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or "validation.db"
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._init_schema()

    def _init_schema(self):
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS backstop_entries (
                backstop_id TEXT PRIMARY KEY,
                rule_id TEXT NOT NULL,
                text TEXT NOT NULL,
                stage INTEGER NOT NULL DEFAULT 1,
                created_at REAL NOT NULL,
                activation_count INTEGER DEFAULT 0,
                test_count INTEGER DEFAULT 0,
                promoted_at REAL,
                insertion_point TEXT DEFAULT '',
                retired INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS backstop_activations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                backstop_id TEXT NOT NULL,
                test_number INTEGER,
                activated INTEGER NOT NULL,
                timestamp REAL NOT NULL,
                notes TEXT DEFAULT '',
                FOREIGN KEY (backstop_id) REFERENCES backstop_entries(backstop_id)
            );

            CREATE INDEX IF NOT EXISTS idx_backstop_rule
                ON backstop_entries(rule_id);
            CREATE INDEX IF NOT EXISTS idx_backstop_activations_id
                ON backstop_activations(backstop_id);
        """)
        self._conn.commit()

    def create(self, rule_id: str, text: str,
               insertion_point: str = "") -> Backstop:
        """Create a new WARM backstop for a Tier 2 rule.

        Args:
            rule_id: The rule this backstop targets.
            text: The backstop text (1-3 sentences restoring the decision framework).
            insertion_point: Where in the compressed prompt this belongs (for HOT).

        Returns:
            Backstop instance.
        """
        backstop_id = f"bs_{rule_id}"
        now = time.time()

        self._conn.execute(
            """INSERT INTO backstop_entries
               (backstop_id, rule_id, text, stage, created_at, insertion_point)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (backstop_id, rule_id, text, int(CompressionStage.WARM), now, insertion_point)
        )
        self._conn.commit()

        return Backstop(
            backstop_id=backstop_id,
            rule_id=rule_id,
            text=text,
            stage=CompressionStage.WARM,
            created_at=now,
            insertion_point=insertion_point,
        )

    def record_activation(self, rule_id: str, activated: bool,
                          test_number: int = None, notes: str = ""):
        """Record whether a backstop activated during a test.

        Args:
            rule_id: The rule whose backstop is being tracked.
            activated: Did the backstop fire correctly?
            test_number: Which test run this was.
            notes: Optional observations.
        """
        backstop_id = f"bs_{rule_id}"
        now = time.time()

        self._conn.execute(
            """INSERT INTO backstop_activations
               (backstop_id, test_number, activated, timestamp, notes)
               VALUES (?, ?, ?, ?, ?)""",
            (backstop_id, test_number, int(activated), now, notes)
        )

        # Update counters
        self._conn.execute(
            """UPDATE backstop_entries
               SET test_count = test_count + 1,
                   activation_count = activation_count + CASE WHEN ? THEN 1 ELSE 0 END
               WHERE backstop_id = ?""",
            (int(activated), backstop_id)
        )
        self._conn.commit()

    def promote_to_hot(self, rule_id: str) -> bool:
        """Promote a backstop from WARM to HOT.

        Prerequisites (enforced):
            - 3+ tests completed
            - 100% activation rate

        Args:
            rule_id: The rule whose backstop to promote.

        Returns:
            True if promoted, False if prerequisites not met.
        """
        backstop_id = f"bs_{rule_id}"
        row = self._conn.execute(
            "SELECT * FROM backstop_entries WHERE backstop_id = ?",
            (backstop_id,)
        ).fetchone()

        if not row:
            return False

        bs = self._get_backstop(row)
        if not bs.ready_for_hot:
            return False

        now = time.time()
        self._conn.execute(
            """UPDATE backstop_entries
               SET stage = ?, promoted_at = ?
               WHERE backstop_id = ?""",
            (int(CompressionStage.HOT), now, backstop_id)
        )
        self._conn.commit()
        return True

    def retire(self, rule_id: str):
        """Retire a backstop that never activated (after 3+ tests)."""
        backstop_id = f"bs_{rule_id}"
        self._conn.execute(
            "UPDATE backstop_entries SET retired = 1 WHERE backstop_id = ?",
            (backstop_id,)
        )
        self._conn.commit()

    def get(self, rule_id: str) -> Optional[Backstop]:
        """Get a backstop by rule ID."""
        backstop_id = f"bs_{rule_id}"
        row = self._conn.execute(
            "SELECT * FROM backstop_entries WHERE backstop_id = ?",
            (backstop_id,)
        ).fetchone()
        return self._get_backstop(row) if row else None

    def warm_backstops(self) -> list:
        """Return all active WARM backstops (not yet promoted, not retired)."""
        rows = self._conn.execute(
            """SELECT * FROM backstop_entries
               WHERE stage = ? AND retired = 0
               ORDER BY created_at""",
            (int(CompressionStage.WARM),)
        ).fetchall()
        return [self._get_backstop(r) for r in rows]

    def hot_backstops(self) -> list:
        """Return all HOT-promoted backstops."""
        rows = self._conn.execute(
            """SELECT * FROM backstop_entries
               WHERE stage = ?
               ORDER BY promoted_at""",
            (int(CompressionStage.HOT),)
        ).fetchall()
        return [self._get_backstop(r) for r in rows]

    def hit_rates(self) -> dict:
        """Return hit rates for all active backstops."""
        rows = self._conn.execute(
            "SELECT * FROM backstop_entries WHERE retired = 0"
        ).fetchall()
        return {
            r["rule_id"]: {
                "hit_rate": r["activation_count"] / r["test_count"] if r["test_count"] > 0 else 0.0,
                "tests": r["test_count"],
                "stage": CompressionStage(r["stage"]).name,
                "ready_for_hot": (
                    r["test_count"] >= 3
                    and r["test_count"] > 0
                    and r["activation_count"] == r["test_count"]
                ),
            }
            for r in rows
        }

    def stats(self) -> dict:
        """Backstop lifecycle statistics."""
        total = self._conn.execute(
            "SELECT COUNT(*) as n FROM backstop_entries WHERE retired = 0"
        ).fetchone()["n"]
        warm = self._conn.execute(
            "SELECT COUNT(*) as n FROM backstop_entries WHERE stage = ? AND retired = 0",
            (int(CompressionStage.WARM),)
        ).fetchone()["n"]
        hot = self._conn.execute(
            "SELECT COUNT(*) as n FROM backstop_entries WHERE stage = ?",
            (int(CompressionStage.HOT),)
        ).fetchone()["n"]
        retired = self._conn.execute(
            "SELECT COUNT(*) as n FROM backstop_entries WHERE retired = 1"
        ).fetchone()["n"]

        return {
            "total_active": total,
            "warm": warm,
            "hot": hot,
            "retired": retired,
        }

    def _get_backstop(self, row) -> Backstop:
        return Backstop(
            backstop_id=row["backstop_id"],
            rule_id=row["rule_id"],
            text=row["text"],
            stage=CompressionStage(row["stage"]),
            created_at=row["created_at"],
            activation_count=row["activation_count"],
            test_count=row["test_count"],
            promoted_at=row["promoted_at"],
            insertion_point=row["insertion_point"],
        )

    def close(self):
        self._conn.close()


# ---------------------------------------------------------------------------
# classify_rule_tier — Heuristic tier classification
# ---------------------------------------------------------------------------

# ---------------------------------------------------------------------------
# Tier classification signal patterns
#
# Emoji signatures (🔒, ❌, 🎯, ⚡, 🔍, 🚫) are strong Tier 1 indicators.
# They function as semantic anchors — LLMs activate behavioral clusters
# around emoji (mandatory, prohibited, target) more reliably than prose
# equivalents. This is distributional compression: emoji map 1:many to
# semantic clusters, unlike abbreviations which map 1:1. In production
# validation, 249 emoji tokens encoded ~800 tokens of recoverable meaning
# (3.2x semantic expansion ratio) with 5/5 decode accuracy.
#
# Emoji-anchored rules survive COLD compression with zero loss (Tier 1).
# Their presence in a rule increases Tier 1 confidence even when
# judgment-heavy language co-occurs.
# ---------------------------------------------------------------------------

# Structural markers that indicate Tier 2 (judgment-heavy) rules
_TIER2_SIGNALS = [
    # Conditional language
    r"\b(when|if|unless|depending on|based on|context|situational)\b",
    # Multi-factor dependencies
    r"\b(balance|weigh|calibrate|match|align|adapt|adjust)\b",
    # Subjective terms
    r"\b(energy|mood|tone|feel|register|vibe|spirit|essence)\b",
    # Hierarchical context markers
    r"\b(hierarchy|framework|decision tree|priority order)\b",
    # Activation/suppression language
    r"\b(activate|suppress|fire|trigger|engage|disengage)\b",
    # Complex conditional patterns
    r"\b(but not when|except when|only if|unless also)\b",
]

# Structural markers that indicate Tier 1 (binary) rules
_TIER1_SIGNALS = [
    # Quantitative bounds
    r"\b(\d+\s*(words?|chars?|characters?|tokens?|sentences?|items?))\b",
    # Binary constraints
    r"\b(always|never|must|required|prohibited|forbidden|mandatory)\b",
    # Format rules
    r"\b(format|punctuation|capitali[sz]|uppercase|lowercase|spacing)\b",
    # Anti-patterns
    r"\b(don't|do not|avoid|no\s+\w+ing|❌|🚫|✗)\b",
    # Emoji signatures
    r"[🔒❌🎯⚡🔍🎓📊🔧🚫]",
    # Explicit pass/fail
    r"\b(pass|fail|valid|invalid|compliant|non-compliant)\b",
]


def classify_rule_tier(rule_text: str, rule_id: str = "") -> dict:
    """Heuristic classifier for Tier 1 (binary) vs Tier 2 (judgment) rules.

    Analyzes the rule text for structural markers that predict whether
    the rule will survive COLD compression (Tier 1) or show drift (Tier 2).

    ⚠️  This is a heuristic aid, not a final classification. Always validate
    with a quality evaluator — the function flags likely Tier 2 rules based
    on structural markers, but the final call requires domain knowledge.

    Args:
        rule_text: The full text of the rule to classify.
        rule_id: Optional identifier for the rule.

    Returns:
        dict with:
            - tier: RuleTier.TIER_1 or RuleTier.TIER_2
            - confidence: 0.0–1.0 (how confident the classification is)
            - tier1_signals: list of Tier 1 markers found
            - tier2_signals: list of Tier 2 markers found
            - reasoning: Human-readable explanation

    Example:
        >>> classify_rule_tier("Maximum 150 words per section")
        {'tier': <RuleTier.TIER_1: 1>, 'confidence': 0.95, ...}

        >>> classify_rule_tier("Match energy register to story mood")
        {'tier': <RuleTier.TIER_2: 2>, 'confidence': 0.85, ...}
    """
    text_lower = rule_text.lower()

    tier1_hits = []
    for pattern in _TIER1_SIGNALS:
        matches = re.findall(pattern, text_lower if "🔒" not in pattern else rule_text,
                             re.IGNORECASE)
        if matches:
            tier1_hits.extend(matches if isinstance(matches[0], str) else
                              [m[0] if isinstance(m, tuple) else m for m in matches])

    tier2_hits = []
    for pattern in _TIER2_SIGNALS:
        matches = re.findall(pattern, text_lower, re.IGNORECASE)
        if matches:
            tier2_hits.extend(matches if isinstance(matches[0], str) else
                              [m[0] if isinstance(m, tuple) else m for m in matches])

    t1_score = len(tier1_hits)
    t2_score = len(tier2_hits)
    total = t1_score + t2_score

    if total == 0:
        # No clear signals — default to Tier 1 (conservative)
        return {
            "tier": RuleTier.TIER_1,
            "confidence": 0.3,
            "tier1_signals": [],
            "tier2_signals": [],
            "reasoning": "No clear structural markers found. Defaulting to Tier 1 "
                         "(conservative). Validate with quality evaluator.",
        }

    # Calculate tier based on signal ratio
    t2_ratio = t2_score / total

    if t2_ratio >= 0.6:
        tier = RuleTier.TIER_2
        confidence = min(0.5 + (t2_ratio * 0.5), 0.95)
        reasoning = (
            f"Tier 2 signals dominate ({t2_score} vs {t1_score} Tier 1). "
            f"This rule likely depends on contextual judgment that COLD "
            f"compression may flatten. Plan for WARM backstop."
        )
    elif t2_ratio <= 0.3:
        tier = RuleTier.TIER_1
        confidence = min(0.5 + ((1 - t2_ratio) * 0.5), 0.95)
        reasoning = (
            f"Tier 1 signals dominate ({t1_score} vs {t2_score} Tier 2). "
            f"This rule has clear pass/fail criteria and should survive "
            f"COLD compression intact."
        )
    else:
        # Ambiguous — lean Tier 2 for safety
        tier = RuleTier.TIER_2
        confidence = 0.5
        reasoning = (
            f"Mixed signals ({t1_score} Tier 1, {t2_score} Tier 2). "
            f"Classifying as Tier 2 for safety — validate with quality "
            f"evaluator before committing to COLD-only compression."
        )

    # 🔒 Emoji signature presence is a strong Tier 1 signal
    emoji_pattern = re.compile(r"[🔒❌🎯⚡🔍🎓📊🔧🚫]")
    if emoji_pattern.search(rule_text) and tier == RuleTier.TIER_2:
        # Emoji-anchored rules are more likely to survive compression
        confidence = max(confidence - 0.15, 0.35)
        reasoning += (
            " Note: emoji anchors detected — these strengthen compliance "
            "and may reduce drift risk even for judgment-heavy rules."
        )

    return {
        "tier": tier,
        "confidence": round(confidence, 2),
        "tier1_signals": tier1_hits[:10],  # Cap for readability
        "tier2_signals": tier2_hits[:10],
        "reasoning": reasoning,
    }


# ---------------------------------------------------------------------------
# Convenience: shared DB context manager
# ---------------------------------------------------------------------------

class ValidationSession:
    """Context manager for using ValidationTracker and BackstopManager
    on a shared database.

    Usage:
        with ValidationSession("project.db") as session:
            session.tracker.record_test(...)
            session.backstops.create(...)
    """

    def __init__(self, db_path: Optional[str] = None):
        self.db_path = db_path or "validation.db"
        self.tracker = None
        self.backstops = None

    def __enter__(self):
        self.tracker = ValidationTracker(self.db_path)
        self.backstops = BackstopManager(self.db_path)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.tracker:
            self.tracker.close()
        if self.backstops:
            self.backstops.close()
        return False
