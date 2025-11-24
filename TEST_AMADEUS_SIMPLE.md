# 🧪 Comment tester Amadeus - Guide Simple

## ⚡ Méthode 1 : Script de test automatique (PLUS SIMPLE)

### Étape 1 : Ajouter tes credentials

Ouvre `backend/.env` et ajoute (si pas déjà fait) :

```bash
AMADEUS_API_KEY=ta_key_ici
AMADEUS_API_SECRET=ton_secret_ici
```

**Comment obtenir les credentials ?**
1. Va sur https://developers.amadeus.com/
2. Crée un compte (gratuit)
3. Crée une app
4. Copie API Key + Secret

---

### Étape 2 : Lancer le script de test

```bash
cd backend
python test_amadeus.py
```

**Ce que tu vas voir :**

Si **TES CREDENTIALS SONT VALIDES** :
```
✅ PASSED - Credentials
✅ PASSED - Token
⚠️  SKIPPED - Flight by number (Mode 2)
⚠️  SKIPPED - Flight search with price
✅ PASSED - Date formats
✅ PASSED - Flight number parsing
```

Si **TES CREDENTIALS SONT MANQUANTS** :
```
❌ FAILED - Credentials
```
→ Va ajouter AMADEUS_API_KEY et AMADEUS_API_SECRET dans backend/.env

Si **TES CREDENTIALS SONT INVALIDES** :
```
✅ PASSED - Credentials
❌ FAILED - Token
```
→ Vérifie que tu as bien copié la bonne key et le bon secret

---

## 🐚 Méthode 2 : Test en shell Django (RAPIDE)

### Test 1 : Vérifier la config

```bash
cd backend
python manage.py shell
```

Puis dans le shell :

```python
from django.conf import settings

# Vérifier que les credentials sont chargés
print("API Key:", settings.AMADEUS_API_KEY[:10] if settings.AMADEUS_API_KEY else "❌ Manquant")
print("API Secret:", settings.AMADEUS_API_SECRET[:10] if settings.AMADEUS_API_SECRET else "❌ Manquant")
```

**Résultat attendu :**
```
API Key: vFdj3kL9mQ...
API Secret: pA5sS9wO3r...
```

---

### Test 2 : Tester le Mode 2 (recherche par numéro de vol)

```python
from api.amadeus_integration import AmadeusFlightService

# Créer le service
amadeus = AmadeusFlightService(use_test=True)

# Tester un vol
result = amadeus.get_flight_by_number("AF001", "2025-12-15")

if result:
    print("✅ Vol trouvé!")
    print(f"Route: {result['departure_airport']} → {result['arrival_airport']}")
    print(f"Horaires: {result['departure_time']} - {result['arrival_time']}")
    print(f"Durée: {result['duration']}")
else:
    print("⚠️  Vol non trouvé (normal en environnement TEST)")
```

**Note :** En environnement TEST, les vols disponibles sont limités. C'est normal de ne pas trouver tous les vols.

---

### Test 3 : Tester la recherche avec prix

```python
# Rechercher des offres CDG → JFK
offers = amadeus.search_flights("CDG", "JFK", "2025-12-15", adults=1)

if offers:
    print(f"✅ {len(offers)} offre(s) trouvée(s)")
    for i, offer in enumerate(offers[:3], 1):
        print(f"\nOffre {i}:")
        print(f"  Vol: {offer['flight_number']}")
        print(f"  Route: {offer['departure_airport']} → {offer['arrival_airport']}")
        print(f"  Horaires: {offer['departure_time']} - {offer['arrival_time']}")
        if offer.get('price'):
            print(f"  Prix: {offer['price']} {offer['currency']}")
else:
    print("⚠️  Aucune offre trouvée")
```

---

## 🌐 Méthode 3 : Test via HTTP (DEPUIS LE FRONTEND)

### Étape 1 : Créer un endpoint de test

Ajoute dans `backend/api/views.py` :

