"""
Intégration de l'API Amadeus pour la recherche de vols.
Documentation: https://developers.amadeus.com/
"""

import requests
import json
import re
from datetime import datetime, timedelta
from django.conf import settings


class AmadeusFlightService:
    """Service pour interagir avec l'API Amadeus"""
    
    BASE_URL_PROD = "https://api.amadeus.com"
    BASE_URL_TEST = "https://test.api.amadeus.com"
    
    def __init__(self, use_test=True):
        """
        Initialise le service Amadeus
        
        Args:
            use_test: Si True, utilise l'environnement de test (recommandé pour dev)
        """
        self.base_url = self.BASE_URL_TEST if use_test else self.BASE_URL_PROD
        self.api_key = getattr(settings, 'AMADEUS_API_KEY', None)
        self.api_secret = getattr(settings, 'AMADEUS_API_SECRET', None)
        self._access_token = None
        self._token_expiry = None
        
        if not self.api_key or not self.api_secret:
            raise ValueError("AMADEUS_API_KEY et AMADEUS_API_SECRET doivent être configurés dans settings.py")
    
    def _get_access_token(self):
        """
        Obtient un token d'accès OAuth2 depuis Amadeus.
        Le token est mis en cache et réutilisé jusqu'à expiration.
        """
        # Vérifier si on a déjà un token valide
        if self._access_token and self._token_expiry:
            if datetime.now() < self._token_expiry:
                return self._access_token
        
        print("🔐 Obtention d'un nouveau token Amadeus...")
        
        url = f"{self.base_url}/v1/security/oauth2/token"
        headers = {
            "Content-Type": "application/x-www-form-urlencoded"
        }
        data = {
            "grant_type": "client_credentials",
            "client_id": self.api_key,
            "client_secret": self.api_secret
        }
        
        try:
            response = requests.post(url, headers=headers, data=data, timeout=10)
            response.raise_for_status()
            
            token_data = response.json()
            self._access_token = token_data['access_token']
            
            # Le token expire généralement après 1799 secondes (30 min)
            # On le considère expiré 5 minutes avant pour être sûr
            expires_in = token_data.get('expires_in', 1799)
            self._token_expiry = datetime.now() + timedelta(seconds=expires_in - 300)
            
            print(f"✅ Token obtenu, valide jusqu'à {self._token_expiry.strftime('%H:%M:%S')}")
            return self._access_token
            
        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur lors de l'obtention du token: {str(e)}")
            raise
    
    def get_flight_by_number(self, flight_number, departure_date):
        """
        MODE 2: Récupère les infos d'un vol à partir de son numéro et sa date.
        
        Args:
            flight_number: Numéro du vol (ex: "AF001" ou juste "001" si carrier_code séparé)
            departure_date: Date de départ au format "YYYY-MM-DD" ou "DD/MM/YYYY"
        
        Returns:
            dict avec les infos du vol ou None si non trouvé
        """
        print("=" * 80)
        print("✈️  MODE 2: Recherche de vol par numéro + date (Amadeus)")
        print("=" * 80)
        
        # Parser le numéro de vol pour extraire le code compagnie
        carrier_code, flight_num = self._parse_flight_number(flight_number)
        
        if not carrier_code or not flight_num:
            print(f"❌ Format de numéro de vol invalide: {flight_number}")
            print("   💡 Formats acceptés: 'AF001', 'KL1234', etc.")
            return None
        
        # Normaliser la date
        departure_date_normalized = self._normalize_date(departure_date)
        if not departure_date_normalized:
            print(f"❌ Format de date invalide: {departure_date}")
            print("   💡 Formats acceptés: 'YYYY-MM-DD' ou 'DD/MM/YYYY'")
            return None
        
        print(f"📋 Recherche du vol:")
        print(f"   - Compagnie: {carrier_code}")
        print(f"   - Numéro: {flight_num}")
        print(f"   - Date: {departure_date_normalized}")
        
        # Obtenir le token
        try:
            token = self._get_access_token()
        except Exception as e:
            print(f"❌ Impossible d'obtenir le token: {str(e)}")
            return None
        
        # Appeler l'API Flight Status
        url = f"{self.base_url}/v2/schedule/flights"
        headers = {
            "Authorization": f"Bearer {token}"
        }
        params = {
            "carrierCode": carrier_code,
            "flightNumber": flight_num,
            "scheduledDepartureDate": departure_date_normalized
        }
        
        print(f"📡 Requête vers Amadeus Flight Status API...")
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            print(f"📊 Code de statut: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if not data.get('data'):
                    print(f"⚠️  Aucun vol trouvé pour {carrier_code}{flight_num} le {departure_date_normalized}")
                    return None
                
                # Prendre le premier résultat (généralement il n'y en a qu'un)
                flight_data = data['data'][0]
                
                # Extraire les infos importantes
                flight_info = self._extract_flight_info_from_amadeus_response(flight_data, carrier_code, flight_num)
                
                if flight_info:
                    print(f"✅ Vol trouvé: {flight_info['flight_number']}")
                    print(f"   {flight_info['departure_airport']} → {flight_info['arrival_airport']}")
                    print(f"   Départ: {flight_info['departure_time']} | Arrivée: {flight_info['arrival_time']}")
                    print(f"   Durée: {flight_info.get('duration', 'N/A')}")
                    return flight_info
                else:
                    print(f"⚠️  Impossible d'extraire les infos du vol")
                    return None
            
            elif response.status_code == 400:
                error_data = response.json()
                print(f"❌ Erreur 400 - Paramètres invalides:")
                print(f"   {json.dumps(error_data, indent=2)}")
                return None
            
            elif response.status_code == 401:
                print(f"❌ Erreur 401 - Authentification échouée")
                print(f"   💡 Vérifiez vos credentials Amadeus")
                return None
            
            else:
                print(f"❌ Erreur {response.status_code}: {response.text[:500]}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"❌ Timeout - l'API Amadeus n'a pas répondu dans les temps")
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur lors de la requête: {str(e)}")
            return None
    
    def search_flights(self, origin, destination, departure_date, adults=1, return_date=None):
        """
        Recherche des vols avec prix (Flight Offers Search API).
        
        Args:
            origin: Code IATA aéroport de départ (ex: "CDG")
            destination: Code IATA aéroport d'arrivée (ex: "JFK")
            departure_date: Date de départ (format "YYYY-MM-DD" ou "DD/MM/YYYY")
            adults: Nombre d'adultes (défaut: 1)
            return_date: Date de retour optionnelle (même format)
        
        Returns:
            list de dicts avec les offres de vol
        """
        print("=" * 80)
        print("🔍 Recherche d'offres de vol avec prix (Amadeus)")
        print("=" * 80)
        
        # Normaliser les dates
        departure_date_normalized = self._normalize_date(departure_date)
        if not departure_date_normalized:
            print(f"❌ Format de date de départ invalide: {departure_date}")
            return None
        
        return_date_normalized = None
        if return_date:
            return_date_normalized = self._normalize_date(return_date)
            if not return_date_normalized:
                print(f"❌ Format de date de retour invalide: {return_date}")
                return None
        
        print(f"📋 Recherche:")
        print(f"   - Origine: {origin}")
        print(f"   - Destination: {destination}")
        print(f"   - Départ: {departure_date_normalized}")
        if return_date_normalized:
            print(f"   - Retour: {return_date_normalized}")
        print(f"   - Adultes: {adults}")
        
        # Obtenir le token
        try:
            token = self._get_access_token()
        except Exception as e:
            print(f"❌ Impossible d'obtenir le token: {str(e)}")
            return None
        
        # Appeler l'API Flight Offers Search
        url = f"{self.base_url}/v2/shopping/flight-offers"
        headers = {
            "Authorization": f"Bearer {token}"
        }
        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date_normalized,
            "adults": adults,
            "nonStop": "false",  # Accepter les vols avec escales
            "max": 5  # Limiter à 5 résultats
        }
        
        if return_date_normalized:
            params["returnDate"] = return_date_normalized
        
        print(f"📡 Requête vers Amadeus Flight Offers Search API...")
        
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            
            print(f"📊 Code de statut: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                if not data.get('data'):
                    print(f"⚠️  Aucune offre trouvée pour {origin} → {destination} le {departure_date_normalized}")
                    return None
                
                # Extraire les offres
                flights = []
                for offer in data['data'][:5]:  # Prendre les 5 meilleures offres
                    flight_info = self._extract_flight_info_from_offer(offer)
                    if flight_info:
                        flights.append(flight_info)
                
                print(f"✅ {len(flights)} offre(s) trouvée(s)")
                return flights
            
            elif response.status_code == 400:
                error_data = response.json()
                print(f"❌ Erreur 400 - Paramètres invalides:")
                print(f"   {json.dumps(error_data, indent=2)}")
                return None
            
            else:
                print(f"❌ Erreur {response.status_code}: {response.text[:500]}")
                return None
                
        except requests.exceptions.Timeout:
            print(f"❌ Timeout - l'API Amadeus n'a pas répondu dans les temps")
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur lors de la requête: {str(e)}")
            return None
    
    def _parse_flight_number(self, flight_number):
        """
        Parse un numéro de vol pour extraire le code compagnie et le numéro.
        
        Args:
            flight_number: Ex: "AF001", "KL1234", "BA2490"
        
        Returns:
            tuple (carrier_code, flight_num) ou (None, None) si invalide
        """
        import re
        
        flight_number = flight_number.strip().upper()
        
        # Format attendu: 2 lettres + 1-4 chiffres
        match = re.match(r'^([A-Z]{2})(\d{1,4})$', flight_number)
        
        if match:
            return match.group(1), match.group(2)
        
        return None, None
    
    def _normalize_date(self, date_str):
        """
        Normalise une date au format YYYY-MM-DD.
        
        Args:
            date_str: Date au format "YYYY-MM-DD" ou "DD/MM/YYYY"
        
        Returns:
            str au format "YYYY-MM-DD" ou None si invalide
        """
        if not date_str:
            return None
        
        date_str = date_str.strip()
        
        # Déjà au bon format
        if re.match(r'^\d{4}-\d{2}-\d{2}$', date_str):
            return date_str
        
        # Format DD/MM/YYYY
        if re.match(r'^\d{2}/\d{2}/\d{4}$', date_str):
            try:
                dt = datetime.strptime(date_str, '%d/%m/%Y')
                return dt.strftime('%Y-%m-%d')
            except ValueError:
                return None
        
        return None
    
    def _extract_flight_info_from_amadeus_response(self, flight_data, carrier_code, flight_num):
        """
        Extrait les infos importantes depuis la réponse Amadeus Flight Status.
        
        Structure attendue:
        {
          "type": "DatedFlight",
          "scheduledDepartureDate": "2025-11-18",
          "flightDesignator": {"carrierCode": "AF", "flightNumber": "1"},
          "flightPoints": [
            {
              "iataCode": "CDG",
              "departure": {
                "timings": [{"qualifier": "STD", "value": "2025-11-18T10:30:00", "delays": {...}}],
                "terminal": {"code": "2E"}
              }
            },
            {
              "iataCode": "JFK",
              "arrival": {
                "timings": [{"qualifier": "STA", "value": "2025-11-18T13:45:00", "delays": {...}}],
                "terminal": {"code": "1"}
              }
            }
          ],
          "segments": [...]
        }
        """
        try:
            flight_points = flight_data.get('flightPoints', [])
            
            if len(flight_points) < 2:
                print(f"⚠️  Structure inattendue: moins de 2 flightPoints")
                return None
            
            # Point de départ (premier)
            departure_point = flight_points[0]
            departure_airport = departure_point.get('iataCode')
            departure_info = departure_point.get('departure', {})
            departure_timings = departure_info.get('timings', [{}])[0]
            departure_time = departure_timings.get('value', '')
            departure_terminal = departure_info.get('terminal', {}).get('code')
            
            # Point d'arrivée (dernier)
            arrival_point = flight_points[-1]
            arrival_airport = arrival_point.get('iataCode')
            arrival_info = arrival_point.get('arrival', {})
            arrival_timings = arrival_info.get('timings', [{}])[0]
            arrival_time = arrival_timings.get('value', '')
            arrival_terminal = arrival_info.get('terminal', {}).get('code')
            
            # Durée (peut être calculée ou fournie)
            duration = None
            if departure_time and arrival_time:
                try:
                    dep_dt = datetime.fromisoformat(departure_time.replace('Z', '+00:00'))
                    arr_dt = datetime.fromisoformat(arrival_time.replace('Z', '+00:00'))
                    duration_delta = arr_dt - dep_dt
                    hours = int(duration_delta.total_seconds() // 3600)
                    minutes = int((duration_delta.total_seconds() % 3600) // 60)
                    duration = f"{hours}h{minutes:02d}"
                except Exception as e:
                    print(f"   ⚠️  Impossible de calculer la durée: {str(e)}")
            
            # Type d'avion
            aircraft_type = None
            segments = flight_data.get('segments', [])
            if segments:
                aircraft_type = segments[0].get('partnership', {}).get('operatingFlight', {}).get('equipment', {}).get('aircraftType')
            
            # Escales
            stops_count = len(flight_points) - 2  # -2 car on exclut départ et arrivée
            
            # Formater les horaires en HH:MM
            def format_time(iso_datetime):
                if not iso_datetime:
                    return None
                try:
                    dt = datetime.fromisoformat(iso_datetime.replace('Z', '+00:00'))
                    return dt.strftime('%H:%M')
                except:
                    return iso_datetime
            
            departure_time_formatted = format_time(departure_time)
            arrival_time_formatted = format_time(arrival_time)
            
            return {
                'flight_number': f"{carrier_code}{flight_num}",
                'carrier_code': carrier_code,
                'departure_airport': departure_airport,
                'arrival_airport': arrival_airport,
                'departure_time': departure_time_formatted,
                'arrival_time': arrival_time_formatted,
                'departure_datetime_full': departure_time,
                'arrival_datetime_full': arrival_time,
                'duration': duration,
                'aircraft_type': aircraft_type,
                'terminal_departure': departure_terminal,
                'terminal_arrival': arrival_terminal,
                'stops': stops_count,
                'source': 'amadeus_flight_status'
            }
            
        except Exception as e:
            print(f"❌ Erreur lors de l'extraction: {str(e)}")
            import traceback
            traceback.print_exc()
            return None
    
    def _extract_flight_info_from_offer(self, offer):
        """
        Extrait les infos depuis une offre de vol (Flight Offers Search).
        Structure plus complexe avec prix et multiples segments.
        """
        try:
            # Prix
            price = offer.get('price', {})
            total_price = price.get('total')
            currency = price.get('currency', 'EUR')
            
            # Itinéraires
            itineraries = offer.get('itineraries', [])
            if not itineraries:
                return None
            
            # Prendre le premier itinéraire (aller)
            itinerary = itineraries[0]
            segments = itinerary.get('segments', [])
            
            if not segments:
                return None
            
            # Premier segment
            first_segment = segments[0]
            last_segment = segments[-1]
            
            # Infos vol
            departure_airport = first_segment.get('departure', {}).get('iataCode')
            arrival_airport = last_segment.get('arrival', {}).get('iataCode')
            departure_time = first_segment.get('departure', {}).get('at', '')
            arrival_time = last_segment.get('arrival', {}).get('at', '')
            
            carrier_code = first_segment.get('carrierCode')
            flight_number = first_segment.get('number')
            
            # Durée totale
            duration = itinerary.get('duration', '')  # Format ISO 8601: PT8H30M
            
            def format_duration(iso_duration):
                """Convertit PT8H30M en 8h30"""
                if not iso_duration:
                    return None
                import re
                match = re.match(r'PT(?:(\d+)H)?(?:(\d+)M)?', iso_duration)
                if match:
                    hours = match.group(1) or '0'
                    minutes = match.group(2) or '0'
                    return f"{hours}h{minutes.zfill(2)}"
                return iso_duration
            
            duration_formatted = format_duration(duration)
            
            # Formater les horaires
            def format_time(iso_datetime):
                if not iso_datetime:
                    return None
                try:
                    dt = datetime.fromisoformat(iso_datetime.replace('Z', '+00:00'))
                    return dt.strftime('%H:%M')
                except:
                    return iso_datetime
            
            return {
                'flight_number': f"{carrier_code}{flight_number}" if carrier_code and flight_number else 'N/A',
                'carrier_code': carrier_code,
                'departure_airport': departure_airport,
                'arrival_airport': arrival_airport,
                'departure_time': format_time(departure_time),
                'arrival_time': format_time(arrival_time),
                'departure_datetime_full': departure_time,
                'arrival_datetime_full': arrival_time,
                'duration': duration_formatted,
                'stops': len(segments) - 1,
                'price': total_price,
                'currency': currency,
                'source': 'amadeus_flight_offers'
            }
            
        except Exception as e:
            print(f"❌ Erreur lors de l'extraction de l'offre: {str(e)}")
            return None

