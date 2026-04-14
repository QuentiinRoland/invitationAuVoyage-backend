"""
FlightWebScraper — recherche les horaires de vol.

Ordre :
  1. AviationStack API  (clé dans .env, fiable, structurée)
  2. MisterFly scraping (Playwright, fallback si AviationStack ne trouve pas)
"""

import os
import re
import json
import requests
from typing import Optional

# ──────────────────────────────────────────────────────────────
# IATA → (ville_fr, pays_fr)
# ──────────────────────────────────────────────────────────────
IATA_CITIES: dict[str, tuple[str, str]] = {
    # France
    "CDG": ("Paris", "France"), "ORY": ("Paris", "France"),
    "LYS": ("Lyon", "France"), "NCE": ("Nice", "France"),
    "MRS": ("Marseille", "France"), "TLS": ("Toulouse", "France"),
    "BOD": ("Bordeaux", "France"), "NTE": ("Nantes", "France"),
    "SXB": ("Strasbourg", "France"), "LIL": ("Lille", "France"),
    "RNS": ("Rennes", "France"), "BES": ("Brest", "France"),
    # France Outre-mer
    "RUN": ("La Réunion", "La Réunion"), "MRU": ("Maurice", "Île Maurice"),
    "PTP": ("Pointe-à-Pitre", "Guadeloupe"), "FDF": ("Fort-de-France", "Martinique"),
    "CAY": ("Cayenne", "Guyane"), "NOU": ("Nouméa", "Nouvelle-Calédonie"),
    "PPT": ("Papeete", "Polynésie française"), "TNR": ("Antananarivo", "Madagascar"),
    "MHQ": ("Mayotte", "Mayotte"),
    # Europe
    "LHR": ("Londres", "Royaume-Uni"), "LGW": ("Londres Gatwick", "Royaume-Uni"),
    "STN": ("Londres Stansted", "Royaume-Uni"), "MAN": ("Manchester", "Royaume-Uni"),
    "EDI": ("Édimbourg", "Royaume-Uni"), "GLA": ("Glasgow", "Royaume-Uni"),
    "AMS": ("Amsterdam", "Pays-Bas"),
    "BRU": ("Bruxelles", "Belgique"),
    "FRA": ("Francfort", "Allemagne"), "MUC": ("Munich", "Allemagne"),
    "TXL": ("Berlin", "Allemagne"), "BER": ("Berlin", "Allemagne"), "HAM": ("Hambourg", "Allemagne"),
    "BCN": ("Barcelone", "Espagne"), "MAD": ("Madrid", "Espagne"),
    "PMI": ("Palma de Majorque", "Espagne"), "AGP": ("Málaga", "Espagne"), "VLC": ("Valence", "Espagne"),
    "FCO": ("Rome", "Italie"), "MXP": ("Milan Malpensa", "Italie"),
    "LIN": ("Milan Linate", "Italie"), "NAP": ("Naples", "Italie"),
    "VCE": ("Venise", "Italie"), "BGY": ("Milan Bergame", "Italie"),
    "ZRH": ("Zurich", "Suisse"), "GVA": ("Genève", "Suisse"),
    "BSL": ("Bâle-Mulhouse", "France/Suisse"),
    "VIE": ("Vienne", "Autriche"), "SZG": ("Salzbourg", "Autriche"), "INN": ("Innsbruck", "Autriche"),
    "LIS": ("Lisbonne", "Portugal"), "OPO": ("Porto", "Portugal"), "FAO": ("Faro", "Portugal"),
    "CPH": ("Copenhague", "Danemark"), "AAR": ("Aarhus", "Danemark"),
    "ARN": ("Stockholm", "Suède"), "GOT": ("Göteborg", "Suède"),
    "OSL": ("Oslo", "Norvège"), "BGO": ("Bergen", "Norvège"), "TRD": ("Trondheim", "Norvège"),
    "HEL": ("Helsinki", "Finlande"),
    "KEF": ("Reykjavik", "Islande"),
    "DUB": ("Dublin", "Irlande"), "ORK": ("Cork", "Irlande"),
    "ATH": ("Athènes", "Grèce"), "SKG": ("Thessalonique", "Grèce"), "HER": ("Héraklion", "Grèce"),
    "RHO": ("Rhodes", "Grèce"), "CFU": ("Corfou", "Grèce"),
    "PRG": ("Prague", "République tchèque"), "WAW": ("Varsovie", "Pologne"), "KRK": ("Cracovie", "Pologne"),
    "BUD": ("Budapest", "Hongrie"), "OTP": ("Bucarest", "Roumanie"),
    "SOF": ("Sofia", "Bulgarie"), "OHD": ("Ohrid", "Macédoine du Nord"),
    "SVO": ("Moscou Cheremetievo", "Russie"), "LED": ("Saint-Pétersbourg", "Russie"),
    "IST": ("Istanbul", "Turquie"), "SAW": ("Istanbul Sabiha", "Turquie"), "AYT": ("Antalya", "Turquie"),
    "TLV": ("Tel Aviv", "Israël"),
    # Afrique
    "CMN": ("Casablanca", "Maroc"), "RAK": ("Marrakech", "Maroc"),
    "RBA": ("Rabat", "Maroc"), "AGA": ("Agadir", "Maroc"),
    "TUN": ("Tunis", "Tunisie"), "JER": ("Djerba", "Tunisie"),
    "ALG": ("Alger", "Algérie"), "ORN": ("Oran", "Algérie"),
    "CAI": ("Le Caire", "Égypte"), "HRG": ("Hurghada", "Égypte"),
    "SSH": ("Charm-el-Cheikh", "Égypte"),
    "JNB": ("Johannesburg", "Afrique du Sud"), "CPT": ("Le Cap", "Afrique du Sud"),
    "NBO": ("Nairobi", "Kenya"), "MBA": ("Mombasa", "Kenya"),
    "ADD": ("Addis-Abeba", "Éthiopie"), "DAR": ("Dar es-Salaam", "Tanzanie"),
    "JRO": ("Kilimandjaro", "Tanzanie"), "ZNZ": ("Zanzibar", "Tanzanie"),
    "DKR": ("Dakar", "Sénégal"), "ABJ": ("Abidjan", "Côte d'Ivoire"),
    "LOS": ("Lagos", "Nigéria"), "ACC": ("Accra", "Ghana"),
    "SEZ": ("Mahé", "Seychelles"), "DZA": ("Dzaoudzi", "Mayotte"),
    # Moyen-Orient
    "DXB": ("Dubaï", "Émirats arabes unis"), "AUH": ("Abu Dhabi", "Émirats arabes unis"),
    "SHJ": ("Charjah", "Émirats arabes unis"),
    "DOH": ("Doha", "Qatar"),
    "RUH": ("Riyad", "Arabie saoudite"), "JED": ("Djeddah", "Arabie saoudite"),
    "KWI": ("Koweït", "Koweït"), "MCT": ("Mascate", "Oman"),
    "BAH": ("Manama", "Bahreïn"), "AMM": ("Amman", "Jordanie"),
    "BEY": ("Beyrouth", "Liban"),
    # Asie
    "BKK": ("Bangkok", "Thaïlande"), "HKT": ("Phuket", "Thaïlande"),
    "CNX": ("Chiang Mai", "Thaïlande"),
    "SIN": ("Singapour", "Singapour"),
    "KUL": ("Kuala Lumpur", "Malaisie"), "PEN": ("Penang", "Malaisie"),
    "DPS": ("Bali", "Indonésie"), "CGK": ("Jakarta", "Indonésie"),
    "SUB": ("Surabaya", "Indonésie"),
    "HKG": ("Hong Kong", "Hong Kong"),
    "NRT": ("Tokyo Narita", "Japon"), "HND": ("Tokyo Haneda", "Japon"),
    "KIX": ("Osaka", "Japon"), "CTS": ("Sapporo", "Japon"),
    "ICN": ("Séoul", "Corée du Sud"),
    "PEK": ("Pékin", "Chine"), "PVG": ("Shanghai", "Chine"),
    "CAN": ("Guangzhou", "Chine"),
    "BOM": ("Mumbai", "Inde"), "DEL": ("New Delhi", "Inde"),
    "MAA": ("Chennai", "Inde"), "BLR": ("Bangalore", "Inde"),
    "CMB": ("Colombo", "Sri Lanka"), "MLE": ("Malé", "Maldives"),
    "HAN": ("Hanoï", "Viêt Nam"), "SGN": ("Hô-Chi-Minh-Ville", "Viêt Nam"),
    "DAD": ("Da Nang", "Viêt Nam"),
    "MNL": ("Manille", "Philippines"), "CEB": ("Cebu", "Philippines"),
    "RGN": ("Rangoun", "Myanmar"),
    "PNH": ("Phnom Penh", "Cambodge"), "REP": ("Siem Reap", "Cambodge"),
    # Amériques
    "JFK": ("New York JFK", "États-Unis"), "EWR": ("New York Newark", "États-Unis"),
    "LGA": ("New York LaGuardia", "États-Unis"),
    "LAX": ("Los Angeles", "États-Unis"), "SFO": ("San Francisco", "États-Unis"),
    "MIA": ("Miami", "États-Unis"), "FLL": ("Fort Lauderdale", "États-Unis"),
    "ORD": ("Chicago O'Hare", "États-Unis"), "MDW": ("Chicago Midway", "États-Unis"),
    "ATL": ("Atlanta", "États-Unis"), "BOS": ("Boston", "États-Unis"),
    "IAD": ("Washington Dulles", "États-Unis"), "DCA": ("Washington Reagan", "États-Unis"),
    "IAH": ("Houston", "États-Unis"), "DFW": ("Dallas", "États-Unis"),
    "SEA": ("Seattle", "États-Unis"), "DEN": ("Denver", "États-Unis"),
    "LAS": ("Las Vegas", "États-Unis"), "PHX": ("Phoenix", "États-Unis"),
    "MSY": ("La Nouvelle-Orléans", "États-Unis"),
    "YUL": ("Montréal", "Canada"), "YYZ": ("Toronto", "Canada"),
    "YVR": ("Vancouver", "Canada"), "YYC": ("Calgary", "Canada"),
    "GRU": ("São Paulo", "Brésil"), "GIG": ("Rio de Janeiro", "Brésil"),
    "BSB": ("Brasília", "Brésil"),
    "EZE": ("Buenos Aires", "Argentine"),
    "SCL": ("Santiago", "Chili"),
    "BOG": ("Bogotá", "Colombie"), "MDE": ("Medellín", "Colombie"),
    "LIM": ("Lima", "Pérou"),
    "MEX": ("Mexico", "Mexique"), "CUN": ("Cancún", "Mexique"),
    "GDL": ("Guadalajara", "Mexique"),
    "PTY": ("Panama City", "Panama"),
    "UIO": ("Quito", "Équateur"), "GYE": ("Guayaquil", "Équateur"),
    "HAV": ("La Havane", "Cuba"),
    # Océanie
    "SYD": ("Sydney", "Australie"), "MEL": ("Melbourne", "Australie"),
    "BNE": ("Brisbane", "Australie"), "PER": ("Perth", "Australie"),
    "AKL": ("Auckland", "Nouvelle-Zélande"),
}


