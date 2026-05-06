"""
Migration utilitaire : importe les données depuis les fichiers JSON
(send_log.json, tracking.json) vers la nouvelle base SQLite.
Usage : python migrate_from_json.py
"""

import json
from pathlib import Path
import db


def migrate_send_log():
    log_file = Path("send_log.json")
    if not log_file.exists():
        print("ℹ️  send_log.json introuvable, ignoré.")
        return

    with open(log_file) as f:
        data = json.load(f)

    # Supporte les deux formats : liste d'emails ou dicts
    if isinstance(data, list):
        for item in data:
            if isinstance(item, str):
                db.add_recipient(email=item)
                db.mark_sent(item, success=True)
            elif isinstance(item, dict):
                email = item.get("email", item.get("to", ""))
                if email:
                    db.add_recipient(email=email)
                    db.mark_sent(email, success=item.get("success", True), error=item.get("error", ""))
        print(f"✅ Migré {len(data)} envois depuis send_log.json")
    else:
        print("⚠️  Format send_log.json non reconnu (liste attendue)")


def migrate_tracking():
    track_file = Path("tracking.json")
    if not track_file.exists():
        print("ℹ️  tracking.json introuvable, ignoré.")
        return

    with open(track_file) as f:
        clicked_emails = json.load(f)

    if isinstance(clicked_emails, list):
        for email in clicked_emails:
            email = email.strip().lower()
            if isinstance(email, str) and "@" in email:
                recipient = db.get_recipient_by_email(email)
                if recipient:
                    db.mark_clicked(recipient["token"])
        print(f"✅ Migré {len(clicked_emails)} clics depuis tracking.json")
    else:
        print("⚠️  Format tracking.json non reconnu (liste d'emails attendue)")


if __name__ == "__main__":
    db.init_db()
    print("🔄 Migration des données JSON vers SQLite...")
    migrate_send_log()
    migrate_tracking()
    print("✅ Migration terminée.")
