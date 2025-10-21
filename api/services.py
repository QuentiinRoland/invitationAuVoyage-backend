from reportlab.lib.pagesizes import letter, A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import inch
from reportlab.lib import colors
from django.http import HttpResponse
import io
import html
import re

class PDFService:
    """
    Service pour générer des PDFs à partir de contenu HTML/texte
    """
    
    @staticmethod
    def generate_offer_pdf(offer_content, company_info=None):
        """
        Génère un PDF d'offre commerciale
        """
        # Créer un buffer en mémoire
        buffer = io.BytesIO()
        
        # Créer le document PDF
        doc = SimpleDocTemplate(
            buffer,
            pagesize=A4,
            rightMargin=72,
            leftMargin=72,
            topMargin=72,
            bottomMargin=18
        )
        
        # Styles
        styles = getSampleStyleSheet()
        
        # Style personnalisé pour le titre
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=24,
            spaceAfter=30,
            textColor=colors.HexColor('#2C3E50'),
            alignment=1  # Centré
        )
        
        # Style pour le contenu
        content_style = ParagraphStyle(
            'CustomContent',
            parent=styles['Normal'],
            fontSize=12,
            spaceAfter=12,
            leading=18
        )
        
        # Construire le contenu du PDF
        story = []
        
        # En-tête avec logo d'entreprise (si fourni)
        if company_info and company_info.get('logo'):
            # TODO: Ajouter le logo
            pass
            
        # Titre
        story.append(Paragraph("OFFRE COMMERCIALE", title_style))
        story.append(Spacer(1, 20))
        
        # Informations de l'entreprise
        if company_info:
            company_style = ParagraphStyle(
                'Company',
                parent=styles['Normal'],
                fontSize=10,
                textColor=colors.HexColor('#7F8C8D'),
                alignment=2  # Aligné à droite
            )
            
            company_text = f"""
            {company_info.get('name', '')}<br/>
            {company_info.get('address', '')}<br/>
            {company_info.get('phone', '')} - {company_info.get('email', '')}
            """
            story.append(Paragraph(company_text, company_style))
            story.append(Spacer(1, 30))
        
        # Contenu principal de l'offre
        # Nettoyer le HTML et convertir en paragraphes
        clean_content = PDFService.clean_html_for_pdf(offer_content)
        
        for paragraph in clean_content.split('\n\n'):
            if paragraph.strip():
                story.append(Paragraph(paragraph.strip(), content_style))
                story.append(Spacer(1, 12))
        
        # Pied de page
        footer_style = ParagraphStyle(
            'Footer',
            parent=styles['Normal'],
            fontSize=8,
            textColor=colors.HexColor('#95A5A6'),
            alignment=1
        )
        
        story.append(Spacer(1, 50))
        story.append(Paragraph("Cette offre est valable 30 jours à compter de sa date d'émission.", footer_style))
        
        # Construire le PDF
        doc.build(story)
        
        # Récupérer le contenu du buffer
        pdf_content = buffer.getvalue()
        buffer.close()
        
        return pdf_content
    
    @staticmethod
    def clean_html_for_pdf(html_content):
        """
        Nettoie le contenu HTML pour l'adapter au PDF
        """
        # Supprimer les balises HTML non supportées
        html_content = re.sub(r'<[^>]+>', '', html_content)
        
        # Décoder les entités HTML
        html_content = html.unescape(html_content)
        
        # Nettoyer les espaces multiples
        html_content = re.sub(r'\s+', ' ', html_content)
        
        return html_content.strip()
    
    @staticmethod
    def create_pdf_response(pdf_content, filename="offre.pdf"):
        """
        Crée une réponse HTTP avec le PDF
        """
        response = HttpResponse(pdf_content, content_type='application/pdf')
        response['Content-Disposition'] = f'attachment; filename="{filename}"'
        return response