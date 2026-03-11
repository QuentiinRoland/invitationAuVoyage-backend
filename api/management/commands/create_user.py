"""
Management command pour créer un utilisateur applicatif (non-admin).
Usage: python manage.py create_user --email user@example.com --password monmdp --username monuser
"""
from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import User
from rest_framework.authtoken.models import Token


class Command(BaseCommand):
    help = 'Crée un utilisateur avec email + mot de passe pour se connecter via le frontend'

    def add_arguments(self, parser):
        parser.add_argument('--email', required=True, help='Adresse email (utilisée pour la connexion)')
        parser.add_argument('--password', required=True, help='Mot de passe (min 8 caractères)')
        parser.add_argument('--username', help='Nom d\'utilisateur (défaut: partie locale de l\'email)')
        parser.add_argument('--first-name', default='', help='Prénom')
        parser.add_argument('--last-name', default='', help='Nom de famille')

    def handle(self, *args, **options):
        email = options['email']
        password = options['password']
        username = options.get('username') or email.split('@')[0]

        if len(password) < 8:
            raise CommandError('Le mot de passe doit contenir au moins 8 caractères.')

        if User.objects.filter(email=email).exists():
            raise CommandError(f'Un utilisateur avec l\'email {email} existe déjà.')

        if User.objects.filter(username=username).exists():
            raise CommandError(f'Un utilisateur avec le username {username} existe déjà.')

        user = User.objects.create_user(
            username=username,
            email=email,
            password=password,
            first_name=options.get('first_name', ''),
            last_name=options.get('last_name', ''),
        )

        token, _ = Token.objects.get_or_create(user=user)

        self.stdout.write(self.style.SUCCESS(f'✅ Utilisateur créé avec succès'))
        self.stdout.write(f'   Email    : {email}')
        self.stdout.write(f'   Username : {username}')
        self.stdout.write(f'   Token    : {token.key}')
        self.stdout.write(f'')
        self.stdout.write(f'👉 Connexion via le frontend avec : email={email} + le mot de passe saisi')
