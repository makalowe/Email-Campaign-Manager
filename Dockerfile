FROM python:3.11-slim

WORKDIR /app

# Dépendances système (aucune pour ce projet, tout est Python pur)
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Créer le dossier data avec les bonnes permissions
RUN mkdir -p /app/data && chmod 777 /app/data

EXPOSE 5000

# Par défaut : gunicorn avec 1 worker (car APScheduler, éviter les doublons)
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", \
     "--timeout", "120", "--access-logfile", "-", "app:create_app()"]
