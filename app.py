"""
📧 Email Campaign Manager — API Flask
=====================================
Endpoints :
  POST   /send              → Envoyer un email (queue)
  GET    /status/<email>    → Statut d'un destinataire
  GET    /click/<token>     → Tracking de clic (redirection)
  GET    /stats             → Statistiques globales
  GET    /recipients        → Liste des destinataires (avec filtre status)
  POST   /send/now          → Envoi immédiat (sans passer par la queue)

Architecture :
  - SQLite avec 3 tables (recipients, sent_log, daily_stats)
  - APScheduler pour les envois espacés (5 min, max 90/jour)
  - Tracking par token unique (pas d'email en clair dans l'URL)
  - Templates HTML personnalisables par destinataire
"""

import os
import json
from datetime import datetime
from http import HTTPStatus

from flask import Flask, request, jsonify, redirect, abort
from werkzeug.exceptions import HTTPException

from config import config
import db
import scheduler as sched


def create_app() -> Flask:
    app = Flask(__name__)
    app.config["SECRET_KEY"] = config.SECRET_KEY

    # Initialiser la BDD
    db.init_db()

    # Démarrer le scheduler (sauf pendant les tests unitaires)
    if not os.getenv("FLASK_TESTING"):
        app.scheduler = sched.start_scheduler(app)

    # ─────────────────────────────────────────────────
    #  Routes
    # ─────────────────────────────────────────────────

    @app.route("/", methods=["GET"])
    def index():
        return jsonify({
            "service": "Email Campaign Manager",
            "version": "2.0",
            "endpoints": {
                "POST /send": "Ajouter un email dans la file d'attente",
                "GET  /status/<email>": "Voir le statut d'un envoi",
                "GET  /click/<token>": "Tracking de clic (redirection)",
                "GET  /stats": "Statistiques globales",
                "GET  /recipients": "Liste des destinataires",
                "POST /send/now": "Envoi immédiat (sans file d'attente)",
            },
            "limits": {
                "send_window_minutes": config.SEND_WINDOW_MINUTES,
                "max_per_day": config.MAX_EMAILS_PER_DAY,
            }
        }), HTTPStatus.OK

    # ────────────────────────────────────────
    #  POST /send — Ajouter à la file d'attente
    # ────────────────────────────────────────

    @app.route("/send", methods=["POST"])
    def send():
        """
        Ajoute un email dans la file d'attente.
        Le scheduler l'enverra dans les prochaines minutes.

        Body (JSON) :
        {
            "to": "programmateur@festival.be",   // obligatoire
            "subject": "Booking 2026",           // optionnel
            "body": "Bonjour, nous sommes...",   // optionnel
            "name": "Marc",                       // optionnel
            "html_template": "<html>....{body}...{tracking_url}...</html>",  // optionnel
            "attachment": "/path/to/file.pdf"     // optionnel (chemin serveur)
        }

        Retourne les infos du destinataire + son token de tracking.
        """
        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Body JSON requis"}), HTTPStatus.BAD_REQUEST

        to_email = (data.get("to") or "").strip().lower()
        if not to_email or "@" not in to_email:
            return jsonify({"error": "Champ 'to' invalide (email requis)"}), HTTPStatus.BAD_REQUEST

        # Ajouter dans la BDD (ou récupérer si déjà existant)
        recipient = db.add_recipient(
            email=to_email,
            name=data.get("name", ""),
            subject=data.get("subject", ""),
            body_text=data.get("body", ""),
            html_template=data.get("html_template", ""),
        )

        return jsonify({
            "status": "queued",
            "email": recipient["email"],
            "token": recipient["token"],
            "tracking_url": f"{config.TRACKING_BASE_URL}/click/{recipient['token']}",
            "message": "Email ajouté dans la file d'attente. "
                       f"Envoi programmé sous ~{config.SEND_WINDOW_MINUTES} min.",
        }), HTTPStatus.ACCEPTED

    # ────────────────────────────────────────
    #  POST /send/now — Envoi immédiat
    # ────────────────────────────────────────

    @app.route("/send/now", methods=["POST"])
    def send_now():
        """
        Envoie un email immédiatement (sans passer par la queue).
        Limite journalière quand même respectée.

        Body : identique à POST /send.
        """
        from email_sender import send_one_email

        data = request.get_json(silent=True)
        if not data:
            return jsonify({"error": "Body JSON requis"}), HTTPStatus.BAD_REQUEST

        to_email = (data.get("to") or "").strip().lower()
        if not to_email or "@" not in to_email:
            return jsonify({"error": "Champ 'to' invalide"}), HTTPStatus.BAD_REQUEST

        # Vérifier limite journalière
        today_count = db.get_today_count()
        if today_count >= config.MAX_EMAILS_PER_DAY:
            return jsonify({
                "error": "Limite journalière atteinte",
                "sent_today": today_count,
                "max_per_day": config.MAX_EMAILS_PER_DAY,
            }), HTTPStatus.TOO_MANY_REQUESTS

        html_template = data.get("html_template", "")
        body_text = data.get("body", "")
        subject = data.get("subject", "Nouveau message")
        tracking_url = ""
        attachment_path = data.get("attachment")

        # Ajouter le tracking
        recipient = db.add_recipient(
            email=to_email,
            name=data.get("name", ""),
            subject=subject,
            body_text=body_text,
            html_template=html_template,
        )
        tracking_url = f"{config.TRACKING_BASE_URL}/click/{recipient['token']}"

        success, error = send_one_email(
            to_email=to_email,
            subject=subject,
            body_text=body_text,
            html_template=html_template,
            tracking_url=tracking_url,
            attachment_path=attachment_path,
        )

        db.mark_sent(to_email, success, error)
        db.increment_sent_count(success)

        if success:
            return jsonify({
                "status": "sent",
                "email": to_email,
                "token": recipient["token"],
            }), HTTPStatus.OK
        else:
            return jsonify({
                "status": "failed",
                "email": to_email,
                "error": error,
            }), HTTPStatus.INTERNAL_SERVER_ERROR

    # ────────────────────────────────────────
    #  GET /status/<email> — Statut d'un envoi
    # ────────────────────────────────────────

    @app.route("/status/<email>", methods=["GET"])
    def status(email: str):
        recipient = db.get_recipient_by_email(email.strip().lower())
        if not recipient:
            return jsonify({"error": "Email introuvable", "email": email}), HTTPStatus.NOT_FOUND

        # Récupérer le log des tentatives
        with db._get_connection() as conn:
            log_rows = conn.execute(
                "SELECT sent_at, success, error FROM sent_log WHERE email = ? ORDER BY sent_at DESC",
                (email.strip().lower(),)
            ).fetchall()
        attempts = [dict(r) for r in log_rows]

        return jsonify({
            "email": recipient["email"],
            "status": recipient["status"],
            "sent_at": recipient.get("sent_at"),
            "clicked_at": recipient.get("clicked_at"),
            "error": recipient.get("error_msg"),
            "tracking_url": f"{config.TRACKING_BASE_URL}/click/{recipient['token']}",
            "attempts": attempts,
        }), HTTPStatus.OK

    # ────────────────────────────────────────
    #  GET /click/<token> — Tracking (redirection)
    # ────────────────────────────────────────

    @app.route("/click/<token>", methods=["GET"])
    def click_tracking(token: str):
        recipient = db.get_recipient_by_token(token)
        if not recipient:
            abort(HTTPStatus.NOT_FOUND, description="Lien de tracking invalide ou expiré.")

        db.mark_clicked(token)
        db.increment_click_count()

        # Rediriger vers la page de booking
        return redirect(config.BOOKING_URL, code=HTTPStatus.FOUND)

    # ────────────────────────────────────────
    #  GET /stats — Statistiques
    # ────────────────────────────────────────

    @app.route("/stats", methods=["GET"])
    def stats():
        days = request.args.get("days", 7, type=int)
        daily = db.get_stats(days=min(days, 90))
        totals = db.get_totals()
        today_count = db.get_today_count()
        return jsonify({
            "totals": totals,
            "today_sent": today_count,
            "max_per_day": config.MAX_EMAILS_PER_DAY,
            "daily": daily,
        }), HTTPStatus.OK

    # ────────────────────────────────────────
    #  GET /recipients — Liste des destinataires
    # ────────────────────────────────────────

    @app.route("/recipients", methods=["GET"])
    def list_recipients():
        status_filter = request.args.get("status")
        limit = request.args.get("limit", 100, type=int)
        offset = request.args.get("offset", 0, type=int)
        rows = db.list_recipients(status=status_filter, limit=min(limit, 500), offset=offset)
        return jsonify({
            "count": len(rows),
            "recipients": rows,
        }), HTTPStatus.OK

    # ────────────────────────────────────────
    #  Gestionnaire d'erreurs global
    # ────────────────────────────────────────

    @app.errorhandler(HTTPException)
    def handle_error(e: HTTPException):
        return jsonify({
            "error": e.description,
            "code": e.code,
        }), e.code

    return app


# ─────────────────────────────────────────────
#  Point d'entrée
# ─────────────────────────────────────────────

if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("FLASK_PORT", "5000"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    print(f"🚀  Email Campaign Manager démarré sur http://0.0.0.0:{port}")
    app.run(host="0.0.0.0", port=port, debug=debug)
