import io, os, time, pytest
import app as appmodule
import utils


@pytest.fixture
def client(tmp_path, monkeypatch):
    docs = tmp_path / "docs"; docs.mkdir()
    audio = tmp_path / "audio"; audio.mkdir()
    monkeypatch.setattr(utils, "Document_folder", str(docs))
    monkeypatch.setattr(utils, "Audio_Folder", str(audio))
    appmodule.JOBS.clear()
    appmodule.app.config["TESTING"] = True
    return appmodule.app.test_client()


def envoie(client, contenu, nom="test.pdf", champ="fichier_pdf"):
    return client.post("/convertir", data={champ: (io.BytesIO(contenu), nom)},
                       content_type="multipart/form-data")

def attend(client, job_id, etat_final=("termine", "erreur"), delai=10):
    fin = time.time() + delai
    while time.time() < fin:
        s = client.get(f"/statut/{job_id}").json
        if s["etat"] in etat_final:
            return s
        time.sleep(0.05)
    raise AssertionError(f"timeout, dernier statut : {s}")

def lance(client, contenu, nom="test.pdf"):
    r = envoie(client, contenu, nom)
    assert r.status_code == 302, r.data
    return r.headers["Location"].rsplit("/", 1)[-1]


def test_home_et_health(client):
    r = client.get("/")
    assert r.status_code == 200 and b"fichier_pdf" in r.data and b".txt" in r.data
    assert client.get("/health").json == {"status": "ok"}

@pytest.mark.parametrize("data,code", [({}, 400)])
def test_aucun_champ(client, data, code):
    assert client.post("/convertir", data=data).status_code == code

def test_nom_vide(client):
    assert envoie(client, b"x", nom="").status_code == 400

def test_extension_refusee(client):
    r = envoie(client, b"x", nom="x.docx")
    assert r.status_code == 400 and b"PDF ou TXT" in r.data

def test_faux_pdf(client):
    r = envoie(client, b"pas un pdf", nom="faux.pdf")
    assert r.status_code == 400 and b"pas un PDF" in r.data

def test_page_job_et_inconnu(client, pdf_fr):
    jid = lance(client, open(pdf_fr, "rb").read(), "livre.pdf")
    assert client.get(f"/job/{jid}").status_code == 200
    attend(client, jid)
    assert client.get("/job/inexistant").status_code == 404
    assert client.get("/statut/inexistant").status_code == 404

def test_conversion_pdf_complete(client, pdf_fr):
    jid = lance(client, open(pdf_fr, "rb").read(), "mon livre.pdf")
    s = attend(client, jid)
    assert s["etat"] == "termine" and s["fait"] == s["total"] >= 1
    assert s["url"].startswith("/static/audio/mon_livre_") and s["url"].endswith(".mp3")
    assert os.path.getsize(os.path.join(utils.Audio_Folder, os.path.basename(s["url"]))) > 0

def test_conversion_txt(client):
    jid = lance(client, "Hello everybody. This is a text file in English.".encode(), "notes.txt")
    s = attend(client, jid)
    assert s["etat"] == "termine" and "notes_" in s["url"]

def test_txt_accentue_cp1252(client):
    jid = lance(client, "Bonjour à tous. Ceci est un texte écrit en français pour le test.".encode("cp1252"), "fr.txt")
    assert attend(client, jid)["etat"] == "termine"

def test_pdf_vide_erreur_non_reprenable(client, pdf_vide):
    jid = lance(client, open(pdf_vide, "rb").read(), "vide.pdf")
    s = attend(client, jid)
    assert s["etat"] == "erreur" and "texte exploitable" in s["erreur"] and s["reprenable"] is False
    assert client.post(f"/reprendre/{jid}").status_code == 409

def test_nom_dangereux_et_non_latin(client, pdf_fr):
    contenu = open(pdf_fr, "rb").read()
    for nom in ("../../etc/evil.pdf", "كتاب.pdf"):
        assert attend(client, lance(client, contenu, nom))["etat"] == "termine"
    assert not os.path.exists("/etc/evil.pdf")

def test_meme_fichier_deux_fois_meme_job(client, pdf_fr):
    c = open(pdf_fr, "rb").read()
    assert lance(client, c, "a.pdf") == lance(client, c, "b.pdf")

def test_echec_service_puis_reprise_via_api(client, pdf_en, faux_tts, monkeypatch):
    monkeypatch.setattr(utils, "TENTATIVES", 2)
    faux_tts.tout_echoue = True
    jid = lance(client, open(pdf_en, "rb").read(), "b.pdf")
    s = attend(client, jid)
    assert s["etat"] == "erreur" and s["reprenable"] is True
    assert "Échec" in s["erreur"] or "refuse" in s["erreur"]
    faux_tts.tout_echoue = False                       # le service revient
    assert client.post(f"/reprendre/{jid}").status_code == 200
    s = attend(client, jid, etat_final=("termine",))
    assert s["etat"] == "termine" and s["url"]

def test_cache_job_instantane(client, pdf_fr, faux_tts):
    c = open(pdf_fr, "rb").read()
    attend(client, lance(client, c, "l.pdf")); n = len(faux_tts.appels)
    appmodule.JOBS.clear()                             # simule un redémarrage du serveur
    assert attend(client, lance(client, c, "l.pdf"))["etat"] == "termine"
    assert len(faux_tts.appels) == n                   # aucun appel réseau

def test_fichier_trop_gros(client, monkeypatch):
    monkeypatch.setitem(appmodule.app.config, "MAX_CONTENT_LENGTH", 100)
    assert envoie(client, b"%PDF-" + b"0" * 500, "gros.pdf").status_code == 413
