"""
Parser intelligent pour différents formats de saisie de vols.
Supporte les formats GDS, numéros de vol simples, etc.
"""

import re
from datetime import datetime
from typing import Optional, Dict, List, Tuple


class FlightInputParser:
    """Parse différents formats de saisie de vols"""
    
    # Mois en format GDS (JAN, FEB, etc.)
    MONTH_MAP = {
        'JAN': 1, 'FEB': 2, 'MAR': 3, 'APR': 4, 'MAY': 5, 'JUN': 6,
        'JUL': 7, 'AUG': 8, 'SEP': 9, 'OCT': 10, 'NOV': 11, 'DEC': 12
    }
    
    @classmethod
    def parse(cls, input_text: str, default_year: Optional[int] = None) -> Optional[Dict]:
        """
        Parse un texte de vol et retourne les infos extraites.
        
        Formats supportés:
        1. Format GDS: "18NOV BRU JFK 10:00 14:00"
        2. Format GDS avec retour: "18NOV-25NOV BRU JFK 10:00 14:00"
        3. Numéro de vol simple: "AF001"
        4. Numéro de vol avec date: "AF001 18/11/2025"
        5. Format libre: "Vol AF001 de Paris à New York le 18/11"
        
        Args:
            input_text: Texte saisi par l'utilisateur
            default_year: Année par défaut (si non spécifiée, année courante)
        
        Returns:
            Dict avec les infos extraites ou None si format non reconnu
        """
        if not input_text:
            return None
        
        input_text = input_text.strip()
        
        # Essayer chaque format dans l'ordre
        parsers = [
            cls._parse_gds_format,
            cls._parse_flight_number_format,
            cls._parse_free_text_format,
        ]
        
        for parser in parsers:
            result = parser(input_text, default_year)
            if result:
                return result
        
        return None
    
    @classmethod
    def _parse_gds_format(cls, text: str, default_year: Optional[int] = None) -> Optional[Dict]:
        """
        Parse le format GDS: "18NOV BRU JFK 10:00 14:00" ou "18NOV-25NOV BRU JFK 10:00 14:00"
        
        Format:
        - [DATE_DEPART][-DATE_RETOUR] [ORIGINE] [DESTINATION] [HEURE_DEP] [HEURE_ARR]
        - Exemple: "18NOV-25NOV BRU JFK 10:00 14:00"
        """
        # Pattern pour format GDS complet
        # Groupe 1: Date départ (18NOV)
        # Groupe 2: Date retour optionnelle (25NOV)
        # Groupe 3: Aéroport origine (BRU)
        # Groupe 4: Aéroport destination (JFK)
        # Groupe 5: Heure départ (10:00)
        # Groupe 6: Heure arrivée (14:00)
        pattern = r'(\d{2}[A-Z]{3})(?:-(\d{2}[A-Z]{3}))?\s+([A-Z]{3})\s+([A-Z]{3})\s+(\d{1,2}:\d{2})\s+(\d{1,2}:\d{2})'
        
        match = re.search(pattern, text.upper())
        if not match:
            return None
        
        dep_date_str = match.group(1)  # 18NOV
        ret_date_str = match.group(2)  # 25NOV ou None
        origin = match.group(3)        # BRU
        destination = match.group(4)   # JFK
        dep_time = match.group(5)      # 10:00
        arr_time = match.group(6)      # 14:00
        
        # Parser les dates
        year = default_year or datetime.now().year
        dep_date = cls._parse_gds_date(dep_date_str, year)
        ret_date = cls._parse_gds_date(ret_date_str, year) if ret_date_str else None
        
        if not dep_date:
            return None
        
        return {
            'format': 'gds',
            'departure_date': dep_date.strftime('%Y-%m-%d'),
            'return_date': ret_date.strftime('%Y-%m-%d') if ret_date else None,
            'origin_airport': origin,
            'destination_airport': destination,
            'departure_time': cls._normalize_time(dep_time),
            'arrival_time': cls._normalize_time(arr_time),
            'flight_number': None,  # Pas de numéro de vol dans ce format
            'source': 'gds_format'
        }
    
    @classmethod
    def _parse_flight_number_format(cls, text: str, default_year: Optional[int] = None) -> Optional[Dict]:
        """
        Parse le format numéro de vol: "AF001" ou "AF001 18/11/2025" ou "AF001 18NOV"
        """
        text_upper = text.upper()
        
        # Pattern pour numéro de vol (2 lettres + 1-4 chiffres)
        flight_pattern = r'\b([A-Z]{2})(\d{1,4})\b'
        flight_match = re.search(flight_pattern, text_upper)
        
        if not flight_match:
            return None
        
        carrier_code = flight_match.group(1)
        flight_number = flight_match.group(2)
        full_flight_number = f"{carrier_code}{flight_number}"
        
        # Chercher une date dans le texte
        date = None
        
        # Format DD/MM/YYYY ou DD-MM-YYYY
        date_pattern1 = r'(\d{2})[/-](\d{2})[/-](\d{4})'
        date_match1 = re.search(date_pattern1, text)
        if date_match1:
            day, month, year = date_match1.groups()
            try:
                date = datetime(int(year), int(month), int(day))
            except ValueError:
                pass
        
        # Format GDS (18NOV)
        if not date:
            gds_date_pattern = r'\b(\d{2}[A-Z]{3})\b'
            gds_date_match = re.search(gds_date_pattern, text_upper)
            if gds_date_match:
                year = default_year or datetime.now().year
                date = cls._parse_gds_date(gds_date_match.group(1), year)
        
        return {
            'format': 'flight_number',
            'flight_number': full_flight_number,
            'carrier_code': carrier_code,
            'departure_date': date.strftime('%Y-%m-%d') if date else None,
            'return_date': None,
            'origin_airport': None,
            'destination_airport': None,
            'departure_time': None,
            'arrival_time': None,
            'source': 'flight_number_format'
        }
    
    @classmethod
    def _parse_free_text_format(cls, text: str, default_year: Optional[int] = None) -> Optional[Dict]:
        """
        Parse du texte libre: "Vol AF001 de Paris à New York le 18/11"
        Extrait ce qu'on peut trouver dans le texte.
        """
        result = {
            'format': 'free_text',
            'flight_number': None,
            'departure_date': None,
            'return_date': None,
            'origin_airport': None,
            'destination_airport': None,
            'departure_time': None,
            'arrival_time': None,
            'source': 'free_text_format'
        }
        
        text_upper = text.upper()
        
        # Chercher numéro de vol
        flight_pattern = r'\b([A-Z]{2})(\d{1,4})\b'
        flight_match = re.search(flight_pattern, text_upper)
        if flight_match:
            result['flight_number'] = flight_match.group(0)
            result['carrier_code'] = flight_match.group(1)
        
        # Chercher date
        date_pattern = r'(\d{2})[/-](\d{2})[/-]?(\d{4})?'
        date_match = re.search(date_pattern, text)
        if date_match:
            day, month, year = date_match.groups()
            year = year or str(default_year or datetime.now().year)
            try:
                date = datetime(int(year), int(month), int(day))
                result['departure_date'] = date.strftime('%Y-%m-%d')
            except ValueError:
                pass
        
        # Chercher codes aéroport (3 lettres majuscules)
        airport_pattern = r'\b([A-Z]{3})\b'
        airports = re.findall(airport_pattern, text_upper)
        # Filtrer les codes qui ne sont probablement pas des aéroports
        common_words = ['VOL', 'DES', 'LES', 'UNE', 'PAR', 'SUR', 'AND', 'THE', 'FOR']
        airports = [a for a in airports if a not in common_words]
        
        if len(airports) >= 1:
            result['origin_airport'] = airports[0]
        if len(airports) >= 2:
            result['destination_airport'] = airports[1]
        
        # Chercher horaires
        time_pattern = r'\b(\d{1,2})[h:](\d{2})\b'
        times = re.findall(time_pattern, text)
        if len(times) >= 1:
            result['departure_time'] = f"{times[0][0].zfill(2)}:{times[0][1]}"
        if len(times) >= 2:
            result['arrival_time'] = f"{times[1][0].zfill(2)}:{times[1][1]}"
        
        # Si on n'a trouvé aucune info utile, retourner None
        if not any([result['flight_number'], result['departure_date'], 
                   result['origin_airport'], result['destination_airport']]):
            return None
        
        return result
    
    @classmethod
    def _parse_gds_date(cls, date_str: str, year: int) -> Optional[datetime]:
        """
        Parse une date au format GDS: "18NOV"
        
        Args:
            date_str: Date au format "18NOV"
            year: Année à utiliser
        
        Returns:
            datetime ou None si parsing échoue
        """
        if not date_str or len(date_str) < 5:
            return None
        
        try:
            day = int(date_str[:2])
            month_str = date_str[2:5].upper()
            month = cls.MONTH_MAP.get(month_str)
            
            if not month:
                return None
            
            return datetime(year, month, day)
        except (ValueError, IndexError):
            return None
    
    @classmethod
    def _normalize_time(cls, time_str: str) -> str:
        """
        Normalise un horaire au format HH:MM
        
        Args:
            time_str: "10:00" ou "9:5" ou "10h00"
        
        Returns:
            "10:00" format normalisé
        """
        if not time_str:
            return None
        
        # Remplacer 'h' par ':'
        time_str = time_str.replace('h', ':').replace('H', ':')
        
        # Extraire heures et minutes
        parts = time_str.split(':')
        if len(parts) != 2:
            return None
        
        try:
            hours = int(parts[0])
            minutes = int(parts[1])
            return f"{hours:02d}:{minutes:02d}"
        except ValueError:
            return None
    
    @classmethod
    def format_for_display(cls, parsed_data: Dict) -> str:
        """
        Formate les données parsées pour affichage à l'utilisateur
        """
        if not parsed_data:
            return "Aucune donnée"
        
        lines = []
        
        if parsed_data.get('format') == 'gds':
            lines.append("📋 Format GDS détecté")
        elif parsed_data.get('format') == 'flight_number':
            lines.append("✈️  Format numéro de vol détecté")
        else:
            lines.append("📝 Format libre détecté")
        
        if parsed_data.get('flight_number'):
            lines.append(f"   Vol: {parsed_data['flight_number']}")
        
        if parsed_data.get('departure_date'):
            date_str = parsed_data['departure_date']
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                lines.append(f"   Date départ: {date_obj.strftime('%d/%m/%Y')}")
            except:
                lines.append(f"   Date départ: {date_str}")
        
        if parsed_data.get('return_date'):
            date_str = parsed_data['return_date']
            try:
                date_obj = datetime.strptime(date_str, '%Y-%m-%d')
                lines.append(f"   Date retour: {date_obj.strftime('%d/%m/%Y')}")
            except:
                lines.append(f"   Date retour: {date_str}")
        
        if parsed_data.get('origin_airport'):
            lines.append(f"   Origine: {parsed_data['origin_airport']}")
        
        if parsed_data.get('destination_airport'):
            lines.append(f"   Destination: {parsed_data['destination_airport']}")
        
        if parsed_data.get('departure_time'):
            lines.append(f"   Départ: {parsed_data['departure_time']}")
        
        if parsed_data.get('arrival_time'):
            lines.append(f"   Arrivée: {parsed_data['arrival_time']}")
        
        return "\n".join(lines)


def test_parser():
    """Tests du parser"""
    print("🧪 Tests du parser de vols\n")
    
    test_cases = [
        "18NOV BRU JFK 10:00 14:00",
        "18NOV-25NOV BRU JFK 10:00 14:00",
        "AF001",
        "AF001 18/11/2025",
        "AF001 18NOV",
        "Vol AF001 de Paris à New York le 18/11/2025",
        "18NOV CDG JFK 10h30 14h45",
    ]
    
    for test in test_cases:
        print(f"Input: '{test}'")
        result = FlightInputParser.parse(test)
        if result:
            print(FlightInputParser.format_for_display(result))
        else:
            print("❌ Pas de résultat")
        print()


if __name__ == "__main__":
    test_parser()


