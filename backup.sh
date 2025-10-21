#!/bin/bash
# Script de sauvegarde automatisé pour Hetzner

set -e

# Configuration
BACKUP_DIR="/home/invitationauvoyage/backups"
DATE=$(date +%Y%m%d_%H%M%S)
DB_NAME="invitationauvoyage"
DB_USER="invitationauvoyage"
PROJECT_DIR="/home/invitationauvoyage/invitationAuVoyage/backend"

echo "💾 Début de la sauvegarde..."

# Créer le répertoire de sauvegarde
mkdir -p $BACKUP_DIR

# Sauvegarder la base de données
echo "🗄️ Sauvegarde de la base de données..."
pg_dump -h localhost -U $DB_USER $DB_NAME > $BACKUP_DIR/db_backup_$DATE.sql

# Compresser la sauvegarde de la base de données
gzip $BACKUP_DIR/db_backup_$DATE.sql

# Sauvegarder les fichiers média
echo "📁 Sauvegarde des fichiers média..."
if [ -d "$PROJECT_DIR/media" ]; then
    tar -czf $BACKUP_DIR/media_backup_$DATE.tar.gz -C $PROJECT_DIR media/
else
    echo "⚠️ Aucun fichier média à sauvegarder"
fi

# Sauvegarder la configuration
echo "⚙️ Sauvegarde de la configuration..."
tar -czf $BACKUP_DIR/config_backup_$DATE.tar.gz -C $PROJECT_DIR .env gunicorn.conf.py

# Supprimer les sauvegardes de plus de 7 jours
echo "🧹 Nettoyage des anciennes sauvegardes..."
find $BACKUP_DIR -name "*.sql.gz" -mtime +7 -delete
find $BACKUP_DIR -name "*.tar.gz" -mtime +7 -delete

# Afficher les informations de la sauvegarde
echo "✅ Sauvegarde terminée : $DATE"
echo "📊 Taille des sauvegardes :"
ls -lh $BACKUP_DIR/*$DATE*

# Vérifier l'espace disque
echo "💽 Espace disque disponible :"
df -h $BACKUP_DIR

