"""
Scheduler APScheduler — tourne en arrière-plan dans l'app Flask.
Envoie 1 email toutes les SEND_WINDOW_MINUTES minutes,
avec un maximum de MAX_EMAILS_PER_DAY par jour.
"""

from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

from config import config
import db
import email_sender as sender


def send_one_per_window():
    """Callback exécuté périodiquement par le scheduler."""
    # Vérifier la limite journalière
    today_count = db.get_today_count()
    if today_count >= config.MAX_EMAILS_PER_DAY:
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] ❌ Limite journalière atteinte "
              f"({today_count}/{config.MAX_EMAILS_PER_DAY})")
        return

    # Récupérer le prochain destinataire en attente
    recipient = db.get_next_pending()
    if not recipient:
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] ℹ️  Aucun email en attente.")
        return

    email = recipient["email"]
    subject = recipient.get("subject") or config.EMAIL_SUBJECT
    body_text = recipient.get("body_text") or "Découvrez notre offre."
    html_template = recipient.get("html_template") or config.DEFAULT_HTML_TEMPLATE
    token = recipient.get("token", "")
    tracking_url = f"{config.TRACKING_BASE_URL}/click/{token}" if token else ""

    print(f"[{datetime.now():%Y-%m-%d %H:%M}] 📤 Envoi à {email}...")

    # Marquer comme "queued" avant l'envoi
    db.mark_queued(email)

    success, error = sender.send_one_email(
        to_email=email,
        subject=subject,
        body_text=body_text,
        html_template=html_template,
        tracking_url=tracking_url,
    )

    db.mark_sent(email, success, error)
    db.increment_sent_count(success)

    if success:
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] ✅  Envoyé à {email}")
    else:
        print(f"[{datetime.now():%Y-%m-%d %H:%M}] ❌ Échec {email} : {error}")


def start_scheduler(app) -> BackgroundScheduler:
    """
    Démarre le scheduler APScheduler en arrière-plan.
    À appeler dans create_app().
    """
    scheduler = BackgroundScheduler()
    scheduler.add_job(
        send_one_per_window,
        trigger=IntervalTrigger(minutes=config.SEND_WINDOW_MINUTES),
        id="email_campaign_sender",
        replace_existing=True,
    )
    scheduler.start()
    print(f"[scheduler] ✅  Démarré — envoi toutes les {config.SEND_WINDOW_MINUTES} min "
          f"(max {config.MAX_EMAILS_PER_DAY}/jour)")
    return scheduler