def iata_to_city(code: str) -> tuple[str, str]:
    return IATA_CITIES.get(code.upper(), (code, ""))


# Reverse : ville → IATA principal
_CITY_TO_IATA: dict[str, str] = {}
for _code, (_city, _country) in IATA_CITIES.items():
    _key = _city.lower().strip()
    if _key not in _CITY_TO_IATA:
        _CITY_TO_IATA[_key] = _code
    _short = _key.split()[0]
    if _short not in _CITY_TO_IATA and len(_short) > 3:
        _CITY_TO_IATA[_short] = _code

_CITY_TO_IATA.update({
    "paris": "CDG", "london": "LHR", "londres": "LHR",
    "dubai": "DXB", "dubaï": "DXB",
    "bali": "DPS", "tokyo": "NRT",
    "singapore": "SIN", "singapour": "SIN",
    "bangkok": "BKK", "new york": "JFK", "los angeles": "LAX",
    "maldives": "MLE", "male": "MLE", "malé": "MLE",
    "seychelles": "SEZ", "mahe": "SEZ", "mahé": "SEZ",
    "rome": "FCO", "milan": "MXP", "venise": "VCE",
    "barcelone": "BCN", "madrid": "MAD",
    "amsterdam": "AMS", "bruxelles": "BRU",
    "francfort": "FRA", "munich": "MUC", "berlin": "BER",
    "zurich": "ZRH", "geneve": "GVA", "genève": "GVA",
    "lisbonne": "LIS", "porto": "OPO",
    "casablanca": "CMN", "marrakech": "RAK",
    "doha": "DOH", "abu dhabi": "AUH",
    "hong kong": "HKG", "seoul": "ICN", "séoul": "ICN",
    "montreal": "YUL", "montréal": "YUL", "toronto": "YYZ", "vancouver": "YVR",
    "cancun": "CUN", "cancún": "CUN", "mexico": "MEX",
    "buenos aires": "EZE", "sao paulo": "GRU", "rio": "GIG",
    "reunion": "RUN", "la reunion": "RUN", "île maurice": "MRU", "mauritius": "MRU",
    "zanzibar": "ZNZ", "nairobi": "NBO", "mombasa": "MBA",
    "hanoi": "HAN", "hanoï": "HAN", "ho chi minh": "SGN", "hô chi minh": "SGN",
    "manille": "MNL", "phnom penh": "PNH", "siem reap": "REP",
})


