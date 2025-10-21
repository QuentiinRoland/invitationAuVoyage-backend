#!/usr/bin/env bash
# Build script pour Render

set -o errexit  # Exit on error

echo "🚀 Début du build pour Render..."

# Installer les dépendances Python
echo "📦 Installation des dépendances Python..."
pip install -r requirements.txt

# Installer Playwright (pour la génération PDF)
echo "🎭 Installation de Playwright..."
playwright install chromium

# Collecter les fichiers statiques
echo "📁 Collection des fichiers statiques..."
python manage.py collectstatic --no-input

# Appliquer les migrations
echo "🗄️ Application des migrations de base de données..."
python manage.py migrate

echo "✅ Build terminé avec succès !"


