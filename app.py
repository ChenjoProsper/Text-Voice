import os
import threading
import uuid

from flask import Flask, jsonify, redirect, render_template, request, url_for
from werkzeug.utils import secure_filename

import utils

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 50 * 1024 * 1024  # 50 Mo

EXTENSIONS = (".pdf", ".txt")

# Tâches en cours / terminées (en mémoire : lancer gunicorn avec UN seul worker)
JOBS = {}
VERROU = threading.Lock()


def _maj(job_id, **champs):
    with VERROU:
        if job_id in JOBS:          # la tâche peut avoir été retirée entre-temps
            JOBS[job_id].update(champs)


def _travail(job_id):
    job = JOBS[job_id]

    def progression(fait, total):
        _maj(job_id, fait=fait, total=total)

    try:
        chemin = utils.genere_audio(
            job["source"], progression=progression, nom=job["nom_audio"]
        )
        _maj(job_id, etat="termine", audio=os.path.basename(chemin), erreur=None)
    except ValueError as e:
        _maj(job_id, etat="erreur", erreur=str(e), reprenable=False)
    except Exception as e:
        app.logger.exception("Erreur de conversion")
        _maj(job_id, etat="erreur", erreur=str(e), reprenable=True)


def _demarre(job_id):
    t = threading.Thread(target=_travail, args=(job_id,), daemon=True)
    t.start()


def _page_erreur(message, code):
    return render_template("index.html", erreur=message), code


@app.route("/")
def Home():
    return render_template("index.html")


@app.route("/health")
def health():
    return {"status": "ok"}


@app.errorhandler(413)
def trop_gros(_e):
    return _page_erreur("Fichier trop volumineux (50 Mo max).", 413)


@app.route("/convertir", methods=["POST"])
def convertir():
    if "fichier_pdf" not in request.files:
        return _page_erreur("Aucun fichier n'a été envoyé.", 400)
    fichier = request.files["fichier_pdf"]
    if fichier.filename == "":
        return _page_erreur("Aucun fichier sélectionné.", 400)

    brut = fichier.filename.lower()
    ext = next((e for e in EXTENSIONS if brut.endswith(e)), None)
    if ext is None:
        return _page_erreur("Formats acceptés : PDF ou TXT.", 400)

    if ext == ".pdf":
        if fichier.stream.read(5) != b"%PDF-":
            return _page_erreur("Ce fichier n'est pas un PDF valide.", 400)
        fichier.stream.seek(0)

    # Sauvegarde sous un nom temporaire puis renommage par empreinte du contenu
    tmp = os.path.join(utils.Document_folder, f"upload_{uuid.uuid4().hex}.tmp")
    fichier.save(tmp)
    empreinte = utils.hash_fichier(tmp)
    chemin = os.path.join(utils.Document_folder, f"{empreinte}{ext}")
    os.replace(tmp, chemin)

    stem = os.path.splitext(secure_filename(fichier.filename))[0]
    if stem in ("", "pdf", "txt"):
        stem = "document"
    job_id = empreinte

    with VERROU:
        existant = JOBS.get(job_id)
        deja_en_cours = existant is not None and existant["etat"] == "en_cours"
        if not deja_en_cours:
            JOBS[job_id] = {
                "etat": "en_cours", "fait": 0, "total": 0, "erreur": None,
                "audio": None, "source": chemin, "nom_audio": stem,
                "nom_affiche": fichier.filename, "reprenable": False,
            }
    if not deja_en_cours:
        _demarre(job_id)
    return redirect(url_for("job", job_id=job_id))


@app.route("/job/<job_id>")
def job(job_id):
    if job_id not in JOBS:
        return _page_erreur("Tâche introuvable (le serveur a peut-être redémarré). "
                            "Renvoyez le fichier : la reprise est automatique.", 404)
    return render_template("job.html", job_id=job_id, nom=JOBS[job_id]["nom_affiche"])


@app.route("/statut/<job_id>")
def statut(job_id):
    j = JOBS.get(job_id)
    if j is None:
        return jsonify(etat="inconnu"), 404
    with VERROU:
        donnees = {k: j[k] for k in ("etat", "fait", "total", "erreur", "reprenable")}
        donnees["url"] = (url_for("static", filename=f"audio/{j['audio']}")
                            if j["audio"] else None)
    return jsonify(donnees)


@app.route("/reprendre/<job_id>", methods=["POST"])
def reprendre(job_id):
    with VERROU:
        j = JOBS.get(job_id)
        if j is None:
            return jsonify(erreur="inconnu"), 404
        if j["etat"] != "erreur" or not j["reprenable"]:
            return jsonify(erreur="Rien à reprendre."), 409
        j.update(etat="en_cours", erreur=None)
    _demarre(job_id)
    return jsonify(etat="en_cours")


if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=int(os.environ.get("PORT", 5000)),
        debug=os.environ.get("FLASK_DEBUG", "0") == "1",
        threaded=True,
    )
