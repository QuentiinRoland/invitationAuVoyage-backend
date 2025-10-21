from rest_framework import serializers
from django.contrib.auth.models import User
from django.contrib.auth import authenticate
from rest_framework.authtoken.models import Token
from .models import Document, Folder, DocumentAsset


class UserRegistrationSerializer(serializers.ModelSerializer):
    """Serializer pour l'inscription d'un nouvel utilisateur"""
    password = serializers.CharField(write_only=True, min_length=8)
    password_confirm = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ('username', 'email', 'password', 'password_confirm', 'first_name', 'last_name')
        extra_kwargs = {
            'email': {'required': True},
            'first_name': {'required': False},
            'last_name': {'required': False},
        }

    def validate_email(self, value):
        """Vérifier que l'email est unique"""
        if User.objects.filter(email=value).exists():
            raise serializers.ValidationError("Un utilisateur avec cet email existe déjà.")
        return value

    def validate(self, data):
        """Vérifier que les mots de passe correspondent"""
        if data['password'] != data['password_confirm']:
            raise serializers.ValidationError("Les mots de passe ne correspondent pas.")
        return data

    def create(self, validated_data):
        """Créer un nouvel utilisateur"""
        validated_data.pop('password_confirm')
        user = User.objects.create_user(
            username=validated_data['username'],
            email=validated_data['email'],
            password=validated_data['password'],
            first_name=validated_data.get('first_name', ''),
            last_name=validated_data.get('last_name', '')
        )
        # Créer automatiquement un token pour l'utilisateur
        Token.objects.create(user=user)
        return user


class UserLoginSerializer(serializers.Serializer):
    """Serializer pour la connexion utilisateur"""
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        """Authentifier l'utilisateur"""
        email = data.get('email')
        password = data.get('password')

        if email and password:
            # Trouver l'utilisateur par email
            try:
                user = User.objects.get(email=email)
                username = user.username
            except User.DoesNotExist:
                raise serializers.ValidationError("Email ou mot de passe incorrect.")

            # Authentifier avec le username
            user = authenticate(username=username, password=password)
            if not user:
                raise serializers.ValidationError("Email ou mot de passe incorrect.")
            
            if not user.is_active:
                raise serializers.ValidationError("Ce compte est désactivé.")
            
            data['user'] = user
        else:
            raise serializers.ValidationError("L'email et le mot de passe sont requis.")
        
        return data


class UserProfileSerializer(serializers.ModelSerializer):
    """Serializer pour le profil utilisateur"""
    class Meta:
        model = User
        fields = ('id', 'username', 'email', 'first_name', 'last_name', 'date_joined')
        read_only_fields = ('id', 'username', 'date_joined')


class FolderSerializer(serializers.ModelSerializer):
    """Serializer pour les dossiers"""
    documents_count = serializers.ReadOnlyField()
    total_documents_count = serializers.ReadOnlyField()
    full_path = serializers.ReadOnlyField()
    owner = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Folder
        fields = '__all__'
        read_only_fields = ('owner', 'created_at', 'updated_at')

    def create(self, validated_data):
        """Créer un dossier en associant l'utilisateur connecté"""
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)


class DocumentAssetSerializer(serializers.ModelSerializer):
    """Serializer pour les assets de documents"""
    class Meta:
        model = DocumentAsset
        fields = '__all__'


class DocumentSerializer(serializers.ModelSerializer):
    """Serializer pour les documents"""
    document_assets = DocumentAssetSerializer(many=True, read_only=True)
    file_size_mb = serializers.ReadOnlyField()
    owner = serializers.StringRelatedField(read_only=True)

    class Meta:
        model = Document
        fields = '__all__'
        read_only_fields = ('owner', 'created_at', 'updated_at')

    def create(self, validated_data):
        """Créer un document en associant l'utilisateur connecté"""
        validated_data['owner'] = self.context['request'].user
        return super().create(validated_data)
