#!/bin/bash
# Script de déploiement automatisé pour Hetzner

set -e

echo "🚀 Début du déploiement sur Hetzner..."

# Configuration
PROJECT_DIR="/home/invitationauvoyage/invitationAuVoyage/backend"
SERVICE_NAME="invitationauvoyage"

# Vérifier que nous sommes dans le bon répertoire
if [ ! -f "manage.py" ]; then
    echo "❌ Erreur: manage.py non trouvé. Êtes-vous dans le répertoire backend ?"
    exit 1
fi

# Activer l'environnement virtuel
echo "📦 Activation de l'environnement virtuel..."
source venv/bin/activate

# Récupérer les dernières modifications
echo "📥 Récupération des dernières modifications..."
git pull origin main

# Installer les nouvelles dépendances
echo "📦 Installation des dépendances..."
pip install --upgrade pip
pip install -r requirements.txt

# Appliquer les migrations
echo "🗄️ Application des migrations..."
python manage.py migrate

# Collecter les fichiers statiques
echo "📁 Collection des fichiers statiques..."
python manage.py collectstatic --noinput

# Redémarrer le service
echo "🔄 Redémarrage du service..."
sudo systemctl restart $SERVICE_NAME

# Vérifier le statut du service
echo "✅ Vérification du statut du service..."
sudo systemctl status $SERVICE_NAME --no-pager

echo "🎉 Déploiement terminé avec succès !"
echo "🌐 Votre application est accessible sur : http://$(curl -s ifconfig.me)/api/"