def city_to_iata(city_name: str) -> Optional[str]:
    if not city_name:
        return None
    try:
        import unicodedata
        key = unicodedata.normalize("NFKD", city_name).encode("ascii", "ignore").decode().lower().strip()
    except Exception:
        key = city_name.lower().strip()

    # 1. Correspondance exacte
    result = _CITY_TO_IATA.get(key)
    if result:
        return result

    # 2. Correspondance par préfixe (ex: "pari" → "paris", "brux" → "bruxelles")
    if len(key) >= 3:
        for k, v in _CITY_TO_IATA.items():
            if k.startswith(key) or key.startswith(k):
                return v

    # 3. Correspondance contient (ex: "new yor" → "new york")
    if len(key) >= 4:
        for k, v in _CITY_TO_IATA.items():
            if key in k:
                return v

    return None


def parse_flight_number(raw: str) -> tuple[str, str]:
    raw = raw.upper().strip()
    m = re.match(r'^([A-Z]{2,3})(\d+)$', raw)
    if m:
        return m.group(1), m.group(2)
    return raw[:2], raw[2:]


# ──────────────────────────────────────────────────────────────
# Utilitaires
# ──────────────────────────────────────────────────────────────
_ISO_RE  = re.compile(r'T(\d{2}):(\d{2})')
_TIME_RE = re.compile(r'\b(\d{1,2})[h:]\s*(\d{2})\b')
_IATA_RE = re.compile(r'\b([A-Z]{3})\b')


