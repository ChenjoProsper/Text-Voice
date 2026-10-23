import os, pytest
import utils
from tests.conftest import fabrique_pdf


# ---------- extraction ----------
def test_extraction_pdf(pdf_fr):
    t = utils.extraire_texte(pdf_fr)
    assert "Bonjour tout le monde" in t and "Deuxieme page" in t

def test_extraction_pdf_vide(pdf_vide):
    assert utils.extraire_texte(pdf_vide).strip() == ""

def test_extraction_txt_utf8(tmp_path):
    p = tmp_path / "a.txt"; p.write_text("Été à Paris, ça va très bien.", encoding="utf-8")
    assert utils.extraire_texte(str(p)) == "Été à Paris, ça va très bien."

def test_extraction_txt_utf8_bom(tmp_path):
    p = tmp_path / "a.txt"; p.write_bytes(b"\xef\xbb\xbfBonjour")
    assert utils.extraire_texte(str(p)) == "Bonjour"

def test_extraction_txt_cp1252(tmp_path):
    p = tmp_path / "a.txt"; p.write_bytes("Été à Paris".encode("cp1252"))
    assert utils.extraire_texte(str(p)) == "Été à Paris"

# ---------- nettoyage ----------
def test_nettoyage_espaces_et_nuls():
    assert utils.nettoyer_texte("a\n\n  b\tc\x00d") == "a b c d"

def test_nettoyage_mot_coupe():
    assert utils.nettoyer_texte("informa-\ntion") == "information"

def test_nettoyage_ligatures_et_controle():
    assert utils.nettoyer_texte("de\ufb01nition\x0c\x1b ok\u00ad") == "definition ok"

# ---------- langue / voix ----------
def test_langue():
    assert utils.detecte_langue("Bonjour, ceci est un texte écrit en français pour le test.") == "fr"
    assert utils.detecte_langue("Hello, this is a text written in English for the test.") == "en"
    assert utils.detecte_langue("") == "fr"

@pytest.mark.parametrize("langue,voix", [
    ("fr", "fr-FR-HenriNeural"), ("en", "en-US-ChristopherNeural"),
    ("es", "es-ES-AlvaroNeural"), ("de", "de-DE-ConradNeural"),
    ("zh-cn", utils.VOIX_PAR_DEFAUT)])
def test_choix_voix(langue, voix):
    assert utils.choisir_voix(langue) == voix

def test_toutes_les_voix_configurees_existent():
    """Régression : 'fr-FR-DenysNeural' n'existe pas => 'No audio was received' partout."""
    from tests.conftest import VOIX_REELLES
    reelles = {v["ShortName"] for v in VOIX_REELLES}
    for langue, prefs in utils.VOIX.items():
        assert any(v in reelles for v in prefs), f"aucune voix valide pour '{langue}'"
    assert "fr-FR-DenysNeural" not in sum(utils.VOIX.values(), [])

def test_choix_voix_valide_contre_liste():
    from tests.conftest import VOIX_REELLES
    # La voix préférée a disparu du service -> on prend la suivante qui existe
    sans_henri = [v for v in VOIX_REELLES if v["ShortName"] != "fr-FR-HenriNeural"]
    assert utils.choisir_voix("fr", sans_henri) == "fr-FR-RemyMultilingualNeural"
    # Aucune voix préférée -> n'importe quelle voix de la langue, homme d'abord
    seulement_be = [v for v in VOIX_REELLES if v["ShortName"] == "fr-BE-GerardNeural"]
    assert utils.choisir_voix("fr", seulement_be) == "fr-BE-GerardNeural"
    # Liste indisponible (None / vide) -> voix par défaut
    assert utils.choisir_voix("fr", None) == "fr-FR-HenriNeural"
    assert utils.choisir_voix("fr", []) == "fr-FR-HenriNeural"

def test_voix_utilisee_est_acceptee_par_le_service_strict(pdf_fr, tmp_path):
    chemin = utils.genere_audio(pdf_fr, str(tmp_path / "o"))
    assert "fr-FR-HenriNeural" in open(chemin).read()

def test_liste_voix_injoignable_ne_bloque_pas(pdf_fr, tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "voix_disponibles", lambda: None)
    assert os.path.getsize(utils.genere_audio(pdf_fr, str(tmp_path / "o"))) > 0

def test_voix_inexistante_echoue_vite_avec_message_clair(pdf_long, faux_tts, tmp_path, monkeypatch):
    """Reproduit exactement le bug rapporté : voix invalide => on doit s'arrêter
    après ~12 requêtes (pas 200) avec un message qui désigne la voix."""
    monkeypatch.setattr(utils, "TAILLE_MAX_MORCEAU", 100)
    monkeypatch.setattr(utils, "voix_disponibles", lambda: None)
    monkeypatch.setitem(utils.VOIX, "en", ["en-US-InexistanteNeural"])
    with pytest.raises(utils.ServiceIndisponible) as e:
        utils.genere_audio(pdf_long, str(tmp_path / "o"))
    assert "en-US-InexistanteNeural" in str(e.value) and "diagnostic_tts" in str(e.value)
    assert len(faux_tts.appels) <= utils.SEUIL_ECHECS_CONSECUTIFS + utils.CONCURRENCE

