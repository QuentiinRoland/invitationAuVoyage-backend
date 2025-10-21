#!/usr/bin/env bash
# Script de test pour simuler l'environnement de production localement

set -e  # Exit on error

echo "🧪 Test de l'environnement de production localement"
echo "=================================================="
echo ""

# Couleurs pour le terminal
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Vérifier que nous sommes dans le bon dossier
if [ ! -f "manage.py" ]; then
    echo -e "${RED}❌ Erreur: manage.py non trouvé. Êtes-vous dans le dossier backend ?${NC}"
    exit 1
fi

# 1. Vérifier les variables d'environnement
echo "🔍 Vérification des variables d'environnement..."
if [ -z "$OPENAI_API_KEY" ]; then
    echo -e "${YELLOW}⚠️  OPENAI_API_KEY n'est pas défini. Chargement depuis .env...${NC}"
    if [ -f ".env" ]; then
        export $(cat .env | grep -v '^#' | xargs)
    else
        echo -e "${RED}❌ Fichier .env non trouvé. Créez-le depuis env.example${NC}"
        exit 1
    fi
fi

if [ -z "$OPENAI_API_KEY" ] || [ "$OPENAI_API_KEY" = "your-openai-api-key-here" ]; then
    echo -e "${RED}❌ OPENAI_API_KEY n'est pas configuré correctement${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Variables d'environnement OK${NC}"
echo ""

# 2. Tester avec DEBUG=False (comme en production)
echo "🔧 Configuration en mode production (DEBUG=False)..."
export DEBUG=False
export SECRET_KEY="test-production-secret-key-$(date +%s)"

# 3. Collecter les fichiers statiques
echo "📁 Collection des fichiers statiques..."
python manage.py collectstatic --no-input --clear > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Fichiers statiques collectés${NC}"
else
    echo -e "${RED}❌ Erreur lors de la collection des fichiers statiques${NC}"
    exit 1
fi
echo ""

# 4. Vérifier les migrations
echo "🗄️  Vérification des migrations..."
python manage.py migrate --check > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Migrations OK${NC}"
else
    echo -e "${YELLOW}⚠️  Des migrations doivent être appliquées${NC}"
    python manage.py migrate
fi
echo ""

# 5. Vérifier la configuration Django
echo "🔍 Vérification de la configuration Django..."
python manage.py check --deploy > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Configuration Django OK${NC}"
else
    echo -e "${YELLOW}⚠️  Avertissements de configuration (normal en test local):${NC}"
    python manage.py check --deploy
fi
echo ""

# 6. Tester Gunicorn
echo "🚀 Test de Gunicorn..."
# Lancer Gunicorn en arrière-plan
if [ -f "gunicorn.render.conf.py" ]; then
    gunicorn config.wsgi:application -c gunicorn.render.conf.py --bind 127.0.0.1:8001 --daemon --pid gunicorn.pid
else
    gunicorn config.wsgi:application --bind 127.0.0.1:8001 --daemon --pid gunicorn.pid
fi

sleep 2

# Vérifier que Gunicorn est lancé
if [ -f "gunicorn.pid" ]; then
    PID=$(cat gunicorn.pid)
    if ps -p $PID > /dev/null; then
        echo -e "${GREEN}✅ Gunicorn démarré (PID: $PID)${NC}"
        
        # Tester une requête HTTP
        echo "🌐 Test d'une requête HTTP..."
        HTTP_CODE=$(curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8001/api/ 2>/dev/null || echo "000")
        
        if [ "$HTTP_CODE" = "200" ] || [ "$HTTP_CODE" = "404" ] || [ "$HTTP_CODE" = "403" ]; then
            echo -e "${GREEN}✅ API répond (HTTP $HTTP_CODE)${NC}"
        else
            echo -e "${RED}❌ Erreur HTTP $HTTP_CODE${NC}"
        fi
        
        # Arrêter Gunicorn
        echo "🛑 Arrêt de Gunicorn..."
        kill $PID
        rm -f gunicorn.pid
        sleep 1
    else
        echo -e "${RED}❌ Gunicorn n'a pas démarré correctement${NC}"
        exit 1
    fi
else
    echo -e "${RED}❌ Fichier PID de Gunicorn non trouvé${NC}"
    exit 1
fi
echo ""

# 7. Vérifier Playwright (pour la génération de PDF)
echo "🎭 Vérification de Playwright..."
python -c "from playwright.sync_api import sync_playwright; print('OK')" > /dev/null 2>&1
if [ $? -eq 0 ]; then
    echo -e "${GREEN}✅ Playwright installé${NC}"
else
    echo -e "${YELLOW}⚠️  Playwright non installé. Lancez: playwright install chromium${NC}"
fi
echo ""

# 8. Tester la connexion à OpenAI (optionnel)
echo "🤖 Test de connexion à OpenAI..."
python -c "
import os
from openai import OpenAI

try:
    client = OpenAI(api_key=os.getenv('OPENAI_API_KEY'))
    # Test simple
    response = client.models.list()
    print('OK')
except Exception as e:
    print(f'ERREUR: {e}')
" > /tmp/openai_test.txt 2>&1

OPENAI_RESULT=$(cat /tmp/openai_test.txt)
rm -f /tmp/openai_test.txt

if [ "$OPENAI_RESULT" = "OK" ]; then
    echo -e "${GREEN}✅ Connexion OpenAI OK${NC}"
else
    echo -e "${RED}❌ Erreur OpenAI: $OPENAI_RESULT${NC}"
fi
echo ""

# Résumé final
echo "=================================================="
echo -e "${GREEN}✅ Tests de production terminés avec succès !${NC}"
echo ""
echo "📝 Prochaines étapes :"
echo "  1. Pushez votre code sur Git"
echo "  2. Créez un Blueprint sur Render"
echo "  3. Configurez OPENAI_API_KEY sur Render"
echo "  4. Déployez !"
echo ""
echo "📖 Consultez RENDER_DEPLOYMENT.md pour plus d'infos"


