# VoceLibre – PDF / TXT → Audio (MP3)

## En local
    python3 -m venv venv && source venv/bin/activate
    pip install -U -r requirements.txt
    python3 app.py                # http://localhost:5000

## Avec Docker
    docker compose up --build     # http://localhost:5000

## Voix
Voix par défaut : français `fr-FR-HenriNeural`, anglais `en-US-ChristopherNeural`, etc.
Un nom de voix inexistant provoque « No audio was received » : l'application vérifie donc la
voix contre la liste officielle du service avant de convertir.

## Si la conversion échoue ("No audio was received", "Connection timeout")
    python3 diagnostic_tts.py     # dit si c'est le réseau, la concurrence ou la version
Réglages (variables d'environnement) :
- TTS_CONCURRENCE (défaut 2)  connexions simultanées ; mettre 1 si le service vous limite
- TTS_TENTATIVES  (défaut 6)  essais par partie, avec attente croissante 2s, 4s, 8s...
- TTS_PASSES      (défaut 4)  passes de rattrapage automatiques
- TTS_PAUSE_PASSE (défaut 10) pause entre passes (10s, 20s, 30s...)
Les parties déjà générées sont conservées (static/audio/.travail_*) :
relancer ou cliquer sur « Reprendre » ne refait que ce qui manque.

## Tests (sans réseau, le service vocal est simulé)
    pip install pytest reportlab
    python3 -m pytest tests -v

Note : un seul worker gunicorn est utilisé car l'état des tâches est en mémoire.
