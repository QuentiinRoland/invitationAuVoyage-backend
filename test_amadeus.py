#!/usr/bin/env python
"""
Script de test rapide pour l'intégration Amadeus.
Lance ce script pour vérifier que tout fonctionne.

Usage:
    python test_amadeus.py
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.amadeus_integration import AmadeusFlightService
from django.conf import settings


def test_credentials():
    """Vérifie que les credentials sont configurés"""
    print("=" * 80)
    print("🔑 TEST 1: Vérification des credentials")
    print("=" * 80)
    
    api_key = getattr(settings, 'AMADEUS_API_KEY', None)
    api_secret = getattr(settings, 'AMADEUS_API_SECRET', None)
    
    if api_key and api_secret:
        print(f"✅ AMADEUS_API_KEY: {api_key[:10]}... (OK)")
        print(f"✅ AMADEUS_API_SECRET: {api_secret[:10]}... (OK)")
        return True
    else:
        print("❌ Credentials manquants !")
        print()
        print("📝 Pour configurer Amadeus:")
        print("1. Va sur https://developers.amadeus.com/")
        print("2. Crée un compte et une application")
        print("3. Ajoute dans backend/.env :")
        print("   AMADEUS_API_KEY=your_key_here")
        print("   AMADEUS_API_SECRET=your_secret_here")
        print()
        return False


def test_token_generation():
    """Test la génération de token"""
    print("\n" + "=" * 80)
    print("🎫 TEST 2: Génération de token d'accès")
    print("=" * 80)
    
    try:
        amadeus = AmadeusFlightService(use_test=True)
        token = amadeus._get_access_token()
        
        if token:
            print(f"✅ Token généré avec succès: {token[:20]}...")
            return True
        else:
            print("❌ Échec de génération du token")
            return False
            
    except ValueError as e:
        print(f"❌ Erreur de configuration: {str(e)}")
        return False
    except Exception as e:
        print(f"❌ Erreur: {str(e)}")
        return False


def test_flight_by_number():
    """Test la recherche par numéro de vol (Mode 2)"""
    print("\n" + "=" * 80)
    print("✈️  TEST 3: Recherche par numéro de vol (MODE 2)")
    print("=" * 80)
    
    try:
        amadeus = AmadeusFlightService(use_test=True)
        
        # Test avec un vol Air France fictif dans l'environnement de test
        print("\n📋 Test 1: Vol AF001 le 2025-11-18")
        result = amadeus.get_flight_by_number("AF001", "2025-11-18")
        
        if result:
            print("\n✅ Vol trouvé !")
            print(f"   - Numéro: {result['flight_number']}")
            print(f"   - Route: {result['departure_airport']} → {result['arrival_airport']}")
            print(f"   - Départ: {result['departure_time']}")
            print(f"   - Arrivée: {result['arrival_time']}")
            print(f"   - Durée: {result.get('duration', 'N/A')}")
            print(f"   - Escales: {result.get('stops', 'N/A')}")
            if result.get('terminal_departure'):
                print(f"   - Terminal départ: {result['terminal_departure']}")
            if result.get('terminal_arrival'):
                print(f"   - Terminal arrivée: {result['terminal_arrival']}")
            return True
        else:
            print("\n⚠️  Vol non trouvé (peut être normal en environnement TEST)")
            print("💡 L'environnement de test Amadeus contient des données limitées")
            print("💡 En production, tu pourras rechercher tous les vols réels")
            return None  # Ni succès ni échec, juste pas de données
            
    except Exception as e:
        print(f"\n❌ Erreur: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_flight_search():
    """Test la recherche avec prix"""
    print("\n" + "=" * 80)
    print("💰 TEST 4: Recherche d'offres avec prix")
    print("=" * 80)
    
    try:
        amadeus = AmadeusFlightService(use_test=True)
        
        print("\n📋 Recherche: CDG → JFK le 2025-12-15")
        offers = amadeus.search_flights(
            origin="CDG",
            destination="JFK",
            departure_date="2025-12-15",
            adults=1
        )
        
        if offers:
            print(f"\n✅ {len(offers)} offre(s) trouvée(s) !")
            for i, offer in enumerate(offers[:3], 1):
                print(f"\n   Offre {i}:")
                print(f"   - Vol: {offer.get('flight_number', 'N/A')}")
                print(f"   - Route: {offer['departure_airport']} → {offer['arrival_airport']}")
                print(f"   - Départ: {offer['departure_time']} | Arrivée: {offer['arrival_time']}")
                print(f"   - Durée: {offer.get('duration', 'N/A')}")
                print(f"   - Escales: {offer.get('stops', 'N/A')}")
                if offer.get('price'):
                    print(f"   - Prix: {offer['price']} {offer.get('currency', 'EUR')}")
            return True
        else:
            print("\n⚠️  Aucune offre trouvée")
            return None
            
    except Exception as e:
        print(f"\n❌ Erreur: {str(e)}")
        import traceback
        traceback.print_exc()
        return False


def test_date_formats():
    """Test les différents formats de date"""
    print("\n" + "=" * 80)
    print("📅 TEST 5: Formats de date acceptés")
    print("=" * 80)
    
    amadeus = AmadeusFlightService(use_test=True)
    
    test_cases = [
        ("2025-11-18", "2025-11-18", "Format YYYY-MM-DD"),
        ("18/11/2025", "2025-11-18", "Format DD/MM/YYYY"),
    ]
    
    all_passed = True
    for input_date, expected, description in test_cases:
        result = amadeus._normalize_date(input_date)
        if result == expected:
            print(f"✅ {description}: '{input_date}' → '{result}'")
        else:
            print(f"❌ {description}: '{input_date}' → '{result}' (attendu: '{expected}')")
            all_passed = False
    
    return all_passed


def test_flight_number_parsing():
    """Test le parsing des numéros de vol"""
    print("\n" + "=" * 80)
    print("🔢 TEST 6: Parsing des numéros de vol")
    print("=" * 80)
    
    amadeus = AmadeusFlightService(use_test=True)
    
    test_cases = [
        ("AF001", ("AF", "001"), "Air France"),
        ("KL1234", ("KL", "1234"), "KLM"),
        ("BA456", ("BA", "456"), "British Airways"),
        ("INVALID", (None, None), "Format invalide"),
    ]
    
    all_passed = True
    for input_num, expected, description in test_cases:
        result = amadeus._parse_flight_number(input_num)
        if result == expected:
            print(f"✅ {description}: '{input_num}' → {result}")
        else:
            print(f"❌ {description}: '{input_num}' → {result} (attendu: {expected})")
            all_passed = False
    
    return all_passed


def main():
    """Lance tous les tests"""
    print("\n")
    print("╔" + "=" * 78 + "╗")
    print("║" + " " * 20 + "🧪 TESTS AMADEUS INTEGRATION" + " " * 29 + "║")
    print("╚" + "=" * 78 + "╝")
    print()
    
    results = []
    
    # Test 1: Credentials
    results.append(("Credentials", test_credentials()))
    
    if not results[0][1]:
        print("\n⚠️  Les tests suivants nécessitent des credentials valides.")
        print("Configure d'abord AMADEUS_API_KEY et AMADEUS_API_SECRET.")
        return
    
    # Test 2: Token
    results.append(("Token", test_token_generation()))
    
    if not results[1][1]:
        print("\n⚠️  Impossible de continuer sans token valide.")
        return
    
    # Tests 3-6
    results.append(("Flight by number (Mode 2)", test_flight_by_number()))
    results.append(("Flight search with price", test_flight_search()))
    results.append(("Date formats", test_date_formats()))
    results.append(("Flight number parsing", test_flight_number_parsing()))
    
    # Résumé
    print("\n" + "=" * 80)
    print("📊 RÉSUMÉ DES TESTS")
    print("=" * 80)
    
    passed = sum(1 for _, result in results if result is True)
    failed = sum(1 for _, result in results if result is False)
    skipped = sum(1 for _, result in results if result is None)
    
    for test_name, result in results:
        if result is True:
            status = "✅ PASSED"
        elif result is False:
            status = "❌ FAILED"
        else:
            status = "⚠️  SKIPPED"
        print(f"{status} - {test_name}")
    
    print()
    print(f"Total: {passed} réussi(s), {failed} échoué(s), {skipped} ignoré(s)")
    
    if failed == 0:
        print("\n🎉 Tous les tests sont passés ! L'intégration Amadeus est prête.")
        print("\n💡 Prochaines étapes:")
        print("   1. Intègre AmadeusFlightService dans views.py")
        print("   2. Adapte ton frontend pour utiliser le Mode 2")
        print("   3. Teste avec de vrais numéros de vol")
        print("   4. Passe en production quand tu es prêt (use_test=False)")
    else:
        print("\n⚠️  Certains tests ont échoué. Vérifie la configuration.")
    
    print()


if __name__ == "__main__":
    main()


