# 🎯 Intégration de la Recherche Intelligente de Vols

## 📋 Vue d'ensemble

Le système de **recherche intelligente** combine :
1. **Parser** qui comprend plein de formats (GDS, numéro de vol, texte libre)
2. **Amadeus** qui recherche les vols réels
3. **Matching intelligent** qui trouve les vols correspondants

---

## ✅ Formats supportés

| Format | Exemple | Ce qui est extrait |
|--------|---------|-------------------|
| **GDS avec retour** ⭐ | `18NOV-25NOV BRU JFK 10:00 14:00` | Dates, aéroports, horaires |
| **GDS simple** | `18NOV BRU JFK 10:00 14:00` | Date, aéroports, horaires |
| **Numéro de vol** | `AF001` | Numéro de vol |
| **Numéro + date** | `AF001 18/11/2025` | Numéro + date |
| **Texte libre** | `Vol AF001 de Paris à NY le 18/11` | Extraction intelligente |

---

## 💻 Utilisation dans views.py

### Option 1 : Remplacement complet (RECOMMANDÉ)

Remplace ta fonction `_search_flights_with_airfrance_klm()` par :

```python
def _search_flights_smart(self, user_input, search_metadata=None):
    """
    Recherche intelligente de vols depuis n'importe quel format d'input.
    
    Args:
        user_input: Texte saisi par l'utilisateur (format libre)
        search_metadata: Dict pour stocker les métadonnées
    
    Returns:
        Liste de dicts avec les vols trouvés
    """
    from api.smart_flight_search import SmartFlightSearch
    from django.conf import settings
    
    try:
        use_test = getattr(settings, 'AMADEUS_USE_TEST', True)
        smart_search = SmartFlightSearch(use_test=use_test)
        
        result = smart_search.search(user_input)
        
        if search_metadata is not None:
            search_metadata['parsed_data'] = result['parsed_data']
            search_metadata['search_strategy'] = result['search_strategy']
            search_metadata['source'] = 'smart_search'
            
            if result['flights_found']:
                search_metadata['real_flights_count'] = len(result['flights_found'])
        
        return result['flights_found']
    
    except Exception as e:
        print(f"❌ Erreur recherche intelligente: {str(e)}")
        if search_metadata:
            search_metadata['failure_reason'] = ['smart_search_error']
        return None
```

---

### Option 2 : Ajout à côté de l'existant

Garde ta fonction actuelle et ajoute :

```python
def _search_flights_smart(self, user_input, search_metadata=None):
    """Version intelligente avec parsing automatique"""
    # ... (code ci-dessus)

def _search_flights_with_amadeus(self, origin, destination, date, ...):
    """Version classique avec paramètres explicites"""
    # ... (ton code existant)
```

Et dans `generate_offer()`, choisis selon le contexte :

```python
# Si l'utilisateur colle du texte (format GDS, etc.)
if 'flight_input' in request.data:
    real_flights_data = self._search_flights_smart(
        request.data['flight_input'],
        search_metadata
    )

# Sinon, méthode classique
elif origin_code and destination_code:
    real_flights_data = self._search_flights_with_amadeus(
        origin_code,
        destination_code,
        travel_date,
        return_date,
        search_metadata
    )
```

---

## 🎨 Adaptation du Frontend

### UX Recommandée : Champ unique intelligent

```typescript
<div>
  <label>Infos de vol (format libre)</label>
  <input 
    type="text"
    placeholder="Ex: 18NOV-25NOV BRU JFK 10:00 14:00 ou AF001 18/11/2025"
    value={flightInput}
    onChange={(e) => setFlightInput(e.target.value)}
  />
  <small className="hint">
    Formats acceptés : GDS, numéro de vol, texte libre
  </small>
</div>
```

### Requête

```typescript
const response = await fetch('/api/generate-offer/', {
  method: 'POST',
  headers: { 'Content-Type': 'application/json' },
  body: JSON.stringify({
    text: offerDescription,
    flight_input: flightInput,  // ← Nouveau champ
    // ... autres paramètres
  })
});
```

---

## 🔄 Stratégies de recherche

Le système choisit automatiquement la meilleure stratégie :

### 1. `flight_number`

**Quand :** Numéro de vol + date fournis

**Exemple :** `AF001 18/11/2025`

**Action :** Recherche directe via Amadeus Flight Status API

**Résultat :** 1 vol précis avec toutes les infos

---

### 2. `origin_destination`

**Quand :** Origine + destination + date (sans numéro de vol)

**Exemple :** `18NOV BRU JFK 10:00 14:00`