def _iso_to_hhmm(s: str) -> Optional[str]:
    """
    Parse les formats :
      "2026-03-31T07:05:00+04:00"   (ISO 8601)
      "2026-03-31 07:05+04:00"      (AeroDataBox)
    """
    if not s:
        return None
    m = re.search(r'[T ](\d{2}):(\d{2})', s)
    return f"{m.group(1)}:{m.group(2)}" if m else None


def _extract_times_from_text(text: str) -> tuple[Optional[str], Optional[str]]:
    times = _TIME_RE.findall(text)
    if len(times) >= 2:
        dep = f"{int(times[0][0]):02d}:{times[0][1]}"
        arr = f"{int(times[1][0]):02d}:{times[1][1]}"
        return dep, arr
    return None, None


def _build_result(carrier: str, number: str, dep: str, arr: str,
                  dep_time: Optional[str], arr_time: Optional[str],
                  source: str, stops: int = 0) -> dict:
    dep_city, dep_country = iata_to_city(dep)
    arr_city, arr_country = iata_to_city(arr)
    return {
        "flight_number": f"{carrier}{number}",
        "carrier_code": carrier,
        "departure_airport": dep,
        "arrival_airport": arr,
        "departure_city": dep_city,
        "departure_country": dep_country,
        "arrival_city": arr_city,
        "arrival_country": arr_country,
        "departure_time": dep_time,
        "arrival_time": arr_time,
        "stops": stops,
        "status": "SCHEDULED",
        "source": source,
    }


