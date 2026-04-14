"""
Intégration Duffel API pour la recherche de vols.
Documentation: https://duffel.com/docs/api
"""

import re
import requests
from datetime import datetime
from django.conf import settings


class DuffelFlightService:
    """Recherche de vols via l'API Duffel (test ou live)."""

    BASE_URL = "https://api.duffel.com"

    def __init__(self):
        self.api_key = getattr(settings, 'DUFFEL_API_KEY', None)
        if not self.api_key:
            raise ValueError("DUFFEL_API_KEY doit être configuré dans settings.py")
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Duffel-Version": "v2",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    # ──────────────────────────────────────────
    # Utilitaires
    # ──────────────────────────────────────────

    @staticmethod
    def _normalize_fn(fn: str) -> str:
        """
        Normalise un numéro de vol pour la comparaison.
        SN 501 / SN0501 / sn501 → SN501
        LH0006 → LH6  (supprime les zéros initiaux du numéro)
        AF0256 → AF256

        Logique : code IATA = préfixe alphanum minimal non-greedy avant les chiffres,
                  numéro = suffix entier (int() supprime les zéros initiaux).
        """
        fn = str(fn).strip().upper().replace(' ', '')
        # Non-greedy : le code compagnie est le plus court préfixe qui permet
        # d'avoir un suffixe tout-numérique non vide.
        m = re.match(r'^([A-Z0-9]+?)(\d+)$', fn)
        if m:
            return m.group(1) + str(int(m.group(2)))
        return fn

    def _normalize_date(self, date_str):
        if not date_str:
            return None
        s = str(date_str).strip().split('T')[0]
        if re.match(r'^\d{4}-\d{2}-\d{2}$', s):
            return s
        m = re.match(r'^(\d{2})/(\d{2})/(\d{4})$', s)
        if m:
            return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
        return None

    def _fmt_time(self, iso):
        if not iso:
            return None
        try:
            return datetime.fromisoformat(iso.replace('Z', '+00:00')).strftime('%H:%M')
        except Exception:
            return iso

    def _fmt_duration(self, iso_dur):
        """Convertit PT16H51M ou P1DT6H30M en '16h51' / '30h30'."""
        if not iso_dur:
            return None
        # Format avec jours : P1DT6H30M
        m = re.match(r'P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?', iso_dur)
        if m:
            days = int(m.group(1) or 0)
            hours = int(m.group(2) or 0) + days * 24
            mins = int(m.group(3) or 0)
            return f"{hours}h{mins:02d}"
        return iso_dur

    def _extract_offer(self, offer, leg='aller'):
        """Transforme une offre Duffel en dict standardisé."""
        try:
            slices = offer.get('slices', [])
            if not slices:
                return None
            sl = slices[0]
            segments = sl.get('segments', [])
            if not segments:
                return None

            first = segments[0]
            last = segments[-1]

            dep_airport = first.get('origin', {}).get('iata_code', '')
            arr_airport = last.get('destination', {}).get('iata_code', '')
            dep_at = first.get('departing_at', '')
            arr_at = last.get('arriving_at', '')
            dep_terminal = first.get('origin_terminal') or ''
            arr_terminal = last.get('destination_terminal') or ''

            carrier = first.get('marketing_carrier') or first.get('operating_carrier') or {}
            carrier_code = carrier.get('iata_code', '')
            carrier_name = carrier.get('name', '')
            fn_raw = first.get('marketing_carrier_flight_number') or first.get('operating_carrier_flight_number') or ''
            flight_number = f"{carrier_code}{fn_raw}" if carrier_code and fn_raw else 'N/A'

            duration = self._fmt_duration(sl.get('duration', ''))
            price = offer.get('total_amount')
            currency = offer.get('total_currency', 'EUR')

            # Stopovers (un par segment intermédiaire)
            stopovers = []
            for i in range(len(segments) - 1):
                seg = segments[i]
                nxt = segments[i + 1]
                via = seg.get('destination', {}).get('iata_code', '')
                via_arr = seg.get('arriving_at', '')
                via_dep = nxt.get('departing_at', '')
                layover = None
                if via_arr and via_dep:
                    try:
                        t1 = datetime.fromisoformat(via_arr.replace('Z', '+00:00'))
                        t2 = datetime.fromisoformat(via_dep.replace('Z', '+00:00'))
                        delta = t2 - t1
                        h = int(delta.total_seconds() // 3600)
                        mn = int((delta.total_seconds() % 3600) // 60)
                        layover = f"{h}h{mn:02d}"
                    except Exception:
                        pass
                stopovers.append({
                    'airport': via,
                    'city': '',   # enrichi par iata_to_city() dans flight_scraper.py
                    'layover_duration': layover or '',
                    'arrival_time': self._fmt_time(via_arr),
                    'departure_time': self._fmt_time(via_dep),
                })

            return {
                'flight_number': flight_number,
                'carrier_code': carrier_code,
                'airline': carrier_name,
                'departure_airport': dep_airport,
                'arrival_airport': arr_airport,
                'departure_time': self._fmt_time(dep_at),
                'arrival_time': self._fmt_time(arr_at),
                'terminal_departure': dep_terminal,
                'terminal_arrival': arr_terminal,
                'duration': duration,
                'stops': len(segments) - 1,
                'stopovers': stopovers,
                'price': price,
                'currency': currency,
                'leg': leg,
                'source': 'duffel',
            }
        except Exception as e:
            print(f"❌ Duffel extraction erreur: {e}")
            return None

    # ──────────────────────────────────────────
    # API publique
    # ──────────────────────────────────────────

    def search_flights(self, origin, destination, departure_date,
                       cabin_class='economy', max_results=5):
        """
        Recherche des vols par itinéraire (origin IATA → destination IATA + date).
        Retourne une liste de dicts standardisés, ou None si aucun résultat.
        """
        print(f"\n{'='*70}")
        print(f"🔍 Duffel search: {origin} → {destination} / {departure_date} [{cabin_class}]")
        print(f"{'='*70}")

        date = self._normalize_date(departure_date)
        if not date:
            print(f"❌ Date invalide: {departure_date}")
            return None

        cabin_map = {
            'eco': 'economy', 'economy': 'economy',
            'premium_eco': 'premium_economy', 'premium_economy': 'premium_economy',
            'business': 'business',
            'first': 'first',
        }
        duffel_cabin = cabin_map.get(cabin_class, 'economy')

        payload = {
            "data": {
                "slices": [{"origin": origin, "destination": destination, "departure_date": date}],
                "passengers": [{"type": "adult"}],
                "cabin_class": duffel_cabin,
            }
        }

        try:
            url = f"{self.BASE_URL}/air/offer_requests"
            print(f"📡 POST /air/offer_requests ...")
            resp = requests.post(
                url, headers=self.headers, json=payload,
                params={"return_offers": "true"}, timeout=30
            )
            print(f"📊 Status: {resp.status_code}")

            if resp.status_code not in (200, 201):
                print(f"❌ Erreur {resp.status_code}: {resp.text[:400]}")
                return None

            data = resp.json()
            offers = data.get('data', {}).get('offers', [])
            if not offers:
                print(f"⚠️ Aucune offre {origin}→{destination}")
                return None

            print(f"✅ {len(offers)} offre(s) reçue(s)")

            # Codes compagnies fictives (test Duffel) à exclure
            TEST_CARRIERS = {'ZZ', 'VY_TEST', 'Z0'}

            def _offer_stops(o):
                segs = (o.get('slices') or [{}])[0].get('segments', [])
                return len(segs) - 1

            def _offer_duration_s(o):
                dur_iso = ((o.get('slices') or [{}])[0].get('duration') or '')
                m = re.match(r'P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?', dur_iso)
                if m:
                    days = int(m.group(1) or 0)
                    hours = int(m.group(2) or 0) + days * 24
                    mins = int(m.group(3) or 0)
                    return hours * 3600 + mins * 60
                return 0

            def _offer_carrier(o):
                segs = (o.get('slices') or [{}])[0].get('segments', [])
                if not segs:
                    return ''
                c = segs[0].get('marketing_carrier') or segs[0].get('operating_carrier') or {}
                return c.get('iata_code', '')

            # Séparer vraies compagnies / fictives
            real_offers = [o for o in offers if _offer_carrier(o) not in TEST_CARRIERS]
            usable = real_offers if real_offers else offers

            # Trier par durée totale uniquement (le vol le plus rapide en premier)
            usable_sorted = sorted(usable, key=_offer_duration_s)

            # Extraire en dédupliquant par (flight_number, departure_time)
            results = []
            seen = set()
            for offer in usable_sorted:
                if len(results) >= max_results:
                    break
                info = self._extract_offer(offer)
                if not info:
                    continue
                key = (info.get('flight_number', ''), info.get('departure_time', ''))
                if key in seen:
                    continue
                seen.add(key)
                results.append(info)

            if results:
                best = results[0]
                print(f"   Meilleur vol : {best.get('flight_number')} | {best.get('airline')} | stops={best.get('stops')} | durée={best.get('duration')}")

            return results or None

        except requests.exceptions.Timeout:
            print("❌ Timeout Duffel (>30s)")
            return None
        except Exception as e:
            print(f"❌ Exception Duffel: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_flight_by_number(self, flight_number, departure_date,
                             origin=None, destination=None):
        """
        Cherche un vol par numéro + date via Duffel.
        Recherche le numéro dans TOUS les segments de chaque offre (pas seulement le 1er),
        ce qui permet de trouver LH1041+LH9792 en cherchant "LH9792".
        """
        if not origin or not destination:
            print(f"❌ get_flight_by_number: origin/destination requis")
            return None

        date = self._normalize_date(departure_date)
        if not date:
            return None

        payload = {
            "data": {
                "slices": [{"origin": origin, "destination": destination, "departure_date": date}],
                "passengers": [{"type": "adult"}],
                "cabin_class": "economy",
            }
        }

        try:
            resp = requests.post(
                f"{self.BASE_URL}/air/offer_requests",
                headers=self.headers, json=payload,
                params={"return_offers": "true"}, timeout=30
            )
            if resp.status_code not in (200, 201):
                print(f"❌ Duffel {resp.status_code}: {resp.text[:200]}")
                return None

            raw_offers = resp.json().get('data', {}).get('offers', [])
            if not raw_offers:
                return None

            print(f"✅ {len(raw_offers)} offre(s) brutes reçues")

        except Exception as e:
            print(f"❌ Duffel exception: {e}")
            return None

        TEST_CARRIERS = {'ZZ', 'VY_TEST', 'Z0'}
        fn_target = self._normalize_fn(flight_number)

        def _carrier(o):
            segs = (o.get('slices') or [{}])[0].get('segments', [])
            if not segs:
                return ''
            c = segs[0].get('marketing_carrier') or segs[0].get('operating_carrier') or {}
            return c.get('iata_code', '')

        def _has_segment(o, target):
            """Vérifie si le numéro cible (normalisé) apparaît dans n'importe quel segment."""
            segs = (o.get('slices') or [{}])[0].get('segments', [])
            for seg in segs:
                cc = (seg.get('marketing_carrier') or {}).get('iata_code', '')
                n = seg.get('marketing_carrier_flight_number', '')
                if self._normalize_fn(f"{cc}{n}") == target:
                    return True
            return False

        def _duration_s(o):
            dur = (o.get('slices') or [{}])[0].get('duration', '')
            m = re.match(r'P(?:(\d+)D)?T(?:(\d+)H)?(?:(\d+)M)?', dur)
            if m:
                return (int(m.group(1) or 0) * 24 + int(m.group(2) or 0)) * 3600 + int(m.group(3) or 0) * 60
            return 0

        real_offers = [o for o in raw_offers if _carrier(o) not in TEST_CARRIERS]
        usable = real_offers if real_offers else raw_offers

        # Priorité 1 : offres contenant le numéro dans n'importe quel segment
        matching = [o for o in usable if _has_segment(o, fn_target)]
        if matching:
            best = min(matching, key=_duration_s)
            info = self._extract_offer(best)
            if info:
                print(f"✅ Segment {fn_target} trouvé → offre {info.get('flight_number')} ({info.get('duration')})")
                return info

        # Vol non trouvé dans Duffel (compagnie non distribuée ex: LX/Swiss)
        print(f"⚠️ {fn_target} absent du catalogue Duffel pour {origin}→{destination} — retour None")
        return None
