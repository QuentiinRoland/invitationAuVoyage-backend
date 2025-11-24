"""
Exemple d'intégration d'Amadeus dans views.py
Ce fichier montre comment remplacer/compléter ta fonction Air France-KLM actuelle
"""

# ===============================================================================
# EXEMPLE 1: Nouvelle fonction pour Amadeus (à ajouter dans views.py)
# ===============================================================================

def _search_flights_with_amadeus(self, origin_code, destination_code, travel_date, return_date=None, 
                                  search_metadata=None, flight_number_outbound=None, flight_number_return=None):
    """
    Recherche de vols avec l'API Amadeus (remplace Air France-KLM).
    Supporte 2 modes:
    - Mode 2 (recommandé): Numéro de vol + date → récupère toutes les infos
    - Mode classique: Origine/destination + date → recherche avec prix
    
    Args:
        origin_code: Code IATA de l'aéroport de départ (ex: 'CDG')
        destination_code: Code IATA de l'aéroport de destination (ex: 'JFK')
        travel_date: Date de voyage au format YYYY-MM-DD
        return_date: Date de retour au format YYYY-MM-DD (optionnel)
        search_metadata: Dict pour stocker les métadonnées de recherche
        flight_number_outbound: Numéro du vol aller (ex: "AF001") - Mode 2
        flight_number_return: Numéro du vol retour (ex: "AF002") - Mode 2
    
    Returns:
        Liste de dicts avec les infos des vols trouvés, ou None si erreur
    """
    from api.amadeus_integration import AmadeusFlightService
    from django.conf import settings
    
    print("=" * 80)
    print("✈️✈️✈️ DÉBUT RECHERCHE AMADEUS API ✈️✈️✈️")
    print("=" * 80)
    
    try:
        # Vérifier si on doit utiliser l'environnement de test ou production
        use_test_env = getattr(settings, 'AMADEUS_USE_TEST', True)
        amadeus = AmadeusFlightService(use_test=use_test_env)
        
        flights = []
        
        # ============================================================
        # MODE 2 : Recherche par numéro de vol (RECOMMANDÉ)
        # ============================================================
        if flight_number_outbound:
            print(f"🎯 MODE 2 activé - Recherche par numéro de vol")
            print(f"   Vol aller: {flight_number_outbound}")
            if flight_number_return:
                print(f"   Vol retour: {flight_number_return}")
            
            # Recherche du vol aller
            print(f"\n1️⃣  Recherche du vol aller...")
            outbound_flight = amadeus.get_flight_by_number(flight_number_outbound, travel_date)
            
            if outbound_flight:
                print(f"✅ Vol aller trouvé: {outbound_flight['flight_number']}")
                flights.append(outbound_flight)
            else:
                print(f"❌ Vol aller non trouvé: {flight_number_outbound} le {travel_date}")
                if search_metadata is not None:
                    search_metadata['failure_reason'] = ['outbound_flight_not_found']
                    search_metadata['failed_flight'] = flight_number_outbound
                # On ne retourne pas None ici, on continue pour essayer le vol retour
            
            # Recherche du vol retour si spécifié
            if flight_number_return and return_date:
                print(f"\n2️⃣  Recherche du vol retour...")
                return_flight = amadeus.get_flight_by_number(flight_number_return, return_date)
                
                if return_flight:
                    print(f"✅ Vol retour trouvé: {return_flight['flight_number']}")
                    flights.append(return_flight)
                else:
                    print(f"❌ Vol retour non trouvé: {flight_number_return} le {return_date}")
                    if search_metadata is not None:
                        if 'failure_reason' not in search_metadata:
                            search_metadata['failure_reason'] = []
                        search_metadata['failure_reason'].append('return_flight_not_found')
                        search_metadata['failed_return_flight'] = flight_number_return
            
            # Résultat
            if flights:
                print(f"\n✅ {len(flights)} vol(s) trouvé(s) via Mode 2")
                if search_metadata is not None:
                    search_metadata['source'] = 'amadeus_flight_status'
                    search_metadata['mode'] = 'flight_number'
                    search_metadata['real_flights_count'] = len(flights)
                return flights
            else:
                print(f"\n❌ Aucun vol trouvé via Mode 2")
                return None
        
        # ============================================================
        # MODE CLASSIQUE : Recherche par origine/destination avec prix
        # ============================================================
        else:
            print(f"🔍 MODE CLASSIQUE - Recherche par origine/destination")
            print(f"   Route: {origin_code} → {destination_code}")
            print(f"   Date aller: {travel_date}")
            if return_date:
                print(f"   Date retour: {return_date}")
            
            offers = amadeus.search_flights(
                origin=origin_code,
                destination=destination_code,
                departure_date=travel_date,
                adults=1,
                return_date=return_date
            )
            
            if offers:
                print(f"\n✅ {len(offers)} offre(s) trouvée(s)")
                if search_metadata is not None:
                    search_metadata['source'] = 'amadeus_flight_offers'
                    search_metadata['mode'] = 'search'
                    search_metadata['real_flights_count'] = len(offers)
                return offers
            else:
                print(f"\n⚠️  Aucune offre trouvée")
                if search_metadata is not None:
                    search_metadata['failure_reason'] = ['no_offers_found']
                return None
    
    except ValueError as e:
        # Erreur de configuration (credentials manquants)
        print(f"❌❌❌ ERREUR DE CONFIGURATION: {str(e)}")
        print("💡 Vérifiez que AMADEUS_API_KEY et AMADEUS_API_SECRET sont configurés dans .env")
        if search_metadata is not None:
            search_metadata['failure_reason'] = ['credentials_missing']
        return None
    
    except Exception as e:
        # Erreur générale
        print(f"❌❌❌ ERREUR AMADEUS: {type(e).__name__}: {str(e)}")
        import traceback
        traceback.print_exc()
        if search_metadata is not None:
            search_metadata['failure_reason'] = ['api_error']
            search_metadata['api_error'] = {
                'type': type(e).__name__,
                'message': str(e)
            }
        return None


