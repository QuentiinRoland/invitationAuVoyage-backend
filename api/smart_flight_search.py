"""
Recherche intelligente de vols combinant parsing et API Amadeus.
"""

from typing import Optional, Dict, List
from api.flight_parser import FlightInputParser
from api.amadeus_integration import AmadeusFlightService


class SmartFlightSearch:
    """
    Recherche intelligente de vols qui :
    1. Parse l'input utilisateur (format GDS, numéro de vol, etc.)
    2. Recherche les vols correspondants via Amadeus
    3. Combine les infos extraites + infos Amadeus
    """
    
    def __init__(self, use_test: bool = True):
        """
        Args:
            use_test: Si True, utilise l'environnement TEST d'Amadeus
        """
        self.amadeus = AmadeusFlightService(use_test=use_test)
        self.parser = FlightInputParser()
    
    def search(self, user_input: str) -> Dict:
        """
        Recherche intelligente depuis n'importe quel format d'input.
        
        Args:
            user_input: Texte saisi par l'utilisateur (format libre)
        
        Returns:
            Dict avec:
            - parsed_data: Infos extraites du texte
            - flights_found: Vols trouvés via Amadeus (si applicable)
            - search_strategy: Stratégie utilisée
            - success: bool
            - message: Message pour l'utilisateur
        """
        print("=" * 80)
        print("🔍 RECHERCHE INTELLIGENTE DE VOLS")
        print("=" * 80)
        print(f"Input utilisateur: '{user_input}'")
        print()
        
        # Étape 1: Parser l'input
        print("📋 Étape 1: Parsing de l'input...")
        parsed_data = self.parser.parse(user_input)
        
        if not parsed_data:
            return {
                'success': False,
                'message': 'Format non reconnu',
                'parsed_data': None,
                'flights_found': None,
                'search_strategy': None
            }
        
        print(self.parser.format_for_display(parsed_data))
        print()
        
        # Étape 2: Déterminer la stratégie de recherche
        strategy = self._determine_search_strategy(parsed_data)
        print(f"🎯 Stratégie: {strategy}")
        print()
        
        # Étape 3: Rechercher les vols selon la stratégie
        print("🔎 Étape 2: Recherche des vols...")
        flights_found = self._execute_search_strategy(strategy, parsed_data)
        
        if flights_found:
            print(f"✅ {len(flights_found)} vol(s) trouvé(s)")
            return {
                'success': True,
                'message': f"{len(flights_found)} vol(s) trouvé(s)",
                'parsed_data': parsed_data,
                'flights_found': flights_found,
                'search_strategy': strategy
            }
        else:
            print("⚠️  Aucun vol trouvé")
            # Même si aucun vol trouvé, on retourne les infos parsées
            return {
                'success': True,  # Parsing réussi même si pas de vol trouvé
                'message': 'Infos extraites mais aucun vol trouvé via Amadeus',
                'parsed_data': parsed_data,
                'flights_found': None,
                'search_strategy': strategy
            }
    
    def _determine_search_strategy(self, parsed_data: Dict) -> str:
        """
        Détermine la meilleure stratégie de recherche selon les infos disponibles.
        
        Stratégies possibles:
        1. "flight_number" - On a un numéro de vol → recherche directe
        2. "origin_destination" - On a origine + destination + date → recherche d'offres
        3. "manual_only" - Infos complètes mais pas de recherche API nécessaire
        """
        has_flight_number = bool(parsed_data.get('flight_number'))
        has_origin_dest = bool(parsed_data.get('origin_airport') and parsed_data.get('destination_airport'))
        has_date = bool(parsed_data.get('departure_date'))
        has_times = bool(parsed_data.get('departure_time') and parsed_data.get('arrival_time'))
        
        # Stratégie 1: Si on a un numéro de vol + date → recherche par numéro
        if has_flight_number and has_date:
            return "flight_number"
        
        # Stratégie 2: Si on a origine + destination + date → recherche d'offres
        if has_origin_dest and has_date:
            return "origin_destination"
        
        # Stratégie 3: Format GDS complet avec horaires → utilisation directe
        if has_origin_dest and has_date and has_times:
            return "manual_complete"
        
        # Stratégie 4: Infos incomplètes → utilisation partielle
        return "manual_partial"
    
    def _execute_search_strategy(self, strategy: str, parsed_data: Dict) -> Optional[List[Dict]]:
        """
        Exécute la stratégie de recherche appropriée.
        """
        if strategy == "flight_number":
            return self._search_by_flight_number(parsed_data)
        
        elif strategy == "origin_destination":
            return self._search_by_origin_destination(parsed_data)
        
        elif strategy == "manual_complete":
            # Pas besoin de rechercher, on a déjà toutes les infos
            print("✅ Format GDS complet - Utilisation directe des infos")
            return [self._create_manual_flight_info(parsed_data)]
        
        elif strategy == "manual_partial":
            # Infos partielles, on retourne ce qu'on a
            print("⚠️  Infos partielles - Certaines données manquent")
            return [self._create_manual_flight_info(parsed_data)]
        
        return None
    
    def _search_by_flight_number(self, parsed_data: Dict) -> Optional[List[Dict]]:
        """Recherche via Amadeus en utilisant le numéro de vol."""
        flight_number = parsed_data['flight_number']
        date = parsed_data['departure_date']
        
        print(f"   🔍 Recherche Amadeus: {flight_number} le {date}")
        
        try:
            result = self.amadeus.get_flight_by_number(flight_number, date)
            if result:
                # Enrichir avec les infos parsées si disponibles
                result['parsed_from_input'] = True
                return [result]
        except Exception as e:
            print(f"   ❌ Erreur Amadeus: {str(e)}")
        
        return None
    
    def _search_by_origin_destination(self, parsed_data: Dict) -> Optional[List[Dict]]:
        """Recherche via Amadeus en utilisant origine/destination."""
        origin = parsed_data['origin_airport']
        destination = parsed_data['destination_airport']
        date = parsed_data['departure_date']
        return_date = parsed_data.get('return_date')
        
        print(f"   🔍 Recherche Amadeus: {origin} → {destination} le {date}")
        
        try:
            results = self.amadeus.search_flights(
                origin=origin,
                destination=destination,
                departure_date=date,
                adults=1,
                return_date=return_date
            )
            
            if results:
                # Enrichir avec les infos parsées
                for result in results:
                    result['parsed_from_input'] = True
                
                # Si on a des horaires attendus dans le parsing,
                # on peut filtrer pour trouver le vol le plus proche
                if parsed_data.get('departure_time'):
                    results = self._filter_by_time(results, parsed_data['departure_time'])
                
                return results
        except Exception as e:
            print(f"   ❌ Erreur Amadeus: {str(e)}")
        
        return None
    
    def _create_manual_flight_info(self, parsed_data: Dict) -> Dict:
        """
        Crée une structure de vol depuis les infos parsées (sans appel API).
        Utile quand on a déjà toutes les infos (format GDS complet).
        """
        return {
            'flight_number': parsed_data.get('flight_number', 'N/A'),
            'carrier_code': parsed_data.get('carrier_code'),
            'departure_airport': parsed_data.get('origin_airport', 'N/A'),
            'arrival_airport': parsed_data.get('destination_airport', 'N/A'),
            'departure_time': parsed_data.get('departure_time'),
            'arrival_time': parsed_data.get('arrival_time'),
            'departure_datetime_full': None,
            'arrival_datetime_full': None,
            'duration': None,
            'aircraft_type': None,
            'terminal_departure': None,
            'terminal_arrival': None,
            'stops': None,
            'source': 'manual_input',
            'parsed_from_input': True,
            'complete': self._is_complete(parsed_data)
        }
    
    def _is_complete(self, parsed_data: Dict) -> bool:
        """Vérifie si on a toutes les infos essentielles."""
        required = ['origin_airport', 'destination_airport', 'departure_time', 'arrival_time']
        return all(parsed_data.get(field) for field in required)
    
    def _filter_by_time(self, flights: List[Dict], target_time: str) -> List[Dict]:
        """
        Filtre les vols pour trouver ceux proches de l'horaire cible.
        """
        from datetime import datetime, timedelta
        
        try:
            target = datetime.strptime(target_time, '%H:%M')
            
            # Calculer la différence pour chaque vol
            flights_with_diff = []
            for flight in flights:
                dep_time = flight.get('departure_time')
                if dep_time:
                    try:
                        flight_time = datetime.strptime(dep_time, '%H:%M')
                        diff = abs((flight_time - target).total_seconds() / 60)  # Différence en minutes
                        flights_with_diff.append((diff, flight))
                    except:
                        pass
            
            if flights_with_diff:
                # Trier par différence et prendre les 3 plus proches
                flights_with_diff.sort(key=lambda x: x[0])
                return [f[1] for f in flights_with_diff[:3]]
        
        except:
            pass
        
        return flights


def test_smart_search():
    """Tests de la recherche intelligente"""
    print("\n" + "=" * 80)
    print("🧪 TESTS RECHERCHE INTELLIGENTE")
    print("=" * 80 + "\n")
    
    smart_search = SmartFlightSearch(use_test=True)
    
    test_cases = [
        "18NOV-25NOV BRU JFK 10:00 14:00",
        "AF001 18/11/2025",
        "18DEC CDG JFK",
    ]
    
    for test in test_cases:
        print(f"\n{'='*80}")
        print(f"TEST: '{test}'")
        print('='*80)
        result = smart_search.search(test)
        print(f"\n✅ Résultat: {result['message']}")
        if result['flights_found']:
            for flight in result['flights_found']:
                print(f"   Vol: {flight.get('flight_number', 'N/A')}")
                print(f"   Route: {flight['departure_airport']} → {flight['arrival_airport']}")
                if flight.get('departure_time'):
                    print(f"   Horaires: {flight['departure_time']} - {flight.get('arrival_time', 'N/A')}")
        print()


if __name__ == "__main__":
    test_smart_search()


