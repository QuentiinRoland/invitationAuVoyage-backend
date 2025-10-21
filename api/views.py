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
from playwright.sync_api import sync_playwright
from datetime import datetime
import os
import requests
from urllib.parse import urlparse
import hashlib
import pathlib
import base64
import io
import fitz  # PyMuPDF
import traceback
from .models import Document, DocumentAsset, Folder

client = OpenAI(api_key=settings.OPENAI_API_KEY)


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
    """Cache une image localement et retourne l'URL locale"""
    try:
        h = hashlib.sha1(url.encode()).hexdigest()
        ext = ".jpg"
        local = MEDIA_DIR / f"{h}{ext}"
        
        if not local.exists():
            r = requests.get(url, timeout=5)  # Réduit à 5 secondes pour éviter les timeouts
            r.raise_for_status()
            local.write_bytes(r.content)
        
        # Retourne une URL relative pour servir depuis Django
        return f"/media/offer_images/{local.name}"
    except Exception as e:
        print(f"Erreur cache image: {e}")
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

            with sync_playwright() as p:
                browser = p.chromium.launch()  # headless par défaut
                page = browser.new_page()
                # Rendre le HTML directement (pas besoin d'un serveur HTML séparé)
                page.set_content(printable_html, wait_until="load")
                pdf_bytes = page.pdf(
                    format="A4",
                    print_background=True,
                    margin={"top": "20mm", "bottom": "20mm", "left": "20mm", "right": "20mm"}
                )
                browser.close()

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
        Convertit le contenu GrapesJS en HTML imprimable (reprend ton ancienne logique).
        """
        company_name  = company_info.get('name', 'Votre Entreprise')
        clean_html    = self.clean_grapesjs_html(grapesjs_html)
        clean_css     = self.clean_grapesjs_css(grapesjs_css)
        current_date  = datetime.now().strftime("%d/%m/%Y à %H:%M")
        footer_html   = self.generate_footer(company_info, current_date)

        # Page HTML complète avec le CSS embarqué
        return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="utf-8">
  <title>Document - {company_name}</title>
  <style>
    /* Reset & base */
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: Arial, sans-serif;
      line-height: 1.6;
      color: #333;
      background: white;
      max-width: 800px;
      margin: 0 auto;
      padding: 20px;
    }}

    /* Impression */
    @page {{ margin: 2cm; size: A4; }}
    @media print {{
      body {{ margin: 0; padding: 15px; max-width: 100%; }}
      .no-print {{ display: none !important; }}
      .page-break {{ page-break-before: always; }}
      .avoid-break {{ page-break-inside: avoid; }}
      * {{ -webkit-print-color-adjust: exact !important; print-color-adjust: exact !important; }}
    }}

    /* CSS GrapesJS nettoyé */
    {clean_css}

    /* Améliorations sections */
    .flight-section, .hotel-section, .price-section {{
      page-break-inside: avoid;
      margin-bottom: 25px;
      padding: 20px;
      border-radius: 8px;
    }}
    .cta-section {{
      page-break-inside: avoid;
      margin: 25px 0;
      padding: 25px;
      border-radius: 8px;
    }}
    .offer-header {{
      page-break-inside: avoid;
      margin-bottom: 30px;
      padding: 30px;
      border-radius: 8px;
    }}
    h1, h2, h3 {{ page-break-after: avoid; margin-bottom: 15px; }}
    img {{ max-width: 100%; height: auto; }}
  </style>
</head>
<body>
  <div class="grapesjs-content">
    {clean_html}
  </div>

  {footer_html}
</body>
</html>"""

    def clean_grapesjs_html(self, html: str) -> str:
        """Nettoie le HTML de GrapesJS pour l'impression (reprend tes regex)."""
        if not html:
            return ""
        html = re.sub(r'data-gjs-[^=]*="[^"]*"', '', html)
        html = re.sub(r'contenteditable="[^"]*"', '', html)
        html = re.sub(r'spellcheck="[^"]*"', '', html)
        html = re.sub(r'\s+', ' ', html).strip()
        return html

    def clean_grapesjs_css(self, css: str) -> str:
        """Nettoie le CSS de GrapesJS pour l'impression."""
        if not css:
            return ""
        css = re.sub(r'\[data-gjs[^\]]*\][^}]*}', '', css)
        css = re.sub(r'\.gjs-[^}]*}', '', css)
        css = css.replace('rgba(0,0,0,0)', 'transparent')
        css = re.sub(r'\s+', ' ', css).strip()
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
    
    def post(self, request):
        text_input = request.data.get("text")
        company_info = request.data.get("company_info", {})
        
        if not text_input:
            return Response({"error": "Texte requis"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            prompt = f"""Crée une offre de voyage DÉTAILLÉE et PROFESSIONNELLE pour : {text_input}

IMPORTANT : Sois TRÈS DÉTAILLÉ dans chaque section. Inclus des informations spécifiques, des prix, des horaires, des descriptions complètes.

Format JSON strict :
{{
  "title": "Titre accrocheur et mémorable",
  "introduction": "Description complète et engageante du voyage (3-4 phrases minimum)",
  "sections": [
    {{
      "id": "flights", 
      "type": "Flights", 
      "title": "✈️ Transport Aérien", 
      "body": "Détails COMPLETS des vols : compagnie, numéros de vol, horaires précis, classe de service, durée du vol, aéroports, bagages inclus, repas à bord, etc."
    }},
    {{
      "id": "transfers", 
      "type": "Transfers", 
      "title": "🚗 Transferts & Transport", 
      "body": "Détails des transferts : type de véhicule, durée, horaires, chauffeur, accueil à l'aéroport, transport local, etc."
    }},
    {{
      "id": "hotel", 
      "type": "Hotel", 
      "title": "🏨 Hébergement", 
      "body": "Description DÉTAILLÉE de l'hôtel : nom, catégorie, localisation, type de chambre, pension, équipements, services, vue, etc."
    }},
    {{
      "id": "activities", 
      "type": "Activities", 
      "title": "🎯 Activités & Excursions", 
      "body": "Programme détaillé : visites guidées, excursions incluses, activités optionnelles, guides, durée, horaires, etc."
    }},
    {{
      "id": "price", 
      "type": "Price", 
      "title": "💰 Tarifs & Conditions", 
      "body": "Prix détaillé par personne, suppléments, conditions de réservation, acompte, annulation, assurance, etc."
    }}
  ],
  "cta": {{
    "title": "🎯 Réservez votre séjour de rêve !", 
    "description": "Offre limitée - Ne manquez pas cette opportunité unique", 
    "buttonText": "Réserver maintenant"
  }}
}}

EXIGENCES :
- Chaque section doit contenir au moins 150-200 mots de contenu détaillé
- Inclus des informations pratiques et spécifiques
- Utilise des listes à puces pour organiser l'information
- Sois professionnel mais engageant
- Inclus des détails sur les services, équipements, et conditions"""
            
            response = client.chat.completions.create(
                model="gpt-4o-mini",
                messages=[
                    {"role": "system", "content": "Expert voyage. JSON uniquement."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=2500,
                temperature=0.7
            )
            
            offer_json = response.choices[0].message.content
            if "```json" in offer_json:
                offer_json = offer_json.split("```json")[1].split("```")[0]
            
            offer_structure = json.loads(offer_json.strip())
            
            # Enrichir les sections avec des images
            self.enrich_sections_with_images(offer_structure)
            
            return Response({
                "offer_structure": offer_structure,
                "company_info": company_info
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

    def enrich_sections_with_images(self, offer_structure):
        """Enrichit chaque section avec des images appropriées"""
        # Vérifier si les APIs d'images sont configurées
        if not UNSPLASH_KEY and not BING_KEY:
            print("⚠️ Aucune API d'images configurée - sections sans images")
            return
        
        # Limiter le nombre de sections pour éviter les timeouts
        sections_to_process = offer_structure.get("sections", [])[:2]  # Max 2 sections seulement
        
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


class PDFOfferGenerator(APIView):
    def post(self, request):
        text_input = request.data.get("text")
        company_info = request.data.get("company_info", {})
        
        if not text_input:
            return Response({"error": "Texte requis"}, status=status.HTTP_400_BAD_REQUEST)
        
        try:
            pdf_generator = GrapesJSPDFGenerator()
            pdf_content = pdf_generator.create_pdf_with_weasyprint(company_info)
            
            response = HttpResponse(pdf_content, content_type='application/pdf')
            response['Content-Disposition'] = 'attachment; filename="offre_voyage.pdf"'
            return response
            
        except Exception as e:
            return Response({"error": f"Erreur : {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)


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

        logo_data_url = request.data.get("logo_data_url") or ""
        background_url = request.data.get("background_url") or ""

        try:
            text_md, assets = self._extract_pdf_content(pdf)
            offer_structure = self._md_to_offer_json(text_md, company_info, assets)

            # Sauvegarder automatiquement le document importé
            try:
                document = Document.objects.create(
                    title=offer_structure.get('title', 'PDF Importé'),
                    description=f"Document importé le {datetime.now().strftime('%d/%m/%Y à %H:%M')}",
                    document_type='pdf_import',
                    offer_structure=offer_structure,
                    company_info=company_info,
                    assets=assets
                )
                
                # Sauvegarder le fichier PDF original
                pdf_file_content = ContentFile(pdf.read(), name=f"imported_{document.id}.pdf")
                document.pdf_file.save(f"imported_{document.id}.pdf", pdf_file_content)
                
                print(f"✅ Document automatiquement sauvegardé avec l'ID: {document.id}")
                
            except Exception as e:
                print(f"⚠️ Erreur sauvegarde automatique: {e}")
                # Ne pas faire échouer l'import si la sauvegarde échoue

            return Response({
                "offer_structure": offer_structure,
                "assets": assets,
                "company_info": company_info,
                "background_url": background_url,
                "logo_data_url": logo_data_url,
                "document_id": document.id if 'document' in locals() else None
            })
        except Exception as e:
            import traceback; traceback.print_exc()
            return Response({"error": f"Erreur import PDF: {e}"}, status=500)

    def _extract_pdf_content(self, pdf_file):
        """Retourne (markdown_consolide, assets_base64[])"""
        doc = fitz.open(stream=pdf_file.read(), filetype="pdf")
        chunks = []
        assets = []
        img_count = 0

        for page_num, page in enumerate(doc):
            # Texte en blocs (unifié)
            text = page.get_text("markdown") or page.get_text("text")
            if text:
                chunks.append(text.strip())

            # Images avec améliorations
            for img_index, img in enumerate(page.get_images(full=True)):
                pix = None
                try:
                    xref = img[0]
                    pix = fitz.Pixmap(doc, xref)
                    
                    # Vérifier la taille de l'image (filtrer les trop petites)
                    if pix.width < 50 or pix.height < 50:
                        continue
                    
                    # Conversion CMYK → RGB si nécessaire
                    if pix.n > 4:  # CMYK → RGB
                        pix = fitz.Pixmap(fitz.csRGB, pix)
                    
                    # Convertir en PNG
                    img_bytes = pix.tobytes("png")
                    
                    # Vérifier que l'image n'est pas trop grande (limite à 2MB)
                    if len(img_bytes) > 2 * 1024 * 1024:
                        continue
                    
                    b64 = base64.b64encode(img_bytes).decode("ascii")
                    
                    # Ajouter des métadonnées utiles
                    assets.append({
                        "name": f"pdf_image_page{page_num+1}_{img_index+1}.png",
                        "data_url": f"data:image/png;base64,{b64}",
                        "width": pix.width,
                        "height": pix.height,
                        "page": page_num + 1,
                        "size_kb": round(len(img_bytes) / 1024, 1)
                    })
                    img_count += 1
                    
                except Exception as e:
                    print(f"Erreur extraction image page {page_num+1}: {e}")
                    continue
                finally:
                    if pix:
                        pix = None

        doc.close()
        md = "\n\n".join(chunks)
        md = re.sub(r'\n{3,}', '\n\n', md).strip()
        return md, assets

    def _md_to_offer_json(self, markdown_text, company_info, assets=[]):
        """Demande à l'IA de mapper le texte → JSON sections normalisées."""
        sys = "Tu es un assistant qui structure des offres de voyage. Réponds en JSON strict."
        
        # Préparer la liste des images disponibles
        images_info = ""
        if assets:
            images_info = f"\nImages disponibles ({len(assets)} images):\n"
            for i, asset in enumerate(assets):
                images_info += f"- Image {i+1}: {asset['name']} (page {asset['page']}, {asset['width']}x{asset['height']}px)\n"
        
        user = f"""
Voici le contenu d'une offre (Markdown, possible désordre). Déduis les sections:
- Flights (transport: vols, trajets, horaires, classe)
- Hotel (hébergement)
- Price (tarifs, conditions, inclus/exclus)
- CTA (appel à l'action)
- Facultatif: d'autres sections pertinentes (type 'Info', 'Activities', etc.) MAIS ne mets que celles utiles.

{images_info}

Contraintes:
- Réponds JSON STRICT sans texte autour.
- Garde les champs: title (string), introduction (string), sections (array), cta (object).
- Chaque section: {{"id":"slug","type":"Flights|Hotel|Price|Info|Activities|...","title":"...","body":"...","images":[...]}}
- body en texte enrichi (markdown simple), pas de HTML.
- IMPORTANT: Si des images sont disponibles, associe-les intelligemment aux sections appropriées :
  * Images d'avions/aéroports → section Flights
  * Images d'hôtels/chambres/piscines → section Hotel  
  * Images d'activités/paysages → section Activities
  * Autres images → section la plus appropriée
- Pour chaque image associée, utilise: {{"index": X, "description": "description de l'image"}} où X est le numéro de l'image (0-based)

Contenu:
{markdown_text}
        """
        res = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.3,
            messages=[
                {"role": "system", "content": sys},
                {"role": "user", "content": user}
            ]
        )
        raw = res.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```json")[-1].split("```")[0]
        data = json.loads(raw)

        # sécurité: clés minimales
        data.setdefault("title", "Votre offre de voyage")
        data.setdefault("introduction", "")
        data.setdefault("sections", [])
        data.setdefault("cta", {"title":"Réservez maintenant","description":"","buttonText":"Réserver"})

        return data


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

        res = client.chat.completions.create(
            model="gpt-4o-mini",
            temperature=0.5,
            messages=[{"role":"system","content":sys},{"role":"user","content":prompt}]
        )
        raw = res.choices[0].message.content.strip()
        if raw.startswith("```"):
            raw = raw.split("```json")[-1].split("```")[0]
        improved = json.loads(raw)

        return Response({"offer_structure": improved})


class DocumentListCreateView(ListCreateAPIView):
    """
    GET: Liste tous les documents sauvegardés
    POST: Crée un nouveau document
    """
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
                'assets_count': len(doc.assets) if doc.assets else 0
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
            
            # Créer le document
            document = Document.objects.create(
                title=title,
                description=description,
                document_type=document_type,
                grapes_html=grapes_html,
                grapes_css=grapes_css,
                offer_structure=offer_structure,
                company_info=company_info,
                assets=assets
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
            
            # Créer le dossier
            folder = Folder.objects.create(
                name=name,
                description=description,
                color=color,
                icon=icon,
                parent=parent
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