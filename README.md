# 🐍 Backend Django - Invitation au Voyage

API REST pour la génération et gestion d'offres de voyage.

## 🚀 Démarrage rapide

### Prérequis

- Python 3.11+
- PostgreSQL (pour la production) ou SQLite (pour le développement)
- OpenAI API Key

### Installation locale

```bash
# 1. Créer un environnement virtuel
python3 -m venv venv
source venv/bin/activate  # Sur Windows: venv\Scripts\activate

# 2. Installer les dépendances
pip install -r requirements.txt

# 3. Installer Playwright pour la génération PDF
playwright install chromium

# 4. Configurer les variables d'environnement
cp env.example .env
# Éditez .env et ajoutez vos clés API

# 5. Appliquer les migrations
python manage.py migrate

# 6. Créer un superutilisateur
python manage.py createsuperuser

# 7. Lancer le serveur
python manage.py runserver
```

L'API est accessible sur `http://localhost:8000/api/`

---

## 📦 Structure du projet

```
backend/
├── api/                      # Application principale
│   ├── models.py            # Modèles de données
│   ├── serializers.py       # Serializers DRF
│   ├── views.py             # Vues de l'API
│   ├── auth_views.py        # Authentification
│   ├── document_views.py    # Gestion des documents
│   ├── services.py          # Logique métier
│   └── urls.py              # Routes de l'API
├── config/                   # Configuration Django
│   ├── settings.py          # Paramètres du projet
│   ├── urls.py              # URLs principales
│   └── wsgi.py              # Point d'entrée WSGI
├── build.sh                 # Script de build pour Render
├── gunicorn.render.conf.py  # Config Gunicorn pour Render
├── requirements.txt         # Dépendances Python
└── manage.py                # CLI Django
```

---

## 🔧 Configuration

### Variables d'environnement

Créez un fichier `.env` à la racine du dossier `backend/` :

```bash
# Django
SECRET_KEY=votre-clé-secrète-très-longue-et-aléatoire
DEBUG=True

# Database (vide = SQLite en local)
DATABASE_URL=

# APIs
OPENAI_API_KEY=sk-votre-clé-openai
UNSPLASH_ACCESS_KEY=votre-clé-unsplash (optionnel)
BING_IMAGE_SUBSCRIPTION_KEY=votre-clé-bing (optionnel)
```

### Base de données

**Développement (SQLite)** : Laissez `DATABASE_URL` vide
**Production (PostgreSQL)** : 
```
DATABASE_URL=postgresql://user:password@host:5432/dbname
```

---

## 🧪 Tests

```bash
# Lancer tous les tests
python manage.py test

# Tests avec couverture
pip install coverage
coverage run manage.py test
coverage report
```

---

## 📝 API Endpoints

### Authentification

```
POST   /api/auth/register/         # Inscription
POST   /api/auth/login/            # Connexion
POST   /api/auth/logout/           # Déconnexion
POST   /api/auth/password-reset/   # Demande de réinitialisation
POST   /api/auth/password-reset-confirm/  # Confirmation
```

### Offres

```
GET    /api/offers/                # Liste des offres
POST   /api/offers/                # Créer une offre
GET    /api/offers/:id/            # Détails d'une offre
PUT    /api/offers/:id/            # Modifier une offre
DELETE /api/offers/:id/            # Supprimer une offre
```

### Documents

```
GET    /api/documents/             # Liste des documents
POST   /api/documents/             # Upload un document
GET    /api/documents/:id/         # Détails d'un document
DELETE /api/documents/:id/         # Supprimer un document
```

### Génération

```
POST   /api/generate/text-to-offer/  # Générer une offre depuis un texte
POST   /api/generate/pdf-to-html/    # Convertir PDF en HTML
POST   /api/generate/export-pdf/     # Exporter en PDF
```

---

## 🚀 Déploiement sur Render

### Vérification pré-déploiement

```bash
python check_render_ready.py
```

### Déploiement automatique

1. Pushez votre code sur GitHub/GitLab
2. Allez sur [Render Dashboard](https://dashboard.render.com/)
3. Créez un nouveau Blueprint depuis votre dépôt
4. Render détectera `render.yaml` automatiquement
5. Configurez `OPENAI_API_KEY` dans les variables d'environnement
6. Cliquez sur "Apply" et attendez le déploiement

Consultez [RENDER_DEPLOYMENT.md](../RENDER_DEPLOYMENT.md) pour le guide complet.

### Déploiement manuel

```bash
# Sur Render, configurez :
Build Command: chmod +x build.sh && ./build.sh
Start Command: gunicorn config.wsgi:application -c gunicorn.render.conf.py
```

---

## 🔍 Commandes utiles

```bash
# Créer les migrations
python manage.py makemigrations

# Appliquer les migrations
python manage.py migrate

# Créer un superutilisateur
python manage.py createsuperuser

# Collecter les fichiers statiques
python manage.py collectstatic

# Lancer un shell Django
python manage.py shell

# Lancer des tests
python manage.py test

# Vérifier les problèmes
python manage.py check

# Lancer le serveur de dev
python manage.py runserver

# Lancer avec Gunicorn (comme en prod)
gunicorn config.wsgi:application -c gunicorn.render.conf.py
```

---

## 🐛 Dépannage

### Erreur d'import de modules

```bash
# Vérifiez que vous êtes dans le bon environnement virtuel
which python  # Doit pointer vers venv/bin/python
pip list      # Vérifiez les packages installés
```

### Erreur de base de données

```bash
# Supprimez la base SQLite et recréez-la
rm db.sqlite3
python manage.py migrate
python manage.py createsuperuser
```

### Erreur Playwright

```bash
# Réinstallez Playwright
playwright install chromium --with-deps
```

### Erreur de permissions

```bash
# Donnez les permissions d'exécution
chmod +x build.sh
chmod +x manage.py
```

---

## 📚 Technologies utilisées

- **Django 5.2** - Framework web
- **Django REST Framework** - API REST
- **PostgreSQL** - Base de données (production)
- **SQLite** - Base de données (développement)
- **Gunicorn** - Serveur WSGI
- **WhiteNoise** - Fichiers statiques
- **OpenAI API** - Génération de contenu
- **Playwright** - Génération de PDF
- **PyMuPDF** - Manipulation de PDF
- **Pillow** - Traitement d'images

---

## 📖 Documentation

- [Guide de déploiement Render](../RENDER_DEPLOYMENT.md)
- [Guide rapide Render](../RENDER_QUICKSTART.md)
- [Documentation Django](https://docs.djangoproject.com/)
- [Documentation DRF](https://www.django-rest-framework.org/)

---

## 🤝 Contribution

1. Créez une branche pour votre feature : `git checkout -b feature/ma-feature`
2. Committez vos changements : `git commit -m "Ajout de ma feature"`
3. Pushez vers la branche : `git push origin feature/ma-feature`
4. Ouvrez une Pull Request

---

## 📄 Licence

Ce projet est sous licence MIT.

---

## 🆘 Support

Si vous rencontrez des problèmes :

1. Consultez la section [Dépannage](#dépannage) ci-dessus
2. Vérifiez les logs : `python manage.py runserver` (en local) ou les logs Render (en production)
3. Consultez la [documentation Render](https://render.com/docs/deploy-django)

---

Bon développement ! 🚀


