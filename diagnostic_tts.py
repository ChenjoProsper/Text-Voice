"""Diagnostic edge-tts :  python3 diagnostic_tts.py
Dit si le problème vient du réseau, de la voix, de la concurrence ou de la version."""
import asyncio, os, sys, tempfile, time
from importlib.metadata import version

import edge_tts
import utils

PHRASE = "Bonjour, ceci est un court test de synthèse vocale."


async def un_essai(texte, voix, nom):
    chemin = os.path.join(tempfile.gettempdir(), f"diag_{nom}.mp3")
    t0 = time.time()
    try:
        await asyncio.wait_for(edge_tts.Communicate(texte, voix).save(chemin), 40)
        return True, f"OK ({os.path.getsize(chemin)} octets, {time.time()-t0:.1f}s)"
    except Exception as e:
        return False, f"ECHEC : {type(e).__name__}: {str(e)[:100]}"


async def main():
    print(f"edge-tts {version('edge-tts')} | python {sys.version.split()[0]}")

    print("\n[0] Liste officielle des voix (test du réseau)")
    try:
        voix = await asyncio.wait_for(edge_tts.list_voices(), 25)
        fr = sorted(v["ShortName"] for v in voix if v["Locale"].startswith("fr-FR"))
        print(f"    OK : {len(voix)} voix. Voix fr-FR disponibles : {', '.join(fr[:8])}")
    except Exception as e:
        print(f"    ECHEC : {type(e).__name__}: {str(e)[:100]}")
        print("\n=== Conclusion ===\nLe service est injoignable depuis cette machine (internet, pare-feu,")
        print("proxy, VPN, DNS, heure du PC erronée). Ce n'est pas un problème de code.")
        return

    choisie = utils.choisir_voix("fr", voix)
    print(f"\n[1] Une requête avec la voix choisie par l'application : {choisie}")
    ok1, msg = await un_essai(PHRASE, choisie, "1"); print("   ", msg)

    print("\n[2] Deux requêtes en parallèle (réglage par défaut)")
    r = await asyncio.gather(*[un_essai(PHRASE, choisie, f"2_{i}") for i in range(2)])
    for _, m in r: print("   ", m)
    ok2 = all(ok for ok, _ in r)

    print("\n[3] Cinq requêtes en parallèle")
    r = await asyncio.gather(*[un_essai(PHRASE, choisie, f"3_{i}") for i in range(5)])
    for _, m in r: print("   ", m)
    ok3 = all(ok for ok, _ in r)

    print("\n=== Conclusion ===")
    if not ok1:
        print("Le réseau marche (liste des voix OK) mais la synthèse échoue : version d'edge-tts")
        print("périmée (pip install -U edge-tts) ou service temporairement refusé.")
    elif not ok2:
        print("1 requête passe mais pas 2 : lancez l'app avec  TTS_CONCURRENCE=1")
    elif not ok3:
        print("2 passent, 5 échouent : gardez TTS_CONCURRENCE=2 (défaut) ou 1.")
    else:
        print("Tout fonctionne. Vous pouvez convertir vos documents.")

asyncio.run(main())