# ===============================================================================
# EXEMPLE 2: Comment modifier ta vue generate_offer pour supporter le Mode 2
# ===============================================================================

def generate_offer(self, request):
    """
    Exemple d'intégration dans ta vue principale.
    Montre comment extraire les paramètres du Mode 2 et les passer à la fonction.
    """
    # Extraire les paramètres depuis la requête
    text_input = request.data.get('text', '')
    travel_date = request.data.get('travel_date')
    return_date = request.data.get('return_date')
    offer_type = request.data.get('type', 'circuit')
    
    # ✨ NOUVEAUX PARAMÈTRES POUR MODE 2
    flight_number_outbound = request.data.get('flight_number_outbound')  # Ex: "AF001"
    flight_number_return = request.data.get('flight_number_return')      # Ex: "AF002"
    use_amadeus = request.data.get('use_amadeus', True)  # True par défaut
    
    # Variables pour stocker les résultats
    real_flights_data = None
    search_metadata = {}
    
    # Détection automatique des codes aéroport (ton code existant)
    origin_code = 'CDG'  # Paris par défaut
    destination_code = self._extract_destination_from_text(text_input)  # Ta fonction existante
    
    # ============================================================
    # RECHERCHE DE VOLS
    # ============================================================
    
    if travel_date:
        print(f"\n📅 Recherche de vols pour le {travel_date}")
        
        if use_amadeus:
            # ✅ Utiliser Amadeus (RECOMMANDÉ)
            print(f"🎯 Utilisation d'Amadeus")
            
            real_flights_data = self._search_flights_with_amadeus(
                origin_code=origin_code,
                destination_code=destination_code,
                travel_date=travel_date,
                return_date=return_date,
                search_metadata=search_metadata,
                flight_number_outbound=flight_number_outbound,  # Mode 2
                flight_number_return=flight_number_return        # Mode 2
            )
        else:
            # ⚠️ Fallback sur Air France-KLM (si tu veux le garder)
            print(f"🔄 Utilisation d'Air France-KLM (fallback)")
            
            real_flights_data = self._search_flights_with_airfrance_klm(
                origin_code=origin_code,
                destination_code=destination_code,
                travel_date=travel_date,
                return_date=return_date,
                search_metadata=search_metadata
            )
        
        # Formater les infos de vol pour les prompts ChatGPT
        if real_flights_data:
            real_flights_context = self._format_flights_for_prompt(real_flights_data)
            print(f"✅ Contexte de vols généré pour ChatGPT")
        else:
            real_flights_context = None
            print(f"⚠️  Pas de vols trouvés - génération sans vols réels")
    
    # ... Le reste de ton code pour générer l'offre avec ChatGPT ...
    
    # ============================================================
    # GÉNÉRER L'OFFRE AVEC CHATGPT
    # ============================================================
    
    # Tes prompts existants, en passant real_flights_context
    if offer_type == 'circuit':
        prompt = self._get_prompt_circuit(
            text_input=text_input,
            travel_date=travel_date,
            return_date=return_date,
            real_flights_context=real_flights_context,  # ✅ Infos des vols
            # ... autres paramètres
        )
    elif offer_type == 'sejour':
        prompt = self._get_prompt_sejour(
            text_input=text_input,
            travel_date=travel_date,
            return_date=return_date,
            real_flights_context=real_flights_context,  # ✅ Infos des vols
            # ... autres paramètres
        )
    # etc.
    
    # ... Générer l'offre avec ChatGPT ...
    # ... Retourner la réponse ...


