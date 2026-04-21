from rest_framework import parsers, status
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.generics import ListCreateAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import AllowAny
from django.conf import settings
from django.http import HttpResponse
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
import json
from openai import OpenAI
import re
from weasyprint import HTML, CSS
from datetime import datetime
import os
import requests
from urllib.parse import urlparse
import hashlib
from bs4 import BeautifulSoup
import pathlib
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed

# Chemin vers le répertoire du projet
BASE_DIR = Path(__file__).resolve().parent.parent

# Recherche web en temps réel (optionnel - nécessite TAVILY_API_KEY)
try:
    from tavily import TavilyClient
    TAVILY_AVAILABLE = True
except ImportError:
    TAVILY_AVAILABLE = False
    print("⚠️ Tavily non disponible. Installer avec: pip install tavily-python")

# Scraping JavaScript (optionnel - nécessite playwright)
try:
    from playwright.sync_api import sync_playwright
    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False
    print("⚠️ Playwright non disponible. Installer avec: pip install playwright && playwright install chromium")
import base64
import io
import fitz  # PyMuPDF
import traceback
from .models import Document, DocumentAsset, Folder

# Client OpenAI initialisé de manière lazy (au moment de l'utilisation)
def get_openai_client():
    """Retourne une instance du client OpenAI avec la clé API"""
    api_key = settings.OPENAI_API_KEY
    if not api_key:
        raise ValueError("OPENAI_API_KEY n'est pas configurée dans les variables d'environnement")
    masked = f"{api_key[:5]}...{api_key[-4:]}"
    print(f"🕵️ API VIEW RUNTIME KEY: {masked}")
    return OpenAI(api_key=api_key)

# Imports pour OpenAI


class APIRootView(APIView):
    """
    Vue racine de l'API - Liste tous les endpoints disponibles
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        return Response({
            "message": "Bienvenue sur l'API Invitation au Voyage",
            "version": "1.0.0",
            "status": "online",
            "endpoints": {
                "authentification": {
                    "register": "/api/auth/register/",
                    "login": "/api/auth/login/",
                    "logout": "/api/auth/logout/",
                    "profile": "/api/auth/profile/",
                    "check": "/api/auth/check/",
                    "password_reset": "/api/auth/password-reset/",
                    "password_reset_confirm": "/api/auth/password-reset-confirm/",
                },
                "offres": {
                    "generate_offer": "/api/generate-offer/",
                    "generate_pdf_offer": "/api/generate-pdf-offer/",
                    "improve_offer": "/api/improve-offer/",
                    "grapesjs_pdf_generator": "/api/grapesjs-pdf-generator/",
                    "pdf_to_gjs": "/api/pdf-to-gjs/",
                },
                "documents": {
                    "list_create": "/api/documents/",
                    "without_folder": "/api/documents/without-folder/",
                    "detail": "/api/documents/{id}/",
                    "generate_pdf": "/api/documents/{id}/generate-pdf/",
                    "move_to_folder": "/api/documents/{id}/move-to-folder/",
                },
                "folders": {
                    "list_create": "/api/folders/",
                    "detail": "/api/folders/{id}/",
                    "documents": "/api/folders/{id}/documents/",
                },
                "admin": "/admin/"
            },
            "documentation": "https://github.com/QuentiinRoland/invitationAuVoyage-backend"
        })

# Configuration des APIs d'images
UNSPLASH_KEY = os.getenv("UNSPLASH_ACCESS_KEY")
BING_KEY = os.getenv("BING_IMAGE_SUBSCRIPTION_KEY")
PIXABAY_KEY = os.getenv("PIXABAY_API_KEY")
GOOGLE_CSE_KEY = os.getenv("GOOGLE_CSE_API_KEY")
GOOGLE_CSE_CX  = os.getenv("GOOGLE_CSE_CX")

# Configuration du cache d'images
MEDIA_DIR = pathlib.Path("/tmp/offer_images")
MEDIA_DIR.mkdir(exist_ok=True, parents=True)

def search_unsplash(query: str, per_page: int = 1):
    """Recherche d'images via l'API Unsplash"""
    if not UNSPLASH_KEY:
        return []
    
    url = "https://api.unsplash.com/search/photos"
    try:
        r = requests.get(url, params={
            "query": query, 
            "per_page": per_page, 
            "orientation": "landscape"
        }, headers={
            "Accept-Version": "v1", 
            "Authorization": f"Client-ID {UNSPLASH_KEY}"
        }, timeout=3)  # Réduit à 3 secondes pour éviter les timeouts
        r.raise_for_status()
        data = r.json().get("results", [])
        out = []
        for item in data:
            out.append({
                "url": item["urls"]["regular"],
                "thumb": item["urls"]["small"],
                "source": item["links"]["html"],
                "photographer": item["user"]["name"],
                "attribution": f'Photo: {item["user"]["name"]} / Unsplash',
                "license": "Unsplash License"
            })
        return out
    except Exception as e:
        print(f"Erreur Unsplash: {e}")
        return []

def search_bing_images(query: str, count: int = 1):
    """Recherche d'images via l'API Bing Image Search"""
    if not BING_KEY:
        return []
    
    url = "https://api.bing.microsoft.com/v7.0/images/search"
    try:
        r = requests.get(url, params={
            "q": query, 
            "count": count, 
            "safeSearch": "Moderate"
        }, headers={
            "Ocp-Apim-Subscription-Key": BING_KEY
        }, timeout=3)  # Réduit à 3 secondes pour éviter les timeouts
        r.raise_for_status()
        data = r.json().get("value", [])
        out = []
        for item in data:
            out.append({
                "url": item.get("contentUrl"),
                "thumb": item.get("thumbnailUrl"),
                "source": item.get("hostPageUrl"),
                "attribution": item.get("hostPageDomainFriendlyName") or item.get("hostPageDisplayUrl"),
                "license": item.get("license", "Check site")
            })
        return out
    except Exception as e:
        print(f"Erreur Bing Images: {e}")
        return []

def cache_image(url: str) -> str:
    """Cache une image localement et retourne le chemin absolu pour WeasyPrint"""
    try:
        h = hashlib.sha1(url.encode()).hexdigest()
        ext = ".png" if url.lower().endswith('.png') else ".jpg"
        local = MEDIA_DIR / f"{h}{ext}"
        
        if not local.exists():
            print(f"📥 Téléchargement image: {url}")
            r = requests.get(url, timeout=10)
            r.raise_for_status()
            local.write_bytes(r.content)
            print(f"✅ Image téléchargée: {local} ({len(r.content)} bytes)")
        
        # Retourne le chemin absolu avec file:// pour WeasyPrint
        return f"file://{local.absolute()}"
    except Exception as e:
        print(f"⚠️ Erreur cache image {url}: {e}")
        return url  # Retourne l'URL originale en cas d'erreur


class GrapesJSPDFGenerator(APIView):
    """
    Prend le contenu de GrapesJS et génère un PDF (Chromium headless via Playwright)
    POST JSON: { html: string, css: string, company_info: {name, phone, email} }
    """
    permission_classes = [AllowAny]  # Accès libre temporaire

    def post(self, request):
        html_content = request.data.get("html", "")
        css_content  = request.data.get("css", "")
        company_info = request.data.get("company_info", {}) or {}

        if not html_content:
            return Response({"error": "Contenu HTML requis"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            # IMPORTANT: on recompose un HTML complet imprimable
            printable_html = self.convert_grapesjs_to_printable_html(html_content, css_content, company_info)

            # Génération PDF avec WeasyPrint (solution standard Django pour production)
            # Support complet HTML5/CSS3, rendu professionnel, rapide et stable
            pdf_bytes = HTML(string=printable_html).write_pdf()

            resp = HttpResponse(pdf_bytes, content_type="application/pdf")
            resp["Content-Disposition"] = 'inline; filename="grapesjs-content.pdf"'
            return resp

        except Exception as e:
            # Log serveur utile pour debug
            import traceback; traceback.print_exc()
            return Response({"error": f"Erreur: {e}"}, status=500)

    # ---------------------------
    # Méthodes utilitaires
    # ---------------------------

    def convert_grapesjs_to_printable_html(self, grapesjs_html: str, grapesjs_css: str, company_info: dict) -> str:
        """
        Convertit le contenu GrapesJS en HTML imprimable optimisé pour WeasyPrint.
        """
        company_name  = company_info.get('name', 'Votre Entreprise')
        clean_html    = self.clean_grapesjs_html(grapesjs_html)
        clean_css     = self.clean_grapesjs_css(grapesjs_css)

        # Page HTML complète avec le CSS embarqué optimisé pour WeasyPrint
        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Document - {company_name}</title>
  <style>
    /* Reset & base */
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    
    /* Configuration de la page pour WeasyPrint - MULTI-PAGES avec background */
    @page {{
      size: A4;
      margin: 0 0 1.2cm 0;
      @bottom-center {{
        content: counter(page) " / " counter(pages);
        font-size: 7pt;
        color: #999;
        font-family: Arial, Helvetica, sans-serif;
        padding-bottom: 4mm;
      }}
    }}
    
    body {{
      font-family: Arial, Helvetica, sans-serif;
      line-height: 1.3;
      color: #333;
      background: transparent;
      width: 100%;
      max-width: 100%;
      padding: 0;
      margin: 0;
      font-size: 9pt;
      position: relative;
    }}
    
    /* Supprimer tous les espaces au-dessus du header */
    body::before {{
      content: none;
      display: none;
    }}

    /* CSS GrapesJS nettoyé - Le background sera sur TOUTES les pages */
    {clean_css}

    /* Conteneur principal - padding pour descendre le texte sur TOUTES les pages */
    .grapesjs-content {{
      width: 100%;
      overflow: visible;
      position: relative;
      padding: 1cm 2cm 2cm 2cm;
    }}

    /* Sections compactes */
    .flight-section, .hotel-section, .price-section {{
      margin-bottom: 8px;
      padding: 8px;
      border-radius: 3px;
    }}
    
    .cta-section {{
      margin: 8px 0;
      padding: 10px;
      border-radius: 3px;
    }}
    
    .offer-header {{
      margin-bottom: 10px;
      padding: 10px;
      border-radius: 3px;
    }}
    
    /* Titres compacts */
    h1, h2, h3 {{ 
      page-break-after: avoid;
      page-break-inside: avoid;
      margin-bottom: 6px;
      margin-top: 8px;
      clear: both;
    }}
    
    h1 {{ 
      font-size: 16pt;
      margin-top: 0;
      line-height: 1.2;
    }}
    h2 {{ 
      font-size: 12pt;
      line-height: 1.2;
    }}
    h3 {{ 
      font-size: 10pt;
      line-height: 1.2;
    }}
    
    /* Paragraphes compacts */
    p {{
      margin-bottom: 5px;
      line-height: 1.3;
      orphans: 2;
      widows: 2;
    }}
    
    /* Images - compatible WeasyPrint */
    img {{
      max-width: 100%;
      height: auto;
      display: block;
      page-break-inside: avoid;
    }}
    
    /* Empêcher les débordements */
    * {{
      max-width: 100%;
      word-wrap: break-word;
      overflow-wrap: break-word;
    }}
    
    /* Listes compactes */
    ul, ol {{
      margin-bottom: 5px;
      padding-left: 20px;
    }}
    
    li {{
      margin-bottom: 2px;
      line-height: 1.3;
    }}
    
    /* Footer compact */
    .footer {{
      margin-top: 15px;
      padding-top: 8px;
      font-size: 7pt;
    }}
    
  </style>
</head>
<body>
  <div class="grapesjs-content">
    {clean_html}
  </div>
</body>
</html>"""

    def clean_grapesjs_html(self, html: str) -> str:
        """Nettoie le HTML de GrapesJS pour l'impression avec WeasyPrint."""
        if not html:
            return ""
        
        # Supprimer les attributs GrapesJS
        html = re.sub(r'data-gjs-[^=]*="[^"]*"', '', html)
        html = re.sub(r'contenteditable="[^"]*"', '', html)
        html = re.sub(r'spellcheck="[^"]*"', '', html)
        html = re.sub(r'draggable="[^"]*"', '', html)
        
        # FORCER background-repeat: no-repeat dans les styles inline
        # Supprimer d'abord les background-repeat existants dans le style inline
        html = re.sub(
            r'style="([^"]*?)background-repeat:\s*[^;]+;?([^"]*)"',
            r'style="\1\2"',
            html,
            flags=re.IGNORECASE
        )
        
        # Ajouter background-repeat: no-repeat après chaque background dans style inline
        html = re.sub(
            r'style="([^"]*?)(background[^:]*:\s*[^";]+url\([^)]+\)[^";]*)',
            r'style="\1\2; background-repeat: no-repeat',
            html,
            flags=re.IGNORECASE
        )
        
        # Ajouter des styles inline pour les images si elles n'en ont pas
        html = re.sub(
            r'<img([^>]*?)(?:style="[^"]*")?([^>]*?)>',
            lambda m: f'<img{m.group(1)} style="max-width: 100%; height: auto; display: block;"{m.group(2)}>',
            html
        )
        
        # Supprimer les styles inline qui causent des problèmes avec WeasyPrint
        html = re.sub(r'position:\s*absolute\s*;?', '', html, flags=re.IGNORECASE)
        html = re.sub(r'position:\s*fixed\s*;?', '', html, flags=re.IGNORECASE)
        html = re.sub(r'transform:[^;]+;?', '', html, flags=re.IGNORECASE)
        
        # Nettoyer les espaces multiples
        html = re.sub(r'\s+', ' ', html).strip()
        html = re.sub(r'>\s+<', '><', html)
        
        return html

    def clean_grapesjs_css(self, css: str) -> str:
        """Nettoie le CSS de GrapesJS pour WeasyPrint."""
        if not css:
            return ""
        
        # Supprimer les attributs GrapesJS
        css = re.sub(r'\[data-gjs[^\]]*\][^}]*}', '', css)
        css = re.sub(r'\.gjs-[^}]*}', '', css)
        
        # Remplacer les valeurs transparentes
        css = css.replace('rgba(0,0,0,0)', 'transparent')
        
        # FORCER background-repeat: no-repeat sur TOUT ce qui a un background
        # Supprimer d'abord les background-repeat existants
        css = re.sub(r'background-repeat:\s*[^;]+;', '', css, flags=re.IGNORECASE)
        
        # Ajouter background-repeat: no-repeat après chaque background-image
        css = re.sub(
            r'(background-image:\s*url\([^)]+\))',
            r'\1; background-repeat: no-repeat',
            css,
            flags=re.IGNORECASE
        )
        
        # Ajouter background-repeat: no-repeat après chaque background:
        css = re.sub(
            r'(background:\s*[^;]+;)',
            lambda m: m.group(1).rstrip(';') + '; background-repeat: no-repeat;' if 'url(' in m.group(1) else m.group(1),
            css,
            flags=re.IGNORECASE
        )
        
        # Supprimer les propriétés CSS non supportées par WeasyPrint
        unsupported_properties = [
            r'transform:[^;]+;',
            r'animation:[^;]+;',
            r'transition:[^;]+;',
            r'box-shadow:[^;]+;',
            r'text-shadow:[^;]+;',
            r'filter:[^;]+;',
            r'backdrop-filter:[^;]+;',
            r'clip-path:[^;]+;',
            r'mask:[^;]+;',
            r'cursor:[^;]+;',
            r'pointer-events:[^;]+;',
            r'user-select:[^;]+;',
            r'-webkit-[^:]+:[^;]+;',
            r'-moz-[^:]+:[^;]+;',
            r'-ms-[^:]+:[^;]+;',
        ]
        
        for prop in unsupported_properties:
            css = re.sub(prop, '', css, flags=re.IGNORECASE)
        
        # Convertir les positionnements absolus/fixed en relatif pour éviter les débordements
        css = re.sub(r'position:\s*absolute\s*;', 'position: relative;', css, flags=re.IGNORECASE)
        css = re.sub(r'position:\s*fixed\s*;', 'position: relative;', css, flags=re.IGNORECASE)
        
        # Limiter les largeurs en pourcentage pour éviter les débordements
        css = re.sub(r'width:\s*(\d+)vw\s*;', lambda m: f'width: {min(100, int(m.group(1)))}%;', css)
        
        # Nettoyer les espaces
        css = re.sub(r'\s+', ' ', css).strip()
        css = re.sub(r'\s*{\s*', ' { ', css)
        css = re.sub(r'\s*}\s*', ' } ', css)
        css = re.sub(r'\s*;\s*', '; ', css)
        css = re.sub(r';\s*}', ' }', css)
        
        return css

    def generate_footer(self, company_info: dict, current_date: str) -> str:
        """Footer simple avec infos entreprise + date."""
        company_name = company_info.get('name', '')
        company_phone = company_info.get('phone', '')
        company_email = company_info.get('email', '')

        if not (company_name or company_phone or company_email):
            return ""

        footer_content = []
        if company_name:
            footer_content.append(f"<strong>{company_name}</strong>")

        contact_parts = []
        if company_phone:
            contact_parts.append(company_phone)
        if company_email:
            contact_parts.append(company_email)
        if contact_parts:
            footer_content.append(" • ".join(contact_parts))

        footer_content.append(f"Document généré le {current_date}")

        return f"""
  <div style="margin-top: 40px; padding: 20px; border-top: 2px solid #ddd; text-align: center; color: #666; font-size: 12px;">
    {"<br>".join(footer_content)}
  </div>"""



