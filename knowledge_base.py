"""
Self-learning knowledge base.
Stores dentist feedback on AI findings and injects learned corrections
into future analysis prompts — improving accuracy with every case reviewed.
"""

import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "cases.db"


# ── Schema ────────────────────────────────────────────────────────────────────

def init_knowledge_tables():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()

    # Per-finding feedback
    c.execute('''CREATE TABLE IF NOT EXISTS feedback (
        id            INTEGER PRIMARY KEY AUTOINCREMENT,
        case_id       INTEGER,
        category      TEXT,     -- e.g. "caries", "periapical", "periodontal"
        tooth_fdi     TEXT,     -- e.g. "36", "48"
        ai_finding    TEXT,     -- what AI said
        verdict       TEXT,     -- "confirmed" | "corrected" | "missed" | "false_positive"
        correct_finding TEXT,   -- dentist's correction (if verdict != confirmed)
        severity      TEXT,     -- dentist's severity rating
        notes         TEXT,
        created_at    TEXT
    )''')

    # Aggregated learned patterns (rebuilt periodically)
    c.execute('''CREATE TABLE IF NOT EXISTS learned_patterns (
        id          INTEGER PRIMARY KEY AUTOINCREMENT,
        pattern_key TEXT UNIQUE,   -- e.g. "periapical_false_positive_after_rct"
        description TEXT,
        frequency   INTEGER DEFAULT 1,
        confidence  REAL DEFAULT 0.5,
        last_seen   TEXT
    )''')

    conn.commit()
    conn.close()


# ── Feedback CRUD ─────────────────────────────────────────────────────────────

def save_feedback(case_id: int, category: str, tooth_fdi: str,
                  ai_finding: str, verdict: str,
                  correct_finding: str = "", severity: str = "", notes: str = ""):
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''INSERT INTO feedback
           (case_id, category, tooth_fdi, ai_finding, verdict,
            correct_finding, severity, notes, created_at)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (case_id, category, tooth_fdi, ai_finding, verdict,
         correct_finding, severity, notes, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    _update_patterns(category, verdict, ai_finding, correct_finding)


def get_feedback_stats():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('''SELECT
        COUNT(*) as total,
        SUM(CASE WHEN verdict="confirmed"      THEN 1 ELSE 0 END) as confirmed,
        SUM(CASE WHEN verdict="corrected"      THEN 1 ELSE 0 END) as corrected,
        SUM(CASE WHEN verdict="missed"         THEN 1 ELSE 0 END) as missed,
        SUM(CASE WHEN verdict="false_positive" THEN 1 ELSE 0 END) as false_pos
        FROM feedback''')
    row = c.fetchone()
    conn.close()
    if not row or row[0] == 0:
        return None
    total = row[0]
    return {
        "total":         total,
        "confirmed":     row[1] or 0,
        "corrected":     row[2] or 0,
        "missed":        row[3] or 0,
        "false_positive": row[4] or 0,
        "accuracy_pct":  round((row[1] or 0) / total * 100, 1) if total else 0,
    }


def get_recent_corrections(limit: int = 30):
    """Retrieve recent corrections to inject as learned context."""
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''SELECT category, tooth_fdi, ai_finding, verdict, correct_finding, notes
           FROM feedback
           WHERE verdict IN ("corrected","missed","false_positive")
           ORDER BY created_at DESC LIMIT ?''',
        (limit,)
    )
    rows = c.fetchall()
    conn.close()
    return rows


def get_all_feedback():
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT * FROM feedback ORDER BY created_at DESC')
    rows = c.fetchall()
    conn.close()
    return rows


# ── Pattern engine ────────────────────────────────────────────────────────────

def _update_patterns(category: str, verdict: str, ai_finding: str, correct_finding: str):
    """Upsert a learned pattern from a feedback entry."""
    if verdict == "confirmed":
        return  # Only learn from errors

    key = f"{verdict}::{category}::{ai_finding[:60]}"
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute('SELECT id, frequency FROM learned_patterns WHERE pattern_key = ?', (key,))
    row = c.fetchone()
    if row:
        new_freq = row[1] + 1
        confidence = min(0.95, 0.5 + new_freq * 0.05)
        c.execute(
            'UPDATE learned_patterns SET frequency=?, confidence=?, last_seen=? WHERE id=?',
            (new_freq, confidence, datetime.now().isoformat(), row[0])
        )
    else:
        desc = _build_pattern_description(verdict, category, ai_finding, correct_finding)
        c.execute(
            '''INSERT INTO learned_patterns (pattern_key, description, frequency, confidence, last_seen)
               VALUES (?, ?, 1, 0.5, ?)''',
            (key, desc, datetime.now().isoformat())
        )
    conn.commit()
    conn.close()


def _build_pattern_description(verdict, category, ai_finding, correct_finding):
    if verdict == "false_positive":
        return f"[{category.upper()}] AI over-reported: '{ai_finding[:80]}' — was NOT present."
    elif verdict == "missed":
        return f"[{category.upper()}] AI MISSED finding: '{correct_finding[:80]}'"
    elif verdict == "corrected":
        return f"[{category.upper()}] AI said: '{ai_finding[:60]}' → Correct: '{correct_finding[:60]}'"
    return f"[{category.upper()}] Feedback: {ai_finding[:80]}"


def build_learning_context(max_patterns: int = 15) -> Optional[str]:
    """
    Build a prompt injection string from learned patterns.
    Returns None if no patterns exist yet.
    """
    corrections = get_recent_corrections(limit=30)
    if not corrections:
        return None

    lines = [
        "\n\n---",
        "## LEARNED CORRECTIONS FROM REVIEWED CASES",
        "The following patterns were identified by reviewing dentist feedback on prior AI analyses.",
        "Apply these corrections proactively in your assessment:\n",
    ]

    # Also pull high-confidence patterns
    conn = sqlite3.connect(DB_PATH)
    c = conn.cursor()
    c.execute(
        '''SELECT description, frequency, confidence
           FROM learned_patterns
           WHERE confidence >= 0.6
           ORDER BY frequency DESC, confidence DESC
           LIMIT ?''',
        (max_patterns,)
    )
    patterns = c.fetchall()
    conn.close()

    if patterns:
        lines.append("**High-confidence learned patterns:**")
        for desc, freq, conf in patterns:
            lines.append(f"- {desc}  _(seen {freq}x, confidence {conf:.0%})_")

    if corrections:
        lines.append("\n**Recent individual corrections:**")
        seen = set()
        for cat, tooth, ai_f, verdict, correct_f, notes in corrections[:10]:
            entry = f"- [{cat.upper()} tooth {tooth or '?'}] {verdict.upper()}: "
            if verdict == "false_positive":
                entry += f"'{ai_f[:70]}' was NOT present"
            elif verdict == "missed":
                entry += f"Missed: '{correct_f[:70]}'"
            elif verdict == "corrected":
                entry += f"'{ai_f[:50]}' → '{correct_f[:50]}'"
            if entry not in seen:
                lines.append(entry)
                seen.add(entry)

    lines.append("---")
    return "\n".join(lines)
