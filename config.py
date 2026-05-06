"""
Configuration centralisée — lue depuis .env ou variables d'environnement.
"""

import os
from dotenv import load_dotenv

load_dotenv()


class Config:
    # SMTP Hostinger (ou autre)
    SMTP_HOST = os.getenv("SMTP_HOST", "smtp.hostinger.com")
    SMTP_PORT = int(os.getenv("SMTP_PORT", "465"))
    SMTP_USERNAME = os.getenv("SMTP_USERNAME", "")
    SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
    SMTP_USE_SSL = os.getenv("SMTP_USE_SSL", "true").lower() == "true"

    # Expéditeur par défaut
    SENDER_EMAIL = os.getenv("SENDER_EMAIL", "booking@zionworld.fr")

    # URL de base pour les liens de tracking (ex: https://tracking.zionworld.fr)
    TRACKING_BASE_URL = os.getenv("TRACKING_BASE_URL", "http://localhost:5000")

    # URL de redirection après clic (page booking)
    BOOKING_URL = os.getenv("BOOKING_URL", "https://chacalbarband.wixsite.com/princesserika")

    # Limites d'envoi
    SEND_WINDOW_MINUTES = int(os.getenv("SEND_WINDOW_MINUTES", "5"))
    MAX_EMAILS_PER_DAY = int(os.getenv("MAX_EMAILS_PER_DAY", "90"))
    MAX_EMAILS_PER_WINDOW = int(os.getenv("MAX_EMAILS_PER_WINDOW", "1"))

    # Secret pour les tokens de tracking
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

    # Chemin de la BDD SQLite
    DATABASE_PATH = os.getenv("DATABASE_PATH", "data/campaign.db")

    # Templates HTML par défaut
    DEFAULT_HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="fr">
<head><meta charset="utf-8"></head>
<body style="font-family:Arial,Helvetica,sans-serif;line-height:1.5;max-width:600px;margin:0 auto;">
<p>Bonjour,</p>
<p>{body}</p>
<p style="margin-top:24px;font-size:12px;color:#888;">
  <a href="{tracking_url}" style="color:#888;">Se désinscrire</a>
</p>
</body>
</html>"""


config = Config()
