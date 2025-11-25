#!/usr/bin/env bash
# Build script pour Render

set -o errexit  # Exit on error

echo "🚀 Début du build pour Render..."

# Installer les dépendances Python
echo "📦 Installation des dépendances Python..."
pip install -r requirements.txt

# Installer les navigateurs Playwright pour le scraping de sites JavaScript
echo "🎭 Installation des navigateurs Playwright..."
playwright install chromium --with-deps || echo "⚠️ Playwright installation partielle - continuons quand même"

# WeasyPrint est utilisé pour la génération PDF professionnelle
# C'est la solution standard pour Django en production (pas de binaire Chromium requis)
echo "✅ WeasyPrint configuré pour la génération PDF"

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


