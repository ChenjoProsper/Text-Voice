from flask import Flask,render_template,request
import utils
from werkzeug.utils import secure_filename
import os
from utils import Audio_Folder, Document_folder

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

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)