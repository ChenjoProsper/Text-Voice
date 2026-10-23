FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# Toutes les dépendances ont des wheels : pas besoin de build-essential
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p static/audio documents

EXPOSE 5000

# UN seul worker : l'état des tâches est en mémoire. Timeout long pour les gros livres.
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "--workers", "1", "--threads", "8", "--timeout", "900", "app:app"]
