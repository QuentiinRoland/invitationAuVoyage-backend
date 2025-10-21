#!/usr/bin/env python3
"""
Script de vérification pour le déploiement sur Render.
Exécutez ce script avant de déployer pour vous assurer que tout est configuré correctement.
"""

import os
import sys
from pathlib import Path

def check_file_exists(filepath, description):
    """Vérifie qu'un fichier existe."""
    if Path(filepath).exists():
        print(f"✅ {description}: OK")
        return True
    else:
        print(f"❌ {description}: MANQUANT")
        return False

def check_file_executable(filepath, description):
    """Vérifie qu'un fichier est exécutable."""
    path = Path(filepath)
    if path.exists() and os.access(filepath, os.X_OK):
        print(f"✅ {description}: EXÉCUTABLE")
        return True
    elif path.exists():
        print(f"⚠️  {description}: Existe mais pas exécutable (sera corrigé par Render)")
        return True
    else:
        print(f"❌ {description}: MANQUANT")
        return False

def check_requirements():
    """Vérifie que requirements.txt contient les dépendances essentielles."""
    required_packages = [
        'Django',
        'djangorestframework',
        'gunicorn',
        'psycopg2-binary',
        'dj-database-url',
        'whitenoise',
        'python-dotenv'
    ]
    
    try:
        with open('requirements.txt', 'r') as f:
            content = f.read().lower()
            
        missing = []
        for package in required_packages:
            if package.lower() not in content:
                missing.append(package)
        
        if missing:
            print(f"❌ requirements.txt: Manque {', '.join(missing)}")
            return False
        else:
            print(f"✅ requirements.txt: Toutes les dépendances essentielles présentes")
            return True
    except FileNotFoundError:
        print(f"❌ requirements.txt: MANQUANT")
        return False

def check_settings():
    """Vérifie les configurations importantes dans settings.py."""
    try:
        with open('config/settings.py', 'r') as f:
            content = f.read()
        
        checks = {
            'dj_database_url': 'Configuration PostgreSQL',
            'ALLOWED_HOSTS': 'ALLOWED_HOSTS',
            'STATIC_ROOT': 'Fichiers statiques',
            'whitenoise': 'WhiteNoise middleware',
        }
        
        all_ok = True
        for check, description in checks.items():
            if check in content:
                print(f"✅ {description}: Configuré")
            else:
                print(f"❌ {description}: MANQUANT dans settings.py")
                all_ok = False
        
        return all_ok
    except FileNotFoundError:
        print(f"❌ config/settings.py: MANQUANT")
        return False

def main():
    print("🔍 Vérification de la configuration pour Render\n")
    print("=" * 60)
    
    checks = []
    
    # Vérifier les fichiers essentiels
    print("\n📁 Fichiers de configuration:")
    checks.append(check_file_exists('requirements.txt', 'requirements.txt'))
    checks.append(check_file_exists('build.sh', 'build.sh'))
    checks.append(check_file_exists('gunicorn.render.conf.py', 'gunicorn.render.conf.py'))
    checks.append(check_file_exists('config/settings.py', 'settings.py'))
    checks.append(check_file_exists('config/wsgi.py', 'wsgi.py'))
    checks.append(check_file_exists('manage.py', 'manage.py'))
    
    # Vérifier que build.sh est exécutable
    print("\n🔐 Permissions:")
    checks.append(check_file_executable('build.sh', 'build.sh'))
    
    # Vérifier le contenu de requirements.txt
    print("\n📦 Dépendances Python:")
    checks.append(check_requirements())
    
    # Vérifier les configurations dans settings.py
    print("\n⚙️  Configuration Django:")
    checks.append(check_settings())
    
    # Vérifier render.yaml dans le dossier parent
    print("\n🌐 Configuration Render:")
    parent_render_yaml = Path('..') / 'render.yaml'
    if parent_render_yaml.exists():
        print(f"✅ render.yaml trouvé dans le dossier parent")
        checks.append(True)
    else:
        print(f"⚠️  render.yaml non trouvé (optionnel si vous déployez manuellement)")
        checks.append(True)  # Pas bloquant
    
    # Résumé
    print("\n" + "=" * 60)
    if all(checks):
        print("✅ TOUT EST PRÊT POUR LE DÉPLOIEMENT SUR RENDER ! 🚀")
        print("\nProcédure :")
        print("1. Pushez votre code sur GitHub/GitLab")
        print("2. Allez sur https://dashboard.render.com/")
        print("3. Créez un nouveau Blueprint depuis votre dépôt")
        print("4. Configurez les variables d'environnement")
        print("5. Déployez !")
        return 0
    else:
        print("❌ CERTAINS PROBLÈMES DOIVENT ÊTRE RÉSOLUS")
        print("\nConsultez le guide RENDER_DEPLOYMENT.md pour plus d'informations.")
        return 1

if __name__ == '__main__':
    # Changer le répertoire de travail vers le dossier backend
    os.chdir(Path(__file__).parent)
    sys.exit(main())


