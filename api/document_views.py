from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import IsAuthenticated, AllowAny
from django.shortcuts import get_object_or_404
from django.db import models
from .models import Document, Folder, DocumentAsset
from .serializers import DocumentSerializer, FolderSerializer


class DocumentListCreateView(ListCreateAPIView):
    """
    GET: Liste tous les documents de l'utilisateur connecté
    POST: Crée un nouveau document pour l'utilisateur connecté
    """
    serializer_class = DocumentSerializer
    permission_classes = [AllowAny]  # TEMPORAIRE pour démo client

    def get_queryset(self):
        """Filtrer les documents par utilisateur connecté"""
        # Si connecté, montrer ses documents, sinon tous
        if self.request.user.is_authenticated:
            return Document.objects.filter(owner=self.request.user).order_by('-updated_at')
        return Document.objects.all().order_by('-updated_at')

    def perform_create(self, serializer):
        """Associer le document à l'utilisateur connecté si authentifié"""
        if self.request.user.is_authenticated:
            serializer.save(owner=self.request.user)
        else:
            serializer.save()  # Sans owner si pas connecté


class DocumentDetailView(RetrieveUpdateDestroyAPIView):
    """
    GET: Récupère un document spécifique
    PUT/PATCH: Met à jour un document
    DELETE: Supprime un document
    """
    serializer_class = DocumentSerializer
    permission_classes = [AllowAny]  # TEMPORAIRE pour démo client

    def get_queryset(self):
        """Filtrer les documents par utilisateur connecté"""
        if self.request.user.is_authenticated:
            return Document.objects.filter(owner=self.request.user)
        return Document.objects.all()  # Tous les documents si pas connecté


class FolderListCreateView(ListCreateAPIView):
    """
    GET: Liste tous les dossiers de l'utilisateur connecté
    POST: Crée un nouveau dossier pour l'utilisateur connecté
    """
    serializer_class = FolderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrer les dossiers par utilisateur connecté"""
        return Folder.objects.filter(owner=self.request.user).order_by('position', 'name')

    def perform_create(self, serializer):
        """Associer le dossier à l'utilisateur connecté"""
        serializer.save(owner=self.request.user)


class FolderDetailView(RetrieveUpdateDestroyAPIView):
    """
    GET: Récupère un dossier spécifique
    PUT/PATCH: Met à jour un dossier
    DELETE: Supprime un dossier
    """
    serializer_class = FolderSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        """Filtrer les dossiers par utilisateur connecté"""
        return Folder.objects.filter(owner=self.request.user)

    def destroy(self, request, *args, **kwargs):
        """Supprime un dossier avec vérification"""
        folder = self.get_object()
        
        # Vérifier s'il y a des documents ou sous-dossiers
        if folder.documents.exists() or folder.subfolders.exists():
            return Response({
                'error': 'Impossible de supprimer un dossier non vide. Déplacez d\'abord son contenu.'
            }, status=status.HTTP_400_BAD_REQUEST)
        
        return super().destroy(request, *args, **kwargs)


class DocumentMoveToFolderView(APIView):
    """
    POST: Déplace un document vers un dossier
    """
    permission_classes = [IsAuthenticated]
    
    def post(self, request, document_id):
        """Déplace un document vers un dossier spécifique"""
        # Récupérer le document en s'assurant qu'il appartient à l'utilisateur
        document = get_object_or_404(Document, pk=document_id, owner=request.user)
        folder_id = request.data.get('folder_id')
        
        if folder_id:
            # Récupérer le dossier en s'assurant qu'il appartient à l'utilisateur
            folder = get_object_or_404(Folder, pk=folder_id, owner=request.user)
            document.folder = folder
        else:
            # Déplacer vers la racine (aucun dossier)
            document.folder = None
        
        document.save()
        
        return Response({
            'message': f'Document "{document.title}" déplacé avec succès',
            'document_id': document.id,
            'folder_id': folder_id,
            'folder_name': document.folder.name if document.folder else 'Racine'
        })


class FolderDocumentsView(APIView):
    """
    GET: Récupère tous les documents d'un dossier spécifique
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request, folder_id):
        """Retourne les documents d'un dossier spécifique"""
        # Récupérer le dossier en s'assurant qu'il appartient à l'utilisateur
        folder = get_object_or_404(Folder, pk=folder_id, owner=request.user)
        
        # Récupérer les documents du dossier
        documents = Document.objects.filter(folder=folder, owner=request.user).order_by('-updated_at')
        serializer = DocumentSerializer(documents, many=True, context={'request': request})
        
        return Response({
            'folder': FolderSerializer(folder, context={'request': request}).data,
            'documents': serializer.data
        })


class DocumentsWithoutFolderView(APIView):
    """
    GET: Récupère tous les documents qui ne sont dans aucun dossier
    """
    permission_classes = [IsAuthenticated]
    
    def get(self, request):
        """Retourne les documents sans dossier"""
        documents = Document.objects.filter(folder=None, owner=request.user).order_by('-updated_at')
        serializer = DocumentSerializer(documents, many=True, context={'request': request})
        
        return Response({
            'documents': serializer.data
        })
