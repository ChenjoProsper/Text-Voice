from flask import Flask,render_template,request
import utils
from werkzeug.utils import secure_filename
import os

Audio_Folder = 'static/audio/'
Document_folder = 'documents/'
os.makedirs(Audio_Folder, exist_ok=True)
os.makedirs(Document_folder, exist_ok=True)

app = Flask(__name__)

@app.route('/')
def Home():
    return render_template('index.html')


@app.route('/convertir',methods=['POST'])
def convertir():
    if 'fichier_pdf' not in request.files:
        return "Aucun fichier n'a ete envoye",400
    
    fichier = request.files['fichier_pdf']
    
    if fichier.filename == '':
        return "Aucun fichier selectionner", 400
    
    if fichier:
        nom_securise = secure_filename(fichier.filename)
        chemin_pdf = os.path.join(Document_folder,nom_securise)
        fichier.save(chemin_pdf)
        
        try:
            chemin_audio = utils.genere_audio(chemin_pdf)
            nom_audio = os.path.basename(chemin_audio)
            return f"""
                <h2>Conversion réussie !</h2>
                <p>Votre fichier a été converti en audio.</p>
                <audio controls>
                    <source src="{Audio_Folder}{nom_audio}" type="audio/mp3">
                    Votre navigateur ne supporte pas l'élément audio.
                </audio>
                <br><br>
                <a href="/">← Convertir un autre fichier</a>
            """
        except Exception as e:
            return f"Erreur lors de la conversion : {e}"
# @app.route('/tester')
# def tester_conversion():
#     test = "Machiavel - Le prince.pdf"
#     lien = os.path.join(Document_folder, test)
    
#     try:
#         chemin_audio = utils.genere_audio(lien)
#         return f"Audio généré avec succès ! Fichier disponible : {chemin_audio}"
#     except Exception as e:
#         return f"Erreur : {e}"

if __name__ == "__main__":
    app.run(debug=True)