# ---------- nettoyage supplémentaire ----------
def test_nettoyage_points_de_conduite():
    assert utils.nettoyer_texte("Préface ........................4 CHAPITRE") == "Préface 4 CHAPITRE"
    assert utils.nettoyer_texte("Il hésita... puis partit") == "Il hésita... puis partit"

def test_nettoyage_numeros_de_page():
    assert utils.nettoyer_texte("jugeant bientôt que – 61 – de telles forces") == "jugeant bientôt que de telles forces"
    assert utils.nettoyer_texte("en 1515 – il écrivit") == "en 1515 – il écrivit"

# ---------- prononçable ----------
@pytest.mark.parametrize("s,attendu", [("Bonjour", True), ("...", False), ("— • —", False),
                                       ("12", True), ("  ", False)])
def test_est_prononcable(s, attendu):
    assert utils.est_prononcable(s) is attendu

# ---------- découpage ----------
def test_decoupage_vide_et_court():
    assert utils.decouper_texte("  ") == []
    assert utils.decouper_texte("Une phrase.") == ["Une phrase."]

def test_decoupage_taille_contenu_ordre():
    texte = " ".join(f"Phrase numero {i} du livre." for i in range(500))
    m = utils.decouper_texte(texte, 200)
    assert all(len(x) <= 200 for x in m) and " ".join(m) == texte
    assert all(x.endswith(".") for x in m)

def test_decoupage_phrase_geante():
    texte = "mot " * 1000
    m = utils.decouper_texte(texte, 100)
    assert all(0 < len(x) <= 100 for x in m) and " ".join(m).split() == texte.split()

def test_decoupage_mot_geant():
    assert [len(x) for x in utils.decouper_texte("x" * 350, 100)] == [100, 100, 100, 50]

# ---------- hash ----------
def test_hash(tmp_path):
    a, b, c = tmp_path/"a", tmp_path/"b", tmp_path/"c"
    a.write_bytes(b"1"); b.write_bytes(b"1"); c.write_bytes(b"2")
    assert utils.hash_fichier(a) == utils.hash_fichier(b) != utils.hash_fichier(c)

# ---------- genere_audio ----------
def test_genere_audio_pdf(pdf_fr, tmp_path):
    sortie = str(tmp_path / "out")
    chemin = utils.genere_audio(pdf_fr, sortie)
    txt = open(chemin, "rb").read().decode()
    assert chemin.endswith(".mp3") and "[fr-FR-HenriNeural]" in txt
    assert txt.index("Bonjour") < txt.index("Deuxieme")
    assert os.listdir(sortie) == [os.path.basename(chemin)]      # ni temp ni dossier de travail

def test_genere_audio_txt(tmp_path):
    p = tmp_path / "mon texte.txt"
    p.write_text("Hello everybody. This is a text file written in English language.")
    chemin = utils.genere_audio(str(p), str(tmp_path / "o"))
    assert "[en-US-ChristopherNeural]" in open(chemin).read()

def test_default_dossier_suit_audio_folder(pdf_en, tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "Audio_Folder", str(tmp_path / "dyn"))
    assert os.path.dirname(utils.genere_audio(pdf_en)) == str(tmp_path / "dyn")

def test_cache_sans_appel_reseau(pdf_fr, faux_tts, tmp_path):
    s = str(tmp_path / "o")
    a = utils.genere_audio(pdf_fr, s); n = len(faux_tts.appels)
    assert utils.genere_audio(pdf_fr, s) == a and len(faux_tts.appels) == n

def test_cache_distingue_meme_nom(tmp_path):
    d1, d2 = tmp_path/"d1", tmp_path/"d2"; d1.mkdir(); d2.mkdir()
    p1 = fabrique_pdf(d1/"livre.pdf", [["Hello this is the first English document here."]])
    p2 = fabrique_pdf(d2/"livre.pdf", [["Hello this is a totally different English document."]])
    s = str(tmp_path / "o")
    a, b = utils.genere_audio(p1, s), utils.genere_audio(p2, s)
    assert a != b and "first" in open(a).read() and "different" in open(b).read()

def test_pdf_sans_texte(pdf_vide, tmp_path):
    with pytest.raises(ValueError, match="texte exploitable"):
        utils.genere_audio(pdf_vide, str(tmp_path / "o"))

def test_texte_uniquement_ponctuation(tmp_path):
    p = tmp_path / "p.txt"; p.write_text("... --- ...")
    with pytest.raises(ValueError, match="prononçable"):
        utils.genere_audio(str(p), str(tmp_path / "o"))

