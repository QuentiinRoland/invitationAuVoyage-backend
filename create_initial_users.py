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

INITIAL_USERS = [
    {"username": "denis",    "email": "denis@invit.be",    "password": "admin123!", "first_name": "Denis"},
    {"username": "sandrine", "email": "sandrine@invit.be", "password": "admin123!", "first_name": "Sandrine"},
    {"username": "maite",    "email": "maite@invit.be",    "password": "admin123!", "first_name": "Maïté"},
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
