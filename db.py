"""
Couche d'accès aux données SQLite.
Tables : recipients, sent_log, daily_stats, tracking_tokens
"""

import sqlite3
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Optional

from config import config


def _get_connection() -> sqlite3.Connection:
    Path(config.DATABASE_PATH).parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DATABASE_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    return conn


def init_db() -> None:
    """Crée les tables si elles n'existent pas."""
    with _get_connection() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS recipients (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                email       TEXT    NOT NULL UNIQUE,
                name        TEXT    DEFAULT '',
                subject     TEXT    DEFAULT '',
                body_text   TEXT    DEFAULT '',
                html_template TEXT  DEFAULT '',
                status      TEXT    NOT NULL DEFAULT 'pending',
                    -- pending | queued | sent | failed | clicked | bounced
                token       TEXT    UNIQUE,
                created_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                sent_at     TEXT,
                clicked_at  TEXT,
                error_msg   TEXT
            );

            CREATE TABLE IF NOT EXISTS sent_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                email       TEXT    NOT NULL,
                recipient_id INTEGER REFERENCES recipients(id),
                success     INTEGER NOT NULL DEFAULT 0,
                error       TEXT,
                sent_at     TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            CREATE TABLE IF NOT EXISTS daily_stats (
                date        TEXT    PRIMARY KEY,
                sent_count  INTEGER NOT NULL DEFAULT 0,
                fail_count  INTEGER NOT NULL DEFAULT 0,
                click_count INTEGER NOT NULL DEFAULT 0
            );

            CREATE INDEX IF NOT EXISTS idx_recipients_status  ON recipients(status);
            CREATE INDEX IF NOT EXISTS idx_recipients_token   ON recipients(token);
            CREATE INDEX IF NOT EXISTS idx_sent_log_email     ON sent_log(email);
        """)


# ─────────────────────────────────────────────
#  RECIPIENTS
# ─────────────────────────────────────────────

def add_recipient(email: str, name: str = "",
                  subject: str = "", body_text: str = "",
                  html_template: str = "") -> dict:
    """Ajoute un destinataire. Retourne ses infos."""
    token = uuid.uuid4().hex[:16]
    with _get_connection() as conn:
        try:
            conn.execute("""
                INSERT INTO recipients (email, name, subject, body_text, html_template, token)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (email.strip().lower(), name, subject, body_text, html_template, token))
            conn.commit()
        except sqlite3.IntegrityError:
            # Déjà existant → récupérer son token
            row = conn.execute("SELECT * FROM recipients WHERE email = ?", (email.strip().lower(),)).fetchone()
            return dict(row)
        row = conn.execute("SELECT * FROM recipients WHERE email = ?", (email.strip().lower(),)).fetchone()
        return dict(row)


def get_recipient_by_email(email: str) -> Optional[dict]:
    with _get_connection() as conn:
        row = conn.execute("SELECT * FROM recipients WHERE email = ?", (email.strip().lower(),)).fetchone()
        return dict(row) if row else None


def get_recipient_by_token(token: str) -> Optional[dict]:
    with _get_connection() as conn:
        row = conn.execute("SELECT * FROM recipients WHERE token = ?", (token,)).fetchone()
        return dict(row) if row else None


def get_next_pending() -> Optional[dict]:
    """Récupère le prochain destinataire en attente (le plus ancien first)."""
    with _get_connection() as conn:
        row = conn.execute("""
            SELECT * FROM recipients
            WHERE status = 'pending'
            ORDER BY created_at ASC
            LIMIT 1
        """).fetchone()
        return dict(row) if row else None


def mark_queued(email: str) -> None:
    with _get_connection() as conn:
        conn.execute("UPDATE recipients SET status = 'queued' WHERE email = ?", (email.strip().lower(),))
        conn.commit()


def mark_sent(email: str, success: bool, error: str = "") -> None:
    status = "sent" if success else "failed"
    now = datetime.utcnow().isoformat()
    with _get_connection() as conn:
        conn.execute("""
            UPDATE recipients
            SET status = ?, sent_at = ?, error_msg = ?
            WHERE email = ?
        """, (status, now, error, email.strip().lower()))
        conn.execute("""
            INSERT INTO sent_log (email, success, error, sent_at)
            VALUES (?, ?, ?, ?)
        """, (email.strip().lower(), 1 if success else 0, error, now))
        conn.commit()


def mark_clicked(token: str) -> None:
    now = datetime.utcnow().isoformat()
    with _get_connection() as conn:
        conn.execute("""
            UPDATE recipients
            SET status = 'clicked', clicked_at = ?
            WHERE token = ?
        """, (now, token))
        conn.commit()


def list_recipients(status: Optional[str] = None, limit: int = 100, offset: int = 0) -> list[dict]:
    with _get_connection() as conn:
        if status:
            rows = conn.execute("""
                SELECT * FROM recipients WHERE status = ?
                ORDER BY created_at DESC LIMIT ? OFFSET ?
            """, (status, limit, offset)).fetchall()
        else:
            rows = conn.execute("""
                SELECT * FROM recipients
                ORDER BY created_at DESC LIMIT ? OFFSET ?
            """, (limit, offset)).fetchall()
        return [dict(r) for r in rows]


# ─────────────────────────────────────────────
#  DAILY STATS
# ─────────────────────────────────────────────

def get_today_count() -> int:
    today_str = date.today().isoformat()
    with _get_connection() as conn:
        row = conn.execute("SELECT sent_count FROM daily_stats WHERE date = ?", (today_str,)).fetchone()
        return row["sent_count"] if row else 0


def increment_sent_count(success: bool) -> None:
    today_str = date.today().isoformat()
    with _get_connection() as conn:
        conn.execute("""
            INSERT INTO daily_stats (date, sent_count, fail_count, click_count)
            VALUES (?, ?, ?, 0)
            ON CONFLICT(date) DO UPDATE SET
                sent_count = sent_count + ?,
                fail_count = fail_count + ?
        """, (today_str, 1 if success else 0, 0 if success else 1,
              1 if success else 0, 0 if success else 1))
        conn.commit()


def increment_click_count() -> None:
    today_str = date.today().isoformat()
    with _get_connection() as conn:
        conn.execute("""
            INSERT INTO daily_stats (date, sent_count, fail_count, click_count)
            VALUES (?, 0, 0, 1)
            ON CONFLICT(date) DO UPDATE SET
                click_count = click_count + 1
        """, (today_str,))
        conn.commit()


def get_stats(days: int = 7) -> list[dict]:
    """Retourne les stats des N derniers jours."""
    with _get_connection() as conn:
        rows = conn.execute("""
            SELECT * FROM daily_stats
            ORDER BY date DESC
            LIMIT ?
        """, (days,)).fetchall()
        return [dict(r) for r in rows]


def get_totals() -> dict:
    """Totaux cumulés."""
    with _get_connection() as conn:
        total_sent = conn.execute("SELECT COUNT(*) as c FROM sent_log WHERE success = 1").fetchone()["c"]
        total_fail = conn.execute("SELECT COUNT(*) as c FROM sent_log WHERE success = 0").fetchone()["c"]
        total_clicked = conn.execute("SELECT COUNT(*) as c FROM recipients WHERE status = 'clicked'").fetchone()["c"]
        total_pending = conn.execute("SELECT COUNT(*) as c FROM recipients WHERE status = 'pending'").fetchone()["c"]
        return {
            "total_sent": total_sent,
            "total_fail": total_fail,
            "total_clicked": total_clicked,
            "total_pending": total_pending,
        }
