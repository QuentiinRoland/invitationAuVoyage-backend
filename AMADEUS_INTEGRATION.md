# 🚀 Intégration Amadeus - Guide complet

## 📋 Vue d'ensemble

Ce document explique comment utiliser l'API Amadeus pour récupérer des informations de vols dans ton application.

---

## 🔑 Configuration

### 1. Obtenir les credentials Amadeus

1. Va sur [https://developers.amadeus.com/](https://developers.amadeus.com/)
2. Crée un compte (gratuit)
3. Crée une nouvelle application
4. Récupère ton `API Key` et `API Secret`

### 2. Configurer dans Django

Ajoute dans ton fichier `.env` :

```bash
# Amadeus API (pour les vols)
AMADEUS_API_KEY=your_api_key_here
AMADEUS_API_SECRET=your_api_secret_here
```

Ajoute dans `backend/config/settings.py` :

```python
# Amadeus API
AMADEUS_API_KEY = os.environ.get('AMADEUS_API_KEY', '')
AMADEUS_API_SECRET = os.environ.get('AMADEUS_API_SECRET', '')
```

### 3. Installer les dépendances

Pas besoin de package supplémentaire ! Le code utilise juste `requests` qui est déjà installé.

---

## 💻 Utilisation

### Mode 2 : Recherche par numéro de vol + date (RECOMMANDÉ)

C'est le mode le plus simple pour tes utilisateurs !

#### Exemple de code

```python
from api.amadeus_integration import AmadeusFlightService

# Initialiser le service (use_test=True pour l'environnement de test)
amadeus = AmadeusFlightService(use_test=True)

# Rechercher un vol par numéro + date
flight_info = amadeus.get_flight_by_number(
    flight_number="AF001",
    departure_date="2025-11-18"
)

if flight_info:
    print(f"Vol trouvé: {flight_info['flight_number']}")
    print(f"Départ: {flight_info['departure_airport']} à {flight_info['departure_time']}")
    print(f"Arrivée: {flight_info['arrival_airport']} à {flight_info['arrival_time']}")
    print(f"Durée: {flight_info['duration']}")
    print(f"Escales: {flight_info['stops']}")
else:
    print("Vol non trouvé")
```

#### Structure de retour

```python
{
    'flight_number': 'AF001',
    'carrier_code': 'AF',
    'departure_airport': 'CDG',
    'arrival_airport': 'JFK',
    'departure_time': '10:30',              # Format HH:MM
    'arrival_time': '13:45',                # Format HH:MM
    'departure_datetime_full': '2025-11-18T10:30:00',  # ISO 8601
    'arrival_datetime_full': '2025-11-18T13:45:00',    # ISO 8601
    'duration': '8h15',
    'aircraft_type': 'Boeing 777-300ER',
    'terminal_departure': '2E',
    'terminal_arrival': '1',
    'stops': 0,                             # 0 = direct, 1+ = avec escales
    'source': 'amadeus_flight_status'
}
```

---

### Mode alternatif : Recherche avec prix

Si tu veux aussi récupérer les prix et voir plusieurs options :

```python
from api.amadeus_integration import AmadeusFlightService

amadeus = AmadeusFlightService(use_test=True)

# Rechercher des offres avec prix
offers = amadeus.search_flights(
    origin="CDG",
    destination="JFK",
    departure_date="2025-11-18",
    adults=1,
    return_date="2025-11-25"  # Optionnel
)

if offers:
    for offer in offers:
        print(f"Vol: {offer['flight_number']}")
        print(f"Prix: {offer['price']} {offer['currency']}")
        print(f"Durée: {offer['duration']}")
        print("---")
```

---

## 🔧 Intégration dans views.py

### Option 1 : Remplacer l'ancienne fonction Air France-KLM

Dans `backend/api/views.py`, trouve la fonction `_search_flights_with_airfrance_klm()` et remplace-la par :

```python
def _search_flights_with_amadeus(self, origin_code, destination_code, travel_date, return_date=None, search_metadata=None, flight_number=None):
    """
    Recherche de vols avec l'API Amadeus.
    
    Args:
        origin_code: Code IATA de l'aéroport de départ (ex: 'CDG')
        destination_code: Code IATA de l'aéroport de destination (ex: 'JFK')
        travel_date: Date de voyage au format YYYY-MM-DD
        return_date: Date de retour au format YYYY-MM-DD (optionnel)
        search_metadata: Dict pour stocker les métadonnées de recherche
        flight_number: Si fourni, recherche ce vol spécifique (Mode 2)
    
    Returns:
        Liste de dicts avec les infos des vols
    """
    from api.amadeus_integration import AmadeusFlightService
    
    try:
        amadeus = AmadeusFlightService(use_test=True)
        
        # MODE 2 : Si un numéro de vol est fourni, recherche directe
        if flight_number:
            print(f"🎯 Mode 2: Recherche du vol {flight_number}")
            flight_info = amadeus.get_flight_by_number(flight_number, travel_date)
            
            if flight_info:
                # Si date de retour et numéro de vol retour fourni aussi
                flights = [flight_info]
                
                if search_metadata is not None:
                    search_metadata['source'] = 'amadeus_flight_status'
                    search_metadata['real_flights_count'] = len(flights)
                
                return flights
            else:
                if search_metadata is not None:
                    search_metadata['failure_reason'] = ['flight_not_found']
                return None
        
        # MODE CLASSIQUE : Recherche par origine/destination
        else:
            print(f"🔍 Mode classique: Recherche {origin_code} → {destination_code}")
            offers = amadeus.search_flights(
                origin=origin_code,
                destination=destination_code,
                departure_date=travel_date,
                adults=1,
                return_date=return_date
            )
            
            if offers:
                if search_metadata is not None:
                    search_metadata['source'] = 'amadeus_flight_offers'
                    search_metadata['real_flights_count'] = len(offers)
                
                return offers
            else:
                if search_metadata is not None:
                    search_metadata['failure_reason'] = ['no_offers_found']
                return None
    
    except ValueError as e:
        # Credentials manquants
        print(f"❌ Erreur de configuration: {str(e)}")
        if search_metadata is not None:
            search_metadata['failure_reason'] = ['credentials_missing']
        return None
    
    except Exception as e:
        print(f"❌ Erreur Amadeus: {str(e)}")
        if search_metadata is not None:
            search_metadata['failure_reason'] = ['api_error']
        return None
```

### Option 2 : Ajouter un paramètre pour choisir l'API

Tu peux garder les deux et choisir dynamiquement :

```python
# Dans la vue principale (generate_offer ou similaire)
use_amadeus = request.data.get('use_amadeus', True)  # True par défaut
flight_number = request.data.get('flight_number', None)

if use_amadeus:
    real_flights_data = self._search_flights_with_amadeus(
        origin_code,
        destination_code,
        travel_date,
        return_date,
        search_metadata,
        flight_number=flight_number
    )
else:
    # Garder l'ancienne méthode en fallback
    real_flights_data = self._search_flights_with_airfrance_klm(
        origin_code,
        destination_code,
        travel_date,
        return_date,
        search_metadata
    )
```

---

## 🎨 Exemple UX Frontend

Voici comment adapter ton frontend pour le Mode 2 :

```typescript
// Dans ton composant de saisie de vol
const [flightMode, setFlightMode] = useState<'manual' | 'flight_number'>('flight_number');
const [flightNumber, setFlightNumber] = useState('');
const [departureDate, setDepartureDate] = useState('');

const handleSearchFlight = async () => {
  if (flightMode === 'flight_number') {
    // Mode 2 : Juste numéro + date
    const response = await fetch('/api/flights/search', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        flight_number: flightNumber,
        departure_date: departureDate,
        use_amadeus: true
      })
    });
    
    const data = await response.json();
    // Afficher les infos du vol trouvé
    if (data.flight_info) {
      setFlightInfo(data.flight_info);
    }
  }
};

// UI
<div>
  <label>Mode de saisie</label>
  <select value={flightMode} onChange={(e) => setFlightMode(e.target.value)}>
    <option value="flight_number">Numéro de vol (recommandé)</option>
    <option value="manual">Saisie manuelle</option>
  </select>
  
  {flightMode === 'flight_number' && (
    <>
      <input 
        type="text" 
        placeholder="Ex: AF001" 
        value={flightNumber}
        onChange={(e) => setFlightNumber(e.target.value)}
      />
      <input 
        type="date" 
        value={departureDate}
        onChange={(e) => setDepartureDate(e.target.value)}
      />
      <button onClick={handleSearchFlight}>Rechercher</button>
    </>
  )}
</div>
```

---

## 💰 Coûts Amadeus

### Environnement TEST (gratuit)
- ✅ Illimité pendant le développement
- ✅ Données de test (vols fictifs mais structure réelle)
- 🔑 Utilise `use_test=True` dans le code

### Environnement PRODUCTION
- **Flight Status API** : ~€0.005 par appel (0.5 centime)
- **Flight Offers Search API** : ~€0.35 par appel
- Plan gratuit : 10 000 appels/mois

**Estimation pour 1000 offres/mois :**
- 1000 offres × 2 vols (aller/retour) = 2000 appels
- 2000 × €0.005 = **~€10/mois** (avec Flight Status)
- 2000 × €0.35 = **~€700/mois** (avec Flight Offers Search)

**💡 Recommandation :** Utilise Flight Status (Mode 2) pour les infos basiques, et laisse l'utilisateur saisir le prix manuellement. Tu économises 99% des coûts !

---

## 🧪 Tester l'intégration

### Test rapide en shell Django

```bash
cd backend
python manage.py shell
```

```python
from api.amadeus_integration import AmadeusFlightService

# Créer le service
amadeus = AmadeusFlightService(use_test=True)

# Tester un vol
result = amadeus.get_flight_by_number("AF001", "2025-11-18")
print(result)
```

### Exemples de vols pour tester (environnement TEST)

Les vols ci-dessous existent dans l'environnement de test Amadeus :

- `AF001` - CDG → JFK (Air France)
- `BA123` - LHR → JFK (British Airways)
- `LH400` - FRA → JFK (Lufthansa)

---

## ❓ FAQ

### Q: Quelle est la différence entre TEST et PRODUCTION ?

**TEST** :
- Données fictives mais structure réelle
- Gratuit et illimité
- Parfait pour le développement
- URL: `https://test.api.amadeus.com`

**PRODUCTION** :
- Données réelles en temps réel
- Coût par appel (mais plan gratuit disponible)
- URL: `https://api.amadeus.com`

### Q: Comment passer de TEST à PRODUCTION ?

Simplement changer :

```python
# DEV
amadeus = AmadeusFlightService(use_test=True)

# PRODUCTION
amadeus = AmadeusFlightService(use_test=False)
```

Ou mieux, dans settings.py :

```python
AMADEUS_USE_TEST = os.environ.get('AMADEUS_USE_TEST', 'True') == 'True'
```

### Q: Et si l'utilisateur se trompe de numéro de vol ?

L'API Amadeus retourne simplement `None` et tu peux afficher un message :

```python
flight_info = amadeus.get_flight_by_number("AF999999", "2025-11-18")
if not flight_info:
    return Response({
        'error': 'Vol non trouvé. Vérifiez le numéro de vol et la date.'
    }, status=404)
```

### Q: Peut-on rechercher plusieurs vols en même temps ?

Oui ! Fais juste plusieurs appels :

```python
outbound = amadeus.get_flight_by_number("AF001", "2025-11-18")
return_flight = amadeus.get_flight_by_number("AF002", "2025-11-25")

flights = {
    'outbound': outbound,
    'return': return_flight
}
```

---

## 🚀 Prochaines étapes

1. ✅ Ajouter les credentials dans `.env`
2. ✅ Tester en shell Django
3. ✅ Intégrer dans `views.py`
4. ✅ Adapter le frontend pour le Mode 2
5. ✅ Tester avec de vrais numéros de vol
6. ✅ Passer en production quand prêt

---

## 📞 Support

- **Documentation Amadeus** : https://developers.amadeus.com/self-service/apis-docs
- **Support Amadeus** : https://developers.amadeus.com/support
- **Ton fichier d'intégration** : `backend/api/amadeus_integration.py`

Bon courage ! 🎯


