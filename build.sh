#!/usr/bin/env bash
# Build script pour Render

set -o errexit  # Exit on error

echo "🚀 Début du build pour Render..."

# Installer les dépendances Python
echo "📦 Installation des dépendances Python..."
pip install -r requirements.txt

# Note : Playwright nécessite des droits root non disponibles sur Render Free
# On utilise WeasyPrint pour la génération PDF (déjà installé via requirements.txt)
echo "📄 WeasyPrint sera utilisé pour la génération PDF"

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