# ──────────────────────────────────────────────────────────────
# SOURCE 1 — AeroDataBox via RapidAPI (fiable, toutes dates)
# ──────────────────────────────────────────────────────────────
# IATA → ICAO (requis par l'endpoint airport departures d'AeroDataBox)
IATA_TO_ICAO: dict[str, str] = {
    "CDG": "LFPG", "ORY": "LFPO", "LYS": "LFLL", "NCE": "LFMN",
    "MRS": "LFML", "TLS": "LFBO", "BOD": "LFBD", "NTE": "LFRS",
    "LIL": "LFQQ", "SXB": "LFSB", "BSL": "LFSB",
    "RUN": "FMEE", "MRU": "FIMP", "PTP": "TFFR", "FDF": "TFFF",
    "CAY": "SOCA", "PPT": "NTAA", "NOU": "NWWW",
    "LHR": "EGLL", "LGW": "EGKK", "STN": "EGSS", "MAN": "EGCC", "EDI": "EGPH",
    "AMS": "EHAM", "BRU": "EBBR",
    "FRA": "EDDF", "MUC": "EDDM", "BER": "EDDB", "HAM": "EDDH",
    "BCN": "LEBL", "MAD": "LEMD", "PMI": "LEPA", "AGP": "LEMG",
    "FCO": "LIRF", "MXP": "LIMC", "LIN": "LIML", "NAP": "LIRN", "VCE": "LIPZ",
    "ZRH": "LSZH", "GVA": "LSGG",
    "VIE": "LOWW",
    "LIS": "LPPT", "OPO": "LPPR",
    "CPH": "EKCH",
    "ARN": "ESSA", "GOT": "ESGG",
    "OSL": "ENGM",
    "HEL": "EFHK",
    "KEF": "BIKF",
    "DUB": "EIDW",
    "ATH": "LGAV", "SKG": "LGTS",
    "PRG": "LKPR", "WAW": "EPWA", "BUD": "LHBP", "OTP": "LROP",
    "IST": "LTFM", "SAW": "LTFJ", "AYT": "LTAI",
    "TLV": "LLBG",
    "CMN": "GMMN", "RAK": "GMMX",
    "TUN": "DTTA", "ALG": "DAAG",
    "CAI": "HECA", "HRG": "HEGN", "SSH": "HESH",
    "DXB": "OMDB", "AUH": "OMAA", "DOH": "OTHH",
    "JNB": "FAOR", "CPT": "FACT",
    "NBO": "HKJK", "MBA": "HKMO",
    "ADD": "HAAB", "DAR": "HTDA", "ZNZ": "HTZA", "JRO": "HTKJ",
    "DKR": "GOOY", "ABJ": "DIAP",
    "SEZ": "FSIA", "MRU": "FIMP",
    "TNR": "FMMI",
    "SIN": "WSSS", "KUL": "WMKK",
    "BKK": "VTBS", "HKT": "VTSP",
    "DPS": "WADD", "CGK": "WIII",
    "HKG": "VHHH",
    "NRT": "RJAA", "HND": "RJTT", "KIX": "RJBB",
    "ICN": "RKSI",
    "PEK": "ZBAA", "PVG": "ZSPD",
    "DEL": "VIDP", "BOM": "VABB", "MAA": "VOMM", "BLR": "VOBL",
    "CMB": "VCBI", "MLE": "VRMM",
    "HAN": "VVNB", "SGN": "VVTS",
    "MNL": "RPLL",
    "JFK": "KJFK", "EWR": "KEWR", "LGA": "KLGA",
    "LAX": "KLAX", "SFO": "KSFO",
    "MIA": "KMIA", "FLL": "KFLL",
    "ORD": "KORD", "MDW": "KMDW",
    "ATL": "KATL", "BOS": "KBOS",
    "IAD": "KIAD", "DCA": "KDCA",
    "IAH": "KIAH", "DFW": "KDFW",
    "SEA": "KSEA", "DEN": "KDEN", "LAS": "KLAS",
    "YUL": "CYUL", "YYZ": "CYYZ", "YVR": "CYVR",
    "GRU": "SBGR", "GIG": "SBRJ",
    "EZE": "SAEZ", "SCL": "SCEL",
    "BOG": "SKBO", "LIM": "SPIM",
    "MEX": "MMMX", "CUN": "MMUN",
    "PTY": "MPTO",
    "SYD": "YSSY", "MEL": "YMML", "BNE": "YBBN", "PER": "YPPH",
    "AKL": "NZAA",
}


def iata_to_icao(iata: str) -> str:
    """Retourne le code ICAO pour un code IATA. Fallback: essaie 'K'+IATA pour USA."""
    code = IATA_TO_ICAO.get(iata.upper())
    if code:
        return code
    # Heuristique USA : JFK→KJFK, LAX→KLAX
    if len(iata) == 3:
        return "K" + iata.upper()
    return iata.upper()


def _search_connecting_flight(via_iata: str, final_iata: str, date: str,
                               depart_after: str = "") -> Optional[dict]:
    """
    Cherche un vol via_iata → final_iata qui PART après depart_after (ex: "15:35").
    Utilisé pour trouver automatiquement le 2e tronçon (ex: KEF→JFK après FI0543).
    """
    import time as _t
    api_key = os.environ.get("AERODATABOX_API_KEY", "")
    if not api_key:
        return None

    # Calcul de la fenêtre horaire : de depart_after jusqu'à minuit
    from_time = depart_after if depart_after else "00:00"
    icao = iata_to_icao(via_iata)
    url = (
        f"https://aerodatabox.p.rapidapi.com/flights/airports/dep"
        f"/{icao}/{date}T{from_time}/{date}T23:59"
    )
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "aerodatabox.p.rapidapi.com",
    }
    params = {"withAircraftImage": "false", "withLocation": "false"}

    print(f"   🔎 Connexion auto: {via_iata}→{final_iata} après {from_time} | ICAO={icao}")
    print(f"   🌐 URL: {url}")
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code == 429:
            print(f"   ⏳ Rate limit — attente 3s puis retry...")
            _t.sleep(3)
            resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code != 200:
            print(f"   ❌ Connexion auto HTTP {resp.status_code} | body: {resp.text[:300]}")
            return None
        data = resp.json()
    except Exception as e:
        print(f"   ❌ Connexion auto erreur: {e}")
        return None

    departures = data.get("departures", [])
    # Filtre sur la destination finale
    candidates = [
        f for f in departures
        if ((f.get("arrival", {}) or {}).get("airport", {}) or {}).get("iata", "").upper()
        == final_iata.upper()
    ]

    if not candidates:
        print(f"   ⚠️  Aucun vol {via_iata}→{final_iata} trouvé")
        return None

    best = candidates[0]
    dep_info = best.get("departure", {}) or {}
    arr_info = best.get("arrival", {}) or {}
    dep_local = ((dep_info.get("scheduledTime") or {}).get("local")
                 or (dep_info.get("scheduledTime") or {}).get("utc", ""))
    arr_local = ((arr_info.get("scheduledTime") or {}).get("local")
                 or (arr_info.get("scheduledTime") or {}).get("utc", ""))
    fn_info = (best.get("number") or "").strip()
    airline_name = (best.get("airline", {}) or {}).get("name", "")

    m = re.match(r'^([A-Z]{2,3})\s*(\d+)$', fn_info.replace(" ", "").upper())
    c, n = (m.group(1), m.group(2)) if m else ("", fn_info)

    result = _build_result(c, n, via_iata, final_iata,
                           _iso_to_hhmm(dep_local), _iso_to_hhmm(arr_local),
                           "aerodatabox_auto")
    result["flight_number"] = fn_info
    if airline_name:
        result["airline"] = airline_name
    print(f"   ✅ Connexion trouvée: {fn_info} {via_iata}({result.get('departure_time')}) → {final_iata}({result.get('arrival_time')})")
    return result


