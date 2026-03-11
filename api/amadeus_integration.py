"""
Intégration de l'API Amadeus pour la recherche de vols.
Documentation: https://developers.amadeus.com/
"""

import requests
import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from django.conf import settings


class AmadeusFlightService:
    """Service pour interagir avec l'API Amadeus"""

    BASE_URL_PROD = "https://api.amadeus.com"
    BASE_URL_TEST = "https://test.api.amadeus.com"

    # Token mis en cache au niveau classe pour survivre entre les requêtes HTTP
    _class_token = None
    _class_token_expiry = None
    _token_lock = threading.Lock()

    def __init__(self, use_test=True):
        """
        Initialise le service Amadeus

        Args:
            use_test: Si True, utilise l'environnement de test (recommandé pour dev)
        """
        self.base_url = self.BASE_URL_TEST if use_test else self.BASE_URL_PROD
        self.api_key = getattr(settings, 'AMADEUS_API_KEY', None)
        self.api_secret = getattr(settings, 'AMADEUS_API_SECRET', None)

        if not self.api_key or not self.api_secret:
            raise ValueError("AMADEUS_API_KEY et AMADEUS_API_SECRET doivent être configurés dans settings.py")

    def _get_access_token(self):
        """
        Obtient un token d'accès OAuth2 depuis Amadeus.
        Le token est mis en cache au niveau classe et réutilisé jusqu'à expiration.
        """
        with AmadeusFlightService._token_lock:
            if AmadeusFlightService._class_token and AmadeusFlightService._class_token_expiry:
                if datetime.now() < AmadeusFlightService._class_token_expiry:
                    return AmadeusFlightService._class_token

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
                AmadeusFlightService._class_token = token_data['access_token']

                # Le token expire généralement après 1799 secondes (30 min)
                # On le considère expiré 5 minutes avant pour être sûr
                expires_in = token_data.get('expires_in', 1799)
                AmadeusFlightService._class_token_expiry = datetime.now() + timedelta(seconds=expires_in - 300)

                print(f"✅ Token obtenu, valide jusqu'à {AmadeusFlightService._class_token_expiry.strftime('%H:%M:%S')}")
                return AmadeusFlightService._class_token

            except requests.exceptions.RequestException as e:
                print(f"❌ Erreur lors de l'obtention du token: {str(e)}")
                raise
    
    def get_flight_by_number(self, flight_number, departure_date, max_days_offset=3):
        """
        Récupère les infos d'un vol par numéro + date via Amadeus Flight Schedule.
        Si le vol n'est pas trouvé à la date exacte, cherche le plus proche (±max_days_offset jours).

        Args:
            flight_number: Ex: "AF006", "KL1234"
            departure_date: Format "YYYY-MM-DD" ou "DD/MM/YYYY"
            max_days_offset: Nombre de jours maximum à chercher autour de la date (défaut: 3)

        Returns:
            dict avec les infos du vol (+ 'date_note' si date approchée) ou None
        """
        print("=" * 80)
        print("✈️  Recherche de vol par numéro + date (Amadeus Flight Schedule)")
        print("=" * 80)

        carrier_code, flight_num = self._parse_flight_number(flight_number)
        if not carrier_code or not flight_num:
            print(f"❌ Format de numéro de vol invalide: {flight_number}")
            return None

        departure_date_normalized = self._normalize_date(departure_date)
        if not departure_date_normalized:
            print(f"❌ Format de date invalide: {departure_date}")
            return None

        print(f"📋 Recherche du vol:")
        print(f"   - Compagnie: {carrier_code}")
        print(f"   - Numéro: {flight_num}")
        print(f"   - Date demandée: {departure_date_normalized}")

        try:
            token = self._get_access_token()
        except Exception as e:
            print(f"❌ Impossible d'obtenir le token: {str(e)}")
            return None

        # 1. Essai sur la date exacte
        result = self._fetch_flight_on_date(carrier_code, flight_num, departure_date_normalized, token)
        if result:
            print(f"✅ Vol trouvé: {result['flight_number']}")
            print(f"   {result['departure_airport']} → {result['arrival_airport']}")
            print(f"   Départ: {result['departure_time']} | Arrivée: {result['arrival_time']}")
            return result

        # 2. Fallback : chercher sur les jours proches en parallèle (±1, ±2, ... ±max_days_offset)
        print(f"⚠️  Vol non trouvé le {departure_date_normalized} — recherche parallèle sur dates proches...")
        base_date = datetime.strptime(departure_date_normalized, '%Y-%m-%d')

        # Construire la liste des (delta, date_str) par ordre de priorité (le plus proche d'abord)
        candidates = []
        for offset in range(1, max_days_offset + 1):
            for delta in [offset, -offset]:
                candidate = base_date + timedelta(days=delta)
                candidates.append((delta, candidate.strftime('%Y-%m-%d')))

        # Lancer tous les appels en parallèle
        with ThreadPoolExecutor(max_workers=min(6, len(candidates))) as executor:
            future_to_info = {
                executor.submit(self._fetch_flight_on_date, carrier_code, flight_num, date_str, token): (delta, date_str)
                for delta, date_str in candidates
            }

            # Collecter les résultats trouvés, indexés par |delta| pour choisir le plus proche
            found_results = {}
            for future in as_completed(future_to_info):
                delta, date_str = future_to_info[future]
                result = future.result()
                if result:
                    abs_delta = abs(delta)
                    if abs_delta not in found_results:
                        found_results[abs_delta] = (result, delta, date_str)

        if found_results:
            best_abs = min(found_results.keys())
            result, delta, date_str = found_results[best_abs]
            direction = f"+{delta}j" if delta > 0 else f"{delta}j"
            result['date_note'] = f"Vol le plus proche trouvé ({direction} par rapport au {departure_date_normalized})"
            result['requested_date'] = departure_date_normalized
            result['actual_date'] = date_str
            print(f"✅ Vol le plus proche trouvé à {direction}: {result['departure_airport']} → {result['arrival_airport']}")
            print(f"   ⚠️ Note: date réelle {date_str} ≠ date demandée {departure_date_normalized}")
            return result

        print(f"❌ Aucun vol {carrier_code}{flight_num} trouvé dans un rayon de ±{max_days_offset} jours")
        return None

    def _fetch_flight_on_date(self, carrier_code, flight_num, date_str, token):
        """
        Effectue un appel Amadeus Flight Schedule pour une date précise.
        Retourne le dict de vol extrait ou None.
        """
        url = f"{self.base_url}/v2/schedule/flights"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "carrierCode": carrier_code,
            "flightNumber": flight_num,
            "scheduledDepartureDate": date_str,
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)

            if response.status_code == 200:
                data = response.json()
                if not data.get('data'):
                    return None
                flight_data = data['data'][0]
                return self._extract_flight_info_from_amadeus_response(flight_data, carrier_code, flight_num)

            elif response.status_code == 400:
                return None  # Paramètres invalides, pas la peine d'insister

            elif response.status_code == 401:
                print(f"❌ Erreur 401 - Authentification échouée")
                raise Exception("Amadeus auth failed")

            else:
                print(f"   ⚠️ HTTP {response.status_code} pour {date_str}")
                return None

        except requests.exceptions.Timeout:
            print(f"   ⚠️ Timeout pour {date_str}")
            return None
        except requests.exceptions.RequestException as e:
            print(f"   ⚠️ Erreur réseau pour {date_str}: {str(e)}")
            return None
    
    def get_flight_price(self, origin, destination, departure_date, carrier_code=None, flight_number=None):
        """
        Récupère le prix indicatif d'un vol via l'API Flight Offers Search.
        Filtre sur le numéro de vol si fourni.

        Args:
            origin: Code IATA aéroport de départ (ex: "CDG")
            destination: Code IATA aéroport d'arrivée (ex: "JFK")
            departure_date: Date au format "YYYY-MM-DD"
            carrier_code: Code compagnie (ex: "AF") — pour filtrer
            flight_number: Numéro de vol (ex: "6") — pour filtrer

        Returns:
            dict avec 'price', 'currency', 'cabin_class' ou None
        """
        print(f"💰 Recherche de prix pour {origin} → {destination} le {departure_date}...")

        departure_date_normalized = self._normalize_date(departure_date)
        if not departure_date_normalized:
            print(f"❌ Date invalide: {departure_date}")
            return None

        try:
            token = self._get_access_token()
        except Exception as e:
            print(f"❌ Token impossible: {str(e)}")
            return None

        url = f"{self.base_url}/v2/shopping/flight-offers"
        headers = {"Authorization": f"Bearer {token}"}
        params = {
            "originLocationCode": origin,
            "destinationLocationCode": destination,
            "departureDate": departure_date_normalized,
            "adults": 1,
            "nonStop": "false",
            "max": 10,
            "currencyCode": "EUR",
        }

        try:
            response = requests.get(url, headers=headers, params=params, timeout=20)

            if response.status_code != 200:
                print(f"⚠️ Prix non disponible (HTTP {response.status_code})")
                return None

            data = response.json()
            offers = data.get('data', [])

            if not offers:
                print("⚠️ Aucune offre de prix trouvée")
                return None

            # Filtrer par numéro de vol si fourni
            if carrier_code and flight_number:
                target_fn = str(flight_number).lstrip('0')
                for offer in offers:
                    for itinerary in offer.get('itineraries', []):
                        for segment in itinerary.get('segments', []):
                            seg_carrier = segment.get('carrierCode', '').upper()
                            seg_number = str(segment.get('number', '')).lstrip('0')
                            if seg_carrier == carrier_code.upper() and seg_number == target_fn:
                                price = offer.get('price', {})
                                result = {
                                    'price': price.get('total') or price.get('grandTotal'),
                                    'base_price': price.get('base'),
                                    'currency': price.get('currency', 'EUR'),
                                    'cabin_class': (
                                        offer.get('travelerPricings', [{}])[0]
                                        .get('fareDetailsBySegment', [{}])[0]
                                        .get('cabin', 'ECONOMY')
                                    ),
                                }
                                print(f"✅ Prix trouvé pour {carrier_code}{flight_number}: {result['price']} {result['currency']}")
                                return result

            # Si pas de match exact, retourner le prix le plus bas disponible
            best_offer = offers[0]
            price = best_offer.get('price', {})
            result = {
                'price': price.get('total') or price.get('grandTotal'),
                'base_price': price.get('base'),
                'currency': price.get('currency', 'EUR'),
                'cabin_class': (
                    best_offer.get('travelerPricings', [{}])[0]
                    .get('fareDetailsBySegment', [{}])[0]
                    .get('cabin', 'ECONOMY')
                ),
                'note': 'prix indicatif (meilleure offre disponible sur la route)',
            }
            print(f"✅ Prix indicatif: {result['price']} {result['currency']} ({result.get('note', '')})")
            return result

        except requests.exceptions.Timeout:
            print("⚠️ Timeout lors de la recherche de prix")
            return None
        except requests.exceptions.RequestException as e:
            print(f"⚠️ Erreur recherche prix: {str(e)}")
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
        Extrait les infos importantes depuis la réponse Amadeus Flight Status / Schedule.

        Structure attendue:
        {
          "type": "DatedFlight",
          "scheduledDepartureDate": "2025-11-18",
          "flightDesignator": {"carrierCode": "AF", "flightNumber": "1"},
          "flightPoints": [
            {
              "iataCode": "CDG",
              "departure": {
                "timings": [{"qualifier": "STD", "value": "2025-11-18T10:30:00"}],
                "terminal": {"code": "2E"},
                "gate": {"mainGate": "K22"}
              }
            },
            {
              "iataCode": "JFK",
              "arrival": {
                "timings": [{"qualifier": "STA", "value": "2025-11-18T13:45:00"}],
                "terminal": {"code": "1"},
                "gate": {"mainGate": "B12"}
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

            def format_time(iso_datetime):
                if not iso_datetime:
                    return None
                try:
                    dt = datetime.fromisoformat(iso_datetime.replace('Z', '+00:00'))
                    return dt.strftime('%H:%M')
                except:
                    return iso_datetime

            # Point de départ (premier)
            departure_point = flight_points[0]
            departure_airport = departure_point.get('iataCode')
            departure_info = departure_point.get('departure', {})
            departure_timings = departure_info.get('timings', [{}])[0]
            departure_time = departure_timings.get('value', '')
            departure_terminal = departure_info.get('terminal', {}).get('code')
            departure_gate = departure_info.get('gate', {}).get('mainGate')

            # Point d'arrivée (dernier)
            arrival_point = flight_points[-1]
            arrival_airport = arrival_point.get('iataCode')
            arrival_info = arrival_point.get('arrival', {})
            arrival_timings = arrival_info.get('timings', [{}])[0]
            arrival_time = arrival_timings.get('value', '')
            arrival_terminal = arrival_info.get('terminal', {}).get('code')
            arrival_gate = arrival_info.get('gate', {}).get('mainGate')

            # Durée calculée
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

            # Type d'avion et statut depuis les segments
            aircraft_type = None
            flight_status = None
            raw_segments = flight_data.get('segments', [])
            if raw_segments:
                first_seg = raw_segments[0]
                aircraft_type = (
                    first_seg.get('partnership', {}).get('operatingFlight', {}).get('equipment', {}).get('aircraftType')
                    or first_seg.get('equipment', {}).get('aircraftType')
                )
                flight_status = first_seg.get('flightStatus') or first_seg.get('status')

            # Statut depuis le niveau racine si non trouvé dans les segments
            if not flight_status:
                flight_status = flight_data.get('flightStatus') or flight_data.get('status')

            # Escales : points intermédiaires
            stops_count = len(flight_points) - 2  # exclut départ et arrivée

            # Construction de la liste complète des segments (pour vols avec escale)
            segments_detail = []
            for i in range(len(flight_points) - 1):
                seg_dep = flight_points[i]
                seg_arr = flight_points[i + 1]

                seg_dep_info = seg_dep.get('departure', {})
                seg_arr_info = seg_arr.get('arrival', {})

                seg_dep_timings = seg_dep_info.get('timings', [{}])[0]
                seg_arr_timings = seg_arr_info.get('timings', [{}])[0]

                seg_dep_time = seg_dep_timings.get('value', '')
                seg_arr_time = seg_arr_timings.get('value', '')

                seg_duration = None
                if seg_dep_time and seg_arr_time:
                    try:
                        d1 = datetime.fromisoformat(seg_dep_time.replace('Z', '+00:00'))
                        d2 = datetime.fromisoformat(seg_arr_time.replace('Z', '+00:00'))
                        delta = d2 - d1
                        h = int(delta.total_seconds() // 3600)
                        m = int((delta.total_seconds() % 3600) // 60)
                        seg_duration = f"{h}h{m:02d}"
                    except:
                        pass

                segments_detail.append({
                    'segment_number': i + 1,
                    'departure_airport': seg_dep.get('iataCode'),
                    'arrival_airport': seg_arr.get('iataCode'),
                    'departure_time': format_time(seg_dep_time),
                    'arrival_time': format_time(seg_arr_time),
                    'departure_terminal': seg_dep_info.get('terminal', {}).get('code'),
                    'arrival_terminal': seg_arr_info.get('terminal', {}).get('code'),
                    'departure_gate': seg_dep_info.get('gate', {}).get('mainGate'),
                    'arrival_gate': seg_arr_info.get('gate', {}).get('mainGate'),
                    'duration': seg_duration,
                })

            return {
                'flight_number': f"{carrier_code}{flight_num}",
                'carrier_code': carrier_code,
                'departure_airport': departure_airport,
                'arrival_airport': arrival_airport,
                'departure_time': format_time(departure_time),
                'arrival_time': format_time(arrival_time),
                'departure_datetime_full': departure_time,
                'arrival_datetime_full': arrival_time,
                'duration': duration,
                'aircraft_type': aircraft_type,
                'terminal_departure': departure_terminal,
                'terminal_arrival': arrival_terminal,
                'gate_departure': departure_gate,
                'gate_arrival': arrival_gate,
                'stops': stops_count,
                'status': flight_status,
                'segments': segments_detail if len(segments_detail) > 1 else None,
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

