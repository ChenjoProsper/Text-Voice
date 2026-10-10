from flask import  Flask
import utils

import os


Audio_Folder = 'static/audio'
Document_folder = 'documents/'
os.makedirs(Audio_Folder,exist_ok=True)
os.makedirs(Document_folder,exist_ok=True)

app =  Flask(__name__)

@app.route('/')
def Home():
    return  "<p>Hello word !!!</p>"


test = "steph  doc.pdf"

lien = Document_folder + test
audio = utils.genere_audio(lien)


# if __name__ == "__main__":
#     app.run(debug=True)