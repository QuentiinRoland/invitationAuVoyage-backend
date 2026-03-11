#!/usr/bin/env python
"""
Script pour créer automatiquement un superuser Django
Utilise les variables d'environnement pour les credentials
"""
import os
import django

# Configuration Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')
django.setup()

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

User = get_user_model()

# Récupérer les credentials depuis les variables d'environnement
username = os.getenv('DJANGO_SUPERUSER_USERNAME', 'admin')
email = os.getenv('DJANGO_SUPERUSER_EMAIL', 'admin@invitationauvoyage.com')
password = os.getenv('DJANGO_SUPERUSER_PASSWORD', 'admin123')

# Créer le superuser seulement s'il n'existe pas déjà
if not User.objects.filter(username=username).exists():
    print(f'👤 Création du superuser: {username}')
    user = User.objects.create_superuser(
        username=username,
        email=email,
        password=password
    )
    token, _ = Token.objects.get_or_create(user=user)
    print(f'✅ Superuser créé avec succès!')
    print(f'   Username: {username}')
    print(f'   Email: {email}')
    print(f'   Token: {token.key}')
    print(f'👉 Connexion frontend avec : email={email}')
    print(f'⚠️  IMPORTANT: Changez le mot de passe après la première connexion!')
else:
    user = User.objects.get(username=username)
    # Reset le mot de passe à chaque démarrage si la variable est définie
    user.set_password(password)
    user.save()
    token, created = Token.objects.get_or_create(user=user)
    print(f'ℹ️  Le superuser {username} existe déjà — mot de passe mis à jour.')
    print(f'   Email: {user.email}')
    print(f'   Token: {token.key} ({"créé" if created else "existant"})')
    print(f'👉 Connexion frontend avec : email={user.email}')