class TravelOfferGenerator(APIView):
    permission_classes = [AllowAny]  # Accès libre temporaire
    
    def _load_default_templates(self, offer_type):
        """
        Charge les templates par défaut depuis les fichiers JSON selon le type d'offre.
        """
        try:
            template_path = BASE_DIR / 'api' / 'templates' / f'{offer_type}_example.json'
            if template_path.exists():
                with open(template_path, 'r', encoding='utf-8') as f:
                    template_data = json.load(f)
                    return [template_data]  # Retourner sous forme de liste
            else:
                print(f"⚠️ Template par défaut non trouvé: {template_path}")
                return None
        except Exception as e:
            print(f"❌ Erreur chargement template par défaut: {str(e)}")
            return None
    
    def _scrape_website_description(self, url, max_length=5000):
        """
        Récupère la description d'un site web en scrapant son contenu.
        Extrait le texte principal et les meta descriptions.
        ATTENTION: Cette méthode ne peut pas exécuter JavaScript.
        Pour les sites JS/Angular/React, utiliser _scrape_with_tavily().
        """
        try:
            # S'assurer que l'URL a un protocole
            original_url = url
            if not url.startswith(('http://', 'https://')):
                url = 'https://' + url
                print(f"🔧 URL corrigée: {original_url} → {url}")
            
            # Détecter si l'URL contient beaucoup de paramètres (souvent signe d'un site JS)
            if '?' in url and len(url.split('?')[1]) > 100:
                print(f"   ⚠️ URL avec beaucoup de paramètres détectée - ce site utilise probablement JavaScript")
                print(f"   💡 Recommandation: Ce type de site nécessite Tavily pour être correctement scrapé")
            
            print(f"📡 Requête HTTP vers: {url}")
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
                'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
                'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                'Accept-Encoding': 'gzip, deflate, br',
                'Connection': 'keep-alive',
                'Upgrade-Insecure-Requests': '1',
                'Referer': 'https://www.google.com/'  # Simuler une arrivée depuis Google
            }
            print(f"⏱️ Timeout de 8 secondes pour le scraping...")
            response = requests.get(url, headers=headers, timeout=8, allow_redirects=True, verify=False)
            print(f"📥 Réponse HTTP: {response.status_code}")
            
            if response.status_code != 200:
                print(f"⚠️ Code HTTP non-200: {response.status_code}")
                return None
            
            response.raise_for_status()
            
            # Vérifier que le contenu n'est pas vide
            if not response.content or len(response.content) < 100:
                print(f"⚠️ Réponse vide ou trop courte: {len(response.content) if response.content else 0} bytes")
                return None
            
            print(f"📄 Taille du contenu HTML: {len(response.content)} bytes")
            soup = BeautifulSoup(response.content, 'html.parser')

            # Supprimer les scripts et styles
            for script in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
                script.decompose()

            # Extraire meta description + og:description
            meta_desc = ""
            for meta_attr in [("property", "og:description"), ("name", "description")]:
                tag = soup.find("meta", {meta_attr[0]: meta_attr[1]})
                if tag and tag.get("content"):
                    meta_desc = tag.get("content", "").strip()
                    break

            # og:title comme premier contexte si dispo
            og_title = ""
            og_title_tag = soup.find("meta", property="og:title") or soup.find("meta", {"name": "og:title"})
            if og_title_tag and og_title_tag.get("content"):
                og_title = og_title_tag.get("content", "").strip()
            elif soup.title and soup.title.string:
                og_title = soup.title.string.strip()

            # Essayer d'extraire le contenu principal (main/article/[role=main]) en priorité
            main_content = (
                soup.find("main") or
                soup.find("article") or
                soup.find(attrs={"role": "main"}) or
                soup.find(id=lambda x: x and any(k in x.lower() for k in ["main", "content", "body"])) or
                soup.find(class_=lambda x: x and any(k in " ".join(x).lower() for k in ["main-content", "page-content", "hotel-detail", "property-detail"]))
            )
            if main_content:
                text_content = main_content.get_text(separator=' ', strip=True)
            else:
                text_content = soup.get_text(separator=' ', strip=True)
            
            # Détecter si le contenu contient beaucoup de templates Angular/React/JS non rendus
            js_templates = ['{{', 'ng-', '[ng', '*ng', 'v-if', 'v-for', '@click', 'className', 'useState']
            has_js_templates = any(template in str(response.content) for template in js_templates)
            
            if has_js_templates:
                print(f"   ⚠️ Site JavaScript détecté (templates non rendus trouvés)")
                print(f"   💡 Ce site nécessite JavaScript pour afficher le contenu. BeautifulSoup ne peut pas l'exécuter.")
                print(f"   💡 Le contenu extrait sera probablement incomplet (templates {{ }})")
            
            # Nettoyer le texte (supprimer espaces multiples)
            lines = (line.strip() for line in text_content.splitlines())
            chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
            text_content = ' '.join(chunk for chunk in chunks if chunk)
            
            # Combiner titre + meta description + texte principal
            full_content = ""
            if og_title:
                full_content += f"Titre: {og_title}\n"
            if meta_desc:
                full_content += f"Description: {meta_desc}\n\n"

            # Limiter la longueur
            if len(text_content) > max_length:
                text_content = text_content[:max_length] + "..."
            
            full_content += text_content
            
            # Vérifier que le contenu final n'est pas vide
            if not full_content or len(full_content.strip()) < 50:
                print(f"⚠️ Contenu extrait trop court: {len(full_content)} caractères")
                print(f"   Preview: {full_content[:200]}")
                return None
            
            print(f"✅ Contenu extrait: {len(full_content)} caractères")
            print(f"   Preview: {full_content[:300]}...")
            
            return full_content
            
        except requests.exceptions.Timeout:
            print(f"⏱️ Timeout lors du scraping de {url} (le site prend trop de temps à répondre)")
            return None
        except requests.exceptions.RequestException as e:
            print(f"❌ Erreur HTTP lors du scraping de {url}: {str(e)}")
            if hasattr(e, 'response') and e.response is not None:
                print(f"   Status code: {e.response.status_code}")
            return None
        except Exception as e:
            print(f"❌ Erreur scraping {url}: {type(e).__name__}: {str(e)}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()}")
            return None
    
    def _scrape_single_url(self, url_clean):
        """
        Scrape une seule URL avec la stratégie : BeautifulSoup d'abord (rapide),
        puis Playwright si nécessaire (lent).
        Retourne un dict {url, content, images} ou None.
        """
        print(f"🌐 Tentative de scraping: {url_clean}")

        js_sites_keywords = ['misterfly', 'booking.com', 'expedia', 'airbnb', 'vrbo', 'hotels.com']
        is_js_site = any(keyword in url_clean.lower() for keyword in js_sites_keywords)

        desc = None

        # Stratégie inversée : BeautifulSoup d'abord (rapide ~2s), Playwright ensuite (lent ~20s)
        if not is_js_site:
            print(f"   📄 Essai rapide avec BeautifulSoup...")
            desc = self._scrape_website_description(url_clean)

        # Si BS4 échoue ou site JS, essayer Playwright
        if (not desc or len(desc.strip()) < 50) and PLAYWRIGHT_AVAILABLE:
            print(f"   🎭 Essai avec Playwright (navigateur headless)...")
            desc = self._scrape_with_playwright(url_clean)

        # Si Playwright échoue, essayer Tavily
        if (not desc or len(desc.strip()) < 50) and TAVILY_AVAILABLE:
            print(f"   🔍 Essai avec Tavily...")
            desc_tavily = self._scrape_with_tavily(url_clean)
            if desc_tavily:
                desc = desc_tavily

        # Dernier recours : BS4 pour les sites JS (au cas où)
        if (not desc or len(desc.strip()) < 50) and is_js_site:
            print(f"   📄 Dernier essai avec BeautifulSoup...")
            desc = self._scrape_website_description(url_clean)

        if desc and len(desc.strip()) > 50:
            images = []
            if is_js_site and PLAYWRIGHT_AVAILABLE:
                images = self._extract_images_with_playwright(url_clean)
            elif desc:
                images = self._extract_images_from_url(url_clean)

            print(f"✅ Scraping réussi pour: {url_clean} ({len(desc)} caractères, {len(images)} image(s))")
            return {
                "url": url_clean,
                "content": desc,
                "images": images[:5] if images else []
            }

        print(f"❌ Échec du scraping pour: {url_clean} (toutes les méthodes ont échoué)")
        return None

    def _get_website_descriptions(self, urls):
        """
        Récupère les descriptions de plusieurs sites web EN PARALLÈLE.
        Utilise ThreadPoolExecutor pour scraper toutes les URLs simultanément.
        """
        descriptions = []
        failed_urls = []

        # Filtrer les URLs valides (doit ressembler à une URL, pas du texte libre)
        def _is_valid_url(u):
            u = u.strip()
            if not u:
                return False
            if u.startswith(('http://', 'https://')):
                return True
            # Accepter si ça ressemble à un domaine (contient un point, pas d'espaces)
            if '.' in u and ' ' not in u:
                return True
            print(f"⚠️ URL ignorée (pas une URL valide) : '{u}'")
            return False

        valid_urls = [url.strip() for url in urls if _is_valid_url(url)]

        if not valid_urls:
            return descriptions

        print(f"🚀 Scraping parallèle de {len(valid_urls)} URL(s)...")

        # Scraper toutes les URLs en parallèle (max 3 workers)
        with ThreadPoolExecutor(max_workers=min(3, len(valid_urls))) as executor:
            future_to_url = {
                executor.submit(self._scrape_single_url, url): url
                for url in valid_urls
            }

            for future in as_completed(future_to_url):
                url = future_to_url[future]
                try:
                    result = future.result()
                    if result:
                        descriptions.append(result)
                    else:
                        failed_urls.append(url)
                except Exception as e:
                    print(f"❌ Exception pour {url}: {e}")
                    failed_urls.append(url)

        if failed_urls:
            print(f"⚠️ {len(failed_urls)} URL(s) n'ont pas pu être scrappées: {', '.join(failed_urls)}")
            if not TAVILY_AVAILABLE:
                print(f"   💡 Astuce: Ajoutez TAVILY_API_KEY dans .env pour les sites JavaScript")

        print(f"✅ Scraping terminé: {len(descriptions)}/{len(valid_urls)} URL(s) réussies")
        return descriptions
    
    def _search_flights_with_airfrance_klm(self, origin_code, destination_code, travel_date, return_date=None, search_metadata=None):
        """
        Recherche de VRAIS vols avec l'API Air France-KLM.
        Retourne des vols réels avec horaires, numéros de vol, compagnies.
        Documentation: https://developer.airfranceklm.com/products/api/flightstatus/api-reference
        
        Args:
            origin_code: Code IATA de l'aéroport de départ (ex: 'CDG')
            destination_code: Code IATA de l'aéroport de destination (ex: 'DPS')
            travel_date: Date de voyage au format YYYY-MM-DD
            return_date: Date de retour au format YYYY-MM-DD (optionnel)
            search_metadata: Dict pour stocker les métadonnées de recherche (détails d'erreur API, etc.)
        """
        from django.conf import settings
        import time
        import random
        
        print("=" * 80)
        print("✈️✈️✈️ DÉBUT RECHERCHE AIR FRANCE-KLM API ✈️✈️✈️")
        print("=" * 80)
        
        api_key = getattr(settings, 'AIRFRANCE_KLM_API_KEY', None)
        
        if not api_key:
            print("❌❌❌ ERREUR: AIRFRANCE_KLM_API_KEY non configurée")
            if search_metadata is not None:
                search_metadata['failure_reason'] = ['credentials_missing']
            return None
        
        # Fonction pour faire des requêtes avec backoff exponentiel
        def make_api_request(url, params, headers, max_retries=3):
            for attempt in range(max_retries):
                try:
                    # Délai exponentiel avec jitter
                    if attempt > 0:
                        backoff_time = (2 ** attempt) + random.uniform(0, 1)
                        print(f"⏱️ Tentative {attempt+1}/{max_retries} - Attente de {backoff_time:.2f} secondes...")
                        time.sleep(backoff_time)
                    
                    print(f"📡 Requête vers {url}")
                    print(f"   - Paramètres: {params}")
                    print(f"   - Headers: {list(headers.keys())}")
                    
                    response = requests.get(url, params=params, headers=headers, timeout=30)
                    
                    print(f"📊 Code de statut: {response.status_code}")
                    if response.status_code == 200:
                        return response.json()
                    elif response.status_code == 403 and "Over Qps" in response.text:
                        print(f"⚠️⚠️⚠️ ERREUR: 'Developer Over Qps' - Trop de requêtes par seconde")
                    else:
                        print(f"❌ Erreur API: {response.status_code} - {response.text[:200]}")
                        if search_metadata is not None:
                            search_metadata['failure_reason'] = ['api_error']
                            search_metadata['api_error'] = {
                                'status_code': response.status_code,
                                'error_message': response.text[:200]
                            }
                        
                except Exception as e:
                    print(f"❌ Exception lors de la requête: {str(e)}")
                    
                # Si nous arrivons ici, c'est que la requête a échoué
                if attempt == max_retries - 1:
                    return None
            
            return None
        
        print(f"📋 Paramètres de recherche:")
        print(f"   - Origin: {origin_code}")
        print(f"   - Destination: {destination_code}")
        print(f"   - Date aller: {travel_date}")
        if return_date:
            print(f"   - Date retour: {return_date}")
        print()
        
        # PRIORITÉ ABSOLUE : API Offers uniquement (pas FlightStatus)
        # Documentation: https://developer.airfranceklm.com/products/api/offers/api-reference/paths/opendata-offers-v3-available-offers/post
        print("\n🔍 RECHERCHE EXCLUSIVE AVEC API OFFERS v3/available-offers...")
        
        # L'endpoint correct est /opendata/offers/v3/available-offers (POST uniquement)
        offers_url = "https://api.airfranceklm.com/opendata/offers/v3/available-offers"
        
        # Construire le body selon la documentation
        # Structure: requestedConnections avec origin/destination en objets
        requested_connections = [
            {
                "departureDate": travel_date,
                "origin": {
                    "code": origin_code,
                    "type": "STOPOVER"
                },
                "destination": {
                    "code": destination_code,
                    "type": "STOPOVER"
                }
            }
        ]
        
        # Si date retour, ajouter la connection retour
        if return_date:
            requested_connections.append({
                "departureDate": return_date,
                "origin": {
                    "code": destination_code,
                    "type": "STOPOVER"
                },
                "destination": {
                    "code": origin_code,
                    "type": "STOPOVER"
                }
            })
        
        # Body selon la documentation
        offers_body = {
            "commercialCabins": ["ALL"],
            "bookingFlow": "LEISURE",
            "passengers": [
                {
                    "id": 1,
                    "type": "ADT"
                }
            ],
            "requestedConnections": requested_connections
        }
        
        # Headers selon la documentation (Content-Type: application/hal+json)
        offers_headers = {
            "API-Key": api_key,
            "AFKL-TRAVEL-Host": "KL",  # Ou "AF" pour Air France
            "Accept": "application/hal+json",
            "Content-Type": "application/hal+json"  # IMPORTANT: hal+json selon la doc
        }
        
        print(f"\n   🔍 POST vers {offers_url}")
        print(f"   📋 Body: {json.dumps(offers_body, indent=2)}")
        
        offers_response = None
        try:
            # Utiliser data= avec json.dumps pour avoir application/hal+json
            response = requests.post(
                offers_url,
                data=json.dumps(offers_body),  # Envoyer comme string JSON
                headers=offers_headers,
                timeout=30
            )
            print(f"   📊 Code de statut: {response.status_code}")
            
            if response.status_code == 200:
                offers_response = response.json()
                print(f"   ✅ Réponse reçue avec succès!")
            elif response.status_code == 404:
                print(f"   ❌ Endpoint 404 - vérifiez que l'endpoint est correct")
                print(f"   📋 Réponse: {response.text[:500]}")
            elif response.status_code == 403:
                print(f"   ⚠️ Erreur 403 - vérifiez vos credentials")
                print(f"   📋 Réponse: {response.text[:500]}")
            else:
                print(f"   ❌ Erreur {response.status_code}: {response.text[:500]}")
        except Exception as e:
            print(f"   ❌ Exception: {type(e).__name__}: {str(e)[:200]}")
        
        if offers_response:
            print("✅ Réponse de l'API Offers v3 reçue!")
            print(f"   📋 Structure réponse: {list(offers_response.keys())[:10]}")
            
            # Traiter la réponse HAL+JSON selon la documentation
            # La réponse contient: recommendations, flightProducts, connections, etc.
            flights = []
            
            # Chercher dans recommendations (première option)
            recommendations = offers_response.get('recommendations', [])
            if recommendations:
                print(f"📋 {len(recommendations)} recommandation(s) trouvée(s)")
                for rec_idx, rec in enumerate(recommendations[:3], 1):  # Prendre les 3 premiers
                    print(f"   🔍 Traitement recommandation {rec_idx}...")
                    
                    # Les flightProducts contiennent les connections
                    flight_products = rec.get('flightProducts', [])
                    if flight_products:
                        print(f"      📋 {len(flight_products)} flightProduct(s) dans cette recommandation")
                        for product_idx, product in enumerate(flight_products[:2], 1):  # Prendre les 2 premiers products
                            print(f"         🔍 Traitement flightProduct {product_idx}...")
                            
                            # Les connections sont dans le flightProduct
                            connections = product.get('connections', [])
                            if connections:
                                print(f"            📋 {len(connections)} connection(s) dans ce product")
                                # connections est un tableau de tableaux (une connection par direction)
                                for conn_group_idx, conn_group in enumerate(connections):
                                    if isinstance(conn_group, list):
                                        for conn_idx, connection in enumerate(conn_group[:1], 1):
                                            print(f"               🔍 Extraction connection {conn_group_idx}-{conn_idx}...")
                                            flight_info = self._extract_flight_info_from_offer_response(connection, origin_code, destination_code)
                                            if flight_info:
                                                print(f"                  ✅ Vol extrait: {flight_info['flight_number']}")
                                                flights.append(flight_info)
                                    elif isinstance(conn_group, dict):
                                        print(f"               🔍 Extraction connection {conn_group_idx}...")
                                        flight_info = self._extract_flight_info_from_offer_response(conn_group, origin_code, destination_code)
                                        if flight_info:
                                            print(f"                  ✅ Vol extrait: {flight_info['flight_number']}")
                                            flights.append(flight_info)
                    
                    # Si pas de flightProducts, essayer directement les connections dans la recommendation
                    if not flights:
                        connections = rec.get('connections', [])
                        if connections:
                            print(f"      📋 {len(connections)} connection(s) directe(s) dans cette recommandation")
                            for conn_group in connections:
                                if isinstance(conn_group, list):
                                    for connection in conn_group[:1]:
                                        flight_info = self._extract_flight_info_from_offer_response(connection, origin_code, destination_code)
                                        if flight_info:
                                            flights.append(flight_info)
                                elif isinstance(conn_group, dict):
                                    flight_info = self._extract_flight_info_from_offer_response(conn_group, origin_code, destination_code)
                                    if flight_info:
                                        flights.append(flight_info)
            
            # Si pas de recommendations, chercher dans flightProducts directement
            if not flights:
                flight_products = offers_response.get('flightProducts', [])
                if flight_products:
                    print(f"📋 {len(flight_products)} flightProduct(s) trouvé(s)")
                    for product in flight_products[:3]:
                        flight_info = self._extract_flight_info_from_offer_response(product, origin_code, destination_code)
                        if flight_info:
                            flights.append(flight_info)
            
            # Fallback: chercher dans connections directement (au niveau supérieur de la réponse)
            if not flights:
                connections = offers_response.get('connections', [])
                if connections:
                    print(f"📋 {len(connections)} connection(s) trouvée(s) au niveau supérieur")
                    # Afficher la structure complète d'une connection pour debug
                    if connections and len(connections) > 0:
                        first_conn = connections[0]
                        if isinstance(first_conn, list) and len(first_conn) > 0:
                            first_conn = first_conn[0]
                        print(f"   📋 Structure première connection (complète): {json.dumps(first_conn, indent=2)[:1500]}")
                    
                    for conn_idx, conn in enumerate(connections[:2], 1):  # Prendre les 2 premières
                        if isinstance(conn, list):
                            for c_idx, c in enumerate(conn[:2], 1):
                                print(f"   🔍 Extraction connection top-level {conn_idx}-{c_idx}...")
                                flight_info = self._extract_flight_info_from_offer_response(c, origin_code, destination_code)
                                if flight_info:
                                    flights.append(flight_info)
                        else:
                            print(f"   🔍 Extraction connection top-level {conn_idx}...")
                            flight_info = self._extract_flight_info_from_offer_response(conn, origin_code, destination_code)
                            if flight_info:
                                flights.append(flight_info)
            
            # Si toujours pas de vols, chercher dans _links (HAL+JSON peut avoir des liens vers les détails)
            if not flights and offers_response.get('_links'):
                print(f"📋 _links trouvé - les détails des vols peuvent être dans les liens HAL+JSON")
                links = offers_response['_links']
                print(f"   📋 Clés dans _links: {list(links.keys())[:10]}")
                # Note: Suivre les liens nécessiterait des requêtes supplémentaires
                # Pour l'instant on ne le fait pas, mais on peut logger les URLs disponibles
            
            if flights:
                print(f"✅ {len(flights)} vol(s) extrait(s) depuis l'API Offers")
                return flights
            else:
                print(f"⚠️ Aucun vol extrait - structure de réponse inattendue")
                # Sauvegarder la réponse complète dans un fichier pour debug
                try:
                    debug_file = '/tmp/airfrance_klm_response_debug.json'
                    with open(debug_file, 'w', encoding='utf-8') as f:
                        json.dump(offers_response, f, indent=2, ensure_ascii=False)
                    print(f"   💡 Réponse complète sauvegardée dans {debug_file} pour analyse")
                except Exception as e:
                    print(f"   ⚠️ Impossible de sauvegarder: {str(e)}")
                print(f"   📋 Réponse complète (premiers 3000 chars): {json.dumps(offers_response, indent=2)[:3000]}")
        
        # Si toutes les tentatives Offers échouent
        print("\n❌ Aucun vol trouvé avec l'API Offers")
        if offers_response:
            print("⚠️⚠️⚠️ L'API a retourné une réponse mais aucun vol n'a pu être extrait")
            print("💡 La structure de la réponse peut être différente de celle attendue")
            print("💡 Vérifiez les logs ci-dessus pour voir la structure exacte de la réponse")
        else:
            print("⚠️⚠️⚠️ L'API Offers n'a pas retourné de réponse valide")
            print("💡 Vérifiez vos credentials et que l'endpoint est correct")
        
        # NE PLUS UTILISER FlightStatus - uniquement Offers
        if search_metadata is not None:
            if offers_response:
                search_metadata['failure_reason'] = ['offers_api_responded_but_no_flights_extracted']
            else:
                search_metadata['failure_reason'] = ['offers_api_failed', 'no_response']
        print("=" * 80)
        return None
        
    def _extract_flight_info_from_offer_response(self, connection_or_product, origin_code, destination_code):
        """
        Extrait les informations de vol depuis une connection ou flightProduct de la réponse Offers API.
        Structure attendue (d'après les logs) :
        - segments[].marketingFlight.number
        - segments[].departureDateTime
        - segments[].arrivalDateTime
        - segments[].origin.code
        - segments[].destination.code
        - segments[].marketingFlight.carrier.name/code
        """
        try:
            # Structure HAL+JSON peut varier, essayer plusieurs formats
            flight_number = None
            airline_name = "Air France-KLM"
            departure_airport = origin_code
            departure_time = None
            arrival_airport = destination_code
            arrival_time = None
            
            # Extraire depuis segments (structure Offers API avec marketingFlight)
            segments = connection_or_product.get('flightSegments', []) or connection_or_product.get('segments', [])
            if segments:
                # Prendre le premier segment pour départ et dernier pour arrivée
                first_segment = segments[0] if segments else {}
                last_segment = segments[-1] if segments else first_segment
                
                # IMPORTANT: Structure Offers API utilise marketingFlight.number (pas flightNumber)
                # Format: marketingFlight: {number: "2016", carrier: {code: "KL", name: "KLM"}}
                marketing_flight = first_segment.get('marketingFlight', {})
                if isinstance(marketing_flight, dict):
                    flight_num = marketing_flight.get('number')
                    carrier = marketing_flight.get('carrier', {})
                    carrier_code = None
                    if isinstance(carrier, dict):
                        airline_name = carrier.get('name', carrier.get('code', 'Air France-KLM'))
                        carrier_code = carrier.get('code')
                    
                    # Formater le numéro de vol avec le code compagnie (ex: KL2016)
                    if flight_num and carrier_code:
                        flight_number = f"{carrier_code}{flight_num}"
                    elif flight_num:
                        flight_number = str(flight_num)
                    
                    # Si pas de flightNumber, essayer operatingFlight
                    if not flight_number:
                        operating_flight = first_segment.get('operatingFlight', {})
                        if isinstance(operating_flight, dict):
                            flight_num = operating_flight.get('number')
                            op_carrier = operating_flight.get('carrier', {})
                            if isinstance(op_carrier, dict):
                                op_carrier_code = op_carrier.get('code')
                                if flight_num and op_carrier_code:
                                    flight_number = f"{op_carrier_code}{flight_num}"
                                elif flight_num:
                                    flight_number = str(flight_num)
                                if not airline_name or airline_name == 'Air France-KLM':
                                    airline_name = op_carrier.get('name', op_carrier.get('code', 'Air France-KLM'))
                
                # Si toujours pas de flightNumber, essayer les autres formats
                if not flight_number:
                    flight_number = (
                        first_segment.get('flightNumber') or 
                        first_segment.get('number') or 
                        first_segment.get('flight', {}).get('number') if isinstance(first_segment.get('flight'), dict) else None
                    )
                
                # Départ depuis le premier segment
                # Format Offers API: origin: {code: "CDG"}, departureDateTime: "2025-11-23T16:55:00"
                origin_info = first_segment.get('origin', {})
                if isinstance(origin_info, dict):
                    departure_airport = origin_info.get('code') or origin_info.get('iata') or origin_code
                
                # Départ time depuis departureDateTime
                departure_time = first_segment.get('departureDateTime') or first_segment.get('departure') or first_segment.get('departureInformation', {}).get('datetime')
                if not departure_time and isinstance(first_segment.get('departure'), dict):
                    departure_time = first_segment['departure'].get('datetime') or first_segment['departure'].get('time') or first_segment['departure'].get('scheduled')
                
                # Arrivée depuis le dernier segment
                destination_info = last_segment.get('destination', {})
                if isinstance(destination_info, dict):
                    arrival_airport = destination_info.get('code') or destination_info.get('iata') or destination_code
                
                # Arrivée time depuis arrivalDateTime
                arrival_time = last_segment.get('arrivalDateTime') or last_segment.get('arrival') or last_segment.get('arrivalInformation', {}).get('datetime')
                if not arrival_time and isinstance(last_segment.get('arrival'), dict):
                    arrival_time = last_segment['arrival'].get('datetime') or last_segment['arrival'].get('time') or last_segment['arrival'].get('scheduled')
            
            # Format 2: champs directs dans connection/product (fallback)
            if not flight_number:
                flight_number = (
                    connection_or_product.get('flightNumber') or 
                    connection_or_product.get('number') or
                    connection_or_product.get('flight', {}).get('number') if isinstance(connection_or_product.get('flight'), dict) else None
                )
            
            # Compagnie depuis connection/product (fallback)
            if airline_name == 'Air France-KLM':
                airline_info = connection_or_product.get('airline') or connection_or_product.get('flight', {}).get('airline')
                if airline_info:
                    if isinstance(airline_info, dict):
                        airline_name = airline_info.get('name', 'Air France-KLM')
                    else:
                        airline_name = airline_info
            
            # Formater le temps si nécessaire
            if departure_time:
                dt = self._parse_iso_datetime(departure_time)
                departure_time = dt.strftime('%Y-%m-%d %H:%M') if dt else str(departure_time)
            else:
                departure_time = 'N/A'
            
            if arrival_time:
                dt = self._parse_iso_datetime(arrival_time)
                arrival_time = dt.strftime('%Y-%m-%d %H:%M') if dt else str(arrival_time)
            else:
                arrival_time = 'N/A'
            
            if flight_number:
                return {
                    'flight_number': str(flight_number),
                    'airline': airline_name,
                    'departure_airport': departure_airport,
                    'departure_time': departure_time,
                    'arrival_airport': arrival_airport,
                    'arrival_time': arrival_time
                }
            return None
        except Exception as e:
            print(f"   ⚠️ Erreur extraction info vol: {type(e).__name__}: {str(e)[:200]}")
            import traceback
            print(f"   📋 Traceback: {traceback.format_exc()[:500]}")
            return None
    
    def _parse_iso_datetime(self, datetime_str):
        """
        Parse une chaîne de date/heure ISO 8601 en objet datetime.
        Gère les fuseaux horaires.
        """
        try:
            import dateutil.parser
            
            dt = dateutil.parser.parse(datetime_str)
            return dt
        except Exception as e:
            print(f"❌ Erreur lors du parsing de la date: {str(e)}")
            return None
    
    def _search_flights_with_aviationstack(self, origin_code, destination_code, travel_date, return_date=None):
        """
        Recherche de VRAIS vols avec Aviationstack API (FALLBACK).
        Retourne des vols réels avec horaires, numéros de vol, compagnies, prix.
        """
        from django.conf import settings
        
        api_key = getattr(settings, 'AVIATIONSTACK_API_KEY', None)
        if not api_key:
            print("⚠️ AVIATIONSTACK_API_KEY non configurée - fallback désactivé")
            return None
        
        try:
            print(f"✈️ Recherche de VRAIS vols avec Aviationstack: {origin_code} → {destination_code}")
            print(f"   Date aller: {travel_date}")
            if return_date:
                print(f"   Date retour: {return_date}")
            
            # API Aviationstack pour chercher des vols réels
            base_url = "http://api.aviationstack.com/v1/flights"
            
            flights_data = []
            
            # Rechercher le vol aller
            params = {
                'access_key': api_key,
                'dep_iata': origin_code,
                'arr_iata': destination_code,
                'flight_date': travel_date,  # Format YYYY-MM-DD
            }
            
            print(f"   📡 Requête API Aviationstack pour vol aller...")
            response = requests.get(base_url, params=params, timeout=15)
            
            print(f"   📊 Code de statut: {response.status_code}")
            
            if response.status_code == 200:
                data = response.json()
                
                # Vérifier les erreurs de l'API
                if data.get('error'):
                    error_info = data.get('error', {})
                    print(f"   ❌ Erreur API Aviationstack: {error_info.get('message', 'Erreur inconnue')}")
                    if error_info.get('code') == 104:
                        print(f"   ⚠️ Limite de requêtes mensuelle atteinte (500 requêtes gratuites)")
                    elif error_info.get('code') == 101:
                        print(f"   ⚠️ Clé API invalide - vérifiez AVIATIONSTACK_API_KEY dans .env")
                    return None
                
                if data.get('data') and len(data['data']) > 0:
                    print(f"   ✅ {len(data['data'])} vol(s) RÉEL(S) trouvé(s) pour {origin_code} → {destination_code}")
                    
                    # Prendre les 3 premiers vols (directs de préférence)
                    for flight in data['data'][:3]:
                        flight_info = {
                            'flight_number': flight.get('flight', {}).get('number', 'N/A'),
                            'airline': flight.get('airline', {}).get('name', 'N/A'),
                            'departure_airport': flight.get('departure', {}).get('iata', origin_code),
                            'departure_time': flight.get('departure', {}).get('scheduled', 'N/A'),
                            'arrival_airport': flight.get('arrival', {}).get('iata', destination_code),
                            'arrival_time': flight.get('arrival', {}).get('scheduled', 'N/A'),
                            'status': flight.get('flight_status', 'scheduled'),
                            'is_direct': not flight.get('departure', {}).get('airport', '') != flight.get('arrival', {}).get('airport', ''),
                        }
                        flights_data.append(flight_info)
                        print(f"      ✈️ Vol trouvé: {flight_info['airline']} {flight_info['flight_number']} - {flight_info['departure_time']} → {flight_info['arrival_time']}")
                else:
                    print(f"   ⚠️ Aucun vol trouvé dans la réponse Aviationstack pour {origin_code} → {destination_code}")
            else:
                error_text = response.text[:500] if hasattr(response, 'text') else str(response)
                print(f"   ❌ Erreur API Aviationstack (HTTP {response.status_code}): {error_text}")
                try:
                    error_data = response.json()
                    if error_data.get('error'):
                        print(f"   📋 Détails: {error_data.get('error')}")
                except:
                    pass
            
            # Rechercher le vol retour si date retour fournie
            if return_date and flights_data:
                params_return = {
                    'access_key': api_key,
                    'dep_iata': destination_code,
                    'arr_iata': origin_code,
                    'flight_date': return_date,
                }
                
                print(f"   📡 Requête API Aviationstack pour vol retour...")
                response_return = requests.get(base_url, params=params_return, timeout=15)
                
                if response_return.status_code == 200:
                    data_return = response_return.json()
                    if data_return.get('data') and len(data_return['data']) > 0:
                        # Prendre le premier vol retour
                        flight_return = data_return['data'][0]
                        return_flight_info = {
                            'flight_number': flight_return.get('flight', {}).get('number', 'N/A'),
                            'airline': flight_return.get('airline', {}).get('name', 'N/A'),
                            'departure_airport': flight_return.get('departure', {}).get('iata', destination_code),
                            'departure_time': flight_return.get('departure', {}).get('scheduled', 'N/A'),
                            'arrival_airport': flight_return.get('arrival', {}).get('iata', origin_code),
                            'arrival_time': flight_return.get('arrival', {}).get('scheduled', 'N/A'),
                            'status': flight_return.get('flight_status', 'scheduled'),
                        }
                        flights_data.append(return_flight_info)
                        print(f"      ✈️ Vol retour trouvé: {return_flight_info['airline']} {return_flight_info['flight_number']}")
            
            if flights_data:
                print(f"✅ {len(flights_data)} vol(s) RÉEL(S) obtenu(s) depuis Aviationstack")
                return flights_data
            else:
                print("⚠️ Aucun vol trouvé avec Aviationstack")
                return None
                
        except Exception as e:
            print(f"❌ Erreur recherche vols Aviationstack: {type(e).__name__}: {str(e)}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()[:300]}")
            return None
    
    def _search_flights_smart(self, flight_input, search_metadata=None):
        """
        Recherche intelligente de vols avec parsing automatique (GDS, numéro de vol, texte libre).
        Remplace l'ancienne fonction Air France-KLM.
        
        Args:
            flight_input: Texte saisi par l'utilisateur (format libre)
            search_metadata: Dict pour stocker les métadonnées
        
        Returns:
            Liste de dicts avec les vols trouvés ou None
        """
        from api.smart_flight_search import SmartFlightSearch
        from django.conf import settings
        
        if not flight_input:
            return None
        
        try:
            use_test = getattr(settings, 'AMADEUS_USE_TEST', True)
            smart_search = SmartFlightSearch(use_test=use_test)
            
            result = smart_search.search(flight_input)
            
            if search_metadata is not None:
                search_metadata['parsed_data'] = result.get('parsed_data')
                search_metadata['search_strategy'] = result.get('search_strategy')
                search_metadata['source'] = 'smart_search_amadeus'
                
                if result.get('flights_found'):
                    search_metadata['real_flights_count'] = len(result['flights_found'])
                    search_metadata['has_valid_flight_info'] = True
                else:
                    search_metadata['real_flights_count'] = 0
                    search_metadata['has_valid_flight_info'] = False
            
            return result.get('flights_found')
        
        except Exception as e:
            print(f"❌ Erreur recherche intelligente: {str(e)}")
            import traceback
            traceback.print_exc()
            if search_metadata:
                search_metadata['failure_reason'] = [f'smart_search_error: {str(e)}']
            return None
    
    def _extract_airport_codes(self, text_input, travel_date=None, for_origin=False):
        """
        Extrait les codes d'aéroport depuis le texte (ex: Paris → CDG, Bali → DPS)
        Si for_origin=True, extrait le code pour l'origine (première valeur du tuple)
        Si for_origin=False (défaut), extrait le code pour la destination (deuxième valeur du tuple)
        """
        # Mapping villes/destinations → codes IATA (plus complet et avec accents)
        # IMPORTANT: Trier par longueur décroissante pour détecter d'abord les noms les plus longs
        airport_codes = {
            # France
            'paris': 'CDG', 'cdg': 'CDG', 'orly': 'ORY', 'ory': 'ORY',
            # Belgique
            'belgique': 'BRU', 'bruxelles': 'BRU', 'brussels': 'BRU', 'bru': 'BRU',
            'charleroi': 'CRL', 'crl': 'CRL', 'liège': 'LGG', 'liege': 'LGG', 'lgg': 'LGG',
            'anvers': 'ANR', 'antwerp': 'ANR', 'anr': 'ANR',
            # Indonésie
            'bali': 'DPS', 'denpasar': 'DPS', 'dps': 'DPS', 'indonesie': 'DPS', 'indonésie': 'DPS',
            'jakarta': 'CGK', 'cgk': 'CGK', 'yogyakarta': 'YIA', 'yia': 'YIA',
            # Thaïlande
            'thailande': 'BKK', 'bangkok': 'BKK', 'bkk': 'BKK', 'thaïlande': 'BKK',
            'phuket': 'HKT', 'hkt': 'HKT', 'chiang mai': 'CNX', 'chiangmai': 'CNX', 'cnx': 'CNX',
            # Grèce
            'grèce': 'ATH', 'grece': 'ATH', 'athènes': 'ATH', 'athenes': 'ATH', 'ath': 'ATH',
            'mykonos': 'JMK', 'jmk': 'JMK', 'santorin': 'JTR', 'santorini': 'JTR', 'jtr': 'JTR',
            # Italie
            'italie': 'FCO', 'rome': 'FCO', 'fco': 'FCO', 'milan': 'MXP', 'mxp': 'MXP',
            'venise': 'VCE', 'venice': 'VCE', 'vce': 'VCE', 'florence': 'FLR', 'flr': 'FLR',
            # Espagne
            'espagne': 'MAD', 'madrid': 'MAD', 'mad': 'MAD', 'barcelone': 'BCN', 'bcn': 'BCN',
            'seville': 'SVQ', 'sevilla': 'SVQ', 'svq': 'SVQ', 'valencia': 'VLC', 'vlc': 'VLC',
            # Maroc
            'maroc': 'CMN', 'casablanca': 'CMN', 'cmn': 'CMN', 'marrakech': 'RAK', 'rak': 'RAK',
            'agadir': 'AGA', 'aga': 'AGA', 'tanger': 'TNG', 'tangier': 'TNG', 'tng': 'TNG',
            # Émirats
            'dubaï': 'DXB', 'dubai': 'DXB', 'dxb': 'DXB', 'abu dhabi': 'AUH', 'auh': 'AUH',
            # Japon
            'japon': 'NRT', 'tokyo': 'NRT', 'narita': 'NRT', 'nrt': 'NRT', 'osaka': 'KIX',
            # UK
            'londres': 'LHR', 'london': 'LHR', 'lhr': 'LHR',
            # Turquie
            'istanbul': 'IST', 'ist': 'IST',
            # USA
            'new york': 'JFK', 'jfk': 'JFK', 'nyc': 'JFK',
            # Autres destinations populaires
            'lisbonne': 'LIS', 'lis': 'LIS',
            'amsterdam': 'AMS', 'ams': 'AMS',
            'berlin': 'BER', 'ber': 'BER',
            'vienne': 'VIE', 'vie': 'VIE',
            'prague': 'PRG', 'prg': 'PRG',
            'budapest': 'BUD', 'bud': 'BUD',
            'venise': 'VCE', 'vce': 'VCE',
            'florence': 'FLR', 'flr': 'FLR',
            'naples': 'NAP', 'nap': 'NAP',
        }
        
        text_lower = text_input.lower()
        origin_code = 'CDG'  # Paris par défaut
        destination_code = None
        
        print(f"   🔍 Recherche de codes aéroport dans: '{text_input[:100]}'")
        
        # Trouver la ville/destination dans le texte
        city_matches = []
        for city, code in airport_codes.items():
            if city in text_lower:
                city_matches.append((city, code))
        
        # Trier par longueur (les noms plus longs sont plus spécifiques)
        city_matches.sort(key=lambda x: len(x[0]), reverse=True)
        
        if city_matches:
            # Prendre la première correspondance (la plus longue/specifique)
            matched_city, matched_code = city_matches[0]
            
            if for_origin:
                # Si on cherche l'origine, on retourne le code trouvé comme origine
                origin_code = matched_code
                print(f"   ✅ Origine détectée: '{matched_city}' → code aéroport {matched_code}")
            else:
                # Si on cherche la destination, on exclut Paris (c'est l'origine par défaut)
                if matched_city != 'paris' and matched_code != 'CDG':
                    destination_code = matched_code
                    print(f"   ✅ Destination détectée: '{matched_city}' → code aéroport {matched_code}")
                else:
                    print(f"   ⚠️ 'Paris' détecté mais c'est l'origine par défaut - pas de destination trouvée")
        else:
            if for_origin:
                print(f"   ⚠️ Aucune origine connue détectée dans le texte - utilisation de Paris (CDG) par défaut")
            else:
                print(f"   ❌ Aucune destination connue détectée dans le texte")
                print(f"   💡 Destinations supportées: belgique, bali, thailande, grèce, italie, espagne, maroc, dubaï, japon, londres, istanbul, new york, etc.")
        
        return origin_code, destination_code
    
    def _search_real_time_info(self, query, max_results=3):
        """
        Recherche d'informations en temps réel via Tavily (si disponible).
        Utile pour rechercher des vols, horaires, prix réels.
        """
        if not TAVILY_AVAILABLE:
            return None
        
        try:
            tavily_api_key = getattr(settings, 'TAVILY_API_KEY', None)
            if not tavily_api_key:
                print("⚠️ TAVILY_API_KEY non configurée dans settings.py")
                return None
            
            tavily = TavilyClient(api_key=tavily_api_key)
            response = tavily.search(
                query=query,
                search_depth="advanced",  # Recherche approfondie
                max_results=max_results,
                include_answer=True,
                include_raw_content=True
            )
            
            results = []
            if response.get('results'):
                for result in response['results'][:max_results]:
                    results.append({
                        "title": result.get('title', ''),
                        "url": result.get('url', ''),
                        "content": result.get('content', '')[:1000],  # Limiter à 1000 chars
                        "raw_content": result.get('raw_content', '')[:1500] if result.get('raw_content') else ''
                    })
            
            # Ajouter aussi la réponse générée par Tavily si disponible
            if response.get('answer'):
                results.append({
                    "title": "Réponse synthétisée",
                    "url": "",
                    "content": response['answer'],
                    "raw_content": ""
                })
            
            return results
        except Exception as e:
            print(f"❌ Erreur recherche Tavily: {str(e)}")
            return None
    
    def _scrape_hotels_search_results(self, url):
        """
        Scrape une page de RECHERCHE d'hôtels (plusieurs résultats) avec Playwright.
        Extrait les informations de plusieurs hôtels pour laisser ChatGPT choisir.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return None
        
        try:
            print(f"🏨 Scraping de RÉSULTATS DE RECHERCHE d'hôtels avec Playwright pour: {url}")
            
            with sync_playwright() as p:
                print(f"   🚀 Lancement du navigateur Chromium...")
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # User-Agent réaliste
                page.set_extra_http_headers({
                    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7',
                    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8'
                })
                
                print(f"   📡 Chargement de la page de recherche...")
                page.goto(url, wait_until='networkidle', timeout=20000)
                
                # Attendre plus longtemps pour que les résultats se chargent
                print(f"   ⏱️ Attente du chargement des résultats d'hôtels (8 secondes)...")
                page.wait_for_timeout(8000)
                
                # Extraire le contenu HTML complet
                content = page.content()
                
                # Prendre des screenshots pour debug si nécessaire (optionnel)
                # page.screenshot(path=f"debug_search_{int(time.time())}.png")
                
                browser.close()
                
                # Parser avec BeautifulSoup
                soup = BeautifulSoup(content, 'html.parser')
                
                # Supprimer les éléments inutiles
                for element in soup(["script", "style", "nav", "footer", "header"]):
                    element.decompose()
                
                # Extraire le texte complet (contient infos sur plusieurs hôtels)
                text_content = soup.get_text(separator=' ', strip=True)
                
                # Nettoyer
                lines = (line.strip() for line in text_content.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text_content = ' '.join(chunk for chunk in chunks if chunk)
                
                # Construire un résumé structuré pour ChatGPT
                result = f"""🏨 RÉSULTATS DE RECHERCHE D'HÔTELS (PLUSIEURS OPTIONS DISPONIBLES)

Cette page contient PLUSIEURS HÔTELS disponibles pour les dates recherchées. 
ChatGPT doit analyser ces options et choisir le(s) meilleur(s) pour le circuit.

📋 CONTENU EXTRAIT :
{text_content[:5000]}