def _try_aerodatabox(carrier: str, number: str, date: str) -> Optional[dict]:
    """
    Appelle l'API AeroDataBox (RapidAPI) pour obtenir les infos du vol.
    Gratuit : 500 req/mois. Fonctionne pour les dates futures.
    Endpoint : GET /flights/number/{flightNumber}/{date}
    """
    api_key = os.environ.get("AERODATABOX_API_KEY", "")
    if not api_key:
        print("   ⚠️  AeroDataBox: clé absente (AERODATABOX_API_KEY)")
        return None

    num_short = str(int(number)) if number.isdigit() else number
    flight_iata = f"{carrier}{num_short}"

    # Avec date spécifique
    url = f"https://aerodatabox.p.rapidapi.com/flights/number/{flight_iata}/{date}"
    headers = {
        "x-rapidapi-key": api_key,
        "x-rapidapi-host": "aerodatabox.p.rapidapi.com",
        "Content-Type": "application/json",
    }
    params = {
        "withAircraftImage": "false",
        "withLocation": "false",
        "withFlightPlan": "false",
    }
    print(f"   🔎 AeroDataBox: {flight_iata} / {date}")

    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code == 404:
            print(f"   ⚠️  AeroDataBox: vol {flight_iata} non trouvé pour {date}")
            return None
        if resp.status_code != 200:
            print(f"   ❌ AeroDataBox HTTP {resp.status_code}: {resp.text[:200]}")
            return None
        data = resp.json()
    except Exception as e:
        print(f"   ❌ AeroDataBox erreur réseau: {e}")
        return None

    # La réponse est une liste de segments (1 par tronçon)
    if not data:
        print(f"   ⚠️  AeroDataBox: réponse vide")
        return None

    segments = data if isinstance(data, list) else [data]

    # Premier segment = départ réel
    first = segments[0]
    # Dernier segment = arrivée finale (destination)
    last = segments[-1]

    dep_info = first.get("departure", {}) or {}
    arr_info = last.get("arrival", {}) or {}

    dep_iata = (dep_info.get("airport", {}) or {}).get("iata", "")
    arr_iata = (arr_info.get("airport", {}) or {}).get("iata", "")

    dep_local = ((dep_info.get("scheduledTime", {}) or {}).get("local")
                 or (dep_info.get("scheduledTime", {}) or {}).get("utc", ""))
    arr_local = ((arr_info.get("scheduledTime", {}) or {}).get("local")
                 or (arr_info.get("scheduledTime", {}) or {}).get("utc", ""))

    dep_time = _iso_to_hhmm(dep_local)
    arr_time = _iso_to_hhmm(arr_local)

    airline_info = first.get("airline", {}) or {}
    airline_name = airline_info.get("name", "")

    # Escales : tous les aéroports intermédiaires
    stopovers = []
    for seg in segments[:-1]:
        via_iata = ((seg.get("arrival", {}) or {}).get("airport", {}) or {}).get("iata", "")
        if via_iata and via_iata not in (dep_iata, arr_iata):
            stopovers.append(via_iata)

    stops = len(stopovers)

    if not dep_iata or not arr_iata:
        print(f"   ⚠️  AeroDataBox: IATA manquants — {json.dumps(first)[:300]}")
        return None

    via_str = f" via {', '.join(stopovers)}" if stopovers else ""
    print(f"   ✅ AeroDataBox: {dep_iata}({dep_time}) → {arr_iata}({arr_time}){via_str}  [{airline_name}]")

    result = _build_result(carrier, number, dep_iata, arr_iata, dep_time, arr_time,
                           "aerodatabox", stops=stops)
    if airline_name:
        result["airline"] = airline_name
    if stopovers:
        result["stopovers"] = stopovers  # ex: ["DXB"]
    return result


# ──────────────────────────────────────────────────────────────
# SOURCE 2 — MisterFly (Playwright, fallback)
# ──────────────────────────────────────────────────────────────
def _scrape_misterfly(carrier: str, number: str, date: str,
                      dep: str, arr: str) -> Optional[dict]:
    """
    Scrape MisterFly en attendant que le numéro de vol apparaisse dans le DOM.
    URL: https://www.misterfly.com/vol/{DEP}-{ARR}/{YYYY-MM-DD}
    """
    url = f"https://www.misterfly.com/vol/{dep}-{arr}/{date}"
    print(f"   🔎 MisterFly: {url}")

    num_int = str(int(number)) if number.isdigit() else number
    flight_variants = [
        f"{carrier}{number}", f"{carrier}{num_int}",
        f"{carrier} {number}", f"{carrier} {num_int}",
    ]
    js_check = " || ".join(
        f"document.body.innerText.includes('{v}')" for v in flight_variants
    )

    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent=(
                    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/122.0.0.0 Safari/537.36"
                ),
                locale="fr-FR",
                viewport={"width": 1280, "height": 900},
            )
            page = ctx.new_page()
            try:
                page.goto(url, timeout=40000, wait_until="domcontentloaded")
            except Exception as e:
                print(f"   ⚠️  MisterFly goto: {e}")

            # Attendre que le numéro de vol apparaisse (max 25s)
            try:
                page.wait_for_function(js_check, timeout=25000)
                print(f"   ✅ Vol trouvé dans le DOM MisterFly")
            except Exception:
                print(f"   ⚠️  MisterFly timeout — extraction quand même")

            page.wait_for_timeout(1500)
            html = page.content()
            browser.close()

    except Exception as e:
        print(f"   ❌ MisterFly Playwright: {e}")
        return None

    # Parser le HTML
    full_text = " ".join(html.split())
    if not any(fv.upper() in full_text.upper() for fv in flight_variants):
        print(f"   ⚠️  MisterFly: vol non trouvé dans le HTML")
        return None

    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, "html.parser")
    text = soup.get_text(separator=" ")

    dep_time, arr_time = _extract_times_from_text(text)

    if not dep_time or not arr_time:
        # Cherche dans le snippet autour du numéro de vol
        for fv in flight_variants:
            idx = full_text.upper().find(fv.upper())
            if idx != -1:
                snippet = full_text[max(0, idx - 200):idx + 400]
                dep_time, arr_time = _extract_times_from_text(snippet)
                if dep_time and arr_time:
                    break

    print(f"   ✅ MisterFly: {dep}({dep_time}) → {arr}({arr_time})")
    return _build_result(carrier, number, dep, arr, dep_time, arr_time, "misterfly")


