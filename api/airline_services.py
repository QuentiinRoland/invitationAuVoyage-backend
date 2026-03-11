"""
Base de données statique des services compagnies aériennes.
Source : sites officiels des compagnies (politique bagages, services à bord).
Utilisé pour pré-remplir les informations sans les inventer.
"""

AIRLINE_SERVICES = {
    'AF': {
        'name': 'Air France',
        'country': 'France',
        'alliance': 'SkyTeam',
        'source_url': 'https://www.airfrance.fr',
        'baggage': {
            'cabin': {
                'economy': '1 bagage cabine (12 kg max, 55×35×25 cm) + 1 sac à main',
                'premium_economy': '1 bagage cabine (18 kg max, 55×35×25 cm) + 1 sac à main',
                'business': '2 bagages cabine (18 kg max chacun, 55×35×25 cm) + 1 sac à main',
                'first': '2 bagages cabine (18 kg max chacun, 55×35×25 cm) + 1 sac à main',
            },
            'checked': {
                'economy': '1 bagage en soute (23 kg max)',
                'premium_economy': '2 bagages en soute (23 kg max chacun)',
                'business': '2 bagages en soute (32 kg max chacun)',
                'first': '3 bagages en soute (32 kg max chacun)',
            },
            'extra_bag_fee': 'À partir de 60€ par bagage supplémentaire (selon la route)',
            'overweight_fee': '100€ par bagage dépassant le poids autorisé',
        },
        'meals': {
            'economy': 'Repas chaud inclus sur les vols long-courriers (>3h30). Collations sur vols moyen-courriers.',
            'premium_economy': 'Repas gastronomique avec choix de menus',
            'business': 'Gastronomie française — menu élaboré par des chefs, service à la carte',
            'first': 'Gastronomie haute couture, service à volonté',
        },
        'entertainment': {
            'long_haul': 'Système AVOD individuel : films, séries, documentaires, musique, jeux (écran 9 à 17 pouces selon classe)',
            'short_haul': 'Application Air France Play (téléchargement avant vol) sur appareils personnels',
        },
        'wifi': {
            'available': True,
            'details': 'Disponible sur la majorité des vols long-courriers (forfaits payants : 4,99€/heure ou 19,99€/vol)',
        },
        'seats': {
            'economy': 'Siège standard inclinable, tablette personnelle, prise USB et secteur',
            'premium_economy': 'Siège plus large et inclinable (160°), repose-pieds, écran 13"',
            'business': 'Siège-lit à plat (180°), intimité renforcée, écran 17"',
            'first': 'Suite privée, lit à plat, accès salon CDG La Première',
        },
        'lounge': {
            'economy': "Pas d'accès salon (sauf avec carte Flying Blue Platinum ou Gold)",
            'business': 'Accès Salon Air France (CDG Business lounge)',
            'first': 'Accès Salon La Première (CDG Terminal 2E)',
        },
        'frequent_flyer': 'Flying Blue (programme de fidélité Air France-KLM)',
    },

    'KL': {
        'name': 'KLM Royal Dutch Airlines',
        'country': 'Pays-Bas',
        'alliance': 'SkyTeam',
        'source_url': 'https://www.klm.com',
        'baggage': {
            'cabin': {
                'economy': '1 bagage cabine (12 kg max, 55×35×25 cm) + 1 sac à main',
                'business': '2 bagages cabine (12 kg max chacun)',
            },
            'checked': {
                'economy': '1 bagage en soute (23 kg max)',
                'business': '2 bagages en soute (32 kg max chacun)',
            },
            'extra_bag_fee': 'À partir de 60€ par bagage supplémentaire',
            'overweight_fee': '100€ par bagage dépassant le poids autorisé',
        },
        'meals': {
            'economy': 'Repas chaud inclus sur vols long-courriers, snack sur vols moyen-courriers',
            'business': 'Menu gastronomique inspiré de la cuisine néerlandaise et internationale',
        },
        'entertainment': {
            'long_haul': 'Système AVOD : films, séries, musique, jeux (écran personnel)',
            'short_haul': 'Application KLM sur appareils personnels',
        },
        'wifi': {
            'available': True,
            'details': 'Disponible sur vols long-courriers (forfaits payants)',
        },
        'seats': {
            'economy': 'Siège standard, prise USB',
            'business': 'Siège-lit à plat (180°), écran personnel',
        },
        'frequent_flyer': 'Flying Blue (programme de fidélité Air France-KLM)',
    },

    'BA': {
        'name': 'British Airways',
        'country': 'Royaume-Uni',
        'alliance': 'Oneworld',
        'source_url': 'https://www.britishairways.com',
        'baggage': {
            'cabin': {
                'economy': '1 bagage cabine (23 kg max, 56×45×25 cm) sur vols long-courriers',
                'business': '2 bagages cabine (23 kg max chacun)',
            },
            'checked': {
                'economy': '1 bagage en soute (23 kg max) inclus sur la plupart des tarifs',
                'business': '2 bagages en soute (32 kg max chacun)',
                'first': '3 bagages en soute (32 kg max chacun)',
            },
            'extra_bag_fee': 'Variable selon la route et le tarif',
        },
        'meals': {
            'economy': 'Repas inclus sur vols long-courriers, achat à bord sur vols courts',
            'business': 'Club Kitchen — repas raffinés à la demande',
            'first': 'Service gastronomique personnalisé',
        },
        'entertainment': {
            'long_haul': 'Système Highlife : films, séries, musique, jeux (écran individuel)',
        },
        'wifi': {
            'available': True,
            'details': 'Disponible sur la majorité des vols long-courriers (forfaits payants)',
        },
        'seats': {
            'economy': 'Siège World Traveller, prise USB',
            'business': 'Siège-lit Club Suite à plat (180°)',
            'first': 'Suite privée First',
        },
        'frequent_flyer': 'Avios (British Airways Executive Club)',
    },

    'LH': {
        'name': 'Lufthansa',
        'country': 'Allemagne',
        'alliance': 'Star Alliance',
        'source_url': 'https://www.lufthansa.com',
        'baggage': {
            'cabin': {
                'economy': '1 bagage cabine (8 kg max, 55×40×23 cm)',
                'business': '2 bagages cabine (8 kg max chacun)',
            },
            'checked': {
                'economy': '1 bagage en soute (23 kg max) selon tarif',
                'business': '2 bagages en soute (32 kg max chacun)',
                'first': '3 bagages en soute (32 kg max chacun)',
            },
            'extra_bag_fee': 'Variable selon la route',
        },
        'meals': {
            'economy': 'Repas chaud sur vols long-courriers',
            'business': 'Menu gastronomique élaboré',
            'first': 'Service First Class, cuisine de chef',
        },
        'entertainment': {
            'long_haul': 'Système FlyNet : films, séries, musique (écran individuel)',
        },
        'wifi': {
            'available': True,
            'details': 'FlyNet Wi-Fi disponible (forfaits payants)',
        },
        'seats': {
            'economy': 'Siège Economy standard, prise USB',
            'business': 'Siège-lit à plat Business',
            'first': 'Suite privée First Class',
        },
        'frequent_flyer': 'Miles & More',
    },

    'IB': {
        'name': 'Iberia',
        'country': 'Espagne',
        'alliance': 'Oneworld',
        'source_url': 'https://www.iberia.com',
        'baggage': {
            'cabin': {
                'economy': '1 bagage cabine (10 kg max, 56×45×25 cm)',
                'business': '2 bagages cabine (10 kg max chacun)',
            },
            'checked': {
                'economy': '1 bagage en soute (23 kg max) selon tarif',
                'business': '2 bagages en soute (32 kg max chacun)',
            },
            'extra_bag_fee': 'Variable selon la route',
        },
        'meals': {
            'economy': 'Repas inclus sur vols long-courriers',
            'business': 'Menu gastronomique espagnol',
        },
        'entertainment': {
            'long_haul': 'Système IFE : films, séries, musique, jeux',
        },
        'wifi': {
            'available': True,
            'details': 'Disponible sur vols long-courriers (forfaits payants)',
        },
        'seats': {
            'economy': 'Siège Economy, prise USB',
            'business': 'Siège-lit à plat',
        },
        'frequent_flyer': 'Iberia Plus',
    },

    'EK': {
        'name': 'Emirates',
        'country': 'Émirats arabes unis',
        'alliance': 'Non-aligné',
        'source_url': 'https://www.emirates.com',
        'baggage': {
            'cabin': {
                'economy': '1 bagage cabine (7 kg max)',
                'business': '2 bagages cabine (7 kg max chacun)',
                'first': '2 bagages cabine (7 kg max chacun)',
            },
            'checked': {
                'economy': '35 kg (poids total en soute)',
                'business': '40 kg (poids total en soute)',
                'first': '50 kg (poids total en soute)',
            },
            'extra_bag_fee': 'Variable selon la route',
        },
        'meals': {
            'economy': 'Repas chauds inclus avec choix de menus',
            'business': 'Dîner à la demande — menu gastronomique',
            'first': 'Cuisine à la carte, bar privé',
        },
        'entertainment': {
            'long_haul': 'ice Digital Widescreen : +4 500 chaînes (films, séries, musique, jeux)',
        },
        'wifi': {
            'available': True,
            'details': 'Disponible sur tous les vols (forfaits payants)',
        },
        'seats': {
            'economy': 'Siège Economy avec écran personnel 13,3"',
            'business': 'Siège-lit à plat avec écran 23"',
            'first': 'Suite privée, lit à plat, douche disponible sur A380',
        },
        'frequent_flyer': 'Skywards',
    },

    'QR': {
        'name': 'Qatar Airways',
        'country': 'Qatar',
        'alliance': 'Oneworld',
        'source_url': 'https://www.qatarairways.com',
        'baggage': {
            'cabin': {
                'economy': '1 bagage cabine (7 kg max)',
                'business': '2 bagages cabine (7 kg max chacun)',
            },
            'checked': {
                'economy': '30 kg (poids total en soute)',
                'business': '40 kg (poids total en soute)',
                'first': '50 kg (poids total en soute)',
            },
            'extra_bag_fee': 'Variable selon la route',
        },
        'meals': {
            'economy': 'Repas chauds inclus avec choix de menus',
            'business': 'Menu gastronomique Qsuite',
        },
        'entertainment': {
            'long_haul': 'Oryx One : +4 000 chaînes (films, séries, musique, jeux)',
        },
        'wifi': {
            'available': True,
            'details': 'Super Wi-Fi disponible (forfaits payants)',
        },
        'seats': {
            'economy': 'Siège Economy, prise USB et secteur',
            'business': 'Qsuite — suite privée à plat (180°)',
        },
        'frequent_flyer': 'Privilege Club',
    },

    'SN': {
        'name': 'Brussels Airlines',
        'country': 'Belgique',
        'alliance': 'Star Alliance',
        'source_url': 'https://www.brusselsairlines.com',
        'baggage': {
            'cabin': {
                'economy': '1 bagage cabine (8 kg max, 55×40×23 cm)',
                'business': '2 bagages cabine (8 kg max chacun)',
            },
            'checked': {
                'economy': '1 bagage en soute (23 kg max) selon tarif',
                'business': '2 bagages en soute (32 kg max chacun)',
            },
            'extra_bag_fee': 'Variable selon la route et le tarif',
        },
        'meals': {
            'economy': 'Repas inclus sur vols long-courriers, snack sur courts-courriers',
            'business': 'Menu gastronomique sélection belge',
        },
        'entertainment': {
            'long_haul': 'Système IFE individuel : films, séries, musique',
        },
        'wifi': {
            'available': True,
            'details': 'Disponible sur vols long-courriers',
        },
        'seats': {
            'economy': 'Siège Economy standard',
            'business': 'Siège-lit à plat',
        },
        'frequent_flyer': 'Miles & More (Star Alliance)',
    },

    'U2': {
        'name': 'easyJet',
        'country': 'Royaume-Uni',
        'alliance': 'Non-aligné (low-cost)',
        'source_url': 'https://www.easyjet.com',
        'baggage': {
            'cabin': {
                'standard': '1 petit sac à main (45×36×20 cm, sous le siège avant)',
                'plus': '1 bagage cabine (56×45×25 cm, 15 kg max) + petit sac',
            },
            'checked': {
                'standard': 'Pas de bagage en soute inclus (option payante, à partir de 13,49€)',
            },
            'extra_bag_fee': 'À partir de 13,49€ par bagage en soute (23 kg max)',
        },
        'meals': {
            'all': 'Achat à bord uniquement (pas de repas inclus)',
        },
        'entertainment': {
            'all': 'Pas de système de divertissement intégré (Wi-Fi limité)',
        },
        'wifi': {
            'available': False,
            'details': 'Non disponible sur la majorité des vols easyJet',
        },
        'seats': {
            'standard': 'Siège standard (attribution aléatoire sauf option payante)',
            'extra_legroom': 'Siège Speedy Boarding avec espace supplémentaire (payant)',
        },
        'frequent_flyer': 'easyJet Plus (abonnement)',
    },

    'FR': {
        'name': 'Ryanair',
        'country': 'Irlande',
        'alliance': 'Non-aligné (low-cost)',
        'source_url': 'https://www.ryanair.com',
        'baggage': {
            'cabin': {
                'standard': '1 petit sac (40×20×25 cm, sous le siège avant uniquement)',
                'priority': '1 bagage cabine (55×40×20 cm, 10 kg max) + petit sac',
            },
            'checked': {
                'standard': 'Pas de bagage en soute inclus (option payante, à partir de 10€)',
            },
            'extra_bag_fee': 'À partir de 10€ par bagage en soute (20 kg max)',
        },
        'meals': {
            'all': 'Achat à bord uniquement (pas de repas inclus)',
        },
        'entertainment': {
            'all': 'Pas de système de divertissement intégré',
        },
        'wifi': {
            'available': False,
            'details': 'Non disponible sur les vols Ryanair',
        },
        'seats': {
            'standard': 'Siège standard (attribution payante)',
        },
        'frequent_flyer': 'myRyanair',
    },
}


