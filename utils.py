"""Extraction de texte (PDF/TXT), découpage et synthèse vocale robuste (edge-tts)."""
import asyncio
import hashlib
import os
import random
import re
import shutil
import time
import unicodedata

import edge_tts
from langdetect import DetectorFactory, detect
from pypdf import PdfReader

DetectorFactory.seed = 0  # détection de langue reproductible

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
Audio_Folder = os.path.join(BASE_DIR, "static", "audio")
Document_folder = os.path.join(BASE_DIR, "documents")
os.makedirs(Audio_Folder, exist_ok=True)
os.makedirs(Document_folder, exist_ok=True)

# --- Réglages (modifiables par variables d'environnement) ---
TAILLE_MAX_MORCEAU = int(os.environ.get("TTS_TAILLE_MORCEAU", 1200))
CONCURRENCE = int(os.environ.get("TTS_CONCURRENCE", 2))   # connexions simultanées
TENTATIVES = int(os.environ.get("TTS_TENTATIVES", 6))     # essais par morceau
ATTENTE_BASE = float(os.environ.get("TTS_ATTENTE", 2.0))  # backoff : 2s, 4s, 8s...
PASSES = int(os.environ.get("TTS_PASSES", 4))              # passes de rattrapage
PAUSE_ENTRE_PASSES = float(os.environ.get("TTS_PAUSE_PASSE", 10.0))  # 10s, 20s, 30s...
SEUIL_ECHECS_CONSECUTIFS = 12  # au-delà, on arrête (service indisponible/bloqué)

# Voix de préférence par langue (la 1re existante est utilisée).
# ATTENTION : un nom de voix inexistant n'est PAS signalé clairement par le service :
# il répond "No audio was received". D'où la validation via voix_disponibles().
VOIX = {
    "fr": ["fr-FR-HenriNeural", "fr-FR-RemyMultilingualNeural", "fr-FR-DeniseNeural"],
    "en": ["en-US-ChristopherNeural", "en-US-GuyNeural"],
    "es": ["es-ES-AlvaroNeural"],
    "de": ["de-DE-ConradNeural"],
    "it": ["it-IT-DiegoNeural"],
    "pt": ["pt-BR-AntonioNeural"],
}
VOIX_PAR_DEFAUT = VOIX["fr"][0]


class ServiceIndisponible(RuntimeError):
    """Trop d'échecs consécutifs : le service vocal refuse ou est injoignable."""


# ------------------------------------------------------------------ texte
def extraire_texte_pdf(chemin_fichier):
    lecteur = PdfReader(chemin_fichier)
    texte = ""
    for page in lecteur.pages:
        texte_page = page.extract_text()
        if texte_page:
            texte += texte_page + "\n"
    return texte


def extraire_texte_txt(chemin_fichier):
    with open(chemin_fichier, "rb") as f:
        brut = f.read()
    for encodage in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            return brut.decode(encodage)
        except UnicodeDecodeError:
            continue
    return brut.decode("utf-8", errors="ignore")


def extraire_texte(chemin_fichier):
    if chemin_fichier.lower().endswith(".txt"):
        return extraire_texte_txt(chemin_fichier)
    return extraire_texte_pdf(chemin_fichier)


def nettoyer_texte(texte):
    """Normalise le texte pour la synthèse : gère les accents, isole les énumérations,
    et nettoie la ponctuation pour une lecture naturelle."""
    
    # 1. Normalisation Unicode NFC (recolle la lettre et l'accent en un seul caractère)
    texte = unicodedata.normalize("NFC", texte)
    
    # 2. Suppression des descriptions d'accents explicites (ex: "e accent aigu" -> "é")
    remplacements_accents = {
        r"\be\s+accent\s+aigu\b": "é",
        r"\be\s+accent\s+grave\b": "è",
        r"\ba\s+accent\s+grave\b": "à",
        r"\be\s+accent\s+circonflexe\b": "ê",
        r"\bu\s+accent\s+grave\b": "ù",
        r"\bc\s+cédille\b": "ç",
    }
    for patron, remplacement in remplacements_accents.items():
        texte = re.sub(patron, remplacement, texte, flags=re.IGNORECASE)

    texte = texte.replace("\xad", "")                      # trait d'union conditionnel
    texte = re.sub(r"(\w)-\n(\w)", r"\1\2", texte)         # "informa-\ntion"
    texte = re.sub(r"[\x00-\x08\x0b-\x1f\x7f-\x9f\ufffd]", " ", texte)
    
    # 3. Isoler les numéros de liste (ex: "1.", "2-") pour marquer des pauses
    texte = re.sub(r"\s+(\d{1,2}[\.\-\)])\s+", r". \n\1 ", texte)
    
    # 4. Ajouter un espace après la ponctuation collée
    texte = re.sub(r"([.!?…,:;])([a-zA-ZÀ-ÿ])", r"\1 \2", texte)
    
    # 5. Espace entre minuscules et majuscules collées (ex: "motTexte" -> "mot Texte")
    texte = re.sub(r"([a-zÀ-ÿ])([A-ZÀ-Ÿ])", r"\1 \2", texte)
    
    # 6. Structuration des paragraphes et retours à la ligne en pauses
    texte = re.sub(r"\n\s*\n", ". ", texte)
    texte = re.sub(r"\n", ". ", texte)
    
    texte = re.sub(r"[.…_·]{4,}", " ", texte)                     
    texte = re.sub(r"\s[–—-]\s?\d{1,4}\s?[–—-]\s", " ", texte)    
    return re.sub(r"\s+", " ", texte).strip()


