#!/usr/bin/env python
"""
Script ultra-simple pour vérifier la config Amadeus.
Lance ça d'abord avant le test complet.
"""

import os
import sys
from pathlib import Path

# Setup path
sys.path.insert(0, str(Path(__file__).parent))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

try:
    import django
    django.setup()
except Exception as e:
    print(f"❌ Erreur Django setup: {e}")
    sys.exit(1)

from django.conf import settings


def check_env_file():
    """Vérifie que le fichier .env existe"""
    env_path = Path(__file__).parent / '.env'
    if env_path.exists():
        print("✅ Fichier .env trouvé")
        return True
    else:
        print("❌ Fichier .env non trouvé")
        print()
        print("📝 Crée le fichier backend/.env avec ce contenu :")
        print()
        print("   AMADEUS_API_KEY=ta_key_ici")
        print("   AMADEUS_API_SECRET=ton_secret_ici")
        print()
        return False


def check_credentials():
    """Vérifie que les credentials sont configurés"""
    api_key = getattr(settings, 'AMADEUS_API_KEY', None)
    api_secret = getattr(settings, 'AMADEUS_API_SECRET', None)
    
    if not api_key or not api_secret:
        print("❌ Credentials Amadeus manquants dans .env")
        print()
        print("📝 Ajoute dans backend/.env :")
        print()
        print("   AMADEUS_API_KEY=ta_key_ici")
        print("   AMADEUS_API_SECRET=ton_secret_ici")
        print()
        print("🔑 Obtiens tes credentials sur https://developers.amadeus.com/")
        return False
    
    print(f"✅ AMADEUS_API_KEY configuré: {api_key[:10]}...")
    print(f"✅ AMADEUS_API_SECRET configuré: {api_secret[:10]}...")
    return True


def check_connection():
    """Teste la connexion à Amadeus"""
    try:
        from api.amadeus_integration import AmadeusFlightService
        
        print()
        print("🔌 Test de connexion à Amadeus...")
        
        amadeus = AmadeusFlightService(use_test=True)
        token = amadeus._get_access_token()
        
        if token:
            print(f"✅ Connexion réussie ! Token obtenu: {token[:20]}...")
            return True
        else:
            print("❌ Connexion échouée - Pas de token reçu")
            return False
            
    except ValueError as e:
        print(f"❌ Erreur de configuration: {e}")
        return False
    except Exception as e:
        print(f"❌ Erreur de connexion: {e}")
        return False


def main():
    print()
    print("╔" + "=" * 58 + "╗")
    print("║" + " " * 15 + "🔍 CHECK AMADEUS CONFIG" + " " * 20 + "║")
    print("╚" + "=" * 58 + "╝")
    print()
    
    # Check 1: Fichier .env
    if not check_env_file():
        print()
        print("⚠️  Configure d'abord le fichier .env")
        return False
    
    print()
    
    # Check 2: Credentials
    if not check_credentials():
        print()
        print("⚠️  Configure d'abord les credentials Amadeus")
        return False
    
    print()
    
    # Check 3: Connexion
    if not check_connection():
        print()
        print("⚠️  Vérifie tes credentials sur https://developers.amadeus.com/")
        return False
    
    # Succès !
    print()
    print("=" * 60)
    print("🎉 Tout est OK ! Amadeus est prêt à l'emploi.")
    print("=" * 60)
    print()
    print("📖 Prochaines étapes :")
    print()
    print("   1. Lance les tests complets:")
    print("      python test_amadeus.py")
    print()
    print("   2. Teste en shell Django:")
    print("      python manage.py shell")
    print("      >>> from api.amadeus_integration import AmadeusFlightService")
    print("      >>> amadeus = AmadeusFlightService(use_test=True)")
    print("      >>> result = amadeus.get_flight_by_number('AF001', '2025-12-15')")
    print()
    print("   3. Lis la doc d'intégration:")
    print("      AMADEUS_INTEGRATION.md")
    print()
    
    return True


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)


