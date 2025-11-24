#!/usr/bin/env python
"""
Test de la recherche intelligente de vols.
"""

import os
import sys
import django

# Setup Django
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from api.smart_flight_search import SmartFlightSearch


def main():
    print("\n" + "=" * 80)
    print("🧪 TESTS RECHERCHE INTELLIGENTE DE VOLS")
    print("=" * 80 + "\n")
    
    smart_search = SmartFlightSearch(use_test=True)
    
    # Test 1: Format GDS avec retour (ce que tu voulais)
    print("\n" + "🎯 TEST 1: Format GDS avec retour")
    print("-" * 80)
    result1 = smart_search.search("18NOV-25NOV BRU JFK 10:00 14:00")
    print(f"✅ Message: {result1['message']}")
    print(f"✅ Stratégie: {result1['search_strategy']}")
    if result1['flights_found']:
        for flight in result1['flights_found']:
            print(f"   Vol: {flight.get('flight_number', 'N/A')}")
            print(f"   {flight['departure_airport']} → {flight['arrival_airport']}")
            print(f"   {flight.get('departure_time')} - {flight.get('arrival_time')}")
    
    # Test 2: Numéro de vol + date
    print("\n\n" + "🎯 TEST 2: Numéro de vol + date")
    print("-" * 80)
    result2 = smart_search.search("AF001 18/11/2025")
    print(f"✅ Message: {result2['message']}")
    print(f"✅ Stratégie: {result2['search_strategy']}")
    if result2['flights_found']:
        for flight in result2['flights_found']:
            print(f"   Vol: {flight['flight_number']}")
            print(f"   {flight['departure_airport']} → {flight['arrival_airport']}")
            print(f"   {flight.get('departure_time')} - {flight.get('arrival_time')}")
    
    # Test 3: Format GDS simple
    print("\n\n" + "🎯 TEST 3: Format GDS simple")
    print("-" * 80)
    result3 = smart_search.search("15DEC CDG JFK 10:30 14:45")
    print(f"✅ Message: {result3['message']}")
    print(f"✅ Stratégie: {result3['search_strategy']}")
    if result3['flights_found']:
        for flight in result3['flights_found']:
            print(f"   Vol: {flight.get('flight_number', 'N/A')}")
            print(f"   {flight['departure_airport']} → {flight['arrival_airport']}")
            print(f"   {flight.get('departure_time')} - {flight.get('arrival_time')}")
    
    print("\n" + "=" * 80)
    print("✅ Tests terminés !")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()


