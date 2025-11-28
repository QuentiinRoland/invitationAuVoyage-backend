# Image Python officielle
FROM python:3.11-slim

# Variables d'environnement
ENV PYTHONUNBUFFERED=1
ENV PLAYWRIGHT_BROWSERS_PATH=/ms-playwright

# Installer les dépendances système pour Playwright
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    ca-certificates \
    fonts-liberation \
    libasound2 \
    libatk-bridge2.0-0 \
    libatk1.0-0 \
    libcups2 \
    libdbus-1-3 \
    libgbm1 \
    libgtk-3-0 \
    libnspr4 \
    libnss3 \
    libx11-xcb1 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    xdg-utils \
    libxshmfence1 \
    libglu1-mesa \
    && rm -rf /var/lib/apt/lists/*

# Dossier de travail
WORKDIR /app

# Copier requirements et installer les deps Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Installer les navigateurs Playwright (avec skip de l'installation des deps - déjà installées)
RUN PLAYWRIGHT_SKIP_VALIDATE_HOST_REQUIREMENTS=true playwright install chromium

# Copier le reste du code
COPY . .

# Collecter les fichiers statiques (sans interaction)
RUN SECRET_KEY=temp python manage.py collectstatic --no-input --clear

# Port exposé
EXPOSE 8000

# Commande de démarrage
CMD python manage.py migrate && (python create_superuser.py || true) && gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 2 --timeout 120

