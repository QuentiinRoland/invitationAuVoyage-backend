# ⚡ Amadeus - Quick Start Guide

Guide ultra-rapide pour mettre en place Amadeus en **5 minutes**.

---

## 🚀 Étape 1 : Obtenir les credentials (2 min)

1. Va sur **https://developers.amadeus.com/**
2. Clique sur **"Sign In"** ou **"Register"**
3. Une fois connecté, clique sur **"Create new app"**
4. Donne un nom à ton app (ex: "InvitationAuVoyage")
5. Tu reçois immédiatement :
   - **API Key** (ex: `vFdj3kL9mQ2xR7yT1wN8`)
   - **API Secret** (ex: `pA5sS9wO3rD2fG7h`)

---

## 🔑 Étape 2 : Configurer Django (30 sec)

Ouvre `backend/.env` et ajoute :

```bash
# Amadeus API
AMADEUS_API_KEY=colle_ta_key_ici
AMADEUS_API_SECRET=colle_ton_secret_ici
```

Ouvre `backend/config/settings.py` et ajoute (si pas déjà fait) :

```python
# Amadeus API
AMADEUS_API_KEY = os.environ.get('AMADEUS_API_KEY', '')
AMADEUS_API_SECRET = os.environ.get('AMADEUS_API_SECRET', '')
AMADEUS_USE_TEST = os.environ.get('AMADEUS_USE_TEST', 'True') == 'True'
```

---

## 🧪 Étape 3 : Tester (1 min)

Lance le script de test :

```bash
cd backend
python test_amadeus.py
```

Tu devrais voir :

```
✅ PASSED - Credentials
✅ PASSED - Token
⚠️  SKIPPED - Flight by number (Mode 2)
⚠️  SKIPPED - Flight search with price
✅ PASSED - Date formats
✅ PASSED - Flight number parsing
```

Les tests "SKIPPED" sont normaux en environnement TEST (données limitées).

---

## 💻 Étape 4 : Intégrer dans views.py (1 min)

Ouvre `backend/api/views.py` et ajoute en haut :

```python
from api.amadeus_integration import AmadeusFlightService
```

Copie-colle cette fonction dans ta classe de vue :

```python
def _search_flights_with_amadeus(self, origin_code, destination_code, travel_date, 
                                  return_date=None, search_metadata=None, 
                                  flight_number_outbound=None, flight_number_return=None):
    """Recherche de vols avec Amadeus (Mode 2 supporté)"""
    from api.amadeus_integration import AmadeusFlightService
    from django.conf import settings
    
    try:
        use_test = getattr(settings, 'AMADEUS_USE_TEST', True)
        amadeus = AmadeusFlightService(use_test=use_test)
        
        flights = []
        
        # MODE 2: Recherche par numéro de vol
        if flight_number_outbound:
            outbound = amadeus.get_flight_by_number(flight_number_outbound, travel_date)
            if outbound:
                flights.append(outbound)
            
            if flight_number_return and return_date:
                return_flight = amadeus.get_flight_by_number(flight_number_return, return_date)
                if return_flight:
                    flights.append(return_flight)
            
            if flights:
                if search_metadata:
                    search_metadata['source'] = 'amadeus_flight_status'
                    search_metadata['real_flights_count'] = len(flights)
                return flights
        
        # MODE CLASSIQUE: Recherche par origine/destination
        else:
            offers = amadeus.search_flights(origin_code, destination_code, travel_date, 1, return_date)
            if offers:
                if search_metadata:
                    search_metadata['source'] = 'amadeus_flight_offers'
                    search_metadata['real_flights_count'] = len(offers)
                return offers
        
        return None
    
    except Exception as e:
        print(f"❌ Erreur Amadeus: {str(e)}")
        if search_metadata:
            search_metadata['failure_reason'] = ['api_error']
        return None
```

Dans ta vue `generate_offer()`, remplace l'appel à `_search_flights_with_airfrance_klm()` par :

```python
# Nouveau paramètres depuis le frontend
flight_number_outbound = request.data.get('flight_number_outbound')
flight_number_return = request.data.get('flight_number_return')

# Appel à Amadeus
real_flights_data = self._search_flights_with_amadeus(
    origin_code,
    destination_code,
    travel_date,
    return_date,
    search_metadata,
    flight_number_outbound=flight_number_outbound,
    flight_number_return=flight_number_return
)
```

---

## 🎨 Étape 5 : Adapter le Frontend (30 sec)

Dans ton composant de génération d'offre, ajoute ces champs :

```typescript
// État
const [flightNumberOutbound, setFlightNumberOutbound] = useState('');
const [flightNumberReturn, setFlightNumberReturn] = useState('');

// Dans le formulaire
<div>
  <label>Vol aller (optionnel)</label>
  <input 
    placeholder="Ex: AF001" 
    value={flightNumberOutbound}
    onChange={(e) => setFlightNumberOutbound(e.target.value)}
  />
</div>

<div>
  <label>Vol retour (optionnel)</label>
  <input 
    placeholder="Ex: AF002" 
    value={flightNumberReturn}
    onChange={(e) => setFlightNumberReturn(e.target.value)}
  />
</div>

// Dans la requête
const response = await fetch('/api/generate-offer/', {
  method: 'POST',
  body: JSON.stringify({
    // ... tes paramètres existants
    flight_number_outbound: flightNumberOutbound || undefined,
    flight_number_return: flightNumberReturn || undefined,
  })
});
```

---

## ✅ C'est tout !

Tu peux maintenant :

### Mode 2 (Recommandé) :
L'utilisateur saisit juste :
- `AF001` + date `18/11/2025`

Le système récupère automatiquement :
- ✅ Aéroports (CDG → JFK)
- ✅ Horaires exacts (10:30 - 14:45)
- ✅ Durée (8h15)
- ✅ Terminaux (2E → 1)
- ✅ Type d'avion (Boeing 777)
- ✅ Escales (0 = direct)

### Mode classique :
Recherche par `CDG → JFK` + date → Liste des vols avec prix

---

## 💰 Coûts estimés

Pour **1000 offres/mois** avec 2 vols (aller/retour) :

- **Mode 2** (Flight Status) : ~**€10/mois**
- Mode classique (Flight Offers) : ~€700/mois

→ **Recommandation : Mode 2** pour économiser 99% des coûts !

---

## 📚 Documentation complète

- **Guide complet** : `AMADEUS_INTEGRATION.md`
- **Exemples de code** : `INTEGRATION_VIEWS_EXAMPLE.py`
- **Tests** : `python test_amadeus.py`
- **Code source** : `api/amadeus_integration.py`

---

## 🆘 Problèmes fréquents

### "Credentials manquants"
→ Vérifie que `.env` contient bien `AMADEUS_API_KEY` et `AMADEUS_API_SECRET`

### "401 Unauthorized"
→ Tes credentials sont invalides, vérifie-les sur le portail Amadeus

### "Vol non trouvé" en TEST
→ Normal, l'environnement TEST contient peu de vols. Essaie avec des vols courants (AF001, BA123, LH400)

### "Vol non trouvé" en PRODUCTION
→ Le numéro de vol ou la date sont incorrects, ou le vol n'existe pas ce jour-là

---

## 🎯 Prochaines étapes

1. ✅ Configure les credentials
2. ✅ Lance `python test_amadeus.py`
3. ✅ Intègre dans `views.py`
4. ✅ Adapte le frontend
5. ✅ Teste avec de vrais numéros de vol
6. 🚀 Passe en production !

Bon courage ! 🎉