def get_airline_services(carrier_code: str) -> dict:
    """
    Retourne les services d'une compagnie aérienne par son code IATA.
    Retourne None si la compagnie n'est pas dans la base.
    """
    return AIRLINE_SERVICES.get(carrier_code.upper())


def format_airline_services_for_prompt(carrier_code: str) -> str:
    """
    Formate les services d'une compagnie pour injection dans un prompt LLM.
    """
    services = get_airline_services(carrier_code)
    if not services:
        return ""

    lines = [
        f"\n\n✈️ SERVICES OFFICIELS {services['name'].upper()} (source : {services['source_url']}) :",
        f"Compagnie : {services['name']} | Alliance : {services['alliance']}",
        "",
        "📦 BAGAGES (politique officielle) :",
    ]

    baggage = services.get('baggage', {})
    cabin = baggage.get('cabin', {})
    checked = baggage.get('checked', {})

    for cls, info in cabin.items():
        lines.append(f"  Cabine {cls} : {info}")
    for cls, info in checked.items():
        lines.append(f"  Soute {cls} : {info}")
    if baggage.get('extra_bag_fee'):
        lines.append(f"  Bagage supplémentaire : {baggage['extra_bag_fee']}")
    if baggage.get('overweight_fee'):
        lines.append(f"  Surpoids : {baggage['overweight_fee']}")

    lines.append("")
    lines.append("🍽️ REPAS À BORD :")
    for cls, info in services.get('meals', {}).items():
        lines.append(f"  {cls.capitalize()} : {info}")

    ent = services.get('entertainment', {})
    if ent:
        lines.append("")
        lines.append("🎬 DIVERTISSEMENT :")
        for scope, info in ent.items():
            lines.append(f"  {scope} : {info}")

    wifi = services.get('wifi', {})
    if wifi:
        lines.append("")
        avail = "Disponible" if wifi.get('available') else "Non disponible"
        lines.append(f"📶 WI-FI : {avail} — {wifi.get('details', '')}")

    seats = services.get('seats', {})
    if seats:
        lines.append("")
        lines.append("💺 SIÈGES :")
        for cls, info in seats.items():
            lines.append(f"  {cls.capitalize()} : {info}")

    ff = services.get('frequent_flyer')
    if ff:
        lines.append("")
        lines.append(f"🏆 PROGRAMME DE FIDÉLITÉ : {ff}")

    lines.append("")
    lines.append("🚨 RÈGLE : Utilise UNIQUEMENT ces informations officielles pour les sections Bagages et Services.")
    lines.append("Pour tout champ non listé ci-dessus, écris 'À confirmer avec la compagnie.'")

    return "\n".join(lines)
