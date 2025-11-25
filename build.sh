#!/usr/bin/env bash
# Build script pour Render

set -o errexit  # Exit on error

echo "🚀 Début du build pour Render..."

# Installer les dépendances Python
echo "📦 Installation des dépendances Python..."
pip install -r requirements.txt

# Note: Playwright nécessite des droits root sur Render (pas disponible en free tier)
# Solution recommandée: Configurer UNSPLASH_ACCESS_KEY ou TAVILY_API_KEY dans Environment
# Ces APIs fonctionnent mieux sur Render et garantissent des images

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