💡 INSTRUCTIONS POUR CHATGPT :
- Plusieurs hôtels sont listés ci-dessus avec leurs caractéristiques (nom, prix, étoiles, équipements, localisation, notes)
- Analyse TOUTES les options disponibles
- Choisis le(s) meilleur(s) hôtel(s) en fonction du rapport qualité/prix, localisation, services
- Utilise les NOMS EXACTS, PRIX RÉELS, et DESCRIPTIONS EXACTES des hôtels mentionnés
- Si plusieurs hôtels sont intéressants pour différentes étapes du circuit, tu peux les utiliser tous
"""
                
                if text_content and len(text_content.strip()) > 200:
                    print(f"✅ Scraping recherche d'hôtels réussi: {len(text_content)} caractères")
                    preview = text_content[:300].replace('\n', ' ')
                    print(f"   📄 Preview: {preview}...")
                    return result
                else:
                    print(f"⚠️ Contenu recherche trop court: {len(text_content) if text_content else 0} caractères")
                    return None
                    
        except Exception as e:
            print(f"❌ Erreur scraping recherche d'hôtels: {type(e).__name__}: {str(e)}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()[:500]}")
            return None
    
    def _scrape_with_playwright(self, url):
        """
        Utilise Playwright (navigateur headless) pour scraper les sites JavaScript.
        Exécute le JavaScript et récupère le contenu rendu.
        
        DÉTECTE automatiquement si c'est une page de recherche (plusieurs hôtels)
        ou une page d'hôtel unique et adapte le scraping.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return None
        
        # 🔍 Détection automatique : Page de recherche vs Page unique
        is_search_page = any(indicator in url.lower() for indicator in [
            'redirect.htm', 'search', 'results', 'recherche', 'liste', 
            'toPolygonCode', 'startDate', 'endDate', 'nbAdults'
        ])
        
        if is_search_page:
            print(f"🔍 Détection : PAGE DE RECHERCHE (plusieurs hôtels) → Mode extraction multiple")
            return self._scrape_hotels_search_results(url)
        else:
            print(f"🔍 Détection : PAGE UNIQUE (hôtel spécifique) → Mode extraction classique")
        
        try:
            print(f"🌐 Tentative de scraping via Playwright (navigateur headless) pour: {url}")
            
            with sync_playwright() as p:
                print(f"   🚀 Lancement du navigateur Chromium...")
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                
                # Définir un User-Agent réaliste
                page.set_extra_http_headers({
                    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7'
                })
                
                print(f"   📡 Chargement de la page: {url}")
                # Attendre que le contenu soit chargé
                page.goto(url, wait_until='networkidle', timeout=10000)

                # Attendre un peu pour que le JavaScript se charge
                page.wait_for_timeout(1000)  # 1 seconde supplémentaire
                
                # Extraire le contenu texte
                print(f"   📄 Extraction du contenu...")
                content = page.content()
                
                # Parser avec BeautifulSoup pour extraire le texte proprement
                soup = BeautifulSoup(content, 'html.parser')

                # Supprimer les scripts et styles
                for script in soup(["script", "style", "nav", "footer", "header", "noscript", "aside"]):
                    script.decompose()

                # Extraire meta/og description
                meta_desc = ""
                for meta_attr in [("property", "og:description"), ("name", "description")]:
                    tag = soup.find("meta", {meta_attr[0]: meta_attr[1]})
                    if tag and tag.get("content"):
                        meta_desc = tag.get("content", "").strip()
                        break

                og_title = ""
                og_title_tag = soup.find("meta", property="og:title")
                if og_title_tag and og_title_tag.get("content"):
                    og_title = og_title_tag.get("content", "").strip()
                elif soup.title and soup.title.string:
                    og_title = soup.title.string.strip()

                # Cibler le contenu principal
                main_content = (
                    soup.find("main") or
                    soup.find("article") or
                    soup.find(attrs={"role": "main"}) or
                    soup.find(id=lambda x: x and any(k in x.lower() for k in ["main", "content", "body"])) or
                    soup.find(class_=lambda x: x and any(k in " ".join(x).lower() for k in ["main-content", "page-content", "hotel-detail", "property-detail"]))
                )
                if main_content:
                    text_content = main_content.get_text(separator=' ', strip=True)
                else:
                    text_content = soup.get_text(separator=' ', strip=True)

                # Nettoyer le texte
                lines = (line.strip() for line in text_content.splitlines())
                chunks = (phrase.strip() for line in lines for phrase in line.split("  "))
                text_content = ' '.join(chunk for chunk in chunks if chunk)

                # Combiner
                full_content = ""
                if og_title:
                    full_content += f"Titre: {og_title}\n"
                if meta_desc:
                    full_content += f"Description: {meta_desc}\n\n"
                full_content += text_content
                
                browser.close()
                
                if full_content and len(full_content.strip()) > 50:
                    print(f"✅ Scraping Playwright réussi: {len(full_content)} caractères")
                    preview = full_content[:200].replace('\n', ' ')
                    print(f"   📄 Preview: {preview}...")
                    return full_content[:6000] if len(full_content) > 6000 else full_content
                else:
                    print(f"⚠️ Contenu Playwright trop court: {len(full_content) if full_content else 0} caractères")
                    return None
                    
        except Exception as e:
            print(f"❌ Erreur scraping Playwright pour {url}: {type(e).__name__}: {str(e)}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()[:500]}")
            return None
    
    def _extract_images_with_playwright(self, url):
        """
        Extrait les URLs des images depuis une page avec Playwright.
        DÉTECTE automatiquement si c'est une page de recherche ou page unique.
        """
        if not PLAYWRIGHT_AVAILABLE:
            return []
        
        # Détection automatique du type de page
        is_search_page = any(indicator in url.lower() for indicator in [
            'redirect.htm', 'search', 'results', 'recherche', 'liste', 
            'toPolygonCode', 'startDate', 'endDate', 'nbAdults'
        ])
        
        limit = 20 if is_search_page else 10  # Plus d'images pour les pages de recherche
        wait_time = 8000 if is_search_page else 2000  # Attendre plus longtemps pour recherche
        
        try:
            print(f"   🖼️ Extraction des images avec Playwright...")
            if is_search_page:
                print(f"   🏨 Page de recherche détectée → Extraction de {limit} images (plusieurs hôtels)")
            
            images = []
            
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.set_extra_http_headers({
                    'Accept-Language': 'fr-FR,fr;q=0.9,en-US;q=0.8,en;q=0.7'
                })
                
                page.goto(url, wait_until='networkidle', timeout=45000)
                page.wait_for_timeout(wait_time)
                
                # Extraire toutes les images
                img_elements = page.query_selector_all('img')
                
                for img in img_elements:
                    src = img.get_attribute('src')
                    if not src:
                        # Essayer data-src (lazy loading)
                        src = img.get_attribute('data-src')
                    if not src:
                        # Essayer data-lazy-src
                        src = img.get_attribute('data-lazy-src')
                    
                    if src:
                        # Convertir les URLs relatives en absolues
                        if src.startswith('//'):
                            src = 'https:' + src
                        elif src.startswith('/'):
                            from urllib.parse import urljoin
                            src = urljoin(url, src)
                        elif not src.startswith('http'):
                            from urllib.parse import urljoin
                            src = urljoin(url, src)
                        
                        # Filtrer les images trop petites (icônes, logos, etc.)
                        try:
                            width = img.get_attribute('width')
                            height = img.get_attribute('height')
                            if width and height:
                                if int(width) < 100 or int(height) < 100:
                                    continue
                        except:
                            pass
                        
                        # Filtrer les images de tracking/pixel (moins strict pour pages de recherche)
                        skip_patterns = ['pixel', 'tracking', 'analytics', 'beacon']
                        if not is_search_page:
                            skip_patterns.extend(['logo', 'icon'])
                        
                        if any(skip in src.lower() for skip in skip_patterns):
                            continue
                        
                        images.append(src)
                
                browser.close()
                
            # Dédoublonner et limiter
            unique_images = list(dict.fromkeys(images))[:limit]
            print(f"   ✅ {len(unique_images)} image(s) extraite(s)")
            return unique_images
            
        except Exception as e:
            print(f"   ⚠️ Erreur extraction images Playwright: {str(e)}")
            return []
    
    def _extract_images_from_url(self, url):
        """
        Extrait les URLs des images depuis une page avec BeautifulSoup.
        Cherche dans: <img>, <noscript>, attributs data-*, background-image CSS
        """
        try:
            print(f"   🖼️ Extraction des images avec BeautifulSoup (mode amélioré)...")
            images = []
            
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            }
            response = requests.get(url, headers=headers, timeout=15, allow_redirects=True, verify=False)
            
            if response.status_code == 200:
                soup = BeautifulSoup(response.content, 'html.parser')
                from urllib.parse import urljoin
                import re
                
                # 1. Images classiques <img>
                img_tags = soup.find_all('img')
                for img in img_tags:
                    # Chercher dans tous les attributs data-* possibles
                    src = (img.get('src') or 
                           img.get('data-src') or 
                           img.get('data-lazy-src') or
                           img.get('data-original') or
                           img.get('data-srcset') or
                           img.get('data-image') or
                           img.get('data-img') or
                           img.get('data-url'))
                    
                    if src:
                        # Si c'est un srcset, prendre la première URL
                        if ' ' in str(src):
                            src = str(src).split(' ')[0].split(',')[0]
                        
                        images.append(str(src))
                
                # 2. Images dans <noscript> (fallback pour sites JavaScript)
                noscript_tags = soup.find_all('noscript')
                for noscript in noscript_tags:
                    noscript_soup = BeautifulSoup(str(noscript), 'html.parser')
                    for img in noscript_soup.find_all('img'):
                        src = img.get('src')
                        if src:
                            images.append(src)
                
                # 3. Background images dans style=""
                elements_with_style = soup.find_all(style=True)
                for element in elements_with_style:
                    style = element.get('style', '')
                    bg_images = re.findall(r'background-image:\s*url\(["\']?([^"\')]+)["\']?\)', style)
                    images.extend(bg_images)
                
                # 4. Normaliser toutes les URLs
                normalized_images = []
                for src in images:
                    if not src or len(src) < 5:
                        continue
                    
                    # Convertir les URLs relatives en absolues
                    if src.startswith('//'):
                        src = 'https:' + src
                    elif src.startswith('/'):
                        src = urljoin(url, src)
                    elif not src.startswith('http'):
                        src = urljoin(url, src)
                    
                    # Filtrer les images trop petites et de tracking
                    if any(skip in src.lower() for skip in ['pixel', 'tracking', 'analytics', 'beacon', 'logo', 'icon', '1x1', 'favicon']):
                        continue
                    
                    # Filtrer les images trop petites par dimensions dans l'URL
                    if re.search(r'[/_-](\d+)x(\d+)[._-]', src):
                        match = re.search(r'[/_-](\d+)x(\d+)[._-]', src)
                        width, height = int(match.group(1)), int(match.group(2))
                        if width < 200 or height < 200:
                            continue
                    
                    normalized_images.append(src)
            
                # Limiter à 10 images et dédoublonner
                unique_images = list(dict.fromkeys(normalized_images))[:10]
                
                if unique_images:
                    print(f"   ✅ {len(unique_images)} image(s) extraite(s) (img: {len(img_tags)}, noscript: {len(noscript_tags)}, style: {len(elements_with_style)})")
                else:
                    print(f"   ⚠️ Aucune image trouvée (img: {len(img_tags)}, noscript: {len(noscript_tags)}, style: {len(elements_with_style)})")
                    print(f"   💡 Ce site nécessite probablement JavaScript (Playwright) ou une API d'images (Unsplash)")
                
                return unique_images
            
        except Exception as e:
            print(f"   ⚠️ Erreur extraction images BeautifulSoup: {str(e)}")
            return []
    
    def _scrape_with_tavily(self, url):
        """
        Utilise Tavily pour extraire le contenu d'une URL spécifique.
        Utile pour les sites avec JavaScript ou protection anti-scraping.
        """
        if not TAVILY_AVAILABLE:
            return None
        
        try:
            tavily_api_key = getattr(settings, 'TAVILY_API_KEY', None)
            if not tavily_api_key:
                print(f"   ⚠️ TAVILY_API_KEY non configurée")
                return None
            
            print(f"🔍 Tentative de scraping via Tavily pour: {url}")
            tavily = TavilyClient(api_key=tavily_api_key)
            
            # Nettoyer l'URL si nécessaire (enlever certains paramètres qui peuvent poser problème)
            clean_url = url
            # Garder l'URL telle quelle pour Tavily car il peut gérer les query strings
            
            print(f"   📡 Appel API Tavily extract...")
            # Utiliser la méthode extract de Tavily qui gère mieux les sites JS
            response = tavily.extract(
                urls=[clean_url],
                extract_depth="advanced",
                format="text",
                include_raw_content=True,
                    timeout=30  # Timeout réduit pour éviter les blocages
            )
            
            print(f"   📥 Réponse Tavily reçue")
            
            if response and response.get('results') and len(response['results']) > 0:
                result = response['results'][0]
                content = result.get('raw_content') or result.get('content', '')
                
                # Afficher un preview du contenu
                if content:
                    preview = content[:200].replace('\n', ' ')
                    print(f"   📄 Preview du contenu: {preview}...")
                
                if content and len(content.strip()) > 50:
                    print(f"✅ Scraping Tavily réussi: {len(content)} caractères")
                    return content[:6000] if len(content) > 6000 else content
                else:
                    print(f"⚠️ Contenu Tavily trop court ou vide: {len(content) if content else 0} caractères")
            
            print(f"⚠️ Aucun résultat dans la réponse Tavily")
            return None
        except Exception as e:
            print(f"❌ Erreur scraping Tavily pour {url}: {type(e).__name__}: {str(e)}")
            import traceback
            print(f"   Traceback: {traceback.format_exc()[:500]}")
            return None
    
    def _extract_flight_info_from_text(self, text_input, travel_date=None, return_date=None):
        """
        Extrait les informations de vol depuis le texte (dates, destinations, etc.)
        pour déclencher une recherche en temps réel si nécessaire.
        Retourne un tuple (query, metadata) pour tracer ce qui a été recherché.
        """
        flight_keywords = ['vol', 'avion', 'aérien', 'départ', 'arrivée', 'compagnie']
        date_keywords = ['date', 'jour', 'mars', 'avril', 'mai', 'juin', 'juillet', 'août', 'septembre', 'octobre', 'novembre', 'décembre']
        
        has_flight = any(keyword in text_input.lower() for keyword in flight_keywords)
        has_date = any(keyword in text_input.lower() for keyword in date_keywords) or travel_date
        
        metadata = {
            'has_flight': has_flight,
            'has_date': has_date,
            'travel_date': travel_date,
            'return_date': return_date,
            'destinations': []
        }
        
        if has_flight and has_date:
            # Construire une query de recherche pour les vols
            # Extraire destination si possible
            destinations = []
            common_destinations = ['paris', 'bali', 'thailande', 'grèce', 'italie', 'espagne', 'maroc', 'tunisie', 'dubaï', 'japon', 'tokyo', 'new york', 'londres', 'rome', 'athènes', 'istanbul']
            for dest in common_destinations:
                if dest in text_input.lower():
                    destinations.append(dest)
            
            metadata['destinations'] = destinations
            
            # Construire la query avec la date si disponible
            query_parts = []
            if destinations:
                query_parts.append(f"vols {destinations[0]}")
            else:
                query_parts.append("vols")
            
            # Ajouter la date aller dans la recherche
            if travel_date:
                # Convertir la date au format lisible
                try:
                    from datetime import datetime
                    # Gérer différents formats de date
                    date_str_input = str(travel_date).strip()
                    print(f"   Formatage date aller: '{date_str_input}'")
                    
                    # Essayer différents formats
                    date_formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%dT%H:%M:%S']
                    date_obj = None
                    for fmt in date_formats:
                        try:
                            date_obj = datetime.strptime(date_str_input.split('T')[0], fmt)
                            break
                        except:
                            continue
                    
                    if date_obj:
                        # Utiliser les mois en français
                        months_fr = {
                            1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
                            5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
                            9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
                        }
                        date_str = f"{date_obj.day} {months_fr[date_obj.month]} {date_obj.year}"
                        query_parts.append(f"date {date_str}")
                        metadata['travel_date_formatted'] = date_str
                        print(f"   ✅ Date formatée: {date_str}")
                    else:
                        query_parts.append(f"date {travel_date}")
                        metadata['travel_date_formatted'] = travel_date
                        print(f"   ⚠️ Format non reconnu, utilisation brute: {travel_date}")
                except Exception as e:
                    print(f"   ❌ Erreur formatage date: {e}")
                    query_parts.append(f"date {travel_date}")
                    metadata['travel_date_formatted'] = travel_date
            
            # Ajouter la date retour si disponible
            if return_date:
                try:
                    from datetime import datetime
                    # Gérer différents formats de date
                    date_str_input = str(return_date).strip()
                    print(f"   Formatage date retour: '{date_str_input}'")
                    
                    # Essayer différents formats
                    date_formats = ['%Y-%m-%d', '%d/%m/%Y', '%m/%d/%Y', '%Y-%m-%dT%H:%M:%S']
                    date_obj = None
                    for fmt in date_formats:
                        try:
                            date_obj = datetime.strptime(date_str_input.split('T')[0], fmt)
                            break
                        except:
                            continue
                    
                    if date_obj:
                        # Utiliser les mois en français
                        months_fr = {
                            1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
                            5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
                            9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
                        }
                        date_str = f"{date_obj.day} {months_fr[date_obj.month]} {date_obj.year}"
                        query_parts.append(f"retour {date_str}")
                        metadata['return_date_formatted'] = date_str
                        print(f"   ✅ Date retour formatée: {date_str}")
                    else:
                        query_parts.append(f"retour {return_date}")
                        metadata['return_date_formatted'] = return_date
                except Exception as e:
                    print(f"   ❌ Erreur formatage date retour: {e}")
                    query_parts.append(f"retour {return_date}")
                    metadata['return_date_formatted'] = return_date
                query_parts.append("aller-retour")
            
            query_parts.append("horaires prix disponibilité")
            query = " ".join(query_parts)
            
            return query, metadata
        
        return None, metadata
    
    def _detect_scraped_prices(self, website_descriptions):
        """
        Détecte si le contenu scrapé contient de vraies informations de prix.
        Retourne (has_prices: bool, price_snippets: list[str])
        """
        import re
        price_patterns = [
            r'\d+\s*[€$£]',           # 450€, 450 €, 450$
            r'[€$£]\s*\d+',           # €450
            r'\d+\s*EUR',             # 450 EUR
            r'à partir de\s*\d+',     # à partir de 450
            r'par nuit',              # par nuit
            r'per night',             # per night
            r'nuit/personne',
            r'par personne',
            r'\d+\s*\/\s*nuit',       # 450/nuit
            r'tarif\s*:\s*\d+',
            r'prix\s*:\s*\d+',
        ]
        snippets = []
        for desc in (website_descriptions or []):
            content = desc.get('content', '').lower()
            for pattern in price_patterns:
                matches = re.findall(pattern, content, re.IGNORECASE)
                if matches:
                    snippets.extend(matches[:3])
            if snippets:
                break
        return bool(snippets), snippets[:5]

    def _get_prompt_circuit(self, text_input, website_descriptions=None, example_templates=None, travel_date=None, return_date=None, real_time_search=None, real_flights_context=None, offer_type="circuit"):
        """Prompt pour un Circuit (plusieurs jours avec itinéraire)"""

        # Détecter si le scraping a trouvé de vrais prix
        has_scraped_prices, price_snippets = self._detect_scraped_prices(website_descriptions)

        # Ajouter les descriptions des sites web si disponibles
        website_context = ""
        has_search_results = False
        
        if website_descriptions and len(website_descriptions) > 0:
            website_context = "\n\n📋📋📋 INFORMATIONS RÉCUPÉRÉES DEPUIS DES SITES WEB (CONTENU RÉEL - UTILISER EN PRIORITÉ ABSOLUE) :\n"
            for idx, desc in enumerate(website_descriptions, 1):
                website_context += f"\n--- Site {idx}: {desc.get('url', 'URL inconnue')} ---\n"
                content = desc.get('content', '')
                
                # Détecter si c'est une page de résultats de recherche
                if "RÉSULTATS DE RECHERCHE D'HÔTELS" in content or "PLUSIEURS OPTIONS DISPONIBLES" in content:
                    has_search_results = True
                    website_context += content[:5000] + "\n"  # Plus de caractères pour les pages de recherche
                else:
                    website_context += content[:5000] + "\n"

                # Ajouter les images si disponibles
                images = desc.get('images', [])
                if images:
                    image_limit = 10 if has_search_results else 5
                    website_context += f"\n🖼️ IMAGES DISPONIBLES DEPUIS CE SITE ({len(images)} image(s)):\n"
                    for img_idx, img_url in enumerate(images[:image_limit], 1):
                        website_context += f"- Image {img_idx}: {img_url}\n"
                    website_context += "\n⚠️ IMPORTANT : Ces images proviennent du site web. Tu peux les mentionner dans l'offre ou les utiliser pour enrichir les descriptions.\n"

            website_context += "\n🚨🚨🚨 CRITIQUE - UTILISATION DES SITES WEB :\n"
            website_context += "- Ces informations proviennent DIRECTEMENT du site web scrapé\n"
            
            if has_search_results:
                website_context += "\n🏨🏨🏨 PAGE DE RECHERCHE DÉTECTÉE (PLUSIEURS HÔTELS) :\n"
                website_context += "- Le site contient PLUSIEURS HÔTELS avec leurs caractéristiques (nom, prix, étoiles, localisation, équipements, notes)\n"
                website_context += "- ANALYSE toutes les options et CHOISIS le(s) meilleur(s) hôtel(s) pour ce circuit\n"
                website_context += "- Critères de sélection : rapport qualité/prix, emplacement, services, note des voyageurs\n"
                website_context += "- Utilise les NOMS EXACTS, PRIX RÉELS, ÉTOILES et DESCRIPTIONS des hôtels mentionnés\n"
                website_context += "- Pour un circuit multi-étapes, tu peux choisir PLUSIEURS hôtels différents si pertinent\n"
                website_context += "- NE CRÉE PAS d'hôtels fictifs - utilise UNIQUEMENT ceux listés dans les résultats\n"
            else:
                website_context += "- Utilise TOUTES les descriptions, détails, activités mentionnées sur le site\n"
            
            website_context += "- Si le site mentionne des temples, plages, activités spécifiques, utilise-les EXACTEMENT\n"
            website_context += "- Si le site mentionne des hôtels, zones, lieux spécifiques, utilise-les\n"
            website_context += "- Si le site mentionne des transferts, transport aéroport-hôtel, ou services de transport, utilise-les EXACTEMENT\n"
            website_context += "- Ne crée PAS de nouvelles descriptions - utilise celles du site scrapé\n"
            website_context += "- Les descriptions du site doivent apparaître dans ton offre, pas des descriptions inventées\n"
            website_context += "- Pour l'introduction, utilise les descriptions du site web, pas tes propres descriptions\n"
            website_context += "- Les images fournies peuvent être utilisées pour enrichir l'offre (mentionner leur contenu dans les descriptions)\n"
        elif website_descriptions is not None and len(website_descriptions) == 0:
            # Des URLs ont été fournies mais le scraping a échoué
            website_context = "\n\n⚠️ ATTENTION : Des URLs de sites web ont été fournies mais n'ont pas pu être scrappées (sites inaccessibles ou protection anti-scraping). Utilise les informations de recherche Tavily ou tes connaissances générales.\n"
        
        # Ajouter les dates explicites dans le prompt
        dates_context = ""
        if travel_date or return_date:
            dates_context = "\n\n📅📅📅 DATES DU VOYAGE (À UTILISER EXACTEMENT - NE PAS INVENTER) :\n"
            if travel_date:
                try:
                    from datetime import datetime
                    months_fr = {
                        1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
                        5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
                        9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
                    }
                    date_obj = datetime.strptime(str(travel_date).strip().split('T')[0], '%Y-%m-%d')
                    date_formatted = f"{date_obj.day} {months_fr[date_obj.month]} {date_obj.year}"
                    dates_context += f"- Date de départ : {date_formatted} ({travel_date})\n"
                except:
                    dates_context += f"- Date de départ : {travel_date}\n"
            if return_date:
                try:
                    from datetime import datetime
                    months_fr = {
                        1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
                        5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
                        9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
                    }
                    date_obj = datetime.strptime(str(return_date).strip().split('T')[0], '%Y-%m-%d')
                    date_formatted = f"{date_obj.day} {months_fr[date_obj.month]} {date_obj.year}"
                    dates_context += f"- Date de retour : {date_formatted} ({return_date})\n"
                except:
                    dates_context += f"- Date de retour : {return_date}\n"
            dates_context += "\n🚨🚨🚨 IMPORTANT : Utilise CES DATES EXACTEMENT pour les vols. Ne crée PAS de dates différentes. Les horaires de vol doivent correspondre à ces dates. Si tu mentionnes des dates dans l'offre, utilise celles-ci, pas d'autres dates.\n"
        
        # Ajouter les exemples de templates si disponibles
        templates_context = ""
        if example_templates:
            templates_context = "\n\n📝 EXEMPLES DE TEMPLATES À COPIER EXACTEMENT (STRUCTURE ET STYLE) :\n"
            for idx, template in enumerate(example_templates, 1):
                templates_context += f"\n--- Exemple Template {idx} ---\n"
                # Si c'est du JSON, on l'affiche tel quel, sinon on prend le texte
                if isinstance(template, dict):
                    templates_context += json.dumps(template, ensure_ascii=False, indent=2)[:2000] + "\n"
                else:
                    templates_context += str(template)[:2000] + "\n"
            templates_context += "\n⚠️⚠️⚠️ CRITIQUE : Copie EXACTEMENT la structure, le style, le format, et l'organisation de ces exemples. Utilise le même niveau de détail, les mêmes types de sections, et le même ton.\n"
        
        # Ajouter UNIQUEMENT les VRAIS vols d'Air France-KLM
        flights_context = ""
        if real_flights_context:
            flights_context = real_flights_context

        # Section retour dynamique
        has_retour = real_flights_context and '(RETOUR)' in real_flights_context
        retour_section_str = """,
    {{
      "id": "flights_retour",
      "type": "Flights",
      "title": "Vol Retour",
      "body": "Reprends EXACTEMENT les informations du VOL RETOUR de la section VOLS RÉELS. Numéro, compagnie, aéroports, horaires, durée, escales. N'invente rien."
    }}""" if has_retour else ""

        return f"""Crée une offre de CIRCUIT de plusieurs jours DÉTAILLÉE et PROFESSIONNELLE pour : {text_input}
{website_context}
{dates_context}
{templates_context}
{flights_context}

🚨🚨🚨 RÈGLES ABSOLUES :
1. Pour l'introduction : Si des informations de sites web ont été fournies ci-dessus, utilise-les EXACTEMENT. Copie les descriptions du site, ne crée pas tes propres descriptions.
2. Pour les dates : Utilise UNIQUEMENT les dates fournies dans la section "DATES DU VOYAGE" ci-dessus. N'invente PAS d'autres dates.
3. Pour les vols :
   - Si des VOLS RÉELS ont été fournis ci-dessus (section "VOLS RÉELS TROUVÉS"), utilise-les EXACTEMENT.
   - Si AUCUN vol réel n'a été fourni, n'invente PAS de numéros de vol fictifs.
4. Pour les transferts :
   - Si des informations de transferts ont été trouvées dans les sites web scrapés, utilise-les EXACTEMENT.
   - Si AUCUNE information de transfert n'a été trouvée, NE CRÉE PAS de section "Transferts".
5. Pour les prix d'hébergement et de séjour :
{"   - Des prix RÉELS ont été trouvés dans le contenu scrapé : " + str(price_snippets) + ". Utilise UNIQUEMENT ces prix." if has_scraped_prices else "   - AUCUN prix réel n'a été trouvé dans le contenu scrapé."}
{"   - Utilise les prix tels qu'ils apparaissent dans les données scrapées ci-dessus." if has_scraped_prices else "   - N'INVENTE PAS de prix d'hôtel, de tarif par nuit ou de prix de séjour."}
{"" if has_scraped_prices else "   - Pour toute mention de prix, écris : 'Prix à confirmer avec l'établissement / l'agence.'"}
{"" if has_scraped_prices else "   - N'écris PAS de montants en euros (ex: 1 200€, 850€/nuit) si tu ne les as pas dans le contenu scrapé."}

Format JSON strict :
{{
  "title": "Titre accrocheur et mémorable pour le circuit",
  "introduction": "Description complète et engageante du circuit (3-4 phrases). Utilise les descriptions des sites web si fournies.",
  "sections": [
    {{
      "id": "flights_aller",
      "type": "Flights",
      "title": "Vol Aller",
      "body": "Reprends EXACTEMENT les informations du VOL ALLER de la section VOLS RÉELS. N'invente pas de numéros de vol ni d'horaires."
    }}{retour_section_str},
    {{
      "id": "transfers",
      "type": "Transfers",
      "title": "Transferts & Transport",
      "body": "Transferts trouvés dans les sites web scrapés uniquement. Omets cette section si aucune info de transfert n'est disponible."
    }},
    {{
      "id": "itinerary",
      "type": "Itinéraire",
      "title": "Programme du Circuit",
      "body": "Itinéraire JOUR PAR JOUR basé sur les informations scrapées. Activités, visites, repas inclus, hébergements."
    }},
    {{
      "id": "hotel",
      "type": "Hotel",
      "title": "Hébergement",
      "body": "{"Nom, catégorie, localisation, équipements et prix des hôtels TELS QUE FOURNIS dans le contenu scrapé." if has_scraped_prices else "Nom, catégorie, localisation et équipements des hôtels si mentionnés dans le contenu scrapé. Pour les prix : écrire 'Prix à confirmer avec l établissement.' Ne pas inventer de tarif par nuit."}"
    }},
    {{
      "id": "activities",
      "type": "Activities",
      "title": "Activités & Excursions",
      "body": "Activités et excursions mentionnées dans le contenu scrapé. Pour les prix d'activités non fournis : écrire 'Tarif à confirmer.'"
    }},
    {{
      "id": "price",
      "type": "Price",
      "title": "Tarifs & Conditions",
      "body": "{"Prix par personne trouvés dans les données scrapées : " + str(price_snippets) + ". Conditions de réservation si mentionnées." if has_scraped_prices else "Prix total du circuit : À confirmer avec l agence. Ne pas inventer de montant. Indiquer les éléments inclus (vols, hébergements, transferts, activités) et ceux à régler sur place. Conditions d annulation : À confirmer."}"
    }}
  ],
  "cta": {{
    "title": "Réservez votre circuit de rêve !", 
    "description": "Offre limitée - Ne manquez pas cette opportunité unique", 
    "buttonText": "Réserver maintenant"
  }}
}}

EXIGENCES SPÉCIFIQUES CIRCUIT :
- L'itinéraire doit être détaillé JOUR PAR JOUR avec toutes les activités, visites, et repas
- Inclus tous les transports entre les différentes étapes du circuit
- Décris chaque hébergement pour chaque étape
- Chaque section doit contenir au moins 150-200 mots de contenu détaillé
- Sois professionnel mais engageant
- Inclus des détails sur les services, équipements, et conditions

⚠️⚠️⚠️ FORMAT JSON CRITIQUE ⚠️⚠️⚠️
- Réponds UNIQUEMENT avec un JSON valide, sans texte avant ou après
- Utilise TOUJOURS des guillemets doubles " pour les chaînes, jamais d'apostrophes '
- Échappe les guillemets dans le texte avec \\"
- Vérifie que toutes les accolades {{ et }} sont bien fermées
- Vérifie qu'il n'y a pas de virgule après le dernier élément d'un tableau ou objet"""

    def _get_prompt_sejour(self, text_input, website_descriptions=None, example_templates=None, travel_date=None, return_date=None, real_time_search=None, real_flights_context=None, offer_type="sejour"):
        """Prompt pour un Séjour (transport et/ou hôtel)"""

        # Détecter si le scraping a trouvé de vrais prix
        has_scraped_prices, price_snippets = self._detect_scraped_prices(website_descriptions)

        # Ajouter les descriptions des sites web si disponibles
        website_context = ""
        if website_descriptions and len(website_descriptions) > 0:
            website_context = "\n\n📋📋📋 INFORMATIONS RÉCUPÉRÉES DEPUIS DES SITES WEB (CONTENU RÉEL - UTILISER EN PRIORITÉ ABSOLUE) :\n"
            for idx, desc in enumerate(website_descriptions, 1):
                website_context += f"\n--- Site {idx}: {desc.get('url', 'URL inconnue')} ---\n"
                content = desc.get('content', '')
                website_context += content[:5000] + "\n"
                
                # Ajouter les images si disponibles
                images = desc.get('images', [])
                if images:
                    website_context += f"\n🖼️ IMAGES DISPONIBLES DEPUIS CE SITE ({len(images)} image(s)):\n"
                    for img_idx, img_url in enumerate(images[:5], 1):  # Limiter à 5 images
                        website_context += f"- Image {img_idx}: {img_url}\n"
                    website_context += "\n⚠️ IMPORTANT : Ces images proviennent du site web. Tu peux les mentionner dans l'offre ou les utiliser pour enrichir les descriptions.\n"
            
            website_context += "\n🚨🚨🚨 CRITIQUE - UTILISATION DES SITES WEB :\n"
            website_context += "- Ces informations proviennent DIRECTEMENT du site web scrapé\n"
            website_context += "- Utilise TOUTES les descriptions, détails, activités mentionnées sur le site\n"
            website_context += "- Si le site mentionne des temples, plages, activités spécifiques, utilise-les EXACTEMENT\n"
            website_context += "- Si le site mentionne des hôtels, zones, lieux spécifiques, utilise-les\n"
            website_context += "- Si le site mentionne des transferts, transport aéroport-hôtel, ou services de transport, utilise-les EXACTEMENT\n"
            website_context += "- Ne crée PAS de nouvelles descriptions - utilise celles du site scrapé\n"
            website_context += "- Les descriptions du site doivent apparaître dans ton offre, pas des descriptions inventées\n"
            website_context += "- Pour l'introduction, utilise les descriptions du site web, pas tes propres descriptions\n"
            website_context += "- Les images fournies peuvent être utilisées pour enrichir l'offre (mentionner leur contenu dans les descriptions)\n"
        elif website_descriptions is not None and len(website_descriptions) == 0:
            # Des URLs ont été fournies mais le scraping a échoué
            website_context = "\n\n⚠️ ATTENTION : Des URLs de sites web ont été fournies mais n'ont pas pu être scrappées (sites inaccessibles ou protection anti-scraping). Utilise les informations de recherche Tavily ou tes connaissances générales.\n"
        
        # Ajouter les dates explicites dans le prompt
        dates_context = ""
        if travel_date or return_date:
            dates_context = "\n\n📅📅📅 DATES DU VOYAGE (À UTILISER EXACTEMENT - NE PAS INVENTER) :\n"
            if travel_date:
                try:
                    from datetime import datetime
                    months_fr = {
                        1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
                        5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
                        9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
                    }
                    date_obj = datetime.strptime(str(travel_date).strip().split('T')[0], '%Y-%m-%d')
                    date_formatted = f"{date_obj.day} {months_fr[date_obj.month]} {date_obj.year}"
                    dates_context += f"- Date de départ : {date_formatted} ({travel_date})\n"
                except:
                    dates_context += f"- Date de départ : {travel_date}\n"
            if return_date:
                try:
                    from datetime import datetime
                    months_fr = {
                        1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
                        5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
                        9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
                    }
                    date_obj = datetime.strptime(str(return_date).strip().split('T')[0], '%Y-%m-%d')
                    date_formatted = f"{date_obj.day} {months_fr[date_obj.month]} {date_obj.year}"
                    dates_context += f"- Date de retour : {date_formatted} ({return_date})\n"
                except:
                    dates_context += f"- Date de retour : {return_date}\n"
            dates_context += "\n🚨🚨🚨 IMPORTANT : Utilise CES DATES EXACTEMENT pour les vols. Ne crée PAS de dates différentes. Les horaires de vol doivent correspondre à ces dates. Si tu mentionnes des dates dans l'offre, utilise celles-ci, pas d'autres dates.\n"
        
        # Ajouter les exemples de templates si disponibles
        templates_context = ""
        if example_templates:
            templates_context = "\n\n📝 EXEMPLES DE TEMPLATES À COPIER EXACTEMENT (STRUCTURE ET STYLE) :\n"
            for idx, template in enumerate(example_templates, 1):
                templates_context += f"\n--- Exemple Template {idx} ---\n"
                if isinstance(template, dict):
                    templates_context += json.dumps(template, ensure_ascii=False, indent=2)[:2000] + "\n"
                else:
                    templates_context += str(template)[:2000] + "\n"
            templates_context += "\n⚠️⚠️⚠️ CRITIQUE : Copie EXACTEMENT la structure, le style, le format, et l'organisation de ces exemples. Utilise le même niveau de détail, les mêmes types de sections, et le même ton.\n"
        
        # Ajouter UNIQUEMENT les VRAIS vols d'Air France-KLM
        flights_context = ""
        if real_flights_context:
            flights_context = real_flights_context
        
        # ── Détection stricte de ce qui est réellement disponible ──────────────
        scraped_content_all = " ".join(
            (d.get('content', '') for d in (website_descriptions or [])),
        ).lower()
        hotel_kws   = ['hôtel', 'hotel', 'hébergement', 'resort', 'chambre', 'nuit', 'logement', 'lodge', 'pension']
        service_kws = ['service', 'petit-déjeuner', 'piscine', 'spa', 'inclus', 'transfert aéroport']
        transfer_kws = ['transfert', 'navette', 'shuttle', 'transport aéroport', 'prise en charge']
        text_lower  = (text_input or '').lower()

        has_real_flights   = bool(real_flights_context)
        has_hotel_info     = any(k in scraped_content_all for k in hotel_kws) or any(k in text_lower for k in hotel_kws)
        has_services_info  = any(k in scraped_content_all for k in service_kws)
        has_transfer_info  = any(k in scraped_content_all for k in transfer_kws)

        # ── Construction dynamique des sections ─────────────────────────────
        sections_json_parts = []

        # Détection vol retour
        has_retour_sejour = real_flights_context and '(RETOUR)' in real_flights_context

        # Section Vols — toujours présente si transport mentionné
        if has_real_flights:
            flight_body_instruction = "Reprends EXACTEMENT les informations du VOL ALLER de la section VOLS RÉELS. Ne modifie aucun horaire ni numéro de vol."
        else:
            flight_body_instruction = "⚠️ Aucun numéro de vol fourni. Indique uniquement la route mentionnée par le client (ex: Bruxelles → Bali). N'invente PAS d'horaires, de numéro de vol, ni de compagnie aérienne. Écris exactement : \\'Informations de vol à compléter — veuillez fournir un numéro de vol et une date.\\'"
        sections_json_parts.append(f'''    {{
      "id": "flights_aller",
      "type": "Flights",
      "title": "Vol Aller",
      "body": "{flight_body_instruction}"
    }}''')

        if has_retour_sejour:
            sections_json_parts.append('''    {
      "id": "flights_retour",
      "type": "Flights",
      "title": "Vol Retour",
      "body": "Reprends EXACTEMENT les informations du VOL RETOUR de la section VOLS RÉELS. Numéro, compagnie, aéroports, horaires, durée, escales. N\\'invente rien."
    }''')

        # Section Transferts — UNIQUEMENT si données scrapées le mentionnent
        if has_transfer_info:
            sections_json_parts.append('''    {
      "id": "transfers",
      "type": "Transfers",
      "title": "Transferts",
      "body": "Reprends EXACTEMENT les informations de transferts trouvées dans les sites scrapés."
    }''')

        # Section Hébergement — UNIQUEMENT si texte ou sites scrapés le mentionnent
        if has_hotel_info:
            hotel_body = ("Nom, catégorie, localisation, équipements et prix de l\\'hôtel TELS QUE FOURNIS dans le contenu scrapé."
                          if has_scraped_prices else
                          "Nom, catégorie, localisation et équipements de l\\'hôtel tels que mentionnés. Prix : écrire exactement \\'Prix à confirmer avec l\\'agence.\\' Ne pas inventer de tarif.")
            sections_json_parts.append(f'''    {{
      "id": "hotel",
      "type": "Hotel",
      "title": "Hébergement",
      "body": "{hotel_body}"
    }}''')

        # Section Services — UNIQUEMENT si données scrapées les mentionnent
        if has_services_info:
            sections_json_parts.append('''    {
      "id": "services",
      "type": "Services",
      "title": "Services Inclus",
      "body": "Reprends EXACTEMENT les services inclus mentionnés dans les sites scrapés."
    }''')

        # Section Prix — UNIQUEMENT si prix réels scrapés ou hôtel présent
        if has_scraped_prices or has_hotel_info:
            price_body = (f"Prix trouvés dans les données scrapées : {price_snippets}. Conditions si mentionnées."
                          if has_scraped_prices else
                          "Prix du séjour : À confirmer avec l\\'agence. N\\'invente pas de montants.")
            sections_json_parts.append(f'''    {{
      "id": "price",
      "type": "Price",
      "title": "Tarifs & Conditions",
      "body": "{price_body}"
    }}''')

        sections_json = ",\n".join(sections_json_parts)

        return f"""Crée une offre de voyage STRICTEMENT basée sur les informations fournies pour : {text_input}
{website_context}
{dates_context}
{templates_context}
{flights_context}

🚨🚨🚨 RÈGLES ABSOLUES — LIRE AVANT TOUT :
1. GÉNÈRE UNIQUEMENT les sections listées dans le format JSON ci-dessous. N'en ajoute PAS d'autres.
2. N'invente AUCUNE information : pas d'hôtel fictif, pas d'horaires inventés, pas de services imaginaires, pas de prix estimés.
3. Pour les vols : utilise UNIQUEMENT les données de la section VOLS RÉELS si présente. Si absente, indique que le numéro de vol est à fournir.
4. Pour les dates : utilise UNIQUEMENT les dates fournies. N'en invente pas.
5. Pour tout champ sans données réelles : écrire "À confirmer" — JAMAIS inventer.
6. Si l'utilisateur n'a mentionné que des vols (pas d'hôtel), la section Hébergement ne doit PAS apparaître.

Format JSON strict — UNIQUEMENT ces sections, rien d'autre :
{{
  "title": "Titre court et factuel basé sur la destination et les dates",
  "introduction": "1-2 phrases factuelles uniquement sur la destination. Pas de superlatifs inventés.",
  "sections": [
{sections_json}
  ],
  "cta": {{
    "title": "Réservez votre voyage",
    "description": "Contactez-nous pour confirmer votre réservation",
    "buttonText": "Réserver maintenant"
  }}
}}

⚠️⚠️⚠️ FORMAT JSON CRITIQUE ⚠️⚠️⚠️
- Réponds UNIQUEMENT avec un JSON valide, sans texte avant ou après
- Utilise TOUJOURS des guillemets doubles " pour les chaînes, jamais d'apostrophes '
- Échappe les guillemets dans le texte avec \\"
- Vérifie que toutes les accolades {{ et }} sont bien fermées
- Vérifie qu'il n'y a pas de virgule après le dernier élément d'un tableau ou objet"""

    def _get_prompt_transport(self, text_input, website_descriptions=None, example_templates=None, real_time_search=None, travel_date=None, return_date=None, real_flights_context=None, offer_type="transport", keywords=None, outbound_cabin_class="eco", return_cabin_class="eco", outbound_escales=None, return_escales=None):
        """Prompt pour Transport seul"""
        if keywords is None:
            keywords = []
        if outbound_escales is None:
            outbound_escales = []
        if return_escales is None:
            return_escales = []

        # Ajouter les descriptions des sites web si disponibles
        website_context = ""
        if website_descriptions and len(website_descriptions) > 0:
            website_context = "\n\n📋📋📋 INFORMATIONS RÉCUPÉRÉES DEPUIS DES SITES WEB (CONTENU RÉEL - UTILISER EN PRIORITÉ ABSOLUE) :\n"
            for idx, desc in enumerate(website_descriptions, 1):
                website_context += f"\n--- Site {idx}: {desc.get('url', 'URL inconnue')} ---\n"
                content = desc.get('content', '')
                website_context += content[:5000] + "\n"
                
                # Ajouter les images si disponibles
                images = desc.get('images', [])
                if images:
                    website_context += f"\n🖼️ IMAGES DISPONIBLES DEPUIS CE SITE ({len(images)} image(s)):\n"
                    for img_idx, img_url in enumerate(images[:5], 1):  # Limiter à 5 images
                        website_context += f"- Image {img_idx}: {img_url}\n"
                    website_context += "\n⚠️ IMPORTANT : Ces images proviennent du site web. Tu peux les mentionner dans l'offre ou les utiliser pour enrichir les descriptions.\n"
            
            website_context += "\n🚨🚨🚨 CRITIQUE - UTILISATION DES SITES WEB :\n"
            website_context += "- Ces informations proviennent DIRECTEMENT du site web scrapé\n"
            website_context += "- Utilise TOUTES les descriptions, détails, activités mentionnées sur le site\n"
            website_context += "- Si le site mentionne des temples, plages, activités spécifiques, utilise-les EXACTEMENT\n"
            website_context += "- Si le site mentionne des hôtels, zones, lieux spécifiques, utilise-les\n"
            website_context += "- Si le site mentionne des transferts, transport aéroport-hôtel, ou services de transport, utilise-les EXACTEMENT\n"
            website_context += "- Ne crée PAS de nouvelles descriptions - utilise celles du site scrapé\n"
            website_context += "- Les descriptions du site doivent apparaître dans ton offre, pas des descriptions inventées\n"
            website_context += "- Pour l'introduction, utilise les descriptions du site web, pas tes propres descriptions\n"
            website_context += "- Les images fournies peuvent être utilisées pour enrichir l'offre (mentionner leur contenu dans les descriptions)\n"
        elif website_descriptions is not None and len(website_descriptions) == 0:
            # Des URLs ont été fournies mais le scraping a échoué
            website_context = "\n\n⚠️ ATTENTION : Des URLs de sites web ont été fournies mais n'ont pas pu être scrappées (sites inaccessibles ou protection anti-scraping). Utilise les informations de recherche Tavily ou tes connaissances générales.\n"
        
        # Ajouter les dates explicites dans le prompt
        dates_context = ""
        if travel_date or return_date:
            dates_context = "\n\n📅📅📅 DATES DU VOYAGE (À UTILISER EXACTEMENT - NE PAS INVENTER) :\n"
            if travel_date:
                try:
                    from datetime import datetime
                    months_fr = {
                        1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
                        5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
                        9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
                    }
                    date_obj = datetime.strptime(str(travel_date).strip().split('T')[0], '%Y-%m-%d')
                    date_formatted = f"{date_obj.day} {months_fr[date_obj.month]} {date_obj.year}"
                    dates_context += f"- Date de départ : {date_formatted} ({travel_date})\n"
                except:
                    dates_context += f"- Date de départ : {travel_date}\n"
            if return_date:
                try:
                    from datetime import datetime
                    months_fr = {
                        1: 'janvier', 2: 'février', 3: 'mars', 4: 'avril',
                        5: 'mai', 6: 'juin', 7: 'juillet', 8: 'août',
                        9: 'septembre', 10: 'octobre', 11: 'novembre', 12: 'décembre'
                    }
                    date_obj = datetime.strptime(str(return_date).strip().split('T')[0], '%Y-%m-%d')
                    date_formatted = f"{date_obj.day} {months_fr[date_obj.month]} {date_obj.year}"
                    dates_context += f"- Date de retour : {date_formatted} ({return_date})\n"
                except:
                    dates_context += f"- Date de retour : {return_date}\n"
            dates_context += "\n🚨🚨🚨 IMPORTANT : Utilise CES DATES EXACTEMENT pour les vols. Ne crée PAS de dates différentes. Les horaires de vol doivent correspondre à ces dates. Si tu mentionnes des dates dans l'offre, utilise celles-ci, pas d'autres dates.\n"
        
        # Ajouter UNIQUEMENT les VRAIS vols d'Air France-KLM (plus de Tavily)
        if real_flights_context:
            real_time_context = real_flights_context
        else:
            # Pas de vols trouvés - contexte vide (pas de Tavily)
            real_time_context = ""

        # Ajouter les mots-clés de la description
        keywords_context = ""
        if keywords:
            keywords_context = f"\n\n🔑 MOTS-CLÉS IMPORTANTS DE LA DESCRIPTION (à réutiliser dans l'offre) :\n"
            keywords_context += ", ".join(keywords) + "\n"
            keywords_context += "→ Reprends ces termes spécifiques dans le contenu généré pour assurer la cohérence avec la demande client.\n"

        # Infos classe cabine et escales
        cabin_context = ""
        cabin_labels = {"eco": "Économique", "premium_eco": "Premium Économique", "business": "Business"}
        if outbound_cabin_class and outbound_cabin_class != "eco":
            cabin_context += f"\n✈️ CLASSE CABINE VOL ALLER : {cabin_labels.get(outbound_cabin_class, outbound_cabin_class)}\n"
        if return_cabin_class and return_cabin_class != "eco":
            cabin_context += f"✈️ CLASSE CABINE VOL RETOUR : {cabin_labels.get(return_cabin_class, return_cabin_class)}\n"
        if outbound_escales:
            cabin_context += f"🛑 ESCALES VOL ALLER : " + " → ".join([e.get('flightNumber', '') for e in outbound_escales if e.get('flightNumber')]) + "\n"
        if return_escales:
            cabin_context += f"🛑 ESCALES VOL RETOUR : " + " → ".join([e.get('flightNumber', '') for e in return_escales if e.get('flightNumber')]) + "\n"

        # Ajouter les exemples de templates si disponibles
        templates_context = ""
        if example_templates:
            templates_context = "\n\n📝 EXEMPLES DE TEMPLATES À COPIER EXACTEMENT (STRUCTURE ET STYLE) :\n"
            for idx, template in enumerate(example_templates, 1):
                templates_context += f"\n--- Exemple Template {idx} ---\n"
                if isinstance(template, dict):
                    templates_context += json.dumps(template, ensure_ascii=False, indent=2)[:2000] + "\n"
                else:
                    templates_context += str(template)[:2000] + "\n"
            templates_context += "\n⚠️⚠️⚠️ CRITIQUE : Copie EXACTEMENT la structure, le style, le format, et l'organisation de ces exemples. Utilise le même niveau de détail, les mêmes types de sections, et le même ton.\n"
        
        # Instructions spéciales pour les vols avec dates/heures
        flight_instructions = ""
        has_flight_keywords = any(keyword in text_input.lower() for keyword in ['date', 'heure', 'jour', 'départ', 'arrivée', 'vol'])
        
        # Vérifier si on a des informations réelles de vols (Amadeus, sites web, ou Tavily)
        has_real_flight_info = bool(real_flights_context)  # Amadeus Flight Status = source prioritaire
        if not has_real_flight_info and website_descriptions:
            for desc in website_descriptions:
                content = desc.get('content', '').lower()
                # Vérifier qu'il y a vraiment des infos de vol (pas juste des mots-clés négatifs)
                if any(keyword in content for keyword in ['vol', 'flight', 'compagnie', 'airline', 'départ', 'arrivée', 'aéroport']):
                    # Exclure les messages négatifs
                    negative = any(indicator in content for indicator in ['aucun vol', 'no flights', 'pas de vol', 'not available'])
                    if not negative:
                        has_real_flight_info = True
                        break
        
        # Pour Tavily, vérifier que les résultats sont valides (pas juste "aucun vol trouvé")
        if real_time_search and isinstance(real_time_search, list):
            for result in real_time_search:
                content = (result.get('content', '') or result.get('raw_content', '')).lower()
                # Vérifier qu'il y a des infos positives
                has_positive = any(keyword in content for keyword in ['vol', 'flight', 'departure', 'départ', 'arrival', 'arrivée', 'airline', 'compagnie'])
                has_negative = any(indicator in content for indicator in ['aucun vol', 'no flights', 'no results', 'pas de vol', 'not available'])
                
                if has_positive and not has_negative:
                    has_real_flight_info = True
                    break
        
        if has_flight_keywords or real_time_search or has_real_flight_info:
            flight_instructions = "\n\n✈️ INSTRUCTIONS SPÉCIALES POUR LES VOLS :\n"

            if has_real_flight_info and real_flights_context:
                flight_instructions += "🚨🚨🚨 VOLS RÉELS DUFFEL DISPONIBLES — UTILISE-LES OBLIGATOIREMENT :\n"
                flight_instructions += "- Des vols RÉELS ont été trouvés via l'API Duffel (voir section VOLS RÉELS ci-dessus)\n"
                flight_instructions += "- Utilise EXACTEMENT ces numéros de vol, compagnies, aéroports, horaires, terminaux et escales\n"
                flight_instructions += "- N'invente AUCUNE information supplémentaire non présente dans ces données\n"
                flight_instructions += "- Si plusieurs OPTIONS sont disponibles pour un même leg (Option 1, Option 2, Option 3), INCLUS LES TOUTES dans l'offre sous forme de tableau ou liste comparative\n"
                flight_instructions += "- Si le vol est 'aller', indique-le clairement. Si un vol 'retour' est aussi fourni, inclus-le dans une section séparée.\n"
                flight_instructions += "- Les informations Duffel sont vérifiables par les clients — NE LES MODIFIE PAS\n"
            elif not has_real_flight_info and offer_type == "transport":
                flight_instructions += "🚨🚨🚨🚨🚨 CRITIQUE ABSOLUE - TRANSPORT SEUL :\n"
                flight_instructions += "- AUCUNE information de vol réelle disponible\n"
                flight_instructions += "- INTERDICTION TOTALE : NE CRÉE ABSOLUMENT PAS de section de vol avec des informations inventées\n"
                flight_instructions += "- N'INVENTE JAMAIS de numéros de vol (UA 123, AF 456, etc.)\n"
                flight_instructions += "- N'INVENTE JAMAIS d'horaires (22h00, 17h30, etc.)\n"
                flight_instructions += "- N'INVENTE JAMAIS de compagnies aériennes\n"
                flight_instructions += "- Crée UNE SEULE section 'Avertissement' : '⚠️ Les informations de vol pour cette route/date ne sont pas disponibles. Veuillez vérifier directement auprès des compagnies aériennes.'\n"
                flight_instructions += "- C'est UN PROBLÈME GRAVE si tu inventes des vols - ces informations seront données à des clients réels\n"
            elif real_time_search:
                flight_instructions += "⚠️⚠️⚠️ ATTENTION : Des recherches en temps réel ont été effectuées. Utilise EN PRIORITÉ les informations réelles trouvées dans les résultats de recherche ci-dessus.\n"

            if has_real_flight_info and not real_flights_context:
                flight_instructions += "- Utilise UNIQUEMENT les informations de vols trouvées dans les sites web scrapés ou les recherches Tavily\n"
                flight_instructions += "- Structure les informations : numéro de vol, compagnie, horaires précis, aéroports (codes IATA), durée\n"

        # Section retour dynamique dans le JSON template
        has_retour = real_flights_context and '(RETOUR)' in real_flights_context
        retour_section = """,
    {
      "id": "flights_retour",
      "type": "Flights",
      "title": "Vol Retour",
      "body": "Reprends EXACTEMENT les informations du VOL RETOUR de la section VOLS RÉELS. Pour chaque vol : numéro, compagnie, aéroport départ + terminal (si fourni), heure départ, aéroport arrivée + terminal (si fourni), heure arrivée, durée, type (direct ou escales avec durées de correspondance), prix. N'ajoute PAS d\\'informations non fournies."
    }""" if has_retour else ""

        return f"""Tu es un assistant pour une agence de voyage. Crée une offre de TRANSPORT SEUL pour : {text_input}
{website_context}
{dates_context}
{templates_context}
{real_time_context}
{flight_instructions}

🚨🚨🚨 RÈGLES ABSOLUES — SOURCES AUTORISÉES PAR SECTION :

SECTION "Transport Aérien" — utilise UNIQUEMENT les champs de la section "VOLS RÉELS" ci-dessus :
  ✅ Numéro de vol, compagnie, aéroports, horaires, durée, terminaux → tels quels
  ✅ Porte (gate) → seulement si "Porte départ/arrivée" est listé. Sinon : NE PAS MENTIONNER.
  ✅ Escales → seulement si "Segments du trajet" est listé. Vol direct si stops = 0.
  ✅ Prix → utilise le champ "Prix:" tel quel (ex: "450 EUR"). Si "À confirmer", écris exactement "Prix à confirmer avec la compagnie".
  ✅ Si un vol indique "⚠️ ATTENTION DATE" → mentionne clairement dans l'offre que c'est le vol le plus proche trouvé et précise les deux dates (demandée vs réelle).
  ✅ Si un vol indique "(NON CONFIRMÉ PAR AMADEUS)" → inclus le numéro de vol et la date demandée tels quels, puis copie la NOTE AGENT mot pour mot dans le body (elle sera supprimée par l'agent). N'invente PAS d'horaires, aéroports ou terminaux.
  ❌ N'invente PAS de numéros de vol, horaires, aéroports, terminaux, portes, prix non fournis.

SECTION "Bagages" — utilise UNIQUEMENT la section "BAGAGES (politique officielle)" ci-dessus :
  ✅ Copie exactement les informations de bagages cabine et soute pour la classe indiquée.
  ❌ N'invente PAS de dimensions, poids, frais non mentionnés.
  Si une information manque → écris "À confirmer avec la compagnie."

SECTION "Services à Bord" — utilise UNIQUEMENT les sections "REPAS", "DIVERTISSEMENT", "WI-FI", "SIÈGES" ci-dessus :
  ✅ Copie exactement les informations officielles de la compagnie.
  ❌ N'invente PAS de services non listés (pas de "200+ films" si non mentionné, pas de "USB" si non listé).
  Si une information manque → écris "À confirmer avec la compagnie."

SECTION "Tarifs & Conditions" :
  ✅ Prix : utilise UNIQUEMENT le prix fourni dans "VOLS RÉELS" (champ Prix:).
  ✅ Bagages inclus : reprends les infos bagages officielles.
  ❌ N'invente PAS de conditions d'annulation, d'acompte, de frais de modification non fournis.
  Pour les conditions non fournies → écris "Conditions à confirmer avec la compagnie."

FORMAT JSON strict — réponds UNIQUEMENT avec ce JSON :
{{
  "title": "Titre professionnel reprenant la route et la compagnie",
  "introduction": "2-3 phrases présentant le(s) vol(s) avec les informations RÉELLES (compagnie, route, horaires). Utilise uniquement les données fournies.",
  "sections": [
    {{
      "id": "flights_aller",
      "type": "Flights",
      "title": "Vol Aller",
      "body": "Reprends EXACTEMENT les informations du VOL ALLER de la section VOLS RÉELS. Pour chaque vol : numéro, compagnie, aéroport départ + terminal (si fourni), heure départ, aéroport arrivée + terminal (si fourni), heure arrivée, durée, type (direct ou escales avec durées de correspondance), prix. N'ajoute PAS d'informations non fournies."
    }}{retour_section},
    {{
      "id": "baggage",
      "type": "Bagage",
      "title": "Bagages",
      "body": "Reprends EXACTEMENT la politique bagages officielle de la compagnie fournie ci-dessus. Pour les informations manquantes : À confirmer avec la compagnie."
    }},
    {{
      "id": "services",
      "type": "Services",
      "title": "Services à Bord",
      "body": "Reprends EXACTEMENT les services officiels de la compagnie fournis ci-dessus (repas, divertissement, Wi-Fi, sièges). Pour les informations manquantes : À confirmer avec la compagnie."
    }},
    {{
      "id": "price",
      "type": "Price",
      "title": "Tarifs & Conditions",
      "body": "Prix : utilise UNIQUEMENT le prix fourni dans les données de vol. Bagages inclus : reprends les données officielles. Conditions d'annulation/modification : À confirmer avec la compagnie si non fournies."
    }}
  ],
  "cta": {{
    "title": "Réservez votre vol",
    "description": "Contactez-nous pour confirmer votre réservation",
    "buttonText": "Réserver maintenant"
  }}
}}

⚠️⚠️⚠️ FORMAT JSON CRITIQUE ⚠️⚠️⚠️
- Réponds UNIQUEMENT avec un JSON valide, sans texte avant ou après
- Utilise TOUJOURS des guillemets doubles " pour les chaînes
- Échappe les guillemets dans le texte avec \\"
- Vérifie que toutes les accolades {{ et }} sont bien fermées
- Vérifie qu'il n'y a pas de virgule après le dernier élément d'un tableau ou objet"""

    def post(self, request):
        text_input = request.data.get("text")
        offer_type = request.data.get("offer_type", "sejour")
        flight_input = request.data.get("flight_input")  # legacy
        company_info = request.data.get("company_info", {})
        website_urls = request.data.get("website_urls", [])
        example_templates = request.data.get("example_templates", [])
        keywords = request.data.get("keywords", [])
        hotel_google_images = request.data.get("hotel_google_images", [])

        # ── Nouveaux champs v2 ────────────────────────────────────────────────
        manual_flights_only = request.data.get("manual_flights_only", False)
        destinations = request.data.get("destinations", []) or []
        logements = request.data.get("logements", []) or []
        dates_texte = request.data.get("dates", "") or ""
        repas = request.data.get("repas", "") or ""
        transfert_type = request.data.get("transfert", "") or ""
        croisiere = request.data.get("croisiere", "") or ""
        type_chambre = request.data.get("type_chambre", "") or ""
        formalites = request.data.get("formalites", "") or ""
        outbound_flight_manual = request.data.get("outbound_flight", {}) or {}
        return_flight_manual = request.data.get("return_flight", {}) or {}

        # Legacy flight fields (compatibilité avec ancien formulaire)
        outbound_flight_number = request.data.get("outbound_flight_number")
        outbound_date = request.data.get("outbound_date")
        outbound_cabin_class = request.data.get("outbound_cabin_class", "eco")
        outbound_escales = request.data.get("outbound_escales", [])
        return_flight_number = request.data.get("return_flight_number")
        return_flight_date = request.data.get("return_flight_date")
        return_cabin_class = request.data.get("return_cabin_class", "eco")
        return_escales = request.data.get("return_escales", [])
        outbound_route = request.data.get("outbound_route", {}) or {}
        return_route = request.data.get("return_route", {}) or {}

        # Si les nouveaux champs de vol manuel sont utilisés, les faire correspondre aux anciens
        if outbound_flight_manual and not outbound_flight_number:
            outbound_flight_number = outbound_flight_manual.get("flight_number", "")
            outbound_date = outbound_flight_manual.get("date", "")
            outbound_cabin_class = outbound_flight_manual.get("cabin_class", "eco")
            outbound_route = {
                'depCity': outbound_flight_manual.get("dep_city", ""),
                'arrCity': outbound_flight_manual.get("arr_city", ""),
            }
        if return_flight_manual and not return_flight_number:
            return_flight_number = return_flight_manual.get("flight_number", "")
            return_flight_date = return_flight_manual.get("date", "")
            return_cabin_class = return_flight_manual.get("cabin_class", "eco")
            return_route = {
                'depCity': return_flight_manual.get("dep_city", ""),
                'arrCity': return_flight_manual.get("arr_city", ""),
            }

        # Legacy
        origin = request.data.get("origin", "Paris")
        destination = request.data.get("destination")
        travel_date = request.data.get("travel_date")
        return_date = request.data.get("return_date")

        # Construire un text_input depuis les nouveaux champs si absent
        if not text_input:
            parts = []
            if destinations:
                parts.append(f"Destination(s) : {', '.join(d for d in destinations if d.strip())}")
            if dates_texte:
                parts.append(f"Dates : {dates_texte}")
            if logements:
                parts.append(f"Logement(s) : {', '.join(l for l in logements if l.strip())}")
            if parts:
                text_input = " — ".join(parts)

        print(f"📥 Requête reçue:")
        print(f"   - offer_type: {offer_type}")
        print(f"   - destinations: {destinations}")
        print(f"   - dates: {dates_texte}")
        print(f"   - manual_flights_only: {manual_flights_only}")
        print(f"   - outbound_flight: {outbound_flight_number} / {outbound_date}")
        print(f"   - text_input longueur: {len(text_input) if text_input else 0} caractères")

        has_structured_flight = bool(outbound_flight_number and outbound_date)

        if not text_input and not has_structured_flight and not flight_input:
            return Response({"error": "Veuillez fournir une destination ou une description."}, status=status.HTTP_400_BAD_REQUEST)

        if not text_input and (has_structured_flight or flight_input):
            vol_desc = f"vol {outbound_flight_number} du {outbound_date}" if has_structured_flight else flight_input
            text_input = f"Demande de devis pour le(s) vol(s) suivant(s) : {vol_desc}"
        
        try:
            # Récupérer les descriptions des sites web si des URLs sont fournies
            # Limiter à 3 URLs max pour éviter les timeouts
            website_descriptions = None
            if website_urls and isinstance(website_urls, list) and len(website_urls) > 0:
                limited_urls = website_urls[:3]  # Maximum 3 URLs pour éviter les timeouts
                if len(website_urls) > 3:
                    print(f"⚠️ Limitation à 3 URLs (sur {len(website_urls)}) pour éviter les timeouts")
                print(f"🌐 Récupération des descriptions depuis {len(limited_urls)} site(s)...")
                website_descriptions = self._get_website_descriptions(limited_urls)
                print(f"✅ {len(website_descriptions)} description(s) récupérée(s)")
            
            # Charger les templates par défaut pour ce type d'offre
            default_templates = self._load_default_templates(offer_type)
            
            # Traiter les exemples de templates (fusionner avec les templates par défaut)
            processed_templates = []
            
            # D'abord ajouter les templates par défaut
            if default_templates:
                processed_templates.extend(default_templates)
                print(f"📝 Template par défaut chargé pour type '{offer_type}'")
            
            # Ensuite ajouter les templates fournis par l'utilisateur (s'ils existent)
            if example_templates and isinstance(example_templates, list) and len(example_templates) > 0:
                print(f"📝 Traitement de {len(example_templates)} exemple(s) de template(s) utilisateur...")
                for template in example_templates:
                    # Si c'est une string, essayer de la parser en JSON, sinon garder comme texte
                    if isinstance(template, str):
                        try:
                            processed_templates.append(json.loads(template))
                        except json.JSONDecodeError:
                            processed_templates.append(template)
                    else:
                        processed_templates.append(template)
                print(f"✅ {len(processed_templates)} template(s) au total (défaut + utilisateur)")
            elif default_templates:
                print(f"✅ Utilisation du template par défaut uniquement")
            
            real_flights_data = None
            real_time_search_results = None
            search_metadata = {}

            # ── MODE MANUEL : vols saisis à la main, pas de recherche Amadeus ──
            if manual_flights_only:
                print("✈️ Mode MANUEL — vols directs depuis le formulaire (pas de recherche Amadeus)")
                manual_collected = []

                def _build_manual_flight(fd: dict, leg: str) -> dict:
                    cabin_labels = {"eco": "Économique", "premium_eco": "Premium Économique", "business": "Business"}
                    carrier = fd.get("flight_number", "")[:2].upper() if fd.get("flight_number") else ""
                    return {
                        'flight_number': fd.get("flight_number", "").upper() or f"Vol {leg}",
                        'carrier_code': carrier,
                        'airline': carrier,
                        'departure_airport': "",
                        'departure_city': fd.get("dep_city", "") or (outbound_route.get("depCity", "") if leg == "aller" else return_route.get("depCity", "")),
                        'departure_country': "",
                        'departure_time': fd.get("dep_time", ""),
                        'arrival_airport': "",
                        'arrival_city': fd.get("arr_city", "") or (outbound_route.get("arrCity", "") if leg == "aller" else return_route.get("arrCity", "")),
                        'arrival_country': "",
                        'arrival_time': fd.get("arr_time", ""),
                        'duration': fd.get("duration", ""),
                        'cabin_class': fd.get("cabin_class", "eco"),
                        'cabin_label': cabin_labels.get(fd.get("cabin_class", "eco"), "Économique"),
                        'stops': 0,
                        'stopovers': [],
                        'source': 'manual',
                        'leg': leg,
                        'not_found': False,
                        'airline_logo_url': f"https://www.gstatic.com/flights/airline_logos/70px/{carrier}.png" if carrier else "",
                    }

                if outbound_flight_manual:
                    manual_collected.append(_build_manual_flight(outbound_flight_manual, "aller"))
                elif outbound_flight_number:
                    manual_collected.append(_build_manual_flight({
                        'flight_number': outbound_flight_number,
                        'dep_city': outbound_route.get('depCity', ''),
                        'arr_city': outbound_route.get('arrCity', ''),
                        'cabin_class': outbound_cabin_class,
                    }, "aller"))

                if return_flight_manual:
                    manual_collected.append(_build_manual_flight(return_flight_manual, "retour"))
                elif return_flight_number:
                    manual_collected.append(_build_manual_flight({
                        'flight_number': return_flight_number,
                        'dep_city': return_route.get('depCity', ''),
                        'arr_city': return_route.get('arrCity', ''),
                        'cabin_class': return_cabin_class,
                    }, "retour"))

                if manual_collected:
                    real_flights_data = manual_collected
                    print(f"   ✅ {len(manual_collected)} vol(s) manuel(s) chargé(s)")

            # MODE AMADEUS : recherche via l'API (mode legacy / recherche Amadeus)
            elif has_structured_flight:
                print(f"✈️ Mode FLIGHT STATUS - Recherche par web scraping (FlightAware / AirFrance / MisterFly)")
                from api.flight_scraper import FlightWebScraper, iata_to_city
                from api.airline_services import format_airline_services_for_prompt

                try:
                    scraper = FlightWebScraper()
                    flights_collected = []

                    def _make_placeholder(fn, date, leg):
                        carrier = fn[:2].upper() if len(fn) >= 2 else ''
                        placeholder = {
                            'flight_number': fn.upper(),
                            'carrier_code': carrier,
                            'requested_date': date,
                            'leg': leg,
                            'not_found': True,
                        }
                        if carrier:
                            placeholder['airline_services_context'] = format_airline_services_for_prompt(carrier)
                        return placeholder

                    def _search_and_enrich(fn, date, leg):
                        manual = outbound_route if leg == 'aller' else return_route
                        dep_hint = manual.get('depCity', '') if manual else ''
                        arr_hint = manual.get('arrCity', '') if manual else ''
                        result = scraper.get_flight_by_number(fn, date, dep_hint=dep_hint, arr_hint=arr_hint)
                        if not result:
                            result = _make_placeholder(fn, date, leg)

                        result['leg'] = leg
                        carrier = result.get('carrier_code', fn[:2].upper())
                        if carrier:
                            result['airline_services_context'] = format_airline_services_for_prompt(carrier)

                        # Classe cabine depuis le formulaire
                        cabin = outbound_cabin_class if leg == 'aller' else return_cabin_class
                        if cabin:
                            result['cabin_class'] = cabin

                        # Fusionner la route manuelle — SEULEMENT si pas de données IATA valides
                        manual = outbound_route if leg == 'aller' else return_route
                        if manual:
                            # Départ : écraser seulement si pas d'aéroport IATA trouvé
                            if not result.get('departure_airport'):
                                if manual.get('depCity'):
                                    result['departure_city'] = manual['depCity']
                                if manual.get('depCountry'):
                                    result['departure_country'] = manual['depCountry']
                            # Arrivée : écraser seulement si pas d'aéroport IATA trouvé
                            if not result.get('arrival_airport'):
                                if manual.get('arrCity'):
                                    result['arrival_city'] = manual['arrCity']
                                if manual.get('arrCountry'):
                                    result['arrival_country'] = manual['arrCountry']
                            # Horaires manuels toujours prioritaires s'ils sont renseignés
                            if manual.get('depTime'):
                                result['departure_time'] = manual['depTime']
                            if manual.get('arrTime'):
                                result['arrival_time'] = manual['arrTime']
                            if manual.get('duration'):
                                result['duration'] = manual['duration']
                            # Si route manuelle renseignée, le placeholder devient valide
                            if manual.get('depCity') or manual.get('arrCity'):
                                result.pop('not_found', None)

                        return result

                    # Construire la liste des vols à chercher (principal + escales)
                    legs_to_search = [(outbound_flight_number, outbound_date, 'aller', [])]

                    # Escales aller : résoudre chaque numéro de vol
                    aller_escales_resolved = []
                    for esc in outbound_escales:
                        fn_esc = esc.get('flightNumber', '').strip()
                        if fn_esc:
                            aller_escales_resolved.append(fn_esc)
                    if aller_escales_resolved:
                        # On passe les escales au leg aller pour les inclure dans le contexte
                        legs_to_search[0] = (outbound_flight_number, outbound_date, 'aller', aller_escales_resolved)

                    if return_flight_number and return_flight_date:
                        retour_escales_resolved = [
                            e.get('flightNumber', '').strip()
                            for e in return_escales if e.get('flightNumber', '').strip()
                        ]
                        legs_to_search.append((return_flight_number, return_flight_date, 'retour', retour_escales_resolved))

                    print(f"   🔄 Recherche séquentielle de {len(legs_to_search)} vol(s)...")
                    import time as _time
                    call_idx = 0
                    for fn, date, leg, escales_fns in legs_to_search:
                        if call_idx > 0:
                            _time.sleep(2)
                        call_idx += 1
                        result = _search_and_enrich(fn, date, leg)

                        # Chercher les escales via AeroDataBox et les attacher au résultat
                        if escales_fns and result:
                            escales_data = []
                            for fn_esc in escales_fns:
                                _time.sleep(2)
                                call_idx += 1
                                esc_result = scraper.get_flight_by_number(fn_esc, date)
                                if esc_result:
                                    escales_data.append(esc_result)
                                    print(f"   ✅ Escale {fn_esc}: {esc_result.get('departure_airport')} → {esc_result.get('arrival_airport')}")
                            if escales_data:
                                result['escales_detail'] = escales_data

                        if result:
                            flights_collected.append(result)
                            if result.get('not_found'):
                                print(f"   ⚠️ Vol {leg} non trouvé — placeholder ajouté")
                            else:
                                print(f"   ✅ Vol {leg}: {result.get('departure_airport')} → {result.get('arrival_airport')} (source: {result.get('source')})")

                    if flights_collected:
                        real_flights_data = flights_collected
                        search_metadata['source'] = 'web_scraping'
                        search_metadata['search_strategy'] = 'flight_number'
                        search_metadata['has_valid_flight_info'] = any(not f.get('not_found') for f in flights_collected)
                        search_metadata['real_flights_count'] = len(flights_collected)
                    else:
                        search_metadata['has_valid_flight_info'] = False
                        search_metadata['failure_reason'] = ['flight_not_found_web_scraping']

                except Exception as e:
                    print(f"❌ Erreur Amadeus Flight Status: {str(e)}")
                    import traceback
                    traceback.print_exc()
                    search_metadata['has_valid_flight_info'] = False
                    search_metadata['failure_reason'] = [f'amadeus_error: {str(e)}']

            # MODE 2 : Ancien champ texte libre (compatibilité)
            elif flight_input:
                print(f"✈️ Mode SMART SEARCH (legacy) - Parsing automatique du texte")
                real_flights_data = self._search_flights_smart(flight_input, search_metadata)
                if real_flights_data:
                    print(f"✅ {len(real_flights_data)} vol(s) trouvé(s) via smart search")
                else:
                    print(f"⚠️ Aucun vol trouvé via smart search")

            else:
                print(f"   ℹ️ Pas de numéro de vol — tentative recherche Amadeus par itinéraire")
                search_metadata['search_attempted'] = True

                from api.flight_scraper import FlightWebScraper
                scraper = FlightWebScraper()

                # ── Recherche Amadeus par itinéraire (aller) ──
                route_flights = []

                def _try_route_search(route_dict, date_str, leg_label, cabin):
                    """Retourne une liste de vols (jusqu'à 3 options) pour un itinéraire."""
                    if not route_dict:
                        return None
                    dep = route_dict.get('depCity', '')
                    arr = route_dict.get('arrCity', '')
                    if not dep or not arr or not date_str:
                        return None
                    print(f"   🔍 Recherche route {leg_label}: {dep} → {arr} / {date_str}")
                    try:
                        results = scraper.search_by_route(dep, arr, date_str, cabin_class=cabin, max_options=3)
                    except Exception as e:
                        print(f"   ❌ Erreur search_by_route: {e}")
                        results = None
                    if not results:
                        print(f"   ⚠️ Aucun vol Duffel trouvé pour {dep} → {arr}")
                        return None
                    for i, r in enumerate(results):
                        r['leg'] = leg_label
                        r['option_index'] = i + 1
                    print(f"   ✅ {len(results)} option(s) trouvée(s) pour {leg_label}")
                    return results

                outbound_found = _try_route_search(
                    outbound_route, outbound_date, 'aller', outbound_cabin_class
                )
                if outbound_found:
                    route_flights.extend(outbound_found)

                if return_route and any(return_route.get(k) for k in ('depCity', 'arrCity')):
                    return_found = _try_route_search(
                        return_route, return_flight_date, 'retour', return_cabin_class
                    )
                    if return_found:
                        route_flights.extend(return_found)

                if route_flights:
                    real_flights_data = route_flights
                    search_metadata['has_valid_flight_info'] = True
                    search_metadata['source'] = 'duffel'
                    print(f"✅ {len(route_flights)} vol(s) trouvé(s) via recherche par itinéraire")
                else:
                    # Aucun résultat Amadeus → stocker route comme placeholder
                    print(f"   ℹ️ Aucun résultat Amadeus — stockage route comme placeholder")
                    manual_flights = []
                    if outbound_route and any(outbound_route.get(k) for k in ('depCity', 'arrCity')):
                        manual_flights.append({
                            "flight_number": "Vol aller",
                            "source": "manual",
                            "leg": "aller",
                            "departure_city": outbound_route.get("depCity", ""),
                            "departure_country": outbound_route.get("depCountry", ""),
                            "arrival_city": outbound_route.get("arrCity", ""),
                            "arrival_country": outbound_route.get("arrCountry", ""),
                            "departure_airport": "",
                            "arrival_airport": "",
                            "departure_time": None,
                            "arrival_time": None,
                        })
                    if return_route and any(return_route.get(k) for k in ('depCity', 'arrCity')):
                        manual_flights.append({
                            "flight_number": "Vol retour",
                            "source": "manual",
                            "leg": "retour",
                            "departure_city": return_route.get("depCity", ""),
                            "departure_country": return_route.get("depCountry", ""),
                            "arrival_city": return_route.get("arrCity", ""),
                            "arrival_country": return_route.get("arrCountry", ""),
                            "departure_airport": "",
                            "arrival_airport": "",
                            "departure_time": None,
                            "arrival_time": None,
                        })
                    if manual_flights:
                        real_flights_data = manual_flights
                        search_metadata['has_valid_flight_info'] = False
                        search_metadata['source'] = 'manual'
                        print(f"ℹ️ Route(s) manuelle(s) stockée(s) : {len(manual_flights)} vol(s) — SANS horaires")

            # Vérification finale des résultats
            print()
            print("🔍 Vérification résultat recherche...")
            if not real_flights_data:
                if search_metadata.get('search_attempted', False):
                    print(f"❌ Aucun vol trouvé")
                    print(f"   💡 Vérifiez les logs ci-dessus pour plus de détails")
                    if search_metadata.get('failure_reason'):
                        print(f"   📋 Raisons: {', '.join(search_metadata.get('failure_reason', []))}")
                else:
                    print(f"ℹ️ Recherche de vols non effectuée")

                search_metadata['has_valid_flight_info'] = False
                if 'source' not in search_metadata:
                    search_metadata['source'] = None
            else:
                print(f"✅ {len(real_flights_data)} vol(s) trouvé(s)")
                print(f"   Source: {search_metadata.get('source', 'unknown')}")
                if search_metadata.get('search_strategy'):
                    print(f"   Stratégie: {search_metadata['search_strategy']}")
            
            real_time_search_results = None  # Tavily toujours désactivé
            
            print("=" * 80)
            print("FIN RECHERCHE DE VOLS")
            print("=" * 80)
            print()
            
            # Formater les vols réels pour le prompt ChatGPT
            real_flights_context = ""
            if real_flights_data:
                source_name = search_metadata.get('source', 'API')

                # Route manuelle sans numéro de vol → contexte minimaliste, pas de données inventées
                if source_name == 'manual':
                    manual_routes = []
                    for flight in real_flights_data:
                        dep = flight.get('departure_city', '')
                        arr = flight.get('arrival_city', '')
                        if dep or arr:
                            manual_routes.append(f"{dep} → {arr}")
                    if manual_routes:
                        real_flights_context = (
                            f"\n\n✈️ ROUTE SAISIE MANUELLEMENT (sans numéro de vol) :\n"
                            + "\n".join(manual_routes)
                            + "\n\n⚠️ AUCUN HORAIRE DISPONIBLE — le client n'a pas fourni de numéro de vol.\n"
                            f"N'invente PAS de numéro de vol, d'horaire, de compagnie ni d'aéroport.\n"
                            f"Dans la section Transport, indique UNIQUEMENT la route et demande le numéro de vol.\n"
                        )
                    # Pas besoin de continuer à construire le contexte pour manual
                else:
                    real_flights_context = f"\n\n✈️✈️✈️ VOLS RÉELS TROUVÉS (UTILISER CES DONNÉES - NE PAS INVENTER) :\n"
                    real_flights_context += f"Source: {source_name}\n"

            # Construire le détail des vols uniquement si source non-manuelle
            if real_flights_data and search_metadata.get('source') != 'manual':
                source_name = search_metadata.get('source', 'API')
                for idx, flight in enumerate(real_flights_data, 1):
                    leg_label = flight.get('leg', '').upper()
                    leg_suffix = f" ({leg_label})" if leg_label else ""
                    if flight.get('not_found'):
                        real_flights_context += f"\n--- Vol {idx}{leg_suffix} (NON TROUVÉ) ---\n"
                        real_flights_context += f"Numéro de vol: {flight.get('flight_number', 'N/A')}\n"
                        real_flights_context += f"Date demandée: {flight.get('requested_date', 'N/A')}\n"
                        real_flights_context += (
                            f"[NOTE] : Le vol {flight.get('flight_number')} du {flight.get('requested_date')} "
                            f"n'a pas pu être trouvé via les sources web. "
                            f"Veuillez vérifier les horaires directement auprès de la compagnie.\n"
                        )
                        continue

                    option_idx = flight.get('option_index')
                    option_suffix = f" — Option {option_idx}" if option_idx else ""
                    found_by_route = flight.get('found_by_route', False)
                    route_note = " [meilleur vol disponible sur la route]" if found_by_route else ""
                    real_flights_context += f"\n--- Vol{leg_suffix}{option_suffix}{route_note} (source: {source_name}) ---\n"
                    fn = flight.get('flight_number', 'N/A')
                    fn_requested = flight.get('flight_number_requested')
                    if fn not in ('Vol aller', 'Vol retour'):
                        if fn_requested and fn_requested.upper().replace(' ', '') != fn.upper().replace(' ', ''):
                            real_flights_context += f"Vol demandé: {fn_requested} (codeshare non trouvé — meilleur vol disponible affiché)\n"
                        real_flights_context += f"Numéro de vol: {fn}\n"

                    # Compagnie
                    airline = flight.get('airline') or flight.get('carrier_code', '')
                    if airline and airline != 'N/A':
                        real_flights_context += f"Compagnie: {airline}\n"

                    # Aéroports + villes + pays
                    dep_airport = flight.get('departure_airport', '')
                    arr_airport = flight.get('arrival_airport', '')
                    dep_city = flight.get('departure_city', '')
                    dep_country = flight.get('departure_country', '')
                    arr_city = flight.get('arrival_city', '')
                    arr_country = flight.get('arrival_country', '')

                    # Départ : afficher code IATA si connu, sinon ville/pays directement
                    if dep_airport:
                        dep_label = dep_airport
                        if dep_city:
                            dep_label += f" ({dep_city}"
                            if dep_country:
                                dep_label += f", {dep_country}"
                            dep_label += ")"
                    else:
                        parts = [p for p in [dep_city, dep_country] if p]
                        dep_label = ", ".join(parts) if parts else "N/A"

                    # Arrivée
                    if arr_airport:
                        arr_label = arr_airport
                        if arr_city:
                            arr_label += f" ({arr_city}"
                            if arr_country:
                                arr_label += f", {arr_country}"
                            arr_label += ")"
                    else:
                        parts = [p for p in [arr_city, arr_country] if p]
                        arr_label = ", ".join(parts) if parts else "N/A"

                    dep_time = flight.get('departure_time') or 'horaire à confirmer'
                    arr_time = flight.get('arrival_time') or 'horaire à confirmer'
                    real_flights_context += f"Départ: {dep_label} à {dep_time}\n"
                    real_flights_context += f"Arrivée: {arr_label} à {arr_time}\n"

                    # Durée
                    if flight.get('duration'):
                        real_flights_context += f"Durée: {flight['duration']}\n"

                    # Type de vol (direct/escales)
                    stops = flight.get('stops')
                    stopovers = flight.get('stopovers', [])
                    if stops is not None:
                        if stops == 0:
                            real_flights_context += f"Type: Vol direct\n"
                        else:
                            if stopovers:
                                via_labels = []
                                for via in stopovers:
                                    # Duffel retourne des dicts ; anciens formats retournent des strings
                                    if isinstance(via, dict):
                                        via_iata = via.get('airport', '')
                                        via_city = via.get('city', '') or iata_to_city(via_iata)[0]
                                        layover = via.get('layover_duration', '')
                                        label = via_iata
                                        if via_city:
                                            label += f" ({via_city})"
                                        if layover:
                                            label += f" — {layover} de correspondance"
                                        via_labels.append(label)
                                    else:
                                        via_city, via_country = iata_to_city(str(via))
                                        via_labels.append(f"{via} ({via_city}, {via_country})" if via_city else str(via))
                                real_flights_context += f"Escale(s): {', '.join(via_labels)}\n"
                            else:
                                real_flights_context += f"Type: {stops} escale(s)\n"


                    # Tronçons auto-détectés (connexion avant / après)
                    conn_b = flight.get('connecting_flight_before')
                    conn_a = flight.get('connecting_flight_after')
                    if conn_b:
                        cb_dep = conn_b.get('departure_airport', '')
                        cb_arr = conn_b.get('arrival_airport', '')
                        real_flights_context += (
                            f"  Tronçon 1 ({conn_b.get('flight_number','')}): "
                            f"{cb_dep} ({iata_to_city(cb_dep)[0]}) {conn_b.get('departure_time','?')} → "
                            f"{cb_arr} ({iata_to_city(cb_arr)[0]}) {conn_b.get('arrival_time','?')}\n"
                        )
                        real_flights_context += (
                            f"  Tronçon 2 ({fn}): "
                            f"{dep_airport} ({dep_city}) {dep_time} → "
                            f"{arr_airport} ({arr_city}) {arr_time}\n"
                        )
                    if conn_a:
                        ca_dep = conn_a.get('departure_airport', '')
                        ca_arr = conn_a.get('arrival_airport', '')
                        t_num = 2 if not conn_b else 3
                        real_flights_context += (
                            f"  Tronçon {t_num} ({conn_a.get('flight_number','')}): "
                            f"{ca_dep} ({iata_to_city(ca_dep)[0]}) {conn_a.get('departure_time','?')} → "
                            f"{ca_arr} ({iata_to_city(ca_arr)[0]}) {conn_a.get('arrival_time','?')}\n"
                        )

                    # Escales détaillées (tronçons saisis manuellement via "+")
                    escales_detail = flight.get('escales_detail', [])
                    if escales_detail:
                        for esc_idx, esc in enumerate(escales_detail, 1):
                            esc_dep = esc.get('departure_airport', '')
                            esc_arr = esc.get('arrival_airport', '')
                            esc_dep_city, _ = iata_to_city(esc_dep) if esc_dep else ('', '')
                            esc_arr_city, _ = iata_to_city(esc_arr) if esc_arr else ('', '')
                            esc_fn = esc.get('flight_number', '')
                            real_flights_context += (
                                f"  → Tronçon {esc_idx + 1} ({esc_fn}): "
                                f"{esc_dep} ({esc_dep_city}) {esc.get('departure_time','?')} → "
                                f"{esc_arr} ({esc_arr_city}) {esc.get('arrival_time','?')}\n"
                            )

                    # Terminaux et portes
                    if flight.get('terminal_departure'):
                        real_flights_context += f"Terminal départ: {flight['terminal_departure']}\n"
                    if flight.get('gate_departure'):
                        real_flights_context += f"Porte départ: {flight['gate_departure']}\n"
                    if flight.get('terminal_arrival'):
                        real_flights_context += f"Terminal arrivée: {flight['terminal_arrival']}\n"
                    if flight.get('gate_arrival'):
                        real_flights_context += f"Porte arrivée: {flight['gate_arrival']}\n"

                    # Type d'avion
                    if flight.get('aircraft_type'):
                        real_flights_context += f"Appareil: {flight['aircraft_type']}\n"

                    # Prix (Amadeus Flight Offers)
                    if flight.get('price'):
                        price_label = f"{flight['price']} {flight.get('currency', 'EUR')}"
                        if flight.get('cabin_class'):
                            price_label += f" (classe {flight['cabin_class']})"
                        if flight.get('price_note'):
                            price_label += f" — {flight['price_note']}"
                        real_flights_context += f"Prix: {price_label}\n"
                    else:
                        real_flights_context += f"Prix: À confirmer avec la compagnie\n"

                    # Segments détaillés (pour vols avec escale)
                    if flight.get('segments'):
                        real_flights_context += f"Segments du trajet:\n"
                        for seg in flight['segments']:
                            real_flights_context += (
                                f"  Segment {seg['segment_number']}: "
                                f"{seg['departure_airport']} {seg['departure_time']} → "
                                f"{seg['arrival_airport']} {seg['arrival_time']}"
                            )
                            if seg.get('duration'):
                                real_flights_context += f" ({seg['duration']})"
                            if seg.get('departure_terminal'):
                                real_flights_context += f" | Terminal départ: {seg['departure_terminal']}"
                            if seg.get('departure_gate'):
                                real_flights_context += f" Porte: {seg['departure_gate']}"
                            real_flights_context += "\n"

                real_flights_context += f"\n🚨 RÈGLE STRICTE : Utilise UNIQUEMENT les champs ci-dessus. N'ajoute PAS d'informations non listées (pas de porte si non fournie, pas de prix si 'À confirmer').\n"

                # Ajouter les services officiels de la première compagnie trouvée
                for flight in real_flights_data:
                    airline_ctx = flight.get('airline_services_context', '')
                    if airline_ctx:
                        real_flights_context += airline_ctx
                        break  # Une seule compagnie suffit (aller/retour = même compagnie en général)
            
            # Sélectionner le prompt selon le type d'offre
            # IMPORTANT: real_time_search_results est TOUJOURS None (Tavily désactivé)
            # Seuls les vols réels d'Air France-KLM sont utilisés via real_flights_context
            print(f"📝 Préparation des prompts:")
            print(f"   - real_time_search_results: {real_time_search_results} (Tavily désactivé)")
            print(f"   - real_flights_context disponible: {bool(real_flights_context)}")
            if real_flights_context:
                print(f"   - Longueur real_flights_context: {len(real_flights_context)} caractères")
            
            # Sélectionner le prompt — séjour par défaut (pas de circuit automatique)
            if offer_type == "transport":
                prompt = self._get_prompt_transport(text_input, website_descriptions, processed_templates, None, travel_date, return_date, real_flights_context, offer_type, keywords=keywords, outbound_cabin_class=outbound_cabin_class, return_cabin_class=return_cabin_class, outbound_escales=outbound_escales, return_escales=return_escales)
            else:
                # "sejour" ou inconnu → prompt séjour (JAMAIS circuit automatique)
                prompt = self._get_prompt_sejour(text_input, website_descriptions, processed_templates, travel_date, return_date, None, real_flights_context, offer_type)

            # ── Contexte des nouveaux champs (v2) ─────────────────────────────
            structured_ctx = ""
            if destinations:
                dest_str = ", ".join(d for d in destinations if d.strip())
                structured_ctx += f"\n🌍 DESTINATION(S) : {dest_str}"
            if dates_texte:
                structured_ctx += f"\n📅 DATES DU SÉJOUR : {dates_texte}"
            if logements:
                log_str = ", ".join(l for l in logements if l.strip())
                structured_ctx += f"\n🏨 LOGEMENT(S) : {log_str}"
            if type_chambre:
                structured_ctx += f"\n🛏️ TYPE DE CHAMBRE : {type_chambre}"
            repas_labels = {'demi-pension': 'Demi-pension', 'pension-complete': 'Pension complète', 'petit-dejeuner': 'Petit-déjeuner inclus', 'tout-inclus': 'Tout inclus'}
            if repas:
                structured_ctx += f"\n🍽️ REPAS : {repas_labels.get(repas, repas)}"
            transfert_labels = {'prive': 'Transfert privé', 'regroupe': 'Transfert regroupé'}
            if transfert_type:
                structured_ctx += f"\n🚐 TRANSFERT : {transfert_labels.get(transfert_type, transfert_type)}"
            if croisiere:
                structured_ctx += f"\n🚢 CROISIÈRE : {croisiere}"
            if structured_ctx:
                structured_ctx = "\n\n📋 INFORMATIONS STRUCTURÉES DU SÉJOUR (à utiliser EXACTEMENT dans l'offre) :" + structured_ctx + "\n🚨 Utilise ces informations telles quelles dans les sections correspondantes. Ne les invente PAS.\n"
                prompt = structured_ctx + "\n" + prompt

            # Ajouter les mots-clés et infos cabine au prompt
            if keywords:
                keywords_suffix = f"\n\n🔑 MOTS-CLÉS DE LA DESCRIPTION (à réutiliser) : {', '.join(keywords)}\n"
                prompt = keywords_suffix + prompt
            cabin_labels = {"eco": "Économique", "premium_eco": "Premium Économique", "business": "Business"}
            cabin_suffix = ""
            if outbound_cabin_class and outbound_cabin_class != "eco":
                cabin_suffix += f"\n✈️ CLASSE VOL ALLER : {cabin_labels.get(outbound_cabin_class, outbound_cabin_class)}"
            if return_cabin_class and return_cabin_class != "eco":
                cabin_suffix += f"\n✈️ CLASSE VOL RETOUR : {cabin_labels.get(return_cabin_class, return_cabin_class)}"
            if outbound_escales:
                legs = " → ".join([e.get('flightNumber', '') for e in outbound_escales if e.get('flightNumber')])
                if legs:
                    cabin_suffix += f"\n🛑 VOLS ESCALES ALLER : {legs}"
            if return_escales:
                legs = " → ".join([e.get('flightNumber', '') for e in return_escales if e.get('flightNumber')])
                if legs:
                    cabin_suffix += f"\n🛑 VOLS ESCALES RETOUR : {legs}"
            if cabin_suffix:
                prompt = cabin_suffix + "\n" + prompt
            
            response = get_openai_client().chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Expert voyage. JSON uniquement."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2000,
                temperature=0.3,
                timeout=60  # Timeout de 60 secondes
            )
            
            offer_json = response.choices[0].message.content
            # Nettoyer le JSON
            if "```json" in offer_json:
                offer_json = offer_json.split("```json")[1].split("```")[0]
            elif "```" in offer_json:
                # Peut être ``` sans json
                offer_json = offer_json.split("```")[1].split("```")[0]
            
            # Nettoyer le JSON avant parsing
            offer_json_clean = offer_json.strip()
            
            # Supprimer les caractères invisibles et nettoyer
            offer_json_clean = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', offer_json_clean)  # Supprimer caractères de contrôle
            
            # Supprimer les URLs d'images qui apparaissent comme texte dans le contenu
            # Pattern pour détecter les URLs d'images (http/https avec extensions d'images)
            image_url_pattern = r'https?://[^\s"\'<>]+\.(jpg|jpeg|png|gif|webp|bmp|svg)(\?[^\s"\'<>]*)?'
            offer_json_clean = re.sub(image_url_pattern, '', offer_json_clean, flags=re.IGNORECASE)
            
            # Supprimer les références "image url" ou "image:" qui pourraient rester
            offer_json_clean = re.sub(r'(?i)(image\s*url|image:\s*|url\s*image)[^\s]*', '', offer_json_clean)
            
            try:
                offer_structure = json.loads(offer_json_clean)
            except json.JSONDecodeError as e:
                print(f"❌ ERREUR PARSING JSON: {e}")
                print(f"📄 JSON REÇU (premiers 1000 chars):\n{offer_json_clean[:1000]}")
                
                # Essayer de corriger les erreurs JSON courantes
                offer_json_fixed = offer_json_clean
                # Remplacer les apostrophes simples dans les clés/valeurs par des doubles quotes
                offer_json_fixed = re.sub(r"'(\w+)':", r'"\1":', offer_json_fixed)  # Clés avec apostrophes
                offer_json_fixed = re.sub(r':\s*\'([^\']*)\'', r': "\1"', offer_json_fixed)  # Valeurs avec apostrophes simples
                # Supprimer les virgules avant } ou ]
                offer_json_fixed = re.sub(r',(\s*[}\]])', r'\1', offer_json_fixed)
                # Corriger les guillemets non fermés
                offer_json_fixed = re.sub(r'(\w+):\s*([^",{\[\s]+)(\s*[,\n}])', r'\1: "\2"\3', offer_json_fixed)
                
                try:
                    offer_structure = json.loads(offer_json_fixed)
                    print("✅ JSON corrigé avec succès !")
                except json.JSONDecodeError as e2:
                    print(f"❌ Échec correction JSON: {e2}")
                    # Essayer une dernière fois avec json5 ou avec une approche plus permissive
                    try:
                        # Extraire juste le JSON entre les premières { et dernières }
                        start_idx = offer_json_fixed.find('{')
                        end_idx = offer_json_fixed.rfind('}')
                        if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                            offer_json_fixed = offer_json_fixed[start_idx:end_idx+1]
                            offer_structure = json.loads(offer_json_fixed)
                            print("✅ JSON extrait avec succès !")
                        else:
                            raise e2
                    except:
                    # Si ça échoue encore, retourner une erreur avec le JSON
                        error_context = offer_json_clean[max(0, e.pos-200):e.pos+200] if hasattr(e, 'pos') else offer_json_clean[:500]
                    return Response({
                        "error": f"Erreur parsing JSON OpenAI: {str(e)}",
                            "error_position": getattr(e, 'pos', None),
                            "raw_json_preview": error_context,
                            "hint": "Le JSON généré par OpenAI contient des erreurs de format. Veuillez réessayer."
                    }, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
            
            # ── Injecter section Formalités si fournie ────────────────────────
            if formalites and formalites.strip() and isinstance(offer_structure, dict):
                sections = offer_structure.get('sections', [])
                formalites_section = {
                    'id': 'formalites',
                    'type': 'Info',
                    'title': 'Formalités',
                    'body': formalites.strip(),
                    'images': [],
                }
                # Ajouter avant le CTA (à la fin des sections)
                sections.append(formalites_section)
                offer_structure['sections'] = sections
                print(f"   ✅ Section Formalités injectée")

            # Préparer les métadonnées de traçabilité
            airfrance_klm_used = search_metadata.get('source') == 'airfrance_klm'
            airfrance_klm_flights_count = search_metadata.get('real_flights_count', 0)
            
            print(f"📊 Préparation métadonnées:")
            print(f"   - search_metadata keys: {list(search_metadata.keys())}")
            print(f"   - search_metadata['source']: {search_metadata.get('source', 'NON DÉFINI')}")
            print(f"   - airfrance_klm_used: {airfrance_klm_used}")
            print(f"   - airfrance_klm_flights_count: {airfrance_klm_flights_count}")
            print(f"   - real_flights_data disponible: {bool(real_flights_data)}")
            if real_flights_data:
                print(f"   - Nombre de vols dans real_flights_data: {len(real_flights_data)}")
            print(f"   - travel_date fourni: {bool(travel_date)} ({travel_date if travel_date else 'NON FOURNI'})")
            print(f"   - return_date fourni: {bool(return_date)} ({return_date if return_date else 'NON FOURNI'})")
            
            metadata = {
                'search_info': {
                    'tavily_used': False,  # TOUJOURS False - Tavily désactivé
                    'airfrance_klm_used': airfrance_klm_used,
                    'airfrance_klm_flights_count': airfrance_klm_flights_count,
                    'search_query': None,  # Pas de Tavily
                    'results_count': 0,  # Pas de Tavily
                    'travel_date': travel_date,
                    'return_date': return_date,
                    'is_round_trip': bool(return_date),
                    'destinations_detected': search_metadata.get('destinations', []),
                    'search_attempted': search_metadata.get('search_attempted', False),
                    'destination_code_found': search_metadata.get('destination_code_found', False),
                    'travel_date_provided': search_metadata.get('travel_date_provided', False),
                    'origin_code': search_metadata.get('origin_code'),
                    'destination_code': search_metadata.get('destination_code'),
                    'origin_provided': search_metadata.get('origin_provided'),
                    'destination_provided': search_metadata.get('destination_provided'),
                    'failure_reason': search_metadata.get('failure_reason', []),
                },
                'website_scraping': {
                    'urls_provided': website_urls if website_urls else [],
                    'urls_scraped': [],
                    'successful_scrapes': 0,
                    'failed_scrapes': 0
                },
                'templates_used': {
                    'default_template_loaded': bool(default_templates),
                    'user_templates_count': len(example_templates) if example_templates else 0,
                    'total_templates': len(processed_templates) if processed_templates else 0
                },
                'tavily_results': None,  # TOUJOURS None - Tavily désactivé
                'airfrance_klm_flights': None  # Vols réels d'Air France-KLM si disponibles
            }
            
            # Ajouter les infos sur le scraping de sites
            if website_descriptions:
                metadata['website_scraping']['urls_scraped'] = [desc.get('url') for desc in website_descriptions if desc.get('url')]
                metadata['website_scraping']['successful_scrapes'] = len(website_descriptions)
            else:
                # Si des URLs ont été fournies mais aucune description récupérée
                if website_urls and len(website_urls) > 0:
                    metadata['website_scraping']['failed_scrapes'] = len(website_urls)
                    metadata['website_scraping']['error'] = "Aucun site n'a pu être scrappé. Vérifiez que les URLs sont accessibles et que le site n'utilise pas de protection anti-scraping."
            
            # Ajouter les vols réels d'Air France-KLM (pas Tavily)
            if real_flights_data:
                metadata['airfrance_klm_flights'] = real_flights_data
                print(f"📊 Métadonnées: {len(real_flights_data)} vol(s) Air France-KLM ajouté(s) aux métadonnées")
            
            # Tavily est DÉSACTIVÉ - plus de tavily_results
            print(f"📊 Métadonnées: tavily_results = None (Tavily désactivé)")
            
            # Enrichir les sections avec des images (y compris celles des sites web)
            # Ajouter les images scrapées aux métadonnées
            scraped_images = []
            if website_descriptions:
                for desc in website_descriptions:
                    if desc.get('images'):
                        scraped_images.extend(desc.get('images', []))

            # Injecter les photos Google Places EN PRIORITÉ (elles sont de meilleure qualité)
            if hotel_google_images:
                print(f"📸 {len(hotel_google_images)} photo(s) Google Places injectée(s) en priorité")
                scraped_images = list(hotel_google_images) + scraped_images

            # Passer les images scrapées à la fonction d'enrichissement
            self.enrich_sections_with_images(offer_structure, scraped_images=scraped_images)
            
            # VALIDATION CRITIQUE POST-PARSING : Supprimer les sections de vol inventées si aucune source valide
            # IMPORTANT: Tavily est désactivé, on utilise uniquement les vols Air France-KLM
            has_valid_flight_info = search_metadata.get('has_valid_flight_info', False)
            
            # Mettre à jour has_valid_flight_info avec les vols réels d'Air France-KLM
            if real_flights_data:
                has_valid_flight_info = True
                print(f"✅✅✅ Vols RÉELS d'Air France-KLM disponibles - validation passée")
            
            # Si pas d'infos valides, SUPPRIMER toutes les sections de vol inventées
            if not has_valid_flight_info and offer_structure.get("sections"):
                print("⚠️⚠️⚠️ VALIDATION CRITIQUE : Aucune source valide trouvée pour les vols")
                print("🔍 Vérification et SUPPRESSION des sections de vol inventées...")
                
                sections = offer_structure.get("sections", [])
                flight_sections_to_remove = []
                sections_to_keep = []
                
                for section in sections:
                    section_type = (section.get("type", "") or "").lower()
                    section_title = (section.get("title", "") or "").lower()
                    section_id = (section.get("id", "") or "").lower()
                    
                    # Détecter les sections de vol
                    is_flight_section = (
                        section_type == "flights" or 
                        "vol" in section_title or 
                        "transport aérien" in section_title or
                        section_id == "flights"
                    )
                    
                    if is_flight_section:
                        flight_sections_to_remove.append(section.get("title", "Transport Aérien"))
                        print(f"   ❌ Section SUPPRIMÉE (inventée) : '{section.get('title', 'Transport Aérien')}'")
                        # NE PAS ajouter cette section à sections_to_keep
                    else:
                        sections_to_keep.append(section)
                
                # Si on a supprimé des sections de vol, ajouter une section d'avertissement
                if flight_sections_to_remove:
                    print(f"   ⚠️ {len(flight_sections_to_remove)} section(s) de vol SUPPRIMÉE(S)")
                    warning_section = {
                        "id": "flight_warning",
                        "type": "Avertissement",
                        "title": "⚠️ Informations de vol non disponibles",
                        "body": "Les informations de vol pour cette route/date ne sont pas disponibles dans nos sources consultées.\n\n⚠️ IMPORTANT : Les horaires, compagnies aériennes et numéros de vol doivent être vérifiés directement auprès des compagnies aériennes avant toute réservation.\n\nMerci de contacter directement les compagnies aériennes pour obtenir les informations de vol actuelles et vérifier les disponibilités."
                    }
                    sections_to_keep.insert(0, warning_section)  # Ajouter au début
                    offer_structure["sections"] = sections_to_keep
                    print(f"   ✅ Section d'avertissement ajoutée à la place")
                    print("   ⚠️⚠️⚠️ PROTECTION CLIENT : Les sections de vol inventées ont été SUPPRIMÉES automatiquement")
                else:
                    print("   ℹ️ Aucune section de vol détectée (pas besoin de suppression)")
            
            # Enrichir les sections de vol avec des preuves (liens et sources) - SEULEMENT si on a des sources valides
            if has_valid_flight_info:
                # Si on a des vols réels (Air France-KLM ou Aviationstack), les utiliser comme source
                if real_flights_data:
                    source_type = search_metadata.get('source', 'airfrance_klm')
                    if source_type == 'airfrance_klm':
                        print("✅✅✅ Utilisation des vols RÉELS d'Air France-KLM comme source")
                        real_flights_source = {
                            "type": "Air France-KLM API (Vols réels vérifiables)",
                            "title": f"Vols réels Air France-KLM - {len(real_flights_data)} vol(s) trouvé(s)",
                            "url": "https://developer.airfranceklm.com",
                            "description": f"Vols réels vérifiables depuis l'API Air France-KLM avec horaires, numéros de vol et compagnies aériennes confirmés"
                        }
                    else:
                        print("✅✅✅ Utilisation des vols RÉELS d'Aviationstack comme source")
                        real_flights_source = {
                            "type": "Aviationstack (Vols réels vérifiables)",
                            "title": f"Vols réels {len(real_flights_data)} vol(s) trouvé(s)",
                            "url": "https://aviationstack.com/",
                            "description": f"Vols réels vérifiables depuis l'API Aviationstack avec horaires, numéros de vol et compagnies aériennes confirmés"
                        }
                    # Ajouter les vols réels aux métadonnées
                    search_metadata['real_flights'] = real_flights_data
                    # Injecter flight_data structuré dans les sections Flights
                    self._inject_flight_data_into_sections(offer_structure, real_flights_data)
                    self._enrich_flight_sections_with_sources(offer_structure, None, website_descriptions, search_metadata, real_flights_source=real_flights_source)
                else:
                    self._enrich_flight_sections_with_sources(offer_structure, None, website_descriptions, search_metadata, real_flights_source='airfrance_klm' if real_flights_data else None)
            else:
                print("⚠️⚠️⚠️ PROTECTION CLIENT : Aucune source valide - pas d'enrichissement des sections de vol (suppression effectuée)")
            
            # Nettoyer les URLs d'images du texte dans les sections
            if offer_structure.get("sections"):
                image_url_pattern = re.compile(
                    r'https?://[^\s"\'<>]+\.(jpg|jpeg|png|gif|webp|bmp|svg)(\?[^\s"\'<>]*)?',
                    re.IGNORECASE
                )
                
                # Pattern pour supprimer les références textuelles aux images
                image_text_patterns = [
                    re.compile(r'(?i)(image\s*url|image:\s*|url\s*image|image\s*:\s*http)[^\s]*', re.IGNORECASE),
                    re.compile(r'(?i)(voir\s*l\'?image|voir\s*image|image\s*ci-dessous|image\s*ci-dessus)[^\n]*', re.IGNORECASE),
                ]
                
                for section in offer_structure["sections"]:
                    # Nettoyer le body
                    if section.get("body"):
                        body = str(section["body"])
                        # Supprimer les URLs d'images
                        body = image_url_pattern.sub('', body)
                        # Supprimer les références textuelles aux images
                        for pattern in image_text_patterns:
                            body = pattern.sub('', body)
                        # Nettoyer les espaces multiples et lignes vides
                        body = re.sub(r'\n\s*\n\s*\n+', '\n\n', body)  # Max 2 sauts de ligne
                        body = re.sub(r' +', ' ', body)  # Un seul espace
                        section["body"] = body.strip()
                    
                    # Nettoyer le contenu
                    if section.get("content"):
                        content = str(section["content"])
                        content = image_url_pattern.sub('', content)
                        for pattern in image_text_patterns:
                            content = pattern.sub('', content)
                        content = re.sub(r'\n\s*\n\s*\n+', '\n\n', content)
                        content = re.sub(r' +', ' ', content)
                        section["content"] = content.strip()
                    
                    # Nettoyer la description (si elle existe)
                    if section.get("description"):
                        description = str(section.get("description"))
                        description = image_url_pattern.sub('', description)
                        for pattern in image_text_patterns:
                            description = pattern.sub('', description)
                        description = re.sub(r'\n\s*\n\s*\n+', '\n\n', description)
                        description = re.sub(r' +', ' ', description)
                        section["description"] = description.strip()
            
            # Nettoyer aussi l'introduction
            if offer_structure.get("introduction"):
                intro = str(offer_structure["introduction"])
                image_url_pattern = re.compile(
                    r'https?://[^\s"\'<>]+\.(jpg|jpeg|png|gif|webp|bmp|svg)(\?[^\s"\'<>]*)?',
                    re.IGNORECASE
                )
                intro = image_url_pattern.sub('', intro)
                intro = re.sub(r'(?i)(image\s*url|image:\s*|url\s*image)[^\s]*', '', intro)
                offer_structure["introduction"] = intro.strip()
            
            return Response({
                "offer_structure": offer_structure,
                "company_info": company_info,
                "metadata": metadata,  # ✅ Ajouter les métadonnées de traçabilité
                "scraped_images": scraped_images[:10] if scraped_images else []  # ✅ Ajouter les images scrapées
            })
            
        except Exception as e:
            return Response({"error": f"Erreur : {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def pick_image_for_section(self, section):
        """Sélectionne et cache une image pour une section donnée"""
        # Construire une query à partir du titre/type
        title = section.get("title", "").replace("✈️", "").replace("🚗", "").replace("🏨", "").replace("🎯", "").replace("💰", "").strip()
        section_type = section.get("type", "")
        
        # Queries spécifiques par type de section
        queries_map = {
            "Flights": f"{title} airplane travel",
            "Transfers": f"{title} airport transfer",
            "Hotel": f"{title} luxury hotel",
            "Activities": f"{title} travel activities",
            "Price": f"{title} travel booking"
        }
        
        query = queries_map.get(section_type, f"{title} {section_type}")
        
        images = []
        try:
            # Utiliser Unsplash par défaut (plus fiable) avec timeout réduit
            images = search_unsplash(query, per_page=1)
            if not images:
                # Fallback sur Bing si Unsplash échoue
                images = search_bing_images(query, count=1)
        except Exception as e:
            print(f"Erreur recherche image pour {section_type}: {e}")
        
        # Cache l'image si trouvée (sans bloquer) - avec timeout court
        if images:
            try:
                original_url = images[0]["url"]
                # Utiliser l'URL originale directement pour éviter le cache lent
                images[0]["url"] = original_url
                # Optionnel: cache en arrière-plan sans bloquer
                import threading
                def cache_in_background():
                    try:
                        cache_image(original_url)
                    except:
                        pass  # Ignore les erreurs de cache
                threading.Thread(target=cache_in_background, daemon=True).start()
            except Exception as e:
                print(f"Erreur cache image pour {section_type}: {e}")
                # Garde l'URL originale si le cache échoue
        
        section["images"] = images or []
        return section

    def enrich_sections_with_images(self, offer_structure, scraped_images=None):
        """Enrichit chaque section avec des images appropriées.
        Priorité aux images scrapées depuis les sites web.
        Pour les circuits: priorité aux sections Hotel/Hébergement/Activités."""
        sections = offer_structure.get("sections", [])
        
        # Si on a des images scrapées, les utiliser en priorité
        if scraped_images and len(scraped_images) > 0:
            print(f"📸 Utilisation de {len(scraped_images)} image(s) scrapée(s) depuis les sites web")
            
            # Dédoublonner les images pour éviter les répétitions
            unique_scraped_images = list(dict.fromkeys(scraped_images))  # Garde l'ordre, supprime les doublons
            if len(scraped_images) > len(unique_scraped_images):
                print(f"📸 {len(scraped_images) - len(unique_scraped_images)} image(s) en doublon supprimée(s)")
            
            # 🏨 PRIORITÉ pour les sections d'hébergement/hôtel dans les circuits
            hotel_sections = []
            activity_sections = []
            itinerary_sections = []
            other_sections = []
            
            for section in sections:
                section_type = section.get("type", "").lower()
                section_title = section.get("title", "").lower()
                
                if "hotel" in section_type or "hébergement" in section_title or "hôtel" in section_title:
                    hotel_sections.append(section)
                elif "activit" in section_type or "activit" in section_title or "excursion" in section_title:
                    activity_sections.append(section)
                elif "itinéraire" in section_title or "itinerary" in section_type or "programme" in section_title:
                    itinerary_sections.append(section)
                else:
                    other_sections.append(section)
            
            # Ordre de priorité pour l'attribution des images
            prioritized_sections = hotel_sections + activity_sections + itinerary_sections + other_sections
            
            print(f"   🏨 {len(hotel_sections)} section(s) d'hôtel/hébergement (priorité haute)")
            print(f"   🎯 {len(activity_sections)} section(s) d'activités (priorité moyenne)")
            print(f"   🗺️ {len(itinerary_sections)} section(s) d'itinéraire (priorité moyenne)")
            print(f"   📋 {len(other_sections)} autre(s) section(s)")
            
            image_index = 0
            used_images = set()  # Tracker les images déjà utilisées pour éviter les doublons
            
            for section in prioritized_sections:
                section_type = section.get("type", "").lower()
                section_title = section.get("title", "").lower()
                
                # Déterminer le nombre d'images en fonction du type de section
                is_hotel_section = "hotel" in section_type or "hébergement" in section_title or "hôtel" in section_title
                is_activity_section = "activit" in section_type or "activit" in section_title or "excursion" in section_title
                is_itinerary_section = "itinéraire" in section_title or "itinerary" in section_type or "programme" in section_title
                
                # Plus d'images pour les sections importantes
                target_images = 3 if is_hotel_section else 2 if (is_activity_section or is_itinerary_section) else 2
                
                # Pour TOUTES les sections, utiliser des images scrapées si disponibles
                if image_index < len(unique_scraped_images) and not section.get("image") and not section.get("images"):
                    section_images = []
                    # Prendre le nombre d'images ciblé
                    while len(section_images) < target_images and image_index < len(unique_scraped_images):
                        image_url = unique_scraped_images[image_index]
                        if image_url not in used_images:
                            section_images.append({"url": image_url})
                            used_images.add(image_url)
                        image_index += 1
                    
                    # Si on n'a pas assez d'images scrapées, compléter avec des images API si disponible
                    if len(section_images) < target_images and (UNSPLASH_KEY or BING_KEY):
                        try:
                            # Chercher des images supplémentaires via API
                            title = section.get("title", "")
                            body = section.get("body", "")
                            
                            # Créer une requête intelligente basée sur le contenu
                            if is_hotel_section:
                                query = f"luxury hotel room {title}"
                            elif is_activity_section:
                                query = f"{title} travel activity"
                            else:
                                query = f"{title} travel"
                            
                            api_images = []
                            if UNSPLASH_KEY:
                                api_images = search_unsplash(query, per_page=target_images - len(section_images))
                            if not api_images and BING_KEY:
                                api_images = search_bing_images(query, count=target_images - len(section_images))
                            
                            for api_img in api_images:
                                additional_url = api_img.get("url")
                                if additional_url and additional_url not in used_images:
                                    section_images.append({"url": additional_url})
                                    used_images.add(additional_url)
                                    if len(section_images) >= target_images:
                                        break
                        except Exception as e:
                            print(f"   ⚠️ Erreur recherche image API pour section '{section.get('title')}': {e}")
                    
                    if section_images:
                        section["images"] = section_images
                        section["image"] = section_images[0]["url"]  # Format simple aussi pour compatibilité
                        emoji = "🏨" if is_hotel_section else "🎯" if is_activity_section else "📸"
                        print(f"   {emoji} {len(section_images)} image(s) ajoutée(s) à la section '{section.get('title')}'")
                elif not section.get("image"):
                    # Si pas d'image scrapée disponible, chercher via API
                    # (on continue ci-dessous avec le code existant)
                    pass
        
        # Vérifier si les APIs d'images sont configurées pour les sections restantes
        if not UNSPLASH_KEY and not BING_KEY:
            if not scraped_images or len(scraped_images) == 0:
                print("⚠️ Aucune API d'images configurée et aucune image scrapée - sections sans images")
            return
        
        # Limiter le nombre de sections pour éviter les timeouts (seulement pour les sections sans images scrapées)
        sections_to_process = [s for s in sections if not s.get("image")][:1]  # Max 1 section pour limiter les délais
        
        # Traitement asynchrone des images pour éviter les timeouts
        import threading
        import time
        
        def process_section_async(section):
            try:
                self.pick_image_for_section(section)
            except Exception as e:
                print(f"Erreur traitement image section {section.get('type', 'unknown')}: {e}")
                section["images"] = []  # Fallback sûr
        
        # Lancer les traitements en parallèle avec timeout
        threads = []
        for section in sections_to_process:
            thread = threading.Thread(target=process_section_async, args=(section,))
            thread.daemon = True
            thread.start()
            threads.append(thread)
        
        # Attendre maximum 10 secondes pour tous les threads
        start_time = time.time()
        for thread in threads:
            remaining_time = 10 - (time.time() - start_time)
            if remaining_time > 0:
                thread.join(timeout=remaining_time)
            else:
                break

    def _inject_flight_data_into_sections(self, offer_structure, real_flights_data):
        """
        Injecte les données de vol structurées (Amadeus) dans les sections Flights de l'offer_structure.
        Ajoute 'flight_data' à chaque section pour affichage visuel côté frontend (logo, horaires, escales).
        """
        if not real_flights_data or not offer_structure.get("sections"):
            return

        sections = offer_structure.get("sections", [])
        flight_sections = [
            s for s in sections
            if (s.get("type", "").lower() == "flights"
                or "vol" in s.get("title", "").lower()
                or "transport" in s.get("title", "").lower()
                or s.get("id", "").lower() in ("flights", "vols", "transport"))
        ]

        if not flight_sections:
            return

        # Séparer aller / retour
        aller_flights = [f for f in real_flights_data if f.get('leg') != 'retour']
        retour_flights = [f for f in real_flights_data if f.get('leg') == 'retour']

        print(f"💉 Injection flight_data dans {len(flight_sections)} section(s) de vol")

        for i, section in enumerate(flight_sections):
            # Première section → vol aller, deuxième → retour (si existe)
            relevant_flights = aller_flights if i == 0 else (retour_flights if retour_flights else aller_flights)
            if not relevant_flights:
                continue

            flight = relevant_flights[0]

            # Route manuelle sans numéro de vol → afficher message À compléter, pas de flight_data
            if flight.get('source') == 'manual':
                dep_city = flight.get('departure_city', '')
                arr_city = flight.get('arrival_city', '')
                route_str = f"{dep_city} → {arr_city}" if dep_city or arr_city else ''
                section['body'] = (
                    f"⚠️ Informations de vol à compléter\n\n"
                    f"{route_str + chr(10) if route_str else ''}"
                    f"Veuillez fournir le numéro de vol et la date pour obtenir les horaires exacts, "
                    f"les terminaux et les éventuelles escales via Amadeus."
                )
                print(f"   ℹ️ Section '{section.get('title')}' : route manuelle sans horaires ({route_str})")
                continue

            # Construire la structure flight_data propre pour le frontend
            stopovers = flight.get('stopovers', [])
            # Normaliser les stopovers (parfois liste de strings, parfois liste de dicts)
            stopovers_normalized = []
            for stop in stopovers:
                if isinstance(stop, dict):
                    stopovers_normalized.append(stop)
                elif isinstance(stop, str):
                    stopovers_normalized.append({'airport': stop, 'city': '', 'layover_duration': ''})

            # Calculer le décalage de jour entre départ et arrivée (heures locales Amadeus)
            dep_full = flight.get('departure_datetime_full', '')
            arr_full = flight.get('arrival_datetime_full', '')
            arrival_day_offset = 0
            if dep_full and arr_full:
                try:
                    dep_date = datetime.fromisoformat(dep_full.replace('Z', '+00:00')).date()
                    arr_date = datetime.fromisoformat(arr_full.replace('Z', '+00:00')).date()
                    arrival_day_offset = (arr_date - dep_date).days
                except Exception:
                    pass

            flight_data = {
                'flight_number': flight.get('flight_number', ''),
                'carrier_code': flight.get('carrier_code', ''),
                'airline': flight.get('airline', flight.get('carrier_code', '')),
                'airline_logo_url': flight.get('airline_logo_url', ''),
                'departure_airport': flight.get('departure_airport', ''),
                'departure_city': flight.get('departure_city', ''),
                'departure_country': flight.get('departure_country', ''),
                'departure_time': flight.get('departure_time', ''),
                'departure_terminal': flight.get('terminal_departure', ''),
                'arrival_airport': flight.get('arrival_airport', ''),
                'arrival_city': flight.get('arrival_city', ''),
                'arrival_country': flight.get('arrival_country', ''),
                'arrival_time': flight.get('arrival_time', ''),
                'arrival_terminal': flight.get('terminal_arrival', ''),
                'total_duration': flight.get('duration', ''),
                'stops': flight.get('stops', 0),
                'stopovers': stopovers_normalized,
                'cabin_class': flight.get('cabin_class', ''),
                'aircraft_type': flight.get('aircraft_type', ''),
                'leg': flight.get('leg', 'aller'),
                'arrival_day_offset': arrival_day_offset,  # 0 = même jour, 1 = +1j, 2 = +2j
            }

            section['flight_data'] = flight_data

            # Améliorer le body avec un texte structuré à partir des données réelles
            dep_airport = flight_data['departure_airport']
            arr_airport = flight_data['arrival_airport']
            dep_city = flight_data['departure_city']
            arr_city = flight_data['arrival_city']
            dep_time = flight_data['departure_time']
            arr_time = flight_data['arrival_time']
            duration = flight_data['total_duration']
            fn = flight_data['flight_number']
            cabin = flight_data['cabin_class'] or ''
            cabin_label = {'eco': 'Économique', 'premium_eco': 'Premium Économique', 'business': 'Business'}.get(cabin, cabin)
            dep_terminal = flight_data.get('departure_terminal') or ''
            arr_terminal = flight_data.get('arrival_terminal') or ''

            lines = []
            leg_label = '✈️ Vol aller' if flight_data['leg'] != 'retour' else '✈️ Vol retour'
            header_parts = [leg_label]
            if fn:
                header_parts.append(fn)
            if cabin_label:
                header_parts.append(cabin_label)
            lines.append('  |  '.join(header_parts))
            lines.append('')

            route = f"{dep_airport} → {arr_airport}"
            if dep_city or arr_city:
                route_cities = f"{dep_city or dep_airport} → {arr_city or arr_airport}"
                lines.append(route)
                lines.append(route_cities)
            else:
                lines.append(route)
            lines.append('')

            if dep_time:
                dep_line = f"Départ : {dep_time}"
                if dep_terminal:
                    dep_line += f" (Terminal {dep_terminal})"
                lines.append(dep_line)
            if arr_time:
                arr_line = f"Arrivée : {arr_time}"
                if arr_terminal:
                    arr_line += f" (Terminal {arr_terminal})"
                lines.append(arr_line)
            if duration:
                lines.append(f"Durée totale : {duration}")

            if stopovers_normalized:
                lines.append('')
                for stop in stopovers_normalized:
                    stop_airport = stop.get('airport', '')
                    stop_city = stop.get('city', '')
                    stop_duration = stop.get('layover_duration', '')
                    stop_line = f"Escale : {stop_airport}"
                    if stop_city:
                        stop_line += f" ({stop_city})"
                    if stop_duration:
                        stop_line += f" — {stop_duration} de correspondance"
                    lines.append(stop_line)

            section['body'] = '\n'.join(lines)
            print(f"   ✅ Section '{section.get('title')}' enrichie avec flight_data ({fn}, {dep_airport}→{arr_airport})")

    def _enrich_flight_sections_with_sources(self, offer_structure, real_time_search_results, website_descriptions, search_metadata, real_flights_source=None):
        """Enrichit les sections de vol avec une seule source (la meilleure) pour prouver les informations"""
        sections = offer_structure.get("sections", [])
        
        # Trouver les sections de vol (Flights)
        flight_sections = [s for s in sections if s.get("type", "").lower() == "flights" or "vol" in s.get("title", "").lower() or "transport aérien" in s.get("title", "").lower()]
        
        if not flight_sections:
            print("ℹ️ Aucune section de vol trouvée pour enrichissement avec sources")
            return
        
        print(f"📋 Enrichissement de {len(flight_sections)} section(s) de vol avec une source de preuve...")
        
        # Préparer la meilleure source disponible (priorité : Aviationstack > Tavily > Sites web)
        best_source = None
        
        # Priorité 1 : Source Air France-KLM ou Aviationstack (vols RÉELS) - LA MEILLEURE SOURCE
        if real_flights_source:
            best_source = real_flights_source
            source_name = "Air France-KLM" if "Air France-KLM" in best_source.get('type', '') else "Aviationstack"
            print(f"   ✅✅✅ Source {source_name} (vols RÉELS) sélectionnée: {best_source['title']}")
        
        # Priorité 2 : Source depuis Tavily (recherche en temps réel) - seulement si pas de vols réels
        if not best_source and real_time_search_results:
            print(f"🔗 {len(real_time_search_results)} source(s) Tavily disponibles pour les vols")
            for result in real_time_search_results:
                url = result.get("url", "")
                content = result.get("content", "").lower() or result.get("raw_content", "").lower()
                
                # Vérifier que le résultat contient réellement des infos de vol (pas juste "aucun vol trouvé")
                if url and content:
                    # Détecter les messages négatifs (pas de vol trouvé, aucun résultat, etc.)
                    negative_indicators = [
                        "aucun vol", "no flights", "no results", "aucun résultat",
                        "pas de vol", "vols non disponibles", "not available",
                        "aucune disponibilité", "no availability", "not found"
                    ]
                    has_negative_indicator = any(indicator in content for indicator in negative_indicators)
                    
                    if has_negative_indicator:
                        print(f"   ⚠️ Source Tavily exclue (message négatif détecté): {result.get('title', 'Source')}")
                        continue
                    
                    # Vérifier qu'il y a des infos positives (numéro de vol, horaires, compagnie, etc.)
                    positive_indicators = [
                        "vol", "flight", "departure", "départ", "arrival", "arrivée",
                        "airline", "compagnie", "terminal", "horaires", "schedule"
                    ]
                    has_positive_indicator = any(indicator in content for indicator in positive_indicators)
                    
                    if has_positive_indicator:
                        best_source = {
                            "type": "Tavily (Recherche temps réel)",
                            "title": result.get("title", "Source Tavily"),
                            "url": url,
                            "description": "Recherche en temps réel pour horaires et prix des vols"
                        }
                        print(f"   ✅ Source Tavily sélectionnée: {best_source['title']} - {best_source['url']}")
                        break
                    else:
                        print(f"   ⚠️ Source Tavily exclue (pas d'infos de vol valides): {result.get('title', 'Source')}")
                elif url:
                    # Si on a une URL mais pas de contenu, on peut quand même l'utiliser
                    best_source = {
                        "type": "Tavily (Recherche temps réel)",
                        "title": result.get("title", "Source Tavily"),
                        "url": url,
                        "description": "Recherche en temps réel pour horaires et prix des vols"
                    }
                    print(f"   ✅ Source Tavily sélectionnée (sans contenu): {best_source['title']} - {best_source['url']}")
                    break
        
        # Priorité 2 : Source depuis les sites web scrapés (si pas de Tavily)
        if not best_source and website_descriptions:
            print(f"🔗 {len(website_descriptions)} site(s) web scrapé(s) disponibles comme sources")
            for desc in website_descriptions:
                url = desc.get("url", "")
                if url:
                    # Vérifier si le contenu contient des infos de vol
                    content = desc.get("content", "").lower()
                    if any(keyword in content for keyword in ["vol", "flight", "compagnie", "airline", "aéroport", "départ", "arrivée"]):
                        best_source = {
                            "type": "Site web scrapé",
                            "title": f"Site web: {url[:50]}...",
                            "url": url,
                            "description": "Informations de vol extraites depuis le site web"
                        }
                        print(f"   ✅ Source Site web sélectionnée: {best_source['url']}")
                        break
        
        # Logs détaillés
        if best_source:
            print(f"📊 Source de preuve sélectionnée pour les vols:")
            print(f"   Type: {best_source['type']}")
            print(f"   Titre: {best_source['title']}")
            print(f"   URL: {best_source['url']}")
            print(f"   Description: {best_source['description']}")
        else:
            print("⚠️ Aucune source de preuve disponible pour les vols (pas de recherche Tavily ni de sites web avec infos de vol)")
        
        # Ajouter la source unique à chaque section de vol (METADATA SEULEMENT - PAS DE TEXTE)
        for flight_section in flight_sections:
            section_title = flight_section.get("title", "Transport Aérien")
            print(f"\n✈️ Enrichissement section '{section_title}' avec source (metadata seulement)...")
            
            # Ajouter un champ "source" (singulier) avec le lien - METADATA SEULEMENT
            if best_source:
                flight_section["source"] = best_source  # Champ singulier pour métadonnées
                print(f"   ✅ Source ajoutée aux métadonnées de la section '{section_title}' (pas de modification du texte)")
                
                # ❌ NE PLUS ajouter le lien dans le body - l'utilisateur ne veut pas de sources/références dans le texte
                # Le body reste tel quel, sans ajout de source
            else:
                print(f"   ⚠️ Aucune source disponible pour la section '{section_title}'")
                flight_section["source"] = None
                
                # ❌ NE PLUS ajouter de note critique dans le body
                # Le body reste tel quel, même si les informations sont inventées
                print(f"   ℹ️ Pas de source mais pas de note critique ajoutée (texte propre demandé par l'utilisateur)")


class UrlPreviewView(APIView):
    """
    POST { url } → retourne { title, description, images[] } depuis le scraping léger de l'URL.
    Utilisé pour afficher une galerie de prévisualisation dans le formulaire.
    """
    permission_classes = [AllowAny]

    def post(self, request):
        url = request.data.get("url", "").strip()
        if not url:
            return Response({"error": "URL manquante"}, status=400)
        if not url.startswith(("http://", "https://")):
            url = "https://" + url
        try:
            import requests as req_lib
            from bs4 import BeautifulSoup as BS4
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
                "Referer": "https://www.google.com/",
            }
            r = req_lib.get(url, headers=headers, timeout=8, allow_redirects=True)
            soup = BS4(r.content, "html.parser")

            # Titre
            title = ""
            if soup.find("meta", property="og:title"):
                title = soup.find("meta", property="og:title").get("content", "")
            if not title and soup.title:
                title = soup.title.string or ""
            title = title.strip()[:120]

            # Description
            description = ""
            for attr in [("property", "og:description"), ("name", "description")]:
                tag = soup.find("meta", {attr[0]: attr[1]})
                if tag and tag.get("content"):
                    description = tag.get("content", "").strip()[:300]
                    break

            # ── Images ──────────────────────────────────────────────────────
            from urllib.parse import urlparse as _urlparse
            import re as _re
            _parsed_base = _urlparse(url)
            _base = f"{_parsed_base.scheme}://{_parsed_base.netloc}"

            images = []
            seen_imgs = set()

            def _norm(src):
                """Normalise un src relatif/protocol-relatif en URL absolue."""
                if not src:
                    return None
                src = src.strip()
                if src.startswith("//"):
                    src = "https:" + src
                elif src.startswith("/"):
                    src = _base + src
                if not src.startswith("http"):
                    return None
                return src

            def _add(src):
                """Ajoute une URL image si elle est valide et nouvelle."""
                n = _norm(src)
                if not n or n in seen_imgs:
                    return
                low = n.lower().split("?")[0]
                # Ignorer SVG, GIF animés, pixels de tracking, data-URI, icônes
                if any(low.endswith(x) for x in (".svg", ".gif", ".ico", ".webp")):
                    return
                if "data:" in low or "base64" in low:
                    return
                if any(s in low for s in ("1x1", "pixel", "tracking", "spacer", "blank", "placeholder", "noimage", "no-image")):
                    return
                seen_imgs.add(n)
                images.append(n)

            # 1. Toutes les balises og:image (certains sites en ont plusieurs)
            for tag in soup.find_all("meta", property="og:image"):
                _add(tag.get("content", ""))

            # 2. Balises <img> — vérifie src ET les attributs lazy-loading courants
            LAZY_ATTRS = [
                "data-src", "data-lazy-src", "data-lazy", "data-original",
                "data-hi-res-src", "data-full-src", "data-img-src", "data-image",
                "data-bg", "data-background",
            ]
            for img_tag in soup.find_all("img"):
                w = img_tag.get("width", "")
                h = img_tag.get("height", "")
                try:
                    if int(w) < 80 or int(h) < 60:
                        continue  # Icône / placeholder minuscule
                except (ValueError, TypeError):
                    pass

                # Cherche le premier attribut lazy, sinon src
                found = False
                for attr in LAZY_ATTRS:
                    val = img_tag.get(attr, "").strip()
                    if val and not val.startswith("data:"):
                        _add(val)
                        found = True
                        break
                if not found:
                    _add(img_tag.get("src", ""))

                # srcset (ex: "img-400.jpg 400w, img-800.jpg 800w")
                for sset_attr in ("srcset", "data-srcset"):
                    sset = img_tag.get(sset_attr, "")
                    if sset:
                        for part in sset.split(","):
                            chunk = part.strip().split()[0]
                            _add(chunk)

                if len(images) >= 20:
                    break

            # 3. Balises <source> dans les éléments <picture>
            if len(images) < 20:
                for src_tag in soup.find_all("source"):
                    for attr in ("srcset", "data-srcset"):
                        sset = src_tag.get(attr, "")
                        if sset:
                            for part in sset.split(","):
                                _add(part.strip().split()[0])
                    if len(images) >= 20:
                        break

            # 4. Contenu <noscript> (fallback des carousels lazy)
            if len(images) < 20:
                for ns in soup.find_all("noscript"):
                    inner = BS4(ns.decode_contents(), "html.parser")
                    for img_tag in inner.find_all("img"):
                        _add(img_tag.get("src", ""))
                    if len(images) >= 20:
                        break

            # 5. CSS background-image dans les attributs style inline
            if len(images) < 20:
                _bg_re = _re.compile(r'background(?:-image)?\s*:\s*url\([\'"]?([^\'")]+)[\'"]?\)', _re.I)
                for tag in soup.find_all(style=True):
                    for m in _bg_re.finditer(tag.get("style", "")):
                        _add(m.group(1))
                    if len(images) >= 20:
                        break

            return Response({"title": title, "description": description, "images": images})
        except Exception as e:
            print(f"⚠️ URL preview error for {url}: {e}")
            return Response({"title": "", "description": "", "images": []})


class HotelGoogleSearchView(APIView):
    """
    POST { url } ou { query }
    → Extrait le nom de l'hôtel depuis l'URL, puis cherche via Google Places API (New).
    Retourne : name, address, rating, phone, website, google_maps_url, photos[]
    """
    permission_classes = [AllowAny]

    # Places API (New) — v1
    PLACES_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"
    PLACES_PHOTO_BASE = "https://places.googleapis.com/v1/{name}/media"

    def post(self, request):
        import requests as req_lib

        api_key = getattr(settings, "GOOGLE_PLACES_API_KEY", None)
        if not api_key:
            return Response({"error": "GOOGLE_PLACES_API_KEY non configurée. Ajoutez-la dans le fichier .env."}, status=503)

        url = request.data.get("url", "").strip()
        query = request.data.get("query", "").strip()

        if url and not query:
            query = self._extract_hotel_name_from_url(url, req_lib)

        if not query:
            return Response({"error": "Impossible d'extraire le nom de l'hôtel depuis cette URL."}, status=400)

        print(f"🔍 Google Places (New) : recherche '{query}'")

        try:
            # Places API (New) — Text Search
            field_mask = (
                "places.id,places.displayName,places.formattedAddress,"
                "places.rating,places.userRatingCount,"
                "places.internationalPhoneNumber,places.websiteUri,"
                "places.googleMapsUri,places.photos"
            )
            headers = {
                "Content-Type": "application/json",
                "X-Goog-Api-Key": api_key,
                "X-Goog-FieldMask": field_mask,
            }
            body = {
                "textQuery": query,
                "includedType": "lodging",
                "languageCode": "fr",
                "maxResultCount": 1,
            }
            search_resp = req_lib.post(self.PLACES_SEARCH_URL, json=body, headers=headers, timeout=10)
            search_data = search_resp.json()

            if search_resp.status_code != 200:
                err = search_data.get("error", {})
                return Response(
                    {"error": f"Google Places erreur {search_resp.status_code}: {err.get('message', search_resp.text[:200])}"},
                    status=502,
                )

            places = search_data.get("places", [])
            if not places:
                return Response({"error": f"Aucun hôtel trouvé pour : {query}", "query_used": query}, status=404)

            place = places[0]
            place_id = place.get("id", "")
            name = place.get("displayName", {}).get("text", "")
            print(f"   ✅ Trouvé: {name} (id={place_id})")

            # Construire les URLs de photos (Places API New)
            photos = []
            for photo in place.get("photos", [])[:10]:
                photo_name = photo.get("name", "")  # ex: "places/ChIJ.../photos/AXCi2Q..."
                if photo_name:
                    photo_url = f"https://places.googleapis.com/v1/{photo_name}/media?maxHeightPx=800&key={api_key}"
                    photos.append(photo_url)

            return Response({
                "query_used": query,
                "name": name,
                "address": place.get("formattedAddress", ""),
                "rating": place.get("rating"),
                "user_ratings_total": place.get("userRatingCount"),
                "phone": place.get("internationalPhoneNumber", ""),
                "website": place.get("websiteUri", url or ""),
                "google_maps_url": place.get("googleMapsUri", f"https://www.google.com/maps/place/?q=place_id:{place_id}"),
                "photos": photos,
                "place_id": place_id,
            })

        except req_lib.exceptions.Timeout:
            return Response({"error": "Timeout Google Places API (>10s)"}, status=504)
        except Exception as e:
            print(f"❌ HotelGoogleSearchView error: {e}")
            return Response({"error": str(e)}, status=500)

    def _extract_hotel_name_from_url(self, url: str, req_lib) -> str:
        """
        Tente d'extraire le nom de l'hôtel depuis :
        1. La balise og:title de la page (rapide, 5s timeout)
        2. En fallback : segments de l'URL nettoyés
        """
        from urllib.parse import urlparse
        from bs4 import BeautifulSoup as BS4

        if not url.startswith(("http://", "https://")):
            url = "https://" + url

        # Essai 1 : og:title de la page
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.7",
            }
            r = req_lib.get(url, headers=headers, timeout=5, allow_redirects=True)
            soup = BS4(r.content, "html.parser")
            for meta_attr in [("property", "og:title"), ("name", "twitter:title")]:
                tag = soup.find("meta", {meta_attr[0]: meta_attr[1]})
                if tag and tag.get("content"):
                    name = tag["content"].strip()
                    # Nettoyer les suffixes courants (site name, "|", "-")
                    for sep in [" | ", " - ", " – ", " : ", " • "]:
                        if sep in name:
                            name = name.split(sep)[0].strip()
                    print(f"   📰 Nom extrait (og:title): {name}")
                    return name
            if soup.title and soup.title.string:
                name = soup.title.string.strip()
                for sep in [" | ", " - ", " – ", " : ", " • "]:
                    if sep in name:
                        name = name.split(sep)[0].strip()
                print(f"   📰 Nom extrait (title): {name}")
                return name
        except Exception as e:
            print(f"   ⚠️ Scraping titre échoué: {e}")

        # Fallback : URL path segments
        parsed = urlparse(url)
        segments = [s for s in parsed.path.split("/") if len(s) > 3 and not s.startswith("?")]
        if segments:
            name = segments[-1].replace("-", " ").replace("_", " ").title()
            print(f"   📰 Nom extrait (URL path): {name}")
            return name

        # Dernier recours : domaine seul + "hotel"
        domain = parsed.netloc.replace("www.", "").split(".")[0]
        return f"hotel {domain}"


class ImageSearchView(APIView):
    """
    GET api/search-images/?q=<query>&count=<n>&page=<p>
    Recherche d'images : Google CSE → Pixabay → Unsplash → Freepik (premier qui répond).
    Retourne { images: [{url, thumb, alt, author, source}], provider, error? }
    """
    permission_classes = [AllowAny]

    def get(self, request):
        query = request.GET.get('q', '').strip()
        count = min(int(request.GET.get('count', 20)), 200)
        page = max(1, int(request.GET.get('page', 1)))
        if not query:
            return Response({'images': [], 'provider': None})

        # ── 0. Google Custom Search ────────────────────────────────────────
        gcs_key = GOOGLE_CSE_KEY or getattr(settings, 'GOOGLE_CSE_API_KEY', '')
        gcs_cx  = GOOGLE_CSE_CX  or getattr(settings, 'GOOGLE_CSE_CX', '')
        if gcs_key and gcs_cx:
            try:
                per_req = min(count, 10)  # Google CSE max 10 par requête
                start = (page - 1) * per_req + 1
                r = requests.get(
                    'https://www.googleapis.com/customsearch/v1',
                    params={
                        'key': gcs_key,
                        'cx': gcs_cx,
                        'q': query,
                        'searchType': 'image',
                        'num': per_req,
                        'start': start,
                        'imgType': 'photo',
                        'safe': 'active',
                    },
                    timeout=10,
                )
                print(f"Google CSE status: {r.status_code}")
                if r.status_code == 200:
                    items = r.json().get('items', [])
                    images = [
                        {
                            'url': item['link'],
                            'thumb': item.get('image', {}).get('thumbnailLink', item['link']),
                            'alt': item.get('title', query),
                            'author': item.get('displayLink', ''),
                            'source': 'google',
                        }
                        for item in items if item.get('link')
                    ]
                    if images:
                        return Response({'images': images, 'provider': 'google'})
            except Exception as e:
                print(f"Google CSE error: {e}")

        # ── 1. Pixabay ─────────────────────────────────────────────────────
        pixabay_key = PIXABAY_KEY or getattr(settings, 'PIXABAY_API_KEY', '')
        if pixabay_key:
            try:
                r = requests.get(
                    'https://pixabay.com/api/',
                    params={
                        'key': pixabay_key,
                        'q': query,
                        'image_type': 'photo',
                        'orientation': 'horizontal',
                        'safesearch': 'true',
                        'per_page': count,
                        'page': page,
                        'order': 'popular',
                    },
                    timeout=10,
                )
                print(f"Pixabay status: {r.status_code}")
                if r.status_code == 200:
                    hits = r.json().get('hits', [])
                    images = [
                        {
                            'url': h['webformatURL'],
                            'thumb': h.get('previewURL', h['webformatURL']),
                            'alt': h.get('tags', query),
                            'author': h.get('user', ''),
                            'source': 'pixabay',
                        }
                        for h in hits if h.get('webformatURL')
                    ]
                    if images:
                        return Response({'images': images, 'provider': 'pixabay'})
            except Exception as e:
                print(f"Pixabay error: {e}")

        # ── 2. Unsplash ────────────────────────────────────────────────────
        unsplash_results = search_unsplash(query, per_page=count)
        if unsplash_results:
            images = [
                {
                    'url': r['url'],
                    'thumb': r.get('thumb', r['url']),
                    'alt': query,
                    'author': r.get('photographer', ''),
                    'source': 'unsplash',
                }
                for r in unsplash_results
            ]
            return Response({'images': images, 'provider': 'unsplash'})

        # ── 3. Freepik ─────────────────────────────────────────────────────
        freepik_key = getattr(settings, 'FREEPIK_API_KEY', '')
        if freepik_key:
            try:
                r = requests.get(
                    'https://api.freepik.com/v1/resources',
                    params={
                        'term': query, 'page': 1, 'limit': count,
                        'order': 'relevance',
                        'filters[content_type][photo]': 1,
                        'filters[orientation][landscape]': 1,
                        'locale': 'en-US',
                    },
                    headers={'X-Freepik-API-Key': freepik_key},
                    timeout=10,
                )
                print(f"Freepik status: {r.status_code}")
                if r.status_code == 200:
                    images = []
                    for item in r.json().get('data', []):
                        # Essayer plusieurs champs possibles pour l'URL
                        url = (
                            (item.get('preview') or {}).get('url') or
                            (item.get('thumbnail') or {}).get('url') or
                            item.get('url', '')
                        )
                        if url:
                            images.append({
                                'url': url,
                                'thumb': url,
                                'alt': item.get('title', query),
                                'author': '',
                                'source': 'freepik',
                            })
                    if images:
                        return Response({'images': images, 'provider': 'freepik'})
                    print(f"Freepik: 0 images dans la réponse")
                else:
                    print(f"Freepik error {r.status_code}: {r.text[:200]}")
            except Exception as e:
                print(f"Freepik error: {e}")

        # ── Aucun provider disponible ──────────────────────────────────────
        return Response({
            'images': [],
            'provider': None,
            'error': 'Aucun fournisseur d\'images configuré. Ajoutez PIXABAY_API_KEY dans .env (gratuit sur pixabay.com/api/docs)',
        })


class PDFOfferGenerator(APIView):
    """
    Génère un PDF à partir d'un texte d'offre
    Cette classe est dépréciée - utiliser TravelOfferGenerator + GrapesJSPDFGenerator
    """
    permission_classes = [AllowAny]
    
    def post(self, request):
        text_input = request.data.get("text")
        company_info = request.data.get("company_info", {})
        
        if not text_input:
            return Response({"error": "Texte requis"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            # Générer d'abord la structure de l'offre
            travel_generator = TravelOfferGenerator()
            offer_response = travel_generator.post(request)
            
            if offer_response.status_code != 200:
                return offer_response
            
            offer_data = offer_response.data
            offer_structure = offer_data.get("offer_structure", {})
            
            # Générer un HTML simple à partir de la structure
            html_content = self._generate_html_from_structure(offer_structure)
            css_content = ""
            
            # Générer le PDF avec WeasyPrint
            pdf_generator = GrapesJSPDFGenerator()
            printable_html = pdf_generator.convert_grapesjs_to_printable_html(
                html_content, 
                css_content, 
                company_info
            )
            
            pdf_bytes = HTML(string=printable_html).write_pdf()
            
            response = HttpResponse(pdf_bytes, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="offre_voyage.pdf"'
            return response
            
        except Exception as e:
            traceback.print_exc()
            return Response({"error": f"Erreur : {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def _generate_html_from_structure(self, offer_structure):
        """Génère un HTML simple à partir de la structure d'offre"""
        html_parts = []
        
        # Titre
        title = offer_structure.get("title", "Offre de voyage")
        html_parts.append(f"<h1>{title}</h1>")
        
        # Introduction
        intro = offer_structure.get("introduction", "")
        if intro:
            html_parts.append(f"<p>{intro}</p>")
        
        # Sections
        sections = offer_structure.get("sections", [])
        for section in sections:
            section_title = section.get("title", "")
            section_body = section.get("body", "")
            
            if section_title:
                html_parts.append(f"<h2>{section_title}</h2>")
            if section_body:
                html_parts.append(f"<div>{section_body}</div>")
        
        # CTA
        cta = offer_structure.get("cta", {})
        if cta:
            cta_title = cta.get("title", "")
            cta_desc = cta.get("description", "")
            
            if cta_title or cta_desc:
                html_parts.append("<div class='cta-section'>")
                if cta_title:
                    html_parts.append(f"<h2>{cta_title}</h2>")
                if cta_desc:
                    html_parts.append(f"<p>{cta_desc}</p>")
                html_parts.append("</div>")
        
        return "\n".join(html_parts)


class PdfToGJSEndpoint(APIView):
    """
    POST multipart/form-data:
      - file: le PDF
      - company_info: JSON string {name, phone, email, address, website}
      - logo_data_url (optionnel): string data:image/png;base64,...
      - background_url (optionnel): URL
    Retourne:
      {
        "offer_structure": {...},     # JSON pour Grapes
        "assets": [{"name":"img1.png","data_url":"data:image/png;base64,..."}],
        "company_info": {...},
        "background_url": "...",
        "logo_data_url": "..."
      }
    """
    permission_classes = [AllowAny]  # Accès libre temporaire

    def post(self, request):
        pdf = request.FILES.get("file")
        if not pdf:
            return Response({"error": "Aucun PDF fourni"}, status=400)

        company_info = request.data.get("company_info") or "{}"
        try:
            company_info = json.loads(company_info)
        except:
            company_info = {}

        try:
            text_md, assets = self._extract_pdf_content(pdf)

            # 1. Parser heuristique (0ms, sans API) — fonctionne sur les PDFs avec titres markdown
            offer_structure = self._parse_sections_heuristic(text_md)

            # 2. Fallback OpenAI uniquement si le PDF n'est pas structuré (< 2 sections trouvées)
            if not offer_structure:
                print("⚠️ Structure non détectée, fallback OpenAI...")
                offer_structure = self._md_to_offer_json(text_md, company_info)

            if not offer_structure or not offer_structure.get('sections') or len(offer_structure.get('sections', [])) == 0:
                raise Exception("Aucun contenu structuré n'a pu être extrait du PDF")

            # 3. Distribuer les images (une par section, sans doublons)
            self._distribute_images(offer_structure, assets)

            document = None
            try:
                # Créer d'abord un document placeholder sans images (évite de stocker des data URLs en DB)
                document = Document.objects.create(
                    title=offer_structure.get('title', 'PDF Importé'),
                    description=f"Document importé le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
                    document_type='pdf_import',
                    offer_structure={},
                    company_info=company_info,
                    assets=[]
                )

                # Sauvegarder les images en parallèle (max 8 images, redimensionnées)
                from PIL import Image as PILImage
                import io as _io

                def _save_asset(args):
                    i, asset, doc_id = args
                    try:
                        header, b64data = asset['data_url'].split(',', 1)
                        file_bytes = base64.b64decode(b64data)
                        # Redimensionner à max 1200px pour réduire la taille
                        try:
                            img = PILImage.open(_io.BytesIO(file_bytes))
                            if max(img.size) > 1200:
                                img.thumbnail((1200, 1200), PILImage.LANCZOS)
                            buf = _io.BytesIO()
                            img.save(buf, format='JPEG', quality=82, optimize=True)
                            file_bytes = buf.getvalue()
                            ext = 'jpg'
                        except Exception:
                            ext = 'png' if 'image/png' in header else 'jpg'
                        filename = f"documents/assets/doc{doc_id}_{i}.{ext}"
                        saved_path = default_storage.save(filename, ContentFile(file_bytes))
                        return i, asset['data_url'], saved_path, ext, len(file_bytes)
                    except Exception as ae:
                        print(f"⚠️ Erreur sauvegarde asset {i}: {ae}")
                        return i, None, None, None, 0

                limited_assets = assets[:10]  # Max 10 images
                url_map = {}
                with ThreadPoolExecutor(max_workers=4) as pool:
                    results = list(pool.map(_save_asset, [(i, a, document.id) for i, a in enumerate(limited_assets)]))

                for i, original_url, saved_path, ext, size_bytes in results:
                    if saved_path and original_url:
                        file_url = request.build_absolute_uri(default_storage.url(saved_path))
                        url_map[original_url] = file_url
                        DocumentAsset.objects.create(
                            document=document,
                            name=limited_assets[i].get('name', f'asset_{i}.{ext}'),
                            file=saved_path,
                            file_type=f'image/{ext}',
                            width=limited_assets[i].get('width'),
                            height=limited_assets[i].get('height'),
                            size_kb=round(size_bytes / 1024, 1)
                        )
                        print(f"✅ Asset {i} sauvegardé: {file_url}")

                # Remplacer les data URLs par les URLs fichiers dans offer_structure (in-place)
                for section in offer_structure.get('sections', []):
                    for img in section.get('images', []):
                        if isinstance(img, dict) and img.get('url') in url_map:
                            img['url'] = url_map[img['url']]

                # Sauvegarder offer_structure propre (URLs HTTP, pas data URLs)
                document.offer_structure = offer_structure
                document.save(update_fields=['offer_structure'])

                # Sauvegarder le PDF original
                pdf.seek(0)
                pdf_file_content = ContentFile(pdf.read(), name=f"imported_{document.id}.pdf")
                document.pdf_file.save(f"imported_{document.id}.pdf", pdf_file_content)

                print(f"✅ Document ID {document.id} sauvegardé avec {len(url_map)} image(s) en fichiers")

            except Exception as e:
                print(f"⚠️ Erreur sauvegarde: {e}")
                traceback.print_exc()

            return Response({
                "offer_structure": offer_structure,
                "company_info": company_info,
                "document_id": document.id if document else None
            })
        except Exception as e:
            traceback.print_exc()
            return Response({"error": f"Erreur import PDF: {e}"}, status=500)

    def _extract_pdf_content(self, pdf_file):
        """
        Retourne (markdown_consolidé, assets_base64[]).

        Stratégie de détection des titres :
          1. Collecter toutes les tailles de police du document
          2. La taille la plus fréquente = corps du texte (body_size)
          3. Seuils dérivés automatiquement :
               ≥ body × 1.45  →  # H1   (titre principal)
               ≥ body × 1.12  →  ## H2  (section)
               gras + court   →  ### H3 (sous-titre)
               sinon          →  paragraphe
        Cette approche est indépendante des mots-clés et fonctionne quelle
        que soit la langue ou le contenu du PDF.
        """
        import collections as _col
        doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
        assets = []

        # ── Phase 1 : identifier le body_size (taille de police dominante) ──
        size_counter = _col.Counter()
        for page in doc:
            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") != 0:
                    continue
                for line in block.get("lines", []):
                    for span in line.get("spans", []):
                        if span.get("text", "").strip():
                            size_counter[round(span["size"], 1)] += 1

        body_size = size_counter.most_common(1)[0][0] if size_counter else 11.0
        h1_min = body_size * 1.45
        h2_min = body_size * 1.12
        print(f"📐 Police: body={body_size}pt → H1≥{h1_min:.1f}pt, H2≥{h2_min:.1f}pt")

        # ── Phase 2 : extraction ligne par ligne avec marqueurs markdown ──
        page_chunks = []

        for page_num, page in enumerate(doc):
            lines_md = []
            last_block_no = None

            for block in page.get_text("dict").get("blocks", []):
                if block.get("type") != 0:
                    continue

                # Ligne vide entre blocs pour préserver la structure paragraphe
                bno = id(block)
                if last_block_no is not None:
                    lines_md.append("")
                last_block_no = bno

                # Les lignes normales du même bloc = même paragraphe → on les joint,
                # SAUF si la ligne est un élément de liste (bullet/numérotée) ou
                # si le buffer contenait déjà un item de liste.
                # Les titres (H1/H2/H3) restent sur leur propre ligne.
                text_buffer = []

                _LIST_LINE_RE = re.compile(
                    r'^([•·▪▸\-\*])\s|^\d+[\.\)]\s'
                )

                def _flush_buffer():
                    if text_buffer:
                        lines_md.append(" ".join(text_buffer))
                        text_buffer.clear()

                for line in block.get("lines", []):
                    line_text = ""
                    max_size = 0.0
                    is_bold = False

                    for span in line.get("spans", []):
                        txt = span.get("text", "")
                        line_text += txt
                        sz = float(span.get("size", body_size))
                        if sz > max_size:
                            max_size = sz
                        flags = span.get("flags", 0)
                        font = span.get("font", "").lower()
                        if (flags & 16) or "bold" in font:
                            is_bold = True

                    line_text = line_text.strip()
                    if not line_text:
                        continue

                    if max_size >= h1_min:
                        _flush_buffer()
                        lines_md.append(f"# {line_text}")
                    elif max_size >= h2_min:
                        _flush_buffer()
                        lines_md.append(f"## {line_text}")
                    elif is_bold and len(line_text) <= 120:
                        _flush_buffer()
                        lines_md.append(f"### {line_text}")
                    elif _LIST_LINE_RE.match(line_text):
                        # Élément de liste : flush le buffer courant + émettre séparément
                        _flush_buffer()
                        lines_md.append(line_text)
                    else:
                        # Texte normal : accumuler pour former un paragraphe continu
                        text_buffer.append(line_text)

                _flush_buffer()

            if lines_md:
                page_chunks.append("\n".join(lines_md))

            # ── Extraction des images ──────────────────────────────────────
            if len(assets) >= 10:
                continue
            for img_index, img in enumerate(page.get_images(full=True)):
                if len(assets) >= 10:
                    break
                pix = None
                try:
                    pix = fitz.Pixmap(doc, img[0])
                    if pix.width < 50 or pix.height < 50:
                        continue
                    try:
                        if pix.n > 4:
                            pix = fitz.Pixmap(fitz.csRGB, pix)
                    except Exception:
                        pass
                    img_bytes = pix.tobytes("png")
                    if len(img_bytes) > 3 * 1024 * 1024:
                        continue
                    b64 = base64.b64encode(img_bytes).decode("ascii")
                    assets.append({
                        "name": f"pdf_image_page{page_num+1}_{img_index+1}.png",
                        "data_url": f"data:image/png;base64,{b64}",
                        "width": pix.width,
                        "height": pix.height,
                        "page": page_num + 1,
                        "size_kb": round(len(img_bytes) / 1024, 1)
                    })
                except Exception as e:
                    print(f"Erreur image page {page_num+1}: {e}")
                finally:
                    pix = None

        doc.close()
        md = "\n\n".join(page_chunks)
        md = re.sub(r'\n{3,}', '\n\n', md).strip()
        print(f"📄 Markdown extrait ({len(md)} chars):\n{md[:600]}\n---")
        return md, assets

    # ─────────────────────────────────────────────────────────────
    # PARSER HEURISTIQUE — 0ms, sans API
    # ─────────────────────────────────────────────────────────────
    SECTION_TYPE_MAP = {
        'Flights':    ['vol ', 'vols', 'flight', 'aéroport', 'airport', 'départ', 'arrivée', 'escale', 'compagnie'],
        'Hotel':      ['hôtel', 'hotel', 'hébergement', 'chambre', 'nuit', 'logement', 'resort', 'lodge', 'pension'],
        'Activities': ['activités', 'excursions', 'visites', 'randonnée', 'safari', 'loisirs'],
        'Price':      ['prix', 'tarif', 'coût', 'forfait', 'budget', 'supplément', 'par personne'],
        'Programme':  ['programme', 'itinéraire', 'itinerary', 'agenda'],
        'Transfers':  ['transfert', 'transfer', 'navette', 'shuttle'],
        'Info':       ['informations pratiques', 'infos pratiques', 'visa', 'assurance', 'formalité', 'documents requis', 'conditions'],
    }

    # Mots-clés déclenchant une NOUVELLE SECTION quand en début de ligne courte (texte plat)
    _SECTION_START_RE = re.compile(
        r'^(programme|itinéraire|itinerary|agenda'
        r'|vols?(\s+(aller|retour|inclus))?|flights?'
        r'|hôtel|hotel|hébergement|logement'
        r'|transferts?|navette'
        r'|activités|activites|excursions?'
        r'|prix|tarifs?|coûts?|forfait|budget'
        r'|informations?\s+pratiques?|conditions?\s+générales?|formalités?'
        r')\s*:?\s*$',
        re.I | re.UNICODE
    )

    # Sous-titres INLINE dans un body (Hôtel :, Date :, Vol AF006 :, etc.) → H3
    _INLINE_H3_RE = re.compile(
        r'^(hôtel|hotel|hébergement|chambre'
        r'|date\s*(de\s*(départ|retour|voyage))?'
        r'|départ|arrivée|retour'
        r'|vol\s+[A-Z0-9]|flight\s+[A-Z0-9]'
        r'|transfert|excursion'
        r'|repas|pension)\s*:',
        re.I | re.UNICODE
    )

    # Patterns de sous-titres journaliers (JOUR X, DAY X, etc.) — créent des H3 dans le body
    DAY_HEADING_PATTERNS = [
        re.compile(r'^jour\s+\d+', re.I),
        re.compile(r'^day\s+\d+', re.I),
        re.compile(r'^étape\s+\d+', re.I),
        re.compile(r'^etape\s+\d+', re.I),
        re.compile(r'^nuit\s+\d+', re.I),
        re.compile(r'^semaine\s+\d+', re.I),
        re.compile(r'^\d+\s*(er|ème|e|eme)?\s+jour', re.I),
        re.compile(r'^(lundi|mardi|mercredi|jeudi|vendredi|samedi|dimanche)\b', re.I),
    ]

    def _is_day_heading(self, text: str) -> bool:
        t = text.strip()
        if len(t) > 120:
            return False
        return any(p.search(t) for p in self.DAY_HEADING_PATTERNS)

    def _is_plain_section_heading(self, text: str) -> bool:
        """Une ligne courte en texte plat qui devrait démarrer une nouvelle section."""
        t = text.strip()
        # Doit être court et ne pas commencer par une minuscule (évite les milieux de phrase)
        if len(t) > 70 or (t and t[0].islower()):
            return False
        # Tout en majuscules (ex: "PROGRAMME", "VOLS ALLER-RETOUR")
        if t.isupper() and 2 < len(t) < 60:
            return True
        # Correspond aux mots-clés de section
        return bool(self._SECTION_START_RE.match(t))

    def _detect_section_type(self, text: str) -> str:
        lower = text.lower()
        for stype, keywords in self.SECTION_TYPE_MAP.items():
            if any(kw in lower for kw in keywords):
                return stype
        return 'Info'

    def _parse_sections_heuristic(self, markdown_text: str):
        """Parse le markdown du PDF en sections sans appel API. Retourne None si insuffisant."""
        # Log pour diagnostiquer la structure du PDF
        print(f"📄 Markdown extrait ({len(markdown_text)} chars) — aperçu:\n{markdown_text[:800]}\n---")

        lines = markdown_text.split('\n')
        title = 'Votre offre de voyage'
        intro_lines = []
        sections = []
        current = None
        body_lines = []
        found_title = False

        def flush_section():
            if current is not None:
                current['body'] = '\n'.join(body_lines).strip()
                sections.append(current)

        def new_section(heading_text):
            nonlocal current, body_lines
            flush_section()
            body_lines = []
            current = {
                'id': re.sub(r'\W+', '-', heading_text.lower())[:30].strip('-'),
                'type': self._detect_section_type(heading_text),
                'title': heading_text,
                'body': '',
                'images': [],
            }

        for line in lines:
            s = line.strip()
            if not s:
                # Conserver les lignes vides dans le body pour la structure
                if current is not None:
                    body_lines.append('')
                continue

            m1 = re.match(r'^#\s+(.+)$', s)
            m2 = re.match(r'^#{2,3}\s+(.+)$', s)
            m4 = re.match(r'^#{4,}\s+(.+)$', s)
            mb = re.match(r'^\*\*(.+?)\*\*\s*$', s)  # Ligne entièrement bold

            if m1:
                if not found_title:
                    # Premier H1 = titre du document
                    title = m1.group(1)
                    found_title = True
                elif self._is_day_heading(m1.group(1)):
                    # H1 jour/day → auto-créer section "Programme" si besoin, puis sous-titre
                    if current is None:
                        new_section("Programme")
                    body_lines.append(f'### {m1.group(1)}')
                else:
                    # H1 suivants = sections principales
                    new_section(m1.group(1))
            elif m2:
                heading = m2.group(1)
                level = len(re.match(r'^(#+)', s).group(1))
                if level == 2 and self._is_day_heading(heading):
                    # H2 jour/day → auto-créer section "Programme" si besoin, puis sous-titre
                    if current is None:
                        new_section("Programme")
                    body_lines.append(f'### {heading}')
                elif level == 2 and current is not None:
                    # H2 dans une section existante → sous-titre simple (ex: noms d'hôtels)
                    body_lines.append(f'### {heading}')
                elif level == 2:
                    # H2 sans section courante → nouvelle section
                    new_section(heading)
                else:
                    # H3 = sous-titre dans le body
                    if current is not None:
                        body_lines.append(f'## {heading}')
                    else:
                        intro_lines.append(s)
            elif m4:
                # H4+ = toujours sous-titre
                if current is not None:
                    body_lines.append(f'## {m4.group(1)}')
            elif mb:
                # Bold line → body ou intro (jamais une nouvelle section)
                if current is not None:
                    body_lines.append(s)
                elif found_title:
                    intro_lines.append(s)
            else:
                # ── Texte plat : détection heuristique de structure ──────────
                # Priorité 1 : ligne courte = titre de section (ex: "HÔTEL", "Programme :")
                if found_title and self._is_plain_section_heading(s):
                    new_section(s.rstrip(':').strip())

                # Priorité 2 : JOUR X / DAY X / Étape X → sous-titre H3 dans Programme
                elif self._is_day_heading(s):
                    if current is None:
                        new_section("Programme")
                    body_lines.append(f'### {s}')

                # Priorité 3 : sous-titres inline dans une section (Hôtel :, Date :, Vol :…)
                elif current is not None and len(s) < 100 and self._INLINE_H3_RE.match(s):
                    body_lines.append(f'### {s}')

                # Priorité 4 : texte normal
                elif current is not None:
                    body_lines.append(s)
                elif found_title:
                    intro_lines.append(s)

        flush_section()

        # Retourner None si trop peu de sections → fallback OpenAI
        if len(sections) < 1:
            print(f"⚠️ Heuristique: {len(sections)} section(s) seulement — fallback OpenAI")
            return None

        print(f"✅ Heuristique: {len(sections)} sections, titre='{title}'")
        return {
            'title': title,
            'introduction': '\n'.join(intro_lines).strip(),  # Pas de limite sur l'intro
            'sections': sections,
            'cta': {'title': 'Réservez maintenant', 'description': '', 'buttonText': 'Réserver'},
        }

    # ─────────────────────────────────────────────────────────────
    # DISTRIBUTION DES IMAGES — une par section, sans doublons
    # ─────────────────────────────────────────────────────────────
    def _distribute_images(self, offer_structure: dict, assets: list):
        """
        Distribue TOUTES les images extraites du PDF (max 8) dans les sections.
        - Passage 1 : 1 image par section (round-robin)
        - Passage 2 : les images restantes vont dans les premières sections (max 2 par section)
        Objectif : utiliser 4-5 images visibles minimum.
        """
        if not assets:
            return

        sections = offer_structure.get('sections', [])
        if not sections:
            return

        pool = list(assets)

        # Passage 1 : une image par section
        for section in sections:
            if not pool:
                break
            section.setdefault('images', [])
            if not section['images']:
                asset = pool.pop(0)
                section['images'].append({
                    'url': asset['data_url'],
                    'alt': asset.get('name', ''),
                    'caption': '',
                })

        # Passage 2 : distribuer les images restantes (max 2 par section au total)
        for section in sections:
            if not pool:
                break
            if len(section.get('images', [])) < 2:
                asset = pool.pop(0)
                section['images'].append({
                    'url': asset['data_url'],
                    'alt': asset.get('name', ''),
                    'caption': '',
                })

        print(f"🖼️ {len(assets) - len(pool)}/{len(assets)} images distribuées dans {len(sections)} sections")

    # ─────────────────────────────────────────────────────────────
    # FALLBACK OPENAI — structure seulement (~200 tokens, ~8s)
    # ─────────────────────────────────────────────────────────────
    def _md_to_offer_json(self, markdown_text: str, company_info: dict):
        """
        Étape 1 : OpenAI identifie juste le titre et les sections (pas le body) → ~200 tokens.
        Étape 2 : on découpe le texte original autour des titres détectés → 0ms.
        """
        # Envoyer seulement les 6000 premiers chars pour identifier la structure
        sample = markdown_text[:6000]

        sys_prompt = "Tu es un expert en offres de voyage. Réponds uniquement en JSON valide."
        user_prompt = f"""Analyse ce document de voyage et retourne UNIQUEMENT:
{{
  "title": "titre principal du document",
  "sections": [
    {{"title": "titre exact de la section tel qu'il apparaît dans le texte", "type": "Flights|Hotel|Price|Programme|Activities|Transfers|Info"}}
  ]
}}

Identifie toutes les sections principales. NE reproduis PAS le contenu, juste les titres.

Document:
{sample}"""

        try:
            res = get_openai_client().chat.completions.create(
                model="gpt-4o-mini",
                temperature=0,
                timeout=30,
                max_tokens=500,  # Juste les titres → très rapide
                messages=[
                    {"role": "system", "content": sys_prompt},
                    {"role": "user", "content": user_prompt},
                ]
            )
        except Exception as e:
            raise Exception(f"Échec OpenAI: {e}")

        raw = res.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```json")[-1].split("```")[0]

        try:
            structure = json.loads(raw)
        except json.JSONDecodeError:
            raise Exception(f"JSON OpenAI invalide: {raw[:200]}")

        doc_title = structure.get("title", "Votre offre de voyage")
        section_defs = structure.get("sections", [])

        if not section_defs:
            raise Exception("OpenAI n'a identifié aucune section")

        # Étape 2 : découper le texte original autour des titres détectés
        sections = self._split_text_by_titles(markdown_text, section_defs)

        print(f"✅ OpenAI structure-only: {len(sections)} sections, titre='{doc_title}'")
        return {
            "title": doc_title,
            "introduction": "",
            "sections": sections,
            "cta": {"title": "Réservez maintenant", "description": "", "buttonText": "Réserver"},
        }

    def _split_text_by_titles(self, text: str, section_defs: list) -> list:
        """Découpe le texte original autour des titres de sections identifiés par OpenAI."""
        sections = []
        remaining = text

        for i, sdef in enumerate(section_defs):
            title = sdef.get("title", "").strip()
            if not title:
                continue

            # Chercher le titre dans le texte (insensible à la casse, ignore les #)
            pattern = re.escape(title)
            match = re.search(pattern, remaining, re.IGNORECASE)

            if not match:
                # Essayer sans accents / avec fuzzy partiel (premiers 30 chars)
                short = title[:30]
                match = re.search(re.escape(short), remaining, re.IGNORECASE)

            if match:
                # Intro = tout ce qui précède la première section
                if i == 0 and match.start() > 0:
                    pass  # l'intro est avant la première section

                # Body = du titre jusqu'au prochain titre
                start = match.start()
                # Chercher la prochaine section pour délimiter
                next_match = None
                if i + 1 < len(section_defs):
                    next_title = section_defs[i + 1].get("title", "")[:30]
                    if next_title:
                        nm = re.search(re.escape(next_title), remaining[start:], re.IGNORECASE)
                        if nm:
                            next_match = start + nm.start()

                body_text = remaining[start:next_match] if next_match else remaining[start:]
                # Enlever la ligne de titre du body
                body_lines = body_text.split('\n')
                body_clean = '\n'.join(body_lines[1:]).strip()

                sections.append({
                    "id": re.sub(r'\W+', '-', title.lower())[:30].strip('-'),
                    "type": sdef.get("type", "Info"),
                    "title": title,
                    "body": body_clean,
                    "images": [],
                })
            else:
                # Titre non trouvé dans le texte → section vide
                sections.append({
                    "id": re.sub(r'\W+', '-', title.lower())[:30].strip('-'),
                    "type": sdef.get("type", "Info"),
                    "title": title,
                    "body": "",
                    "images": [],
                })

        return sections


class ImproveOfferEndpoint(APIView):
    """
    POST JSON:
      { "offer_structure": {...}, "mode": "premium|concis|vendeur|familial|luxe" }
    Retourne: { "offer_structure": {...} } (même schéma)
    """
    permission_classes = [AllowAny]  # Accès libre temporaire
    def post(self, request):
        data = request.data
        offer = data.get("offer_structure")
        mode = data.get("mode", "premium")

        if not offer:
            return Response({"error":"offer_structure manquant"}, status=400)

        sys = "Tu améliores la rédaction d'une offre de voyage. Tu renvoies le même JSON, champs identiques."
        tone_map = {
            "premium": "ton premium, clair et rassurant, orienté valeur.",
            "concis": "ton concis et factuel.",
            "vendeur": "ton commercial soft, orienté bénéfices.",
            "familial": "ton chaleureux, accessible et rassurant.",
            "luxe": "ton haut de gamme, raffiné, exclusif."
        }
        tone = tone_map.get(mode, tone_map["premium"])

        prompt = f"""Améliore l'offre ci-dessous (garde le même JSON, mêmes clés),
réécris uniquement les champs textuels (title, introduction, sections[*].title/body, cta.*) avec un {tone}

JSON:
{json.dumps(offer, ensure_ascii=False)}
"""

        res = get_openai_client().chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.5,
            timeout=90,  # Timeout de 90 secondes pour éviter les worker timeouts
            messages=[{"role":"system","content":sys},{"role":"user","content":prompt}]
        )
        raw = res.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```json")[-1].split("```")[0]
        improved = json.loads(raw)

        # ImproveOfferEndpoint ne génère pas d'offre, donc pas de metadata
        return Response({
            "offer_structure": improved
        })


class DocumentListCreateView(ListCreateAPIView):
    """
    GET: Liste tous les documents sauvegardés
    POST: Crée un nouveau document
    """
    permission_classes = [AllowAny]
    queryset = Document.objects.all()
    
    def get(self, request):
        """Retourne la liste des documents avec leurs métadonnées"""
        documents = Document.objects.all().order_by('-updated_at')
        data = []
        
        for doc in documents:
            data.append({
                'id': doc.id,
                'title': doc.title,
                'description': doc.description,
                'document_type': doc.document_type,
                'document_type_display': doc.get_document_type_display(),
                'created_at': doc.created_at.isoformat(),
                'updated_at': doc.updated_at.isoformat(),
                'file_size_mb': doc.file_size_mb,
                'has_pdf': bool(doc.pdf_file),
                'has_thumbnail': bool(doc.thumbnail),
                'company_info': doc.company_info,
                'assets_count': len(doc.assets) if doc.assets else 0,
                'folder_id': doc.folder_id
            })
        
        return Response(data)
    
    def post(self, request):
        """Sauvegarde un nouveau document"""
        try:
            title = request.data.get('title', 'Document sans titre')
            description = request.data.get('description', '')
            document_type = request.data.get('document_type', 'grapesjs_project')
            
            # Données GrapesJS
            grapes_html = request.data.get('grapes_html', '')
            grapes_css = request.data.get('grapes_css', '')
            offer_structure = request.data.get('offer_structure')
            company_info = request.data.get('company_info', {})
            assets = request.data.get('assets', [])
            # Données éditeurs
            puck_data = request.data.get('puck_data')
            global_background = request.data.get('global_background')
            header_footer = request.data.get('header_footer')
            blocknote_data = request.data.get('blocknote_data')
            folder_id = request.data.get('folder_id')

            # Résoudre le dossier
            folder = None
            if folder_id:
                try:
                    folder = Folder.objects.get(pk=folder_id)
                except Folder.DoesNotExist:
                    pass

            # Créer le document
            document = Document.objects.create(
                title=title,
                description=description,
                document_type=document_type,
                grapes_html=grapes_html,
                grapes_css=grapes_css,
                offer_structure=offer_structure,
                company_info=company_info,
                assets=assets,
                puck_data=puck_data,
                global_background=global_background,
                header_footer=header_footer,
                blocknote_data=blocknote_data,
                folder=folder
            )
            
            # Sauvegarder le PDF si fourni
            pdf_content = request.data.get('pdf_content')
            if pdf_content:
                # Décoder le contenu base64 si nécessaire
                if pdf_content.startswith('data:application/pdf;base64,'):
                    pdf_content = pdf_content.split(',')[1]
                
                pdf_bytes = base64.b64decode(pdf_content)
                pdf_file = ContentFile(pdf_bytes, name=f"{document.id}_generated.pdf")
                document.pdf_file.save(f"{document.id}_generated.pdf", pdf_file)
            
            # Traiter les assets (images)
            if assets:
                for i, asset in enumerate(assets):
                    if isinstance(asset, dict) and 'data_url' in asset:
                        try:
                            # Extraire le contenu base64
                            header, data = asset['data_url'].split(',', 1)
                            file_bytes = base64.b64decode(data)
                            
                            # Déterminer l'extension
                            if 'image/png' in header:
                                ext = 'png'
                            elif 'image/jpeg' in header:
                                ext = 'jpg'
                            else:
                                ext = 'png'
                            
                            # Créer l'asset
                            asset_file = ContentFile(file_bytes, name=f"asset_{document.id}_{i}.{ext}")
                            
                            DocumentAsset.objects.create(
                                document=document,
                                name=asset.get('name', f'asset_{i}.{ext}'),
                                file=asset_file,
                                file_type=f'image/{ext}',
                                width=asset.get('width'),
                                height=asset.get('height'),
                                size_kb=asset.get('size_kb', len(file_bytes) / 1024)
                            )
                        except Exception as e:
                            print(f"Erreur sauvegarde asset {i}: {e}")
            
            return Response({
                'id': document.id,
                'title': document.title,
                'message': 'Document sauvegardé avec succès'
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            traceback.print_exc()
            return Response({'error': f'Erreur sauvegarde: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DocumentDetailView(RetrieveUpdateDestroyAPIView):
    """
    GET: Récupère un document spécifique avec tous ses détails
    PUT/PATCH: Met à jour un document
    DELETE: Supprime un document
    """
    permission_classes = [AllowAny]
    queryset = Document.objects.all()
    
    def get(self, request, pk):
        """Récupère un document avec tous ses détails"""
        try:
            document = Document.objects.get(pk=pk)
            
            # Récupérer les assets
            assets_data = []
            for asset in document.document_assets.all():
                assets_data.append({
                    'id': asset.id,
                    'name': asset.name,
                    'file_url': asset.file.url if asset.file else None,
                    'file_type': asset.file_type,
                    'width': asset.width,
                    'height': asset.height,
                    'size_kb': asset.size_kb
                })
            
            data = {
                'id': document.id,
                'title': document.title,
                'description': document.description,
                'document_type': document.document_type,
                'grapes_html': document.grapes_html,
                'grapes_css': document.grapes_css,
                'offer_structure': document.offer_structure,
                'company_info': document.company_info,
                'assets': document.assets,  # Assets originaux (base64)
                'stored_assets': assets_data,  # Assets stockés sur disque
                'pdf_url': document.pdf_file.url if document.pdf_file else None,
                'thumbnail_url': document.thumbnail.url if document.thumbnail else None,
                'created_at': document.created_at.isoformat(),
                'updated_at': document.updated_at.isoformat(),
                'file_size_mb': document.file_size_mb
            }
            
            return Response(data)
            
        except Document.DoesNotExist:
            return Response({'error': 'Document non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': f'Erreur: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def patch(self, request, pk):
        """Mise à jour partielle d'un document (ex: déplacement vers un dossier)"""
        try:
            document = Document.objects.get(pk=pk)

            if 'folder_id' in request.data:
                folder_id = request.data.get('folder_id')
                if folder_id:
                    try:
                        document.folder = Folder.objects.get(pk=folder_id)
                    except Folder.DoesNotExist:
                        return Response({'error': 'Dossier non trouvé'}, status=status.HTTP_404_NOT_FOUND)
                else:
                    document.folder = None

            if 'title' in request.data:
                document.title = request.data['title']

            if 'blocknote_data' in request.data:
                document.blocknote_data = request.data['blocknote_data']

            if 'offer_structure' in request.data:
                document.offer_structure = request.data['offer_structure']

            document.save()

            return Response({
                'id': document.id,
                'title': document.title,
                'folder_id': document.folder_id,
                'message': 'Document mis à jour'
            })

        except Document.DoesNotExist:
            return Response({'error': 'Document non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': f'Erreur: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

    def put(self, request, pk):
        """Met à jour un document"""
        try:
            document = Document.objects.get(pk=pk)

            # Mettre à jour les champs
            document.title = request.data.get('title', document.title)
            document.description = request.data.get('description', document.description)
            document.grapes_html = request.data.get('grapes_html', document.grapes_html)
            document.grapes_css = request.data.get('grapes_css', document.grapes_css)
            document.offer_structure = request.data.get('offer_structure', document.offer_structure)
            document.company_info = request.data.get('company_info', document.company_info)
            document.assets = request.data.get('assets', document.assets)

            document.save()
            
            return Response({
                'id': document.id,
                'title': document.title,
                'message': 'Document mis à jour avec succès'
            })
            
        except Document.DoesNotExist:
            return Response({'error': 'Document non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': f'Erreur: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def delete(self, request, pk):
        """Supprime un document"""
        try:
            document = Document.objects.get(pk=pk)
            title = document.title
            
            # Supprimer les fichiers associés
            if document.pdf_file:
                document.pdf_file.delete()
            if document.thumbnail:
                document.thumbnail.delete()
            
            # Supprimer les assets
            for asset in document.document_assets.all():
                if asset.file:
                    asset.file.delete()
            
            document.delete()
            
            return Response({
                'message': f'Document "{title}" supprimé avec succès'
            })
            
        except Document.DoesNotExist:
            return Response({'error': 'Document non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': f'Erreur: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DocumentGeneratePDFView(APIView):
    """
    POST: Génère un PDF à partir d'un document sauvegardé
    """
    
    def post(self, request, pk):
        """Génère un PDF à partir d'un document GrapesJS sauvegardé"""
        try:
            document = Document.objects.get(pk=pk)
            
            if not document.grapes_html:
                return Response({'error': 'Pas de contenu HTML dans ce document'}, status=status.HTTP_400_BAD_REQUEST)
            
            # Utiliser la même logique que GrapesJSPDFGenerator
            generator = GrapesJSPDFGenerator()
            printable_html = generator.convert_grapesjs_to_printable_html(
                document.grapes_html, 
                document.grapes_css, 
                document.company_info
            )
            
            with sync_playwright() as p:
                browser = p.chromium.launch()
                page = browser.new_page()
                page.set_content(printable_html, wait_until="load")
                pdf_bytes = page.pdf(
                    format="A4",
                    print_background=True,
                    margin={"top": "20mm", "bottom": "20mm", "left": "20mm", "right": "20mm"}
                )
                browser.close()
            
            # Sauvegarder le PDF généré dans le document
            pdf_file = ContentFile(pdf_bytes, name=f"{document.id}_generated.pdf")
            document.pdf_file.save(f"{document.id}_generated.pdf", pdf_file)
            
            resp = HttpResponse(pdf_bytes, content_type="application/pdf")
            resp["Content-Disposition"] = f'inline; filename="{document.title}.pdf"'
            return resp
            
        except Document.DoesNotExist:
            return Response({'error': 'Document non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            traceback.print_exc()
            return Response({'error': f'Erreur génération PDF: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FolderListCreateView(ListCreateAPIView):
    """
    GET: Liste tous les dossiers avec leur hiérarchie
    POST: Crée un nouveau dossier
    """
    permission_classes = [AllowAny]
    queryset = Folder.objects.all()
    
    def get(self, request):
        """Retourne la liste des dossiers avec leur hiérarchie"""
        # Récupérer tous les dossiers racines (sans parent)
        root_folders = Folder.objects.filter(parent=None).order_by('position', 'name')
        
        def serialize_folder(folder):
            return {
                'id': folder.id,
                'name': folder.name,
                'description': folder.description,
                'color': folder.color,
                'icon': folder.icon,
                'position': folder.position,
                'full_path': folder.full_path,
                'documents_count': folder.documents_count,
                'total_documents_count': folder.total_documents_count,
                'created_at': folder.created_at.isoformat(),
                'updated_at': folder.updated_at.isoformat(),
                'parent_id': folder.parent.id if folder.parent else None,
                'subfolders': [serialize_folder(sub) for sub in folder.subfolders.all()]
            }
        
        data = [serialize_folder(folder) for folder in root_folders]
        
        return Response(data)
    
    def post(self, request):
        """Crée un nouveau dossier"""
        try:
            name = request.data.get('name', 'Nouveau dossier')
            description = request.data.get('description', '')
            color = request.data.get('color', '#3498DB')
            icon = request.data.get('icon', '📁')
            parent_id = request.data.get('parent_id')
            
            # Vérifier que le parent existe si spécifié
            parent = None
            if parent_id:
                try:
                    parent = Folder.objects.get(pk=parent_id)
                except Folder.DoesNotExist:
                    return Response({'error': 'Dossier parent non trouvé'}, status=status.HTTP_404_NOT_FOUND)
            
            # Créer le dossier (get_or_create pour éviter les doublons)
            folder, _ = Folder.objects.get_or_create(
                name=name,
                parent=parent,
                defaults=dict(description=description, color=color, icon=icon)
            )
            
            return Response({
                'id': folder.id,
                'name': folder.name,
                'full_path': folder.full_path,
                'message': 'Dossier créé avec succès'
            }, status=status.HTTP_201_CREATED)
            
        except Exception as e:
            traceback.print_exc()
            return Response({'error': f'Erreur création dossier: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class FolderDetailView(RetrieveUpdateDestroyAPIView):
    """
    GET: Récupère un dossier avec ses documents
    PUT/PATCH: Met à jour un dossier
    DELETE: Supprime un dossier
    """
    permission_classes = [AllowAny]
    queryset = Folder.objects.all()
    
    def get(self, request, pk):
        """Récupère un dossier avec ses documents et sous-dossiers"""
        try:
            folder = Folder.objects.get(pk=pk)
            
            # Récupérer les documents du dossier
            documents = []
            for doc in folder.documents.all():
                documents.append({
                    'id': doc.id,
                    'title': doc.title,
                    'description': doc.description,
                    'document_type': doc.document_type,
                    'document_type_display': doc.get_document_type_display(),
                    'created_at': doc.created_at.isoformat(),
                    'updated_at': doc.updated_at.isoformat(),
                    'file_size_mb': doc.file_size_mb,
                    'has_pdf': bool(doc.pdf_file),
                    'has_thumbnail': bool(doc.thumbnail),
                    'assets_count': len(doc.assets) if doc.assets else 0
                })
            
            # Récupérer les sous-dossiers
            subfolders = []
            for sub in folder.subfolders.all():
                subfolders.append({
                    'id': sub.id,
                    'name': sub.name,
                    'description': sub.description,
                    'color': sub.color,
                    'icon': sub.icon,
                    'documents_count': sub.documents_count,
                    'total_documents_count': sub.total_documents_count
                })
            
            data = {
                'id': folder.id,
                'name': folder.name,
                'description': folder.description,
                'color': folder.color,
                'icon': folder.icon,
                'full_path': folder.full_path,
                'documents_count': folder.documents_count,
                'total_documents_count': folder.total_documents_count,
                'created_at': folder.created_at.isoformat(),
                'updated_at': folder.updated_at.isoformat(),
                'parent_id': folder.parent.id if folder.parent else None,
                'documents': documents,
                'subfolders': subfolders
            }
            
            return Response(data)
            
        except Folder.DoesNotExist:
            return Response({'error': 'Dossier non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': f'Erreur: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def put(self, request, pk):
        """Met à jour un dossier"""
        try:
            folder = Folder.objects.get(pk=pk)
            
            # Mettre à jour les champs
            folder.name = request.data.get('name', folder.name)
            folder.description = request.data.get('description', folder.description)
            folder.color = request.data.get('color', folder.color)
            folder.icon = request.data.get('icon', folder.icon)
            
            # Gestion du parent
            parent_id = request.data.get('parent_id')
            if parent_id:
                try:
                    parent = Folder.objects.get(pk=parent_id)
                    # Vérifier qu'on ne crée pas de boucle (simple vérification)
                    if parent.id == folder.id:
                        return Response({'error': 'Impossible de créer une boucle dans la hiérarchie'}, 
                                      status=status.HTTP_400_BAD_REQUEST)
                    folder.parent = parent
                except Folder.DoesNotExist:
                    return Response({'error': 'Dossier parent non trouvé'}, status=status.HTTP_404_NOT_FOUND)
            elif parent_id is None:
                folder.parent = None
            
            folder.save()
            
            return Response({
                'id': folder.id,
                'name': folder.name,
                'full_path': folder.full_path,
                'message': 'Dossier mis à jour avec succès'
            })
            
        except Folder.DoesNotExist:
            return Response({'error': 'Dossier non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': f'Erreur: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
    
    def delete(self, request, pk):
        """Supprime un dossier"""
        try:
            folder = Folder.objects.get(pk=pk)
            name = folder.name
            
            # Vérifier s'il y a des documents ou sous-dossiers
            if folder.documents.exists() or folder.subfolders.exists():
                return Response({
                    'error': 'Impossible de supprimer un dossier non vide. Déplacez d\'abord son contenu.'
                }, status=status.HTTP_400_BAD_REQUEST)
            
            folder.delete()
            
            return Response({
                'message': f'Dossier "{name}" supprimé avec succès'
            })
            
        except Folder.DoesNotExist:
            return Response({'error': 'Dossier non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': f'Erreur: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


class DocumentMoveToFolderView(APIView):
    """
    POST: Déplace un document vers un dossier
    """
    
    def post(self, request, document_id):
        """Déplace un document vers un dossier spécifique"""
        try:
            document = Document.objects.get(pk=document_id)
            folder_id = request.data.get('folder_id')
            
            if folder_id:
                try:
                    folder = Folder.objects.get(pk=folder_id)
                    document.folder = folder
                except Folder.DoesNotExist:
                    return Response({'error': 'Dossier non trouvé'}, status=status.HTTP_404_NOT_FOUND)
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
            
        except Document.DoesNotExist:
            return Response({'error': 'Document non trouvé'}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({'error': f'Erreur: {str(e)}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class FreepikImageSearchView(APIView):
    """
    Proxy pour rechercher des images via l'API Freepik.
    Résout les problèmes CORS en passant par le backend.
    """
    permission_classes = [AllowAny]
    
    def get(self, request):
        """
        Recherche d'images Freepik
        
        Query params:
        - query: Terme de recherche (requis)
        - page: Numéro de page (défaut: 1)
        - limit: Nombre d'images par page (défaut: 30, max: 50)
        """
        try:
            query = request.GET.get('query', '').strip()
            page = int(request.GET.get('page', 1))
            limit = min(int(request.GET.get('limit', 30)), 50)  # Max 50
            
            if not query:
                return Response(
                    {'error': 'Le paramètre "query" est requis'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            # Clé API Freepik depuis settings
            api_key = getattr(settings, 'FREEPIK_API_KEY', 'FPSXdbb31bca84c6e7f77a957daa99cbd3b6')
            
            # Appel à l'API Freepik avec filtres pour wallpapers/photos
            freepik_url = 'https://api.freepik.com/v1/resources'
            params = {
                'locale': 'en-US',
                'term': query,
                'page': page,
                'limit': limit,
                'order': 'relevance',  # Meilleure pertinence pour les recherches
                # Filtres pour avoir des vraies photos (pas flat backgrounds)
                'filters[content_type][photo]': 1,  # Seulement des photos
                'filters[orientation][landscape]': 1,  # Format paysage (wallpaper)
            }
            headers = {
                'Content-Type': 'application/json',
                'X-Freepik-API-Key': api_key
            }
            
            print(f"🔍 Freepik API: Recherche '{query}' (page {page}, limit {limit})")
            print(f"   📸 Filtres: photos uniquement, format paysage (wallpaper)")
            
            response = requests.get(freepik_url, params=params, headers=headers, timeout=10)
            
            if response.status_code == 200:
                data = response.json()
                images_count = len(data.get('data', []))
                print(f"✅ Freepik API: {images_count} images trouvées")
                
                return Response(data, status=status.HTTP_200_OK)
            else:
                error_data = response.json() if response.content else {}
                print(f"❌ Freepik API error {response.status_code}: {error_data}")
                
                return Response(
                    {
                        'error': f'Erreur Freepik API: {response.status_code}',
                        'details': error_data
                    },
                    status=response.status_code
                )
                
        except requests.Timeout:
            return Response(
                {'error': 'Timeout de l\'API Freepik'},
                status=status.HTTP_504_GATEWAY_TIMEOUT
            )
        except requests.RequestException as e:
            print(f"❌ Erreur réseau Freepik: {str(e)}")
            return Response(
                {'error': f'Erreur réseau: {str(e)}'},
                status=status.HTTP_502_BAD_GATEWAY
            )
        except Exception as e:
            print(f"❌ Erreur Freepik proxy: {str(e)}")
            traceback.print_exc()
            return Response(
                {'error': f'Erreur serveur: {str(e)}'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )
