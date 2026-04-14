"""
Intégration Air France / KLM API — fallback Duffel pour les vols AF et KL.
Documentation: https://developer.airfranceklm.com
"""

import json
import re
import requests
from datetime import datetime
from django.conf import settings


class AFKLFlightService:
    """Recherche de vols AF/KL via l'API Open Data Air France-KLM."""

    BASE_URL = "https://api.airfranceklm.com"
    OFFERS_URL = "https://api.airfranceklm.com/opendata/offers/v3/available-offers"

    def __init__(self):
        self.api_key = getattr(settings, 'AIRFRANCE_KLM_API_KEY', None)
        if not self.api_key:
            raise ValueError("AIRFRANCE_KLM_API_KEY non configurée dans settings")
        self.headers = {
            "API-Key": self.api_key,
            "AFKL-TRAVEL-Host": "AF",
            "Accept": "application/hal+json",
            "Content-Type": "application/hal+json",
        }

    # ──────────────────────────────────────────
    # Utilitaires
    # ──────────────────────────────────────────

    def _parse_dt(self, dt_str):
        if not dt_str:
            return None
        try:
            return datetime.fromisoformat(str(dt_str).replace('Z', '+00:00'))
        except Exception:
            return None

    def _fmt_time(self, dt_str):
        dt = self._parse_dt(dt_str)
        return dt.strftime('%H:%M') if dt else None

    def _calc_duration(self, dep_str, arr_str):
        dep = self._parse_dt(dep_str)
        arr = self._parse_dt(arr_str)
        if not dep or not arr:
            return None
        delta = arr - dep
        total = delta.total_seconds()
        if total < 0:
            return None
        h = int(total // 3600)
        m = int((total % 3600) // 60)
        return f"{h}h{m:02d}"

    # ──────────────────────────────────────────
    # Parsing réponse HAL+JSON
    # ──────────────────────────────────────────

    def _collect_connections(self, data):
        """
        Extrait les connections racine de la réponse AFKL.
        Les connections à la racine (data['connections']) contiennent les vraies
        données de vol (segments avec horaires, numéros, aéroports).
        Les connections dans recommendations/flightProducts ne contiennent que
        la tarification — on les ignore.
        """
        connections = []
        for cg in data.get('connections', []):
            if isinstance(cg, list):
                connections.extend(cg)
            elif isinstance(cg, dict):
                connections.append(cg)
        return connections

    def _parse_connection(self, conn, origin, destination):
        """Transforme une connection AFKL en dict standardisé (compatible Duffel)."""
        try:
            segments = conn.get('flightSegments') or conn.get('segments', [])
            if not segments:
                return None

            first = segments[0]
            last = segments[-1]

            # Numéro de vol + compagnie (marketingFlight)
            mf = first.get('marketingFlight') or {}
            carrier = mf.get('carrier') or {} if isinstance(mf, dict) else {}
            carrier_code = (carrier.get('code', '') if isinstance(carrier, dict) else '').upper()
            fn_num = (mf.get('number', '') if isinstance(mf, dict) else '').strip()
            flight_number = f"{carrier_code}{fn_num}" if fn_num else None
            airline_name = (carrier.get('name', '') if isinstance(carrier, dict) else '') or 'Air France-KLM'

            # Fallback operatingFlight
            if not flight_number:
                of_ = first.get('operatingFlight') or {}
                op_carrier = of_.get('carrier') or {} if isinstance(of_, dict) else {}
                carrier_code = (op_carrier.get('code', '') if isinstance(op_carrier, dict) else '').upper()
                fn_num = (of_.get('number', '') if isinstance(of_, dict) else '').strip()
                flight_number = f"{carrier_code}{fn_num}" if fn_num else None
                if not airline_name or airline_name == 'Air France-KLM':
                    airline_name = (op_carrier.get('name', '') if isinstance(op_carrier, dict) else '') or 'Air France-KLM'

            if not flight_number:
                return None

            # Aéroports
            dep_airport = ((first.get('origin') or {}).get('code') or origin)
            arr_airport = ((last.get('destination') or {}).get('code') or destination)
            dep_terminal = (first.get('origin') or {}).get('terminal', '')
            arr_terminal = (last.get('destination') or {}).get('terminal', '')

            # Horaires
            dep_dt = first.get('departureDateTime') or (first.get('departure') or {}).get('dateTime', '')
            arr_dt = last.get('arrivalDateTime') or (last.get('arrival') or {}).get('dateTime', '')

            # Durée : utiliser le champ 'duration' (minutes) de la connection AFKL
            # en priorité car les horaires sont en heure locale sans fuseau → diff incorrecte
            conn_duration_min = conn.get('duration')
            if conn_duration_min:
                h = int(conn_duration_min) // 60
                m = int(conn_duration_min) % 60
                duration = f"{h}h{m:02d}"
            else:
                duration = self._calc_duration(dep_dt, arr_dt)

            # Stopovers
            stopovers = []
            for i in range(len(segments) - 1):
                seg = segments[i]
                nxt = segments[i + 1]
                via_iata = (seg.get('destination') or {}).get('code', '')
                via_arr = seg.get('arrivalDateTime') or (seg.get('arrival') or {}).get('dateTime', '')
                via_dep = nxt.get('departureDateTime') or (nxt.get('departure') or {}).get('dateTime', '')
                stopovers.append({
                    'airport': via_iata,
                    'city': '',
                    'layover_duration': self._calc_duration(via_arr, via_dep) or '',
                    'arrival_time': self._fmt_time(via_arr),
                    'departure_time': self._fmt_time(via_dep),
                })

            return {
                'flight_number': flight_number,
                'carrier_code': carrier_code,
                'airline': airline_name,
                'departure_airport': dep_airport,
                'arrival_airport': arr_airport,
                'departure_time': self._fmt_time(dep_dt),
                'arrival_time': self._fmt_time(arr_dt),
                'terminal_departure': dep_terminal or '',
                'terminal_arrival': arr_terminal or '',
                'duration': duration,
                'stops': len(segments) - 1,
                'stopovers': stopovers,
                'price': None,
                'currency': 'EUR',
                'source': 'afkl',
            }
        except Exception as e:
            print(f"❌ AFKL parse erreur: {e}")
            return None

    # ──────────────────────────────────────────
    # API publique
    # ──────────────────────────────────────────

    def search_flights(self, origin, destination, departure_date, max_results=3):
        """
        Recherche des vols AF/KL par route + date.
        Retourne une liste de dicts standardisés, ou None.
        """
        print(f"\n{'='*60}")
        print(f"✈️  AFKL search: {origin} → {destination} / {departure_date}")
        print(f"{'='*60}")

        payload = {
            "commercialCabins": ["ALL"],
            "bookingFlow": "LEISURE",
            "passengers": [{"id": 1, "type": "ADT"}],
            "requestedConnections": [
                {
                    "departureDate": departure_date,
                    "origin": {"code": origin, "type": "STOPOVER"},
                    "destination": {"code": destination, "type": "STOPOVER"},
                }
            ],
        }

        try:
            resp = requests.post(
                self.OFFERS_URL,
                data=json.dumps(payload),
                headers=self.headers,
                timeout=30,
            )
            print(f"📊 Status: {resp.status_code}")

            if resp.status_code not in (200, 201):
                print(f"❌ AFKL erreur {resp.status_code}: {resp.text[:300]}")
                return None

            data = resp.json()

        except requests.exceptions.Timeout:
            print("❌ Timeout AFKL (>30s)")
            return None
        except Exception as e:
            print(f"❌ Exception AFKL: {e}")
            return None

        connections = self._collect_connections(data)
        print(f"✅ {len(connections)} connection(s) AFKL extraite(s)")

        results = []
        seen = set()
        for conn in connections:
            parsed = self._parse_connection(conn, origin, destination)
            if not parsed:
                continue
            key = (parsed['flight_number'], parsed['departure_time'])
            if key in seen:
                continue
            seen.add(key)
            results.append(parsed)
            if len(results) >= max_results:
                break

        if results:
            print(f"   Vols AFKL: {', '.join(r['flight_number'] for r in results)}")
        else:
            print("   ⚠️ Aucun vol extrait de la réponse AFKL")

        return results or None

    def get_flight_by_number(self, flight_number, departure_date,
                              origin=None, destination=None):
        """
        Cherche un vol AF/KL par numéro + date.
        Stratégie :
          1. Recherche origin→destination (route principale)
          2. Si pas trouvé, essaie les hubs AF/KL courants comme destination
             (AF0256 CDG→SIN n'apparaît que si on cherche CDG→SIN)
        """
        if not origin:
            print("❌ AFKL get_flight_by_number: origin requis")
            return None

        import time as _time

        fn_target = flight_number.strip().upper().replace(' ', '')

        # Destinations à essayer par ordre de probabilité
        carrier = flight_number[:2].upper()
        # Hubs AF triés par fréquence de vols long-courriers
        af_hubs = ['SIN', 'JFK', 'LAX', 'NRT', 'HKG', 'BKK', 'YUL', 'GRU', 'GIG', 'MEX']
        # Hubs KL triés
        kl_hubs = ['AMS', 'SIN', 'NRT', 'JFK', 'HKG']

        candidate_dests = []
        if destination:
            candidate_dests.append(destination)
        for hub in (af_hubs if carrier == 'AF' else kl_hubs):
            if hub not in candidate_dests and hub != origin:
                candidate_dests.append(hub)

        for i, dest in enumerate(candidate_dests[:4]):    # max 4 tentatives
            if i > 0:
                _time.sleep(1.0)   # éviter "Over Qps"
            results = self.search_flights(origin, dest, departure_date, max_results=20)
            if not results:
                continue
            for r in results:
                fn = r.get('flight_number', '').upper().replace(' ', '')
                if fn == fn_target:
                    print(f"✅ AFKL: {fn_target} trouvé ({origin}→{dest})")
                    return r

        print(f"⚠️ AFKL: {fn_target} non trouvé")
        return None