**Action :** Recherche via Amadeus Flight Offers + filtrage par horaire

**Résultat :** 3-5 vols proches de l'horaire demandé

---

### 3. `manual_complete`

**Quand :** Format GDS avec toutes les infos

**Exemple :** `18NOV BRU JFK 10:00 14:00` (si pas de recherche API voulue)

**Action :** Utilisation directe des infos parsées

**Résultat :** Infos extraites sans appel API

---

### 4. `manual_partial`

**Quand :** Infos incomplètes

**Exemple :** `AF001` (sans date)

**Action :** Retourne les infos disponibles

**Résultat :** Infos partielles, demande de compléter

---

## 📊 Exemples de réponses

### Format GDS → Recherche Amadeus

**Input :** `18NOV-25NOV BRU JFK 10:00 14:00`

**Réponse :**

```json
{
  "success": true,
  "message": "3 vol(s) trouvé(s)",
  "search_strategy": "origin_destination",
  "parsed_data": {
    "format": "gds",
    "departure_date": "2025-11-18",
    "return_date": "2025-11-25",
    "origin_airport": "BRU",
    "destination_airport": "JFK",
    "departure_time": "10:00",
    "arrival_time": "14:00"
  },
  "flights_found": [
    {
      "flight_number": "SK594",
      "departure_airport": "BRU",
      "arrival_airport": "JFK",
      "departure_time": "10:20",
      "arrival_time": "15:45",
      "duration": "8h25",
      "stops": 0,
      "source": "amadeus_flight_offers"
    }
  ]
}
```

---

### Numéro de vol → Recherche directe

**Input :** `AF001 18/11/2025`

**Réponse :**

```json
{
  "success": true,
  "message": "1 vol(s) trouvé(s)",
  "search_strategy": "flight_number",
  "flights_found": [
    {
      "flight_number": "AF001",
      "carrier_code": "AF",
      "departure_airport": "JFK",
      "arrival_airport": "CDG",
      "departure_time": "16:30",
      "arrival_time": "05:45",
      "duration": "7h15",
      "stops": 0,
      "terminal_departure": "1",
      "terminal_arrival": "2E",
      "source": "amadeus_flight_status"
    }
  ]
}
```

---

## 🧪 Tester

### En shell Django

```bash
cd backend
source venv/bin/activate
python manage.py shell
```

```python
from api.smart_flight_search import SmartFlightSearch

smart_search = SmartFlightSearch(use_test=True)

# Test format GDS
result = smart_search.search("18NOV-25NOV BRU JFK 10:00 14:00")
print(result['message'])
print(f"Vols trouvés: {len(result['flights_found'])}")

# Test numéro de vol
result = smart_search.search("AF001 18/11/2025")
print(result['flights_found'][0]['flight_number'])
```

---

### Via le script de test

```bash
python test_smart_search.py
```

---

## 💰 Coûts

Identiques à Amadeus standard :

| Stratégie | API utilisée | Coût par recherche |
|-----------|--------------|-------------------|
| `flight_number` | Flight Status | ~€0.005 |
| `origin_destination` | Flight Offers | ~€0.35 |
| `manual_complete` | Aucune | **Gratuit** ⭐ |
| `manual_partial` | Aucune | **Gratuit** ⭐ |

**Recommandation :** Utilise le format GDS complet pour éviter les coûts API si tu as déjà toutes les infos !

---

## 🎯 Avantages

✅ **UX simplifiée** : Un seul champ pour tout

✅ **Formats multiples** : GDS, numéro de vol, texte libre

✅ **Matching intelligent** : Trouve les vols proches des horaires demandés

✅ **Coût optimisé** : Utilise direct les infos si complètes (pas d'API call)

✅ **Compatible** : Fonctionne avec ton code existant

---

## 📝 Checklist d'intégration

- [ ] Parser testé : `python api/flight_parser.py`
- [ ] Recherche intelligente testée : `python test_smart_search.py`
- [ ] Fonction `_search_flights_smart()` ajoutée dans views.py
- [ ] Frontend adapté avec champ `flight_input`
- [ ] Tests d'intégration OK
- [ ] Prêt à déployer ! 🚀

---

## 🆘 Besoin d'aide ?

- **Parser seul** : `backend/api/flight_parser.py`
- **Recherche intelligente** : `backend/api/smart_flight_search.py`
- **Tests** : `backend/test_smart_search.py`
- **Doc Amadeus** : `backend/AMADEUS_INTEGRATION.md`

Bon courage ! 🎉