# ===============================================================================
# EXEMPLE 3: Fonction helper pour formater les vols pour ChatGPT
# ===============================================================================

def _format_flights_for_prompt(self, flights):
    """
    Formate les infos de vol pour les inclure dans les prompts ChatGPT.
    
    Args:
        flights: Liste de dicts avec les infos de vol depuis Amadeus
    
    Returns:
        str: Texte formaté pour inclusion dans le prompt
    """
    if not flights:
        return None
    
    context = "🛫 VOLS RÉELS TROUVÉS (À UTILISER OBLIGATOIREMENT):\n\n"
    
    for i, flight in enumerate(flights, 1):
        flight_type = "ALLER" if i == 1 else "RETOUR"
        
        context += f"Vol {flight_type}:\n"
        context += f"- Numéro de vol: {flight['flight_number']}\n"
        context += f"- Compagnie: {flight.get('carrier_code', 'N/A')}\n"
        context += f"- Départ: {flight['departure_airport']} à {flight['departure_time']}\n"
        context += f"- Arrivée: {flight['arrival_airport']} à {flight['arrival_time']}\n"
        context += f"- Durée: {flight.get('duration', 'N/A')}\n"
        
        if flight.get('stops') is not None:
            if flight['stops'] == 0:
                context += f"- Type: Vol direct\n"
            else:
                context += f"- Type: Vol avec {flight['stops']} escale(s)\n"
        
        if flight.get('terminal_departure'):
            context += f"- Terminal départ: {flight['terminal_departure']}\n"
        
        if flight.get('terminal_arrival'):
            context += f"- Terminal arrivée: {flight['terminal_arrival']}\n"
        
        if flight.get('price'):
            context += f"- Prix: {flight['price']} {flight.get('currency', 'EUR')}\n"
        
        context += "\n"
    
    context += "⚠️ IMPORTANT: Tu DOIS utiliser ces vols réels dans ta réponse. "
    context += "N'invente AUCUN numéro de vol. Utilise exactement les informations ci-dessus.\n"
    
    return context


# ===============================================================================
# EXEMPLE 4: Endpoint API pour tester la recherche de vol (optionnel)
# ===============================================================================

from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework import status

