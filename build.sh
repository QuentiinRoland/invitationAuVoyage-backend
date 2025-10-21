#!/usr/bin/env bash
# Build script pour Render

set -o errexit  # Exit on error

echo "🚀 Début du build pour Render..."

# Installer les dépendances Python
echo "📦 Installation des dépendances Python..."
pip install -r requirements.txt

# Installation de Playwright avec Chromium (Render Pro)
echo "🎭 Installation de Playwright avec Chromium..."
playwright install --with-deps chromium

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