```python
from rest_framework.decorators import api_view
from rest_framework.response import Response

@api_view(['POST'])
def test_amadeus(request):
    """Endpoint de test pour Amadeus"""
    from api.amadeus_integration import AmadeusFlightService
    
    flight_number = request.data.get('flight_number', 'AF001')
    date = request.data.get('date', '2025-12-15')
    
    try:
        amadeus = AmadeusFlightService(use_test=True)
        result = amadeus.get_flight_by_number(flight_number, date)
        
        if result:
            return Response({
                'success': True,
                'flight': result
            })
        else:
            return Response({
                'success': False,
                'message': 'Vol non trouvé'
            })
    except Exception as e:
        return Response({
            'success': False,
            'error': str(e)
        }, status=500)
```

### Étape 2 : Ajouter la route

Dans `backend/api/urls.py`, ajoute :

```python
from .views import test_amadeus

urlpatterns = [
    # ... tes routes existantes
    path('test-amadeus/', test_amadeus, name='test_amadeus'),
]
```

### Étape 3 : Tester avec curl ou Postman

```bash
curl -X POST http://localhost:8000/api/test-amadeus/ \
  -H "Content-Type: application/json" \
  -d '{
    "flight_number": "AF001",
    "date": "2025-12-15"
  }'
```

**Réponse attendue :**
```json
{
  "success": true,
  "flight": {
    "flight_number": "AF001",
    "departure_airport": "CDG",
    "arrival_airport": "JFK",
    "departure_time": "10:30",
    "arrival_time": "14:45",
    "duration": "8h15"
  }
}
```

---

## 🔍 Débogage

### Problème : "Credentials manquants"

**Vérification 1 : Le fichier .env existe-t-il ?**
```bash
ls -la backend/.env
```

**Vérification 2 : Les clés sont-elles dans .env ?**
```bash
cat backend/.env | grep AMADEUS
```

Tu dois voir :
```
AMADEUS_API_KEY=...
AMADEUS_API_SECRET=...
```

**Vérification 3 : Django charge-t-il le .env ?**
```python
python manage.py shell
>>> from django.conf import settings
>>> settings.AMADEUS_API_KEY
```

---

### Problème : "401 Unauthorized"

Tes credentials sont invalides. Vérifie :
1. As-tu bien copié la **clé complète** (sans espace) ?
2. As-tu copié le **secret complet** ?
3. Les credentials sont-ils pour le bon environnement (TEST vs PRODUCTION) ?

**Astuce :** Va sur https://developers.amadeus.com/ → My Apps → Clique sur ton app → Copie à nouveau les credentials

---

### Problème : "Vol non trouvé" en environnement TEST

**C'est NORMAL !** L'environnement TEST d'Amadeus contient peu de vols fictifs.

**Solutions :**
1. Essaie avec d'autres vols courants : AF001, BA123, LH400
2. Utilise des dates dans le futur (pas trop loin, genre +2 mois)
3. Passe en environnement PRODUCTION pour tester avec de vrais vols :
   ```python
   amadeus = AmadeusFlightService(use_test=False)  # ⚠️ Attention aux coûts !
   ```

---

## ✅ Checklist de test

Coche au fur et à mesure :

- [ ] Credentials Amadeus obtenus sur https://developers.amadeus.com/
- [ ] AMADEUS_API_KEY ajouté dans backend/.env
- [ ] AMADEUS_API_SECRET ajouté dans backend/.env
- [ ] `python test_amadeus.py` lancé → Tests PASSED
- [ ] Test en shell Django → Vol trouvé ou "pas trouvé" normal en TEST
- [ ] (Optionnel) Endpoint HTTP créé et testé
- [ ] Prêt à intégrer dans views.py !

---

## 🎯 Prochaine étape

Une fois que les tests passent, suis le guide `AMADEUS_INTEGRATION.md` pour intégrer dans ton code.

Bon courage ! 🚀