@api_view(['POST'])
@permission_classes([IsAuthenticated])
def search_flight_by_number(request):
    """
    Endpoint pour tester la recherche de vol par numéro (Mode 2).
    
    Body:
    {
        "flight_number": "AF001",
        "departure_date": "2025-11-18"
    }
    """
    from api.amadeus_integration import AmadeusFlightService
    
    flight_number = request.data.get('flight_number')
    departure_date = request.data.get('departure_date')
    
    if not flight_number or not departure_date:
        return Response({
            'error': 'flight_number et departure_date sont requis'
        }, status=status.HTTP_400_BAD_REQUEST)
    
    try:
        amadeus = AmadeusFlightService(use_test=True)
        flight_info = amadeus.get_flight_by_number(flight_number, departure_date)
        
        if flight_info:
            return Response({
                'success': True,
                'flight': flight_info
            })
        else:
            return Response({
                'success': False,
                'error': 'Vol non trouvé',
                'message': f'Le vol {flight_number} le {departure_date} n\'a pas été trouvé'
            }, status=status.HTTP_404_NOT_FOUND)
    
    except ValueError as e:
        return Response({
            'success': False,
            'error': 'Configuration error',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    except Exception as e:
        return Response({
            'success': False,
            'error': 'API error',
            'message': str(e)
        }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


# ===============================================================================
# EXEMPLE 5: Comment ajouter la route dans urls.py
# ===============================================================================

"""
Dans backend/api/urls.py, ajoute:

from .views import search_flight_by_number  # Ou depuis un autre fichier

urlpatterns = [
    # ... tes routes existantes ...
    
    # Nouvelle route pour tester la recherche de vol
    path('flights/search-by-number/', search_flight_by_number, name='search_flight_by_number'),
]

Ensuite tu peux tester avec:
POST /api/flights/search-by-number/
{
    "flight_number": "AF001",
    "departure_date": "2025-11-18"
}
"""


# ===============================================================================
# CHECKLIST D'INTÉGRATION
# ===============================================================================

"""
✅ CHECKLIST POUR INTÉGRER AMADEUS:

1. Configuration
   □ Créer un compte sur https://developers.amadeus.com/
   □ Créer une application et récupérer API Key + Secret
   □ Ajouter AMADEUS_API_KEY et AMADEUS_API_SECRET dans .env
   □ Ajouter dans settings.py: AMADEUS_API_KEY = os.environ.get('AMADEUS_API_KEY', '')
   □ (Optionnel) Ajouter AMADEUS_USE_TEST = True/False dans settings.py

2. Code Backend
   □ Fichier amadeus_integration.py créé ✓
   □ Copier la fonction _search_flights_with_amadeus() dans views.py
   □ Copier la fonction _format_flights_for_prompt() dans views.py
   □ Modifier generate_offer() pour accepter flight_number_outbound et flight_number_return
   □ Passer ces paramètres à _search_flights_with_amadeus()
   □ (Optionnel) Créer l'endpoint search_flight_by_number pour tester

3. Tests
   □ Lancer python backend/test_amadeus.py
   □ Vérifier que tous les tests passent
   □ Tester avec de vrais numéros de vol en environnement TEST

4. Frontend (à adapter selon ton framework)
   □ Ajouter des champs pour flight_number_outbound
   □ Ajouter des champs pour flight_number_return
   □ Ajouter un toggle use_amadeus (ou le mettre à True par défaut)
   □ Envoyer ces paramètres dans la requête POST

5. Production
   □ Tester en environnement TEST d'abord (use_test=True)
   □ Vérifier les coûts estimés
   □ Passer en production (use_test=False ou AMADEUS_USE_TEST=False)
   □ Monitorer les coûts et les erreurs

6. Optionnel - Garder Air France-KLM en fallback
   □ Garder la fonction _search_flights_with_airfrance_klm()
   □ Utiliser use_amadeus pour choisir l'API
   □ Fallback automatique si Amadeus échoue
"""