def detecte_langue(texte):
    try:
        return detect(texte[:5000])
    except Exception:
        return "fr"


def voix_disponibles():
    """Liste officielle des voix du service (1 requête). None si injoignable."""
    async def _liste():
        return await asyncio.wait_for(edge_tts.list_voices(), 20)
    try:
        return asyncio.run(_liste())
    except Exception as e:
        print(f"-> Liste des voix indisponible ({e}) : voix par défaut utilisée.")
        return None


def choisir_voix(langue, disponibles=None):
    """Choisit une voix qui EXISTE. Sans liste officielle : 1re voix de préférence."""
    code = langue[:2].lower()
    preferees = VOIX.get(code, [])
    defaut = preferees[0] if preferees else VOIX_PAR_DEFAUT
    if not disponibles:
        return defaut
    noms = {v["ShortName"] for v in disponibles}
    for voix in preferees:
        if voix in noms:
            return voix
    # Aucune voix de préférence : n'importe quelle voix de cette langue (hommes d'abord)
    de_la_langue = [v for v in disponibles if v.get("Locale", "").lower().startswith(code + "-")]
    choix = [v for v in de_la_langue if v.get("Gender") == "Male"] or de_la_langue
    if choix:
        return sorted(choix, key=lambda v: v["ShortName"])[0]["ShortName"]
    return defaut if defaut in noms else sorted(noms)[0]


def est_prononcable(morceau):
    """Un morceau sans aucune lettre/chiffre (ex. '...', '—') ne produit pas
    d'audio : edge-tts répondrait « No audio was received »."""
    return re.search(r"\w", morceau) is not None


def decouper_texte(texte, max_taille=None):
    """Morceaux <= max_taille, coupés sur les fins de phrase (sinon sur les espaces)."""
    max_taille = max_taille or TAILLE_MAX_MORCEAU
    texte = texte.strip()
    if not texte:
        return []
    phrases = re.split(r"(?<=[.!?…])\s+", texte)
    morceaux, courant = [], ""
    for phrase in phrases:
        while len(phrase) > max_taille:
            coupe = phrase.rfind(" ", 0, max_taille)
            coupe = coupe if coupe > 0 else max_taille
            if courant:
                morceaux.append(courant)
                courant = ""
            morceaux.append(phrase[:coupe].strip())
            phrase = phrase[coupe:].strip()
        if not phrase:
            continue
        if courant and len(courant) + 1 + len(phrase) > max_taille:
            morceaux.append(courant)
            courant = phrase
        else:
            courant = f"{courant} {phrase}".strip()
    if courant:
        morceaux.append(courant)
    return [m for m in morceaux if m.strip()]


def hash_fichier(chemin, taille_bloc=1 << 20):
    h = hashlib.sha256()
    with open(chemin, "rb") as f:
        for bloc in iter(lambda: f.read(taille_bloc), b""):
            h.update(bloc)
    return h.hexdigest()[:12]


# ------------------------------------------------------------------ synthèse
class _Etat:
    """État partagé entre les tâches : compteur de progression + disjoncteur."""

    def __init__(self, total, deja_faits, progression):
        self.total = total
        self.faits = deja_faits
        self.echecs_consecutifs = 0
        self.derniere_erreur = ""
        self.voix = ""
        self.progression = progression

    def succes(self):
        self.faits += 1
        self.echecs_consecutifs = 0
        if self.progression:
            self.progression(self.faits, self.total)

    def echec(self, erreur=""):
        self.echecs_consecutifs += 1
        self.derniere_erreur = str(erreur)

    def message_blocage(self):
        msg = (f"Le service vocal refuse les requêtes après {self.echecs_consecutifs} échecs "
                f"consécutifs (voix : {self.voix}). Dernière erreur : {self.derniere_erreur}")
        if "No audio" in self.derniere_erreur:
            msg += (" — « No audio was received » signifie souvent un paramètre invalide "
                    "(nom de voix inexistant). Lancez : python3 diagnostic_tts.py")
        return msg

    @property
    def disjoncteur_ouvert(self):
        return self.echecs_consecutifs >= SEUIL_ECHECS_CONSECUTIFS


def _chemin_partie(dossier_travail, i):
    return os.path.join(dossier_travail, f"part_{i:05d}.mp3")


