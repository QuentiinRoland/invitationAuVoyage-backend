from django.urls import path
from .views import (
    APIRootView, TravelOfferGenerator, GrapesJSPDFGenerator, PdfToGJSEndpoint,
    ImproveOfferEndpoint, DocumentGeneratePDFView, PDFOfferGenerator, FreepikImageSearchView,
    UrlPreviewView, HotelGoogleSearchView, ImageSearchView, WebSearchView
)
from .auth_views import (
    RegisterView, LoginView, LogoutView, ProfileView, ChangePasswordView, CheckAuthView,
    PasswordResetRequestView, PasswordResetConfirmView
)
from .document_views import (
    DocumentListCreateView, DocumentDetailView, FolderListCreateView, FolderDetailView,
    DocumentMoveToFolderView, FolderDocumentsView, DocumentsWithoutFolderView, UploadImageView
)

urlpatterns = [
    # Page d'accueil de l'API
    path("", APIRootView.as_view(), name="api-root"),
    
    # Authentification
    path("auth/register/", RegisterView.as_view(), name="auth-register"),
    path("auth/login/", LoginView.as_view(), name="auth-login"),
    path("auth/logout/", LogoutView.as_view(), name="auth-logout"),
    path("auth/profile/", ProfileView.as_view(), name="auth-profile"),
    path("auth/change-password/", ChangePasswordView.as_view(), name="auth-change-password"),
    path("auth/check/", CheckAuthView.as_view(), name="auth-check"),
    
    # Réinitialisation de mot de passe
    path("auth/password-reset/", PasswordResetRequestView.as_view(), name="auth-password-reset"),
    path("auth/password-reset-confirm/", PasswordResetConfirmView.as_view(), name="auth-password-reset-confirm"),
    
    # Génération d'offres (nécessite authentification)
    path("generate-travel-offer/", TravelOfferGenerator.as_view(), name="generate-travel-offer"),
    path("generate-offer/", TravelOfferGenerator.as_view(), name="generate-offer"),  # Alias pour compatibilité
    path("generate-pdf-offer/", PDFOfferGenerator.as_view(), name="generate-pdf-offer"),
    path("grapesjs-pdf-generator/", GrapesJSPDFGenerator.as_view(), name="grapesjs-pdf-generator"),
    path("pdf-to-gjs/", PdfToGJSEndpoint.as_view(), name="pdf-to-gjs"),
    path("improve-offer/", ImproveOfferEndpoint.as_view(), name="improve-offer"),
    
    # Gestion des documents sauvegardés (nécessite authentification)
    path("documents/", DocumentListCreateView.as_view(), name="document-list-create"),
    path("documents/without-folder/", DocumentsWithoutFolderView.as_view(), name="documents-without-folder"),
    path("documents/<int:pk>/", DocumentDetailView.as_view(), name="document-detail"),
    path("documents/<int:pk>/generate-pdf/", DocumentGeneratePDFView.as_view(), name="document-generate-pdf"),
    path("documents/<int:document_id>/move-to-folder/", DocumentMoveToFolderView.as_view(), name="document-move-to-folder"),
    
    # Gestion des dossiers (nécessite authentification)
    path("folders/", FolderListCreateView.as_view(), name="folder-list-create"),
    path("folders/<int:pk>/", FolderDetailView.as_view(), name="folder-detail"),
    path("folders/<int:folder_id>/documents/", FolderDocumentsView.as_view(), name="folder-documents"),
    
    # Upload d'images (public)
    path("upload-image/", UploadImageView.as_view(), name="upload-image"),

    # Proxy Freepik API (public - pas besoin d'authentification)
    path("freepik/search/", FreepikImageSearchView.as_view(), name="freepik-search"),

    # Prévisualisation d'URL (galerie d'images scrapées)
    path("preview-url/", UrlPreviewView.as_view(), name="preview-url"),

    # Recherche hôtel via Google Places API
    path("hotel-google-search/", HotelGoogleSearchView.as_view(), name="hotel-google-search"),

    # Recherche d'images (Unsplash / Freepik)
    path("search-images/", ImageSearchView.as_view(), name="search-images"),

    # Recherche web (hôtels / destinations) → URLs à scrapper
    path("web-search/", WebSearchView.as_view(), name="web-search"),
]
