"""
Envoi d'emails via SMTP avec retry et template HTML.
"""

import smtplib
import time
from email.message import EmailMessage
from pathlib import Path
from typing import Optional

from config import config


def build_message(to_email: str, subject: str, body_text: str,
                  html_template: Optional[str] = None,
                  tracking_url: str = "",
                  attachment_path: Optional[str] = None) -> EmailMessage:
    """
    Construit un EmailMessage.
    - Si html_template est fourni, on l'utilise (format {body} et {tracking_url}).
    - Sinon on envoie le body_text en texte brut.
    """
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.SENDER_EMAIL
    msg["To"] = to_email

    if html_template:
        html = html_template.format(body=body_text, tracking_url=tracking_url)
        msg.set_content(body_text)  # fallback texte
        msg.add_alternative(html, subtype="html")
    else:
        msg.set_content(body_text)

    # Pièce jointe optionnelle
    if attachment_path and Path(attachment_path).exists():
        with open(attachment_path, "rb") as f:
            file_data = f.read()
            filename = Path(attachment_path).name
        msg.add_attachment(file_data, maintype="application", subtype="octet-stream",
                           filename=filename)

    return msg


def send_one_email(to_email: str, subject: str, body_text: str,
                   html_template: Optional[str] = None,
                   tracking_url: str = "",
                   attachment_path: Optional[str] = None,
                   retries: int = 3) -> tuple[bool, str]:
    """
    Envoie un email avec 3 tentatives.
    Retourne (success: bool, error_message: str).
    """
    msg = build_message(to_email, subject, body_text,
                        html_template, tracking_url, attachment_path)

    for attempt in range(retries):
        try:
            if config.SMTP_USE_SSL:
                with smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
                    server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
                    server.send_message(msg)
            else:
                with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=30) as server:
                    server.starttls()
                    server.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
                    server.send_message(msg)
            return True, ""
        except smtplib.SMTPDataError as e:
            # Erreur permanente — inutile de retenter
            return False, f"SMTP permanent error: {e}"
        except Exception as e:
            if attempt < retries - 1:
                time.sleep(5 * (attempt + 1))
            else:
                return False, str(e)

    return False, "All retries exhausted"
