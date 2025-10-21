#!/usr/bin/env bash
# Build script pour Render

set -o errexit  # Exit on error

echo "🚀 Début du build pour Render..."

# Installer les dépendances Python
echo "📦 Installation des dépendances Python..."
pip install -r requirements.txt

# Installation de Playwright Chromium (sans sudo - compatible Render)
echo "🎭 Installation de Playwright Chromium..."
# Installer uniquement le binaire sans les dépendances système
PLAYWRIGHT_BROWSERS_PATH=0 playwright install chromium

# Collecter les fichiers statiques
echo "📁 Collection des fichiers statiques..."
python manage.py collectstatic --no-input

# Appliquer les migrations
echo "🗄️ Application des migrations de base de données..."
python manage.py migrate

# Créer le superuser automatiquement
echo "👤 Création du superuser..."
python create_superuser.py

echo "✅ Build terminé avec succès !"


