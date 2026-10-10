from pypdf import PdfReader

def extraire_texte_pdf(chemin_fichier):
    lecteur = PdfReader(chemin_fichier)
    texte = ""
    for page in lecteur.pages:
        texte_page = page.extract_text()
        if texte_page:
            texte += texte_page + "\n"
    return texte


from langdetect import detect

def detecte_langue(texte):
    langue = 'fr'
    try:
        langue =  detect(texte)
    except:
        pass
    return langue

from gtts import gTTS

def genere_audio(lien):

    texte = extraire_texte_pdf(lien)
    audio = gTTS(text = texte,lang = detecte_langue(texte))
    audio.save("sortie.mp3")
    
    print("Audio generer avec succes  !!")
    
    return audio