# ──────────────────────────────────────────────────────────────
# API publique
# ──────────────────────────────────────────────────────────────
class FlightWebScraper:
    """
    Source unique : Amadeus Flight Schedule API (production).
    Données IATA officielles, toutes dates futures, toutes compagnies.
    """

    def _enrich_result(self, result: dict, dep_city_hint: str = "", arr_city_hint: str = "") -> dict:
        """Enrichit un résultat de vol avec noms de villes, logo, stopovers."""
        dep_airport = result.get('departure_airport', '')
        arr_airport = result.get('arrival_airport', '')

        dep_city, dep_country = iata_to_city(dep_airport)
        arr_city, arr_country = iata_to_city(arr_airport)
        result['departure_city'] = dep_city or dep_city_hint
        result['departure_country'] = dep_country
        result['arrival_city'] = arr_city or arr_city_hint
        result['arrival_country'] = arr_country

        carrier = result.get('carrier_code', '')
        if carrier:
            result['airline_logo_url'] = f"https://www.gstatic.com/flights/airline_logos/70px/{carrier}.png"

        for stop in result.get('stopovers', []):
            if not stop.get('city'):
                stop['city'], _ = iata_to_city(stop.get('airport', ''))

        return result

    def get_flight_by_number(self, flight_number: str, departure_date: str,
                             dep_hint: str = "", arr_hint: str = "") -> Optional[dict]:
        """
        Recherche un vol par numéro + date.
        Ordre : 1) Duffel (toutes compagnies sauf AF/KL)
                2) Air France / KLM API (fallback si Duffel ne trouve pas)
        dep_hint / arr_hint : noms de villes pour retrouver les codes IATA.
        """
        print(f"\n{'='*60}")
        print(f"✈️  {flight_number} / {departure_date}")
        print(f"{'='*60}")

        dep_iata = city_to_iata(dep_hint) if dep_hint else None
        arr_iata = city_to_iata(arr_hint) if arr_hint else None

        if not dep_iata or not arr_iata:
            print(f"   ⚠️ IATA inconnus (dep={dep_hint}→{dep_iata}, arr={arr_hint}→{arr_iata})")
            return None

        result = None
        carrier = flight_number[:2].upper() if len(flight_number) >= 2 else ''

        # ── 1. Duffel ──────────────────────────────────────────────────
        if carrier not in ('AF', 'KL'):
            # AF/KL absents du catalogue Duffel → on saute directement AFKL
            try:
                from api.duffel_integration import DuffelFlightService
                result = DuffelFlightService().get_flight_by_number(
                    flight_number, departure_date, origin=dep_iata, destination=arr_iata
                )
            except Exception as e:
                print(f"   ❌ Duffel exception: {e}")

        # ── 2. Air France / KLM API (fallback) ─────────────────────────
        if not result and carrier in ('AF', 'KL'):
            print(f"   🔄 Fallback AFKL pour {carrier}...")
            try:
                from api.airfrance_klm_integration import AFKLFlightService
                result = AFKLFlightService().get_flight_by_number(
                    flight_number, departure_date, origin=dep_iata, destination=arr_iata
                )
            except Exception as e:
                print(f"   ❌ AFKL exception: {e}")
                import traceback
                traceback.print_exc()

        # ── 3. Fallback route Duffel (vol spécifique introuvable = codeshare, etc.) ──
        if not result and dep_iata and arr_iata:
            print(f"   🔄 Vol {flight_number} introuvable — fallback recherche route {dep_iata}→{arr_iata}")
            try:
                from api.duffel_integration import DuffelFlightService
                route_offers = DuffelFlightService().search_flights(
                    dep_iata, arr_iata, departure_date, max_results=1
                )
                if route_offers:
                    result = route_offers[0]
                    result['flight_number_requested'] = flight_number  # garder trace
                    result['found_by_route'] = True
                    print(f"   ℹ️ Meilleur vol disponible sur la route: {result.get('flight_number')}")
            except Exception as e:
                print(f"   ❌ Fallback route exception: {e}")

        if not result:
            print(f"   ❌ Vol {flight_number} non trouvé sur aucune source")
            return None

        result = self._enrich_result(result, dep_hint, arr_hint)

        via_str = f" via {', '.join(s['airport'] for s in result.get('stopovers', []))}" if result.get('stopovers') else ""
        print(f"\n✅ {dep_iata}({result.get('departure_time','?')}) → {arr_iata}({result.get('arrival_time','?')}){via_str}  [{result.get('source')}]")
        if result.get('stops'):
            print(f"   {result['stops']} escale(s) détectée(s)")
        return result

    def search_by_route(self, dep_city: str, arr_city: str, departure_date: str,
                        cabin_class: str = "", max_options: int = 3) -> Optional[list]:
        """
        Recherche Duffel par itinéraire (sans numéro de vol).
        Retourne une liste de jusqu'à max_options vols enrichis (triés par durée).
        """
        print(f"\n{'='*60}")
        print(f"🔍  Duffel route search: {dep_city} → {arr_city} / {departure_date}")
        print(f"{'='*60}")

        dep_iata = city_to_iata(dep_city) if dep_city else None
        arr_iata = city_to_iata(arr_city) if arr_city else None

        if not dep_iata or not arr_iata:
            print(f"   ❌ Codes IATA non trouvés : '{dep_city}'→{dep_iata}, '{arr_city}'→{arr_iata}")
            return None

        print(f"   IATA : {dep_iata} → {arr_iata}")

        try:
            from api.duffel_integration import DuffelFlightService
            service = DuffelFlightService()
            offers = service.search_flights(dep_iata, arr_iata, departure_date,
                                            cabin_class=cabin_class or 'eco',
                                            max_results=max_options)
        except Exception as e:
            print(f"   ❌ Duffel exception: {e}")
            import traceback
            traceback.print_exc()
            return None

        if not offers:
            print(f"   ❌ Aucune offre {dep_iata}→{arr_iata}")
            return None

        results = []
        for offer in offers:
            enriched = self._enrich_result(offer, dep_city, arr_city)
            if cabin_class:
                enriched['cabin_class'] = cabin_class
            results.append(enriched)

        for i, r in enumerate(results, 1):
            stops = r.get('stops', 0)
            via = ', '.join(s['airport'] for s in r.get('stopovers', []))
            print(f"   {i}. {r.get('flight_number')} {r.get('airline')} {r.get('departure_time')}→{r.get('arrival_time')} ({r.get('duration')}) stops={stops}{' via '+via if via else ''}")

        return results