async def _genere_un_morceau(i, morceau, voix, dossier_travail, semaphore, etat):
    final = _chemin_partie(dossier_travail, i)
    tmp = final + ".tmp"
    derniere_erreur = None

    for tentative in range(1, TENTATIVES + 1):
        try:
            async with semaphore:
                if etat.disjoncteur_ouvert:
                    raise ServiceIndisponible(etat.message_blocage())
                
                # On passe directement le morceau nettoyé sans balises texte SSML manuelles
                await edge_tts.Communicate(morceau, voix).save(tmp)
                
            if os.path.getsize(tmp) == 0:
                raise RuntimeError("fichier audio vide")
            os.replace(tmp, final)
            etat.succes()
            return
        except ServiceIndisponible:
            raise
        except Exception as e:
            derniere_erreur = e
            etat.echec(e)
            print(f"Erreur partie {i} (essai {tentative}/{TENTATIVES}) : {e}")
            if os.path.exists(tmp):
                os.remove(tmp)
            if tentative < TENTATIVES:
                await asyncio.sleep(ATTENTE_BASE * 2 ** (tentative - 1) + random.uniform(0, min(1.0, ATTENTE_BASE)))
    raise RuntimeError(f"Échec de la partie {i} : {derniere_erreur}")


async def _genere_tous_les_morceaux(morceaux, voix, dossier_travail, progression):
    """Génère les morceaux manquants (reprise : ceux déjà présents sont conservés)."""
    a_faire = [
        (i, m) for i, m in enumerate(morceaux)
        if not (os.path.exists(_chemin_partie(dossier_travail, i))
                and os.path.getsize(_chemin_partie(dossier_travail, i)) > 0)
    ]
    etat = _Etat(len(morceaux), len(morceaux) - len(a_faire), progression)
    etat.voix = voix
    if progression:
        progression(etat.faits, etat.total)
    semaphore = asyncio.Semaphore(CONCURRENCE)
    resultats = await asyncio.gather(
        *[_genere_un_morceau(i, m, voix, dossier_travail, semaphore, etat) for i, m in a_faire],
        return_exceptions=True,
    )
    erreurs = [r for r in resultats if isinstance(r, Exception)]
    if erreurs:
        indisponible = [e for e in erreurs if isinstance(e, ServiceIndisponible)]
        raise indisponible[0] if indisponible else erreurs[0]


def genere_audio(chemin_source, dossier_sortie=None, progression=None, nom=None):
    """PDF/TXT -> MP3. `progression(fait, total)` est appelé au fil de l'eau.
    En cas d'échec, les parties déjà générées sont conservées : relancer reprend."""
    dossier_sortie = dossier_sortie or Audio_Folder
    os.makedirs(dossier_sortie, exist_ok=True)
    empreinte = hash_fichier(chemin_source)
    nom_base = nom or os.path.splitext(os.path.basename(chemin_source))[0]
    chemin_sortie = os.path.join(dossier_sortie, f"{nom_base}_{empreinte}.mp3")

    if os.path.exists(chemin_sortie) and os.path.getsize(chemin_sortie) > 0:
        print(f"-> Audio en cache pour '{nom_base}'.")
        if progression:
            progression(1, 1)
        return chemin_sortie

    print(f"-> Extraction du texte : {chemin_source}")
    texte = nettoyer_texte(extraire_texte(chemin_source))
    print(f"-> Caractères extraits : {len(texte)}")
    if not texte:
        raise ValueError("Le fichier ne contient pas de texte exploitable (PDF scanné/image ?).")

    langue = detecte_langue(texte)
    voix = choisir_voix(langue, voix_disponibles())
    morceaux = [m for m in decouper_texte(texte) if est_prononcable(m)]
    if not morceaux:
        raise ValueError("Le fichier ne contient aucun texte prononçable.")
    print(f"-> Langue : {langue} | voix : {voix} | {len(morceaux)} partie(s)")

    # Dossier de travail STABLE (lié au contenu) => permet la reprise
    dossier_travail = os.path.join(dossier_sortie, f".travail_{empreinte}")
    os.makedirs(dossier_travail, exist_ok=True)

    # Passes de rattrapage : une partie récalcitrante ne doit pas faire échouer tout
    # le livre. Chaque passe ne retente que les parties encore manquantes.
    for passe in range(1, PASSES + 1):
        try:
            asyncio.run(_genere_tous_les_morceaux(morceaux, voix, dossier_travail, progression))
            break
        except ServiceIndisponible:
            raise                      # service bloqué : inutile d'insister
        except Exception as e:
            if passe == PASSES:
                raise
            pause = PAUSE_ENTRE_PASSES * passe
            print(f"-> Passe {passe}/{PASSES} incomplète ({e}). Nouvel essai dans {pause:.0f}s...")
            time.sleep(pause)

    tmp_final = chemin_sortie + ".tmp"
    with open(tmp_final, "wb") as final:
        for i in range(len(morceaux)):
            with open(_chemin_partie(dossier_travail, i), "rb") as f:
                shutil.copyfileobj(f, final)
    os.replace(tmp_final, chemin_sortie)
    shutil.rmtree(dossier_travail, ignore_errors=True)
    print("-> Audio généré et mis en cache.")
    return chemin_sortie
