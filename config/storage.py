"""
Configuration du stockage de fichiers pour la production
Supporte le stockage local et AWS S3
"""

import os
from django.conf import settings

# Configuration du stockage selon l'environnement
if not settings.DEBUG and os.getenv('USE_S3') == 'true':
    # Configuration AWS S3 pour la production
    DEFAULT_FILE_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'
    STATICFILES_STORAGE = 'storages.backends.s3boto3.S3StaticStorage'
    
    # Paramètres AWS
    AWS_ACCESS_KEY_ID = os.getenv('AWS_ACCESS_KEY_ID')
    AWS_SECRET_ACCESS_KEY = os.getenv('AWS_SECRET_ACCESS_KEY')
    AWS_STORAGE_BUCKET_NAME = os.getenv('AWS_STORAGE_BUCKET_NAME')
    AWS_S3_REGION_NAME = os.getenv('AWS_S3_REGION_NAME', 'eu-west-3')
    
    # Configuration S3
    AWS_S3_FILE_OVERWRITE = False
    AWS_DEFAULT_ACL = None
    AWS_S3_VERIFY = True
    AWS_S3_SIGNATURE_VERSION = 's3v4'
    
    # URLs personnalisées
    AWS_S3_CUSTOM_DOMAIN = f'{AWS_STORAGE_BUCKET_NAME}.s3.{AWS_S3_REGION_NAME}.amazonaws.com'
    
    # Séparation des fichiers media et static
    AWS_LOCATION = 'static'
    AWS_MEDIA_LOCATION = 'media'
    
    # URLs publiques
    STATIC_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_LOCATION}/'
    MEDIA_URL = f'https://{AWS_S3_CUSTOM_DOMAIN}/{AWS_MEDIA_LOCATION}/'
    
    print("📦 Stockage configuré : AWS S3")
    
else:
    # Configuration locale pour le développement et Render
    import os
    from django.core.files.storage import FileSystemStorage
    
    # Stockage local
    MEDIA_ROOT = settings.BASE_DIR / 'media'
    MEDIA_URL = '/media/'
    
    # Créer le dossier media s'il n'existe pas
    os.makedirs(MEDIA_ROOT, exist_ok=True)
    
    print("📦 Stockage configuré : Système de fichiers local")


class OptimizedFileStorage(FileSystemStorage):
    """
    Stockage optimisé avec gestion des erreurs et nettoyage automatique
    """
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
    def _save(self, name, content):
        """Sauvegarde avec gestion d'erreur"""
        try:
            return super()._save(name, content)
        except Exception as e:
            print(f"Erreur sauvegarde fichier {name}: {e}")
            raise
    
    def delete(self, name):
        """Suppression avec gestion d'erreur"""
        try:
            return super().delete(name)
        except Exception as e:
            print(f"Erreur suppression fichier {name}: {e}")
            # Ne pas lever l'erreur pour éviter les crashes
            pass
    
    def exists(self, name):
        """Vérification d'existence avec gestion d'erreur"""
        try:
            return super().exists(name)
        except Exception as e:
            print(f"Erreur vérification fichier {name}: {e}")
            return False


def cleanup_old_files():
    """
    Nettoie les anciens fichiers (utile pour Render qui a un stockage temporaire)
    """
    import time
    from pathlib import Path
    
    if settings.DEBUG:
        return  # Ne pas nettoyer en développement
    
    try:
        media_root = Path(settings.MEDIA_ROOT)
        if not media_root.exists():
            return
        
        # Supprimer les fichiers plus vieux que 7 jours
        cutoff_time = time.time() - (7 * 24 * 60 * 60)
        
        for file_path in media_root.rglob('*'):
            if file_path.is_file():
                if file_path.stat().st_mtime < cutoff_time:
                    try:
                        file_path.unlink()
                        print(f"🗑️ Fichier ancien supprimé : {file_path.name}")
                    except Exception as e:
                        print(f"Erreur suppression {file_path}: {e}")
                        
    except Exception as e:
        print(f"Erreur nettoyage fichiers : {e}")


# Helpers pour l'upload de fichiers
def get_upload_path(instance, filename):
    """
    Génère un chemin d'upload organisé par type et date
    """
    import os
    from datetime import datetime
    
    # Obtenir l'extension du fichier
    name, ext = os.path.splitext(filename)
    
    # Créer un nom de fichier unique
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_filename = f"{timestamp}_{name[:50]}{ext}"
    
    # Organiser par type de document
    if hasattr(instance, 'document_type'):
        folder = instance.document_type
    else:
        folder = 'misc'
    
    return f'documents/{folder}/{unique_filename}'


def get_asset_upload_path(instance, filename):
    """
    Génère un chemin d'upload pour les assets (images, etc.)
    """
    import os
    from datetime import datetime
    
    name, ext = os.path.splitext(filename)
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    unique_filename = f"{timestamp}_{name[:50]}{ext}"
    
    return f'assets/{unique_filename}'


