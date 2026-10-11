from pypdf import PdfReader
from langdetect import detect
from gtts import gTTS
import os

def extraire_texte_pdf(chemin_fichier):
    lecteur = PdfReader(chemin_fichier)
    texte = ""
    for page in lecteur.pages:
        texte_page = page.extract_text()
        if texte_page:
            texte += texte_page + "\n"
    return texte

def detecte_langue(texte):
    langue = 'fr'
    try:
        langue = detect(texte)
    except:
        pass
    return langue

from app import Audio_Folder


def genere_audio(chemin_pdf, dossier_sortie=Audio_Folder):
    nom_base = os.path.splitext(os.path.basename(chemin_pdf))[0]
    chemin_sortie = os.path.join(dossier_sortie, f"{nom_base}.mp3")


# 1. VÉRIFICATION DU CACHE (mp3 ou wav)
    if os.path.exists(chemin_sortie):
        print(f"-> Audio trouvé en cache pour '{nom_base}' ! Aucun appel réseau nécessaire.")
        return chemin_sortie

    print(f"-> Aucun cache trouvé. Extraction et génération en cours pour : {chemin_pdf}...")
    print(f"-> Extraction du texte pour : {chemin_pdf}...")
    texte = extraire_texte_pdf(chemin_pdf)
    texte = extraire_texte_pdf(chemin_pdf)
    print(f"-> Nombre de caractères extraits du PDF : {len(texte)}")
    
    if not texte.strip():
        raise ValueError("Le fichier PDF est vide ou le texte n'a pas pu être extrait.")
        
    langue = detecte_langue(texte)
    print(f"-> Langue détectée : {langue}")
    
# 2. Découpage intelligent du texte en morceaux (~1500 caractères max par morceau)
    max_taille = 10000
    morceaux = []
    
    while len(texte) > 0:
        if len(texte) <= max_taille:
            morceaux.append(texte)
            break
        # Chercher un point pour couper proprement en fin de phrase
        index = texte.rfind('.', 0, max_taille)
        if index == -1:
            index = max_taille
        else:
            index += 1  # Inclure le point dans le morceau
        morceaux.append(texte[:index])
        texte = texte[index:]

    print(f"-> Texte découpé en {len(morceaux)} partie(s). Génération en cours...")

    # 3. Génération de chaque morceau et stockage temporaire
    fichiers_temp = []
    for i, morceau in enumerate(morceaux):
        if not morceau.strip():
            continue
        print(f"   -> Traitement de la partie {i+1}/{len(morceaux)}...")
        tts = gTTS(text=morceau, lang=langue)
        temp_path = os.path.join(dossier_sortie, f"temp_{nom_base}_{i}.mp3")
        tts.save(temp_path)
        fichiers_temp.append(temp_path)

    # 4. Fusion des morceaux MP3 en un seul fichier final
    print("-> Assemblage des fichiers audio...")
    with open(chemin_sortie, 'wb') as fichier_final:
        for f_temp in fichiers_temp:
            with open(f_temp, 'rb') as f:
                fichier_final.write(f.read())
            os.remove(f_temp)  # Nettoyage du fichier temporaire

    print("-> Audio complet généré et mis en cache avec succès !")
    return chemin_sortie