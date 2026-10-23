import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
import utils


VOIX_REELLES = [
    {"ShortName": n, "Locale": n[:5], "Gender": g} for n, g in [
        ("fr-FR-HenriNeural", "Male"), ("fr-FR-DeniseNeural", "Female"),
        ("fr-FR-RemyMultilingualNeural", "Male"), ("fr-BE-GerardNeural", "Male"),
        ("en-US-ChristopherNeural", "Male"), ("en-US-GuyNeural", "Male"),
        ("es-ES-AlvaroNeural", "Male"), ("de-DE-ConradNeural", "Male"),
        ("it-IT-DiegoNeural", "Male"), ("pt-BR-AntonioNeural", "Male")]]


class FauxCommunicate:
    """Simule edge_tts.Communicate. `echecs` : préfixe de texte -> nb d'échecs
    à simuler (-1 = toujours). `tout_echoue` simule un service qui refuse tout."""
    echecs = {}
    appels = []
    tout_echoue = False

    def __init__(self, texte, voix):
        self.texte, self.voix = texte, voix

    async def save(self, chemin):
        FauxCommunicate.appels.append(self.texte)
        await asyncio.sleep(0.001)      # vraie pause réseau => les tâches s'entrelacent
        # Comme le vrai service : voix inexistante => "No audio was received"
        if self.voix not in {v["ShortName"] for v in VOIX_REELLES}:
            raise RuntimeError("No audio was received. Please verify that your parameters are correct.")
        if FauxCommunicate.tout_echoue:
            raise RuntimeError("No audio was received. Please verify that your parameters are correct.")
        cle = next((k for k in FauxCommunicate.echecs if self.texte.startswith(k)), None)
        if cle is not None and FauxCommunicate.echecs[cle] != 0:
            if FauxCommunicate.echecs[cle] > 0:
                FauxCommunicate.echecs[cle] -= 1
            raise RuntimeError("No audio was received. Please verify that your parameters are correct.")
        with open(chemin, "wb") as f:
            f.write(f"[{self.voix}]{self.texte}".encode())


@pytest.fixture(autouse=True)
def faux_tts(monkeypatch):
    FauxCommunicate.echecs = {}
    FauxCommunicate.appels = []
    FauxCommunicate.tout_echoue = False
    monkeypatch.setattr(utils.edge_tts, "Communicate", FauxCommunicate)
    monkeypatch.setattr(utils, "voix_disponibles", lambda: VOIX_REELLES)
    monkeypatch.setattr(utils, "ATTENTE_BASE", 0)      # tests rapides
    monkeypatch.setattr(utils, "PAUSE_ENTRE_PASSES", 0)
    return FauxCommunicate


def fabrique_pdf(chemin, lignes_par_page):
    c = canvas.Canvas(str(chemin), pagesize=A4)
    for lignes in lignes_par_page:
        y = 800
        for l in lignes:
            c.drawString(50, y, l)
            y -= 14
            if y < 40:
                c.showPage(); y = 800
        c.showPage()
    c.save()
    return str(chemin)


@pytest.fixture
def pdf_fr(tmp_path):
    return fabrique_pdf(tmp_path / "livre.pdf", [
        ["Bonjour tout le monde. Ceci est un livre en francais.",
         "Il parle de la vie, des amis et des voyages dans le monde entier."],
        ["Deuxieme page : la suite de l'histoire commence ici. Fin du chapitre."],
    ])

@pytest.fixture
def pdf_en(tmp_path):
    return fabrique_pdf(tmp_path / "book.pdf", [
        ["Hello everybody. This is a book written in English language.",
         "It talks about life, friends and travelling around the whole world."]])

@pytest.fixture
def pdf_vide(tmp_path):
    return fabrique_pdf(tmp_path / "vide.pdf", [[]])

@pytest.fixture
def pdf_long(tmp_path):
    """Livre de ~30 morceaux de 100 caractères max (avec TAILLE_MAX_MORCEAU réduit)."""
    lignes = [f"This is the English sentence number {i:03d} of this long book." for i in range(60)]
    return fabrique_pdf(tmp_path / "long.pdf", [lignes])
