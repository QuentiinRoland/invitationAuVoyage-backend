from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.authtoken.models import Token
from django.contrib.auth import login, logout
from django.contrib.auth.models import User
from django.contrib.auth.tokens import default_token_generator
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.http import urlsafe_base64_encode, urlsafe_base64_decode
from django.utils.encoding import force_bytes, force_str
from django.conf import settings
import uuid
from .serializers import UserRegistrationSerializer, UserLoginSerializer, UserProfileSerializer


class RegisterView(APIView):
    """Vue pour l'inscription d'un nouvel utilisateur"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserRegistrationSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.save()
            token, created = Token.objects.get_or_create(user=user)
            
            return Response({
                'message': 'Utilisateur créé avec succès',
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                },
                'token': token.key
            }, status=status.HTTP_201_CREATED)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LoginView(APIView):
    """Vue pour la connexion utilisateur"""
    permission_classes = [AllowAny]

    def post(self, request):
        serializer = UserLoginSerializer(data=request.data)
        if serializer.is_valid():
            user = serializer.validated_data['user']
            token, created = Token.objects.get_or_create(user=user)
            
            # Connexion de l'utilisateur pour les sessions
            login(request, user)
            
            return Response({
                'message': 'Connexion réussie',
                'user': {
                    'id': user.id,
                    'username': user.username,
                    'email': user.email,
                    'first_name': user.first_name,
                    'last_name': user.last_name,
                },
                'token': token.key
            }, status=status.HTTP_200_OK)
        
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class LogoutView(APIView):
    """Vue pour la déconnexion utilisateur"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            # Supprimer le token de l'utilisateur
            request.user.auth_token.delete()
        except:
            pass
        
        # Déconnexion de la session
        logout(request)
        
        return Response({
            'message': 'Déconnexion réussie'
        }, status=status.HTTP_200_OK)


class ProfileView(APIView):
    """Vue pour consulter et modifier le profil utilisateur"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Récupérer le profil de l'utilisateur connecté"""
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data)

    def put(self, request):
        """Mettre à jour le profil de l'utilisateur connecté"""
        serializer = UserProfileSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response({
                'message': 'Profil mis à jour avec succès',
                'user': serializer.data
            })
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class ChangePasswordView(APIView):
    """Vue pour changer le mot de passe"""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        current_password = request.data.get('current_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')

        if not all([current_password, new_password, confirm_password]):
            return Response({
                'error': 'Tous les champs sont requis'
            }, status=status.HTTP_400_BAD_REQUEST)

        if not request.user.check_password(current_password):
            return Response({
                'error': 'Mot de passe actuel incorrect'
            }, status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({
                'error': 'Les nouveaux mots de passe ne correspondent pas'
            }, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({
                'error': 'Le mot de passe doit contenir au moins 8 caractères'
            }, status=status.HTTP_400_BAD_REQUEST)

        request.user.set_password(new_password)
        request.user.save()

        return Response({
            'message': 'Mot de passe changé avec succès'
        }, status=status.HTTP_200_OK)


class CheckAuthView(APIView):
    """Vue pour vérifier si l'utilisateur est authentifié"""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({
            'authenticated': True,
            'user': {
                'id': request.user.id,
                'username': request.user.username,
                'email': request.user.email,
                'first_name': request.user.first_name,
                'last_name': request.user.last_name,
            }
        })


class PasswordResetRequestView(APIView):
    """Vue pour demander une réinitialisation de mot de passe"""
    permission_classes = [AllowAny]

    def post(self, request):
        email = request.data.get('email')
        
        if not email:
            return Response({
                'error': 'Email requis'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            user = User.objects.get(email=email)
        except User.DoesNotExist:
            # Pour la sécurité, on ne révèle pas si l'email existe ou non
            return Response({
                'message': 'Si cet email existe, un lien de réinitialisation a été envoyé'
            }, status=status.HTTP_200_OK)

        # Générer un token unique pour la réinitialisation
        token = default_token_generator.make_token(user)
        uid = urlsafe_base64_encode(force_bytes(user.pk))
        
        # URL de réinitialisation (frontend)
        frontend_url = getattr(settings, 'FRONTEND_URL', 'http://localhost:3002')
        reset_url = f"{frontend_url}/reset-password/{uid}/{token}/"

        # Envoyer l'email
        subject = 'Réinitialisation de votre mot de passe - Invitation au Voyage'
        message = f"""
Bonjour {user.first_name or user.username},

Vous avez demandé une réinitialisation de votre mot de passe.

Cliquez sur le lien suivant pour réinitialiser votre mot de passe :
{reset_url}

Ce lien expirera dans 24 heures.

Si vous n'avez pas demandé cette réinitialisation, ignorez cet email.

Cordialement,
L'équipe Invitation au Voyage
        """

        try:
            send_mail(
                subject,
                message,
                settings.DEFAULT_FROM_EMAIL,
                [email],
                fail_silently=False,
            )
        except Exception as e:
            return Response({
                'error': 'Erreur lors de l\'envoi de l\'email'
            }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

        return Response({
            'message': 'Si cet email existe, un lien de réinitialisation a été envoyé'
        }, status=status.HTTP_200_OK)


class PasswordResetConfirmView(APIView):
    """Vue pour confirmer la réinitialisation de mot de passe"""
    permission_classes = [AllowAny]

    def post(self, request):
        uid = request.data.get('uid')
        token = request.data.get('token')
        new_password = request.data.get('new_password')
        
        if not all([uid, token, new_password]):
            return Response({
                'error': 'Tous les champs sont requis'
            }, status=status.HTTP_400_BAD_REQUEST)

        try:
            # Décoder l'UID
            user_id = force_str(urlsafe_base64_decode(uid))
            user = User.objects.get(pk=user_id)
        except (TypeError, ValueError, OverflowError, User.DoesNotExist):
            return Response({
                'error': 'Lien de réinitialisation invalide'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Vérifier le token
        if not default_token_generator.check_token(user, token):
            return Response({
                'error': 'Lien de réinitialisation expiré ou invalide'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Valider le nouveau mot de passe
        if len(new_password) < 8:
            return Response({
                'error': 'Le mot de passe doit contenir au moins 8 caractères'
            }, status=status.HTTP_400_BAD_REQUEST)

        # Changer le mot de passe
        user.set_password(new_password)
        user.save()

        # Supprimer tous les tokens existants pour forcer une nouvelle connexion
        Token.objects.filter(user=user).delete()

        return Response({
            'message': 'Mot de passe réinitialisé avec succès'
        }, status=status.HTTP_200_OK)