def test_retry_puis_succes(pdf_en, faux_tts, tmp_path):
    faux_tts.echecs = {"Hello everybody": 2}
    chemin = utils.genere_audio(pdf_en, str(tmp_path / "o"))
    assert os.path.getsize(chemin) > 0

def test_echec_definitif_garde_progres_puis_reprise(pdf_long, faux_tts, tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "TAILLE_MAX_MORCEAU", 100)
    monkeypatch.setattr(utils, "SEUIL_ECHECS_CONSECUTIFS", 10**6)  # désactive le disjoncteur ici
    s = str(tmp_path / "o")
    faux_tts.echecs = {"This is the English sentence number 030": -1}   # un morceau KO
    with pytest.raises(RuntimeError, match="Échec"):
        utils.genere_audio(pdf_long, s)
    assert not any(f.endswith(".mp3") and not f.startswith("part") for f in os.listdir(s)
                   if os.path.isfile(os.path.join(s, f)))             # pas de MP3 final
    travail = [d for d in os.listdir(s) if d.startswith(".travail_")]
    assert len(travail) == 1                                          # progrès conservés
    sauves = len([f for f in os.listdir(os.path.join(s, travail[0])) if f.endswith(".mp3")])
    assert sauves > 5

    # Le service "revient" : la reprise ne regénère QUE ce qui manque
    faux_tts.echecs = {}; faux_tts.appels.clear()
    chemin = utils.genere_audio(pdf_long, s)
    assert len(faux_tts.appels) < sauves + 5 and len(faux_tts.appels) >= 1
    txt = open(chemin).read()
    pos = [txt.index(f"number {i:03d}") for i in range(60)]
    assert pos == sorted(pos)                                         # intégralité + ordre
    assert not any(d.startswith(".travail_") for d in os.listdir(s))  # nettoyé

def test_disjoncteur_arrete_vite(pdf_long, faux_tts, tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "TAILLE_MAX_MORCEAU", 100)
    faux_tts.tout_echoue = True
    with pytest.raises(utils.ServiceIndisponible):
        utils.genere_audio(pdf_long, str(tmp_path / "o"))
    # sans disjoncteur : 30 morceaux x 6 essais = 180 appels ; ici on s'arrête vite
    assert len(faux_tts.appels) <= utils.SEUIL_ECHECS_CONSECUTIFS + utils.CONCURRENCE

def test_progression_monotone_et_complete(pdf_long, tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "TAILLE_MAX_MORCEAU", 100)
    vus = []
    utils.genere_audio(pdf_long, str(tmp_path / "o"), progression=lambda f, t: vus.append((f, t)))
    faits = [f for f, _ in vus]
    assert faits == sorted(faits) and vus[-1][0] == vus[-1][1] and vus[-1][1] > 5

def test_concurrence_respectee(pdf_long, tmp_path, monkeypatch):
    import asyncio
    monkeypatch.setattr(utils, "TAILLE_MAX_MORCEAU", 100)
    monkeypatch.setattr(utils, "CONCURRENCE", 2)
    actifs = {"n": 0, "max": 0}
    class Lent:
        def __init__(s, t, v): pass
        async def save(s, chemin):
            actifs["n"] += 1; actifs["max"] = max(actifs["max"], actifs["n"])
            await asyncio.sleep(0.01)
            open(chemin, "wb").write(b"x"); actifs["n"] -= 1
    monkeypatch.setattr(utils.edge_tts, "Communicate", Lent)
    utils.genere_audio(pdf_long, str(tmp_path / "o"))
    assert actifs["max"] == 2


def test_passe_de_rattrapage_recupere_une_partie_tetue(pdf_en, faux_tts, tmp_path, monkeypatch):
    # 8 échecs > 6 essais d'une passe : la 1re passe échoue, la 2e réussit
    monkeypatch.setattr(utils, "TENTATIVES", 6)
    faux_tts.echecs = {"Hello everybody": 8}
    chemin = utils.genere_audio(pdf_en, str(tmp_path / "o"))
    assert os.path.getsize(chemin) > 0 and faux_tts.echecs["Hello everybody"] == 0

def test_rattrapage_limite_par_passes(pdf_en, faux_tts, tmp_path, monkeypatch):
    monkeypatch.setattr(utils, "TENTATIVES", 2)
    monkeypatch.setattr(utils, "PASSES", 3)
    monkeypatch.setattr(utils, "SEUIL_ECHECS_CONSECUTIFS", 10**6)
    faux_tts.echecs = {"Hello everybody": -1}
    with pytest.raises(RuntimeError, match="Échec"):
        utils.genere_audio(pdf_en, str(tmp_path / "o"))
    assert len(faux_tts.appels) == 2 * 3     # 3 passes x 2 essais, pas de boucle infinie
