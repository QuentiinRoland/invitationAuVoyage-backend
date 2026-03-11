#!/usr/bin/env python
"""
Script pour créer les utilisateurs initiaux de l'application.
Appelé au démarrage via start.sh — crée les users s'ils n'existent pas.
"""
import os
import django

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token
from api.models import Folder

INITIAL_USERS = [
    {"username": "denis",    "email": "denis@invit.be",    "password": "admin123!", "first_name": "Denis"},
    {"username": "sandrine", "email": "sandrine@invit.be", "password": "admin123!", "first_name": "Sandrine"},
    {"username": "maite",    "email": "maite@invit.be",    "password": "admin123!", "first_name": "Maïté"},
]

DEFAULT_FOLDERS = [
    {"name": "Dossier de Denis",    "color": "#3B82F6", "icon": "👤", "position": 0, "username": "denis"},
    {"name": "Dossier de Sandrine", "color": "#10B981", "icon": "👤", "position": 1, "username": "sandrine"},
    {"name": "Dossier de Maïté",    "color": "#F59E0B", "icon": "👤", "position": 2, "username": "maite"},
    {"name": "Dossier Commun",      "color": "#8B5CF6", "icon": "📂", "position": 3, "username": "denis"},
]

for u in INITIAL_USERS:
    user, created = User.objects.get_or_create(
        username=u["username"],
        defaults={"email": u["email"], "first_name": u.get("first_name", "")},
    )
    if created:
        user.set_password(u["password"])
        user.save()
        token, _ = Token.objects.get_or_create(user=user)
        print(f"✅ Utilisateur créé : {u['email']}")
    else:
        print(f"ℹ️  Utilisateur existant : {user.email}")

# Créer les dossiers par défaut s'ils n'existent pas
for f in DEFAULT_FOLDERS:
    try:
        owner = User.objects.get(username=f["username"])
        folder, created = Folder.objects.get_or_create(
            name=f["name"],
            owner=owner,
            defaults={"color": f["color"], "icon": f["icon"], "position": f["position"], "parent": None},
        )
        if created:
            print(f"✅ Dossier créé : {f['name']}")
        else:
            print(f"ℹ️  Dossier existant : {f['name']}")
    except User.DoesNotExist:
        print(f"⚠️  User {f['username']} introuvable, dossier {f['name']} non créé")
