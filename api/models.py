from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json


class Folder(models.Model):
    """
    Modèle pour organiser les documents en dossiers
    """
    name = models.CharField(max_length=255, verbose_name="Nom du dossier")
    description = models.TextField(blank=True, verbose_name="Description")
    color = models.CharField(max_length=7, default="#3498DB", verbose_name="Couleur")
    icon = models.CharField(max_length=50, default="📁", verbose_name="Icône")
    
    # Hiérarchie des dossiers (dossier parent)
    parent = models.ForeignKey('self', on_delete=models.CASCADE, null=True, blank=True, 
                              related_name='subfolders', verbose_name="Dossier parent")
    
    # Position pour l'ordre d'affichage
    position = models.IntegerField(default=0, verbose_name="Position")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")
    
    # Utilisateur propriétaire du dossier
    owner = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Propriétaire", null=True, blank=True)
    
    class Meta:
        ordering = ['position', 'name']
        verbose_name = "Dossier"
        verbose_name_plural = "Dossiers"
    
    def __str__(self):
        if self.parent:
            return f"{self.parent.name} > {self.name}"
        return self.name
    
    @property
    def full_path(self):
        """Retourne le chemin complet du dossier"""
        if self.parent:
            return f"{self.parent.full_path} > {self.name}"
        return self.name
    
    @property
    def documents_count(self):
        """Compte les documents dans ce dossier"""
        return self.documents.count()
    
    @property
    def total_documents_count(self):
        """Compte tous les documents (incluant les sous-dossiers)"""
        count = self.documents.count()
        for subfolder in self.subfolders.all():
            count += subfolder.total_documents_count
        return count

class Document(models.Model):
    """
    Modèle pour stocker les documents (PDF, projets GrapesJS)
    """
    DOCUMENT_TYPES = [
        ('pdf_import', 'PDF Importé'),
        ('grapesjs_project', 'Projet GrapesJS'),
        ('puck_project', 'Projet Puck'),
        ('generated_offer', 'Offre Générée'),
    ]
    
    title = models.CharField(max_length=255, verbose_name="Titre")
    description = models.TextField(blank=True, verbose_name="Description")
    document_type = models.CharField(max_length=20, choices=DOCUMENT_TYPES, verbose_name="Type de document")
    
    # Dossier parent
    folder = models.ForeignKey(Folder, on_delete=models.SET_NULL, null=True, blank=True, 
                              related_name='documents', verbose_name="Dossier")
    
    # Données structurées (JSON)
    offer_structure = models.JSONField(null=True, blank=True, verbose_name="Structure de l'offre")
    grapes_html = models.TextField(blank=True, verbose_name="HTML GrapesJS")
    grapes_css = models.TextField(blank=True, verbose_name="CSS GrapesJS")
    
    # Fichiers
    pdf_file = models.FileField(upload_to='documents/pdfs/', null=True, blank=True, verbose_name="Fichier PDF")
    thumbnail = models.ImageField(upload_to='documents/thumbnails/', null=True, blank=True, verbose_name="Miniature")
    
    # Métadonnées
    company_info = models.JSONField(default=dict, verbose_name="Informations entreprise")
    assets = models.JSONField(default=list, verbose_name="Assets (images, etc.)")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")
    
    # Utilisateur propriétaire du document
    owner = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Propriétaire", null=True, blank=True)
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Document"
        verbose_name_plural = "Documents"
    
    def __str__(self):
        return f"{self.title} ({self.get_document_type_display()})"
    
    @property
    def file_size(self):
        """Retourne la taille du fichier PDF en bytes"""
        if self.pdf_file:
            return self.pdf_file.size
        return 0
    
    @property
    def file_size_mb(self):
        """Retourne la taille du fichier PDF en MB"""
        return round(self.file_size / (1024 * 1024), 2)


class DocumentAsset(models.Model):
    """
    Modèle pour stocker les assets associés à un document (images, etc.)
    """
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name='document_assets')
    name = models.CharField(max_length=255, verbose_name="Nom du fichier")
    file = models.FileField(upload_to='documents/assets/', verbose_name="Fichier")
    file_type = models.CharField(max_length=50, verbose_name="Type de fichier")
    width = models.IntegerField(null=True, blank=True, verbose_name="Largeur")
    height = models.IntegerField(null=True, blank=True, verbose_name="Hauteur")
    size_kb = models.FloatField(null=True, blank=True, verbose_name="Taille (KB)")
    
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        verbose_name = "Asset de document"
        verbose_name_plural = "Assets de documents"
    
    def __str__(self):
        return f"{self.name} ({self.document.title})"


class UserTemplate(models.Model):
    """
    Modèle pour stocker les templates GrapesJS personnalisés par utilisateur
    """
    TEMPLATE_TYPES = [
        ('travel_offer', 'Offre de voyage'),
        ('brochure', 'Brochure'),
        ('newsletter', 'Newsletter'),
        ('custom', 'Personnalisé'),
    ]
    
    owner = models.ForeignKey(User, on_delete=models.CASCADE, verbose_name="Propriétaire", related_name='templates')
    name = models.CharField(max_length=255, verbose_name="Nom du template")
    description = models.TextField(blank=True, verbose_name="Description")
    template_type = models.CharField(max_length=20, choices=TEMPLATE_TYPES, default='custom', verbose_name="Type de template")
    
    # Structure GrapesJS
    grapes_html = models.TextField(verbose_name="HTML GrapesJS")
    grapes_css = models.TextField(verbose_name="CSS GrapesJS")
    grapes_components = models.JSONField(default=dict, verbose_name="Composants GrapesJS")
    grapes_styles = models.JSONField(default=list, verbose_name="Styles GrapesJS")
    
    # Métadonnées
    thumbnail = models.ImageField(upload_to='templates/thumbnails/', null=True, blank=True, verbose_name="Miniature")
    is_default = models.BooleanField(default=False, verbose_name="Template par défaut")
    is_public = models.BooleanField(default=False, verbose_name="Template public (partagé)")
    
    # Paramètres personnalisables
    color_scheme = models.JSONField(default=dict, verbose_name="Palette de couleurs")
    fonts = models.JSONField(default=list, verbose_name="Polices utilisées")
    
    # Timestamps
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Créé le")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Modifié le")
    
    class Meta:
        ordering = ['-updated_at']
        verbose_name = "Template utilisateur"
        verbose_name_plural = "Templates utilisateurs"
        unique_together = ['owner', 'name']  # Nom unique par utilisateur
    
    def __str__(self):
        return f"{self.name} ({self.owner.username})"
    
    @property
    def full_grapes_data(self):
        """Retourne la structure complète pour GrapesJS"""
        return {
            'html': self.grapes_html,
            'css': self.grapes_css,
            'components': self.grapes_components,
            'styles': self.grapes_styles
        }
