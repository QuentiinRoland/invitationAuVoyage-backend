"""
URL configuration for config project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods


@require_http_methods(["GET"])
def root_view(request):
    """Vue racine qui affiche les informations du projet"""
    return JsonResponse({
        "project": "Invitation au Voyage - Backend API",
        "version": "1.0.0",
        "status": "online",
        "api": "/api/",
        "admin": "/admin/",
        "documentation": "https://github.com/QuentiinRoland/invitationAuVoyage-backend"
    })


urlpatterns = [
    path('', root_view, name='root'),
    path('admin/', admin.site.urls),
    path("api/", include("api.urls")),
]

# Servir les fichiers média en développement
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
