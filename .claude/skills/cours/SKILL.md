---
name: cours
description: Agent qui écoute un cours au micro du Mac, le transcrit en direct (Whisper, en local) et le restitue à la fin (résumé, plan, définitions, devoirs, questions de révision). À utiliser pour les commandes courtes « cours <matière> » (ex. « cours maths »), « fin cours », « cours statut », « cours fichier <chemin> », et aussi pour « écoute le cours », « fin du cours », « restitue le cours », ou pour transcrire un fichier audio/vidéo de cours.
argument-hint: "<matière> | fin | statut | fichier <chemin>"
---

## Commandes en deux mots

| Commande | Action |
|---|---|
| `cours maths` (ou `/cours maths`) | démarre l'écoute du cours de maths |
| `cours statut` | où en est l'écoute |
| `fin cours` (ou `/cours fin`) | arrête, transcrit la fin et restitue |
| `cours fichier <chemin>` | transcrit et restitue un enregistrement existant |

Règle : si le mot après « cours » n'est pas `fin`, `statut`, `fichier` ou `micros`, c'est le nom de la matière → démarrer. « cours » seul → démarrer avec la matière « cours », sans poser de question.

# Agent cours

Script : `.venv/bin/python .claude/skills/cours/scripts/cours.py` (à lancer depuis la racine du projet, le dossier qui contient `.claude/` et `.venv/`). Les cours sont rangés dans `cours/<date>_<matière>/` : `audio/`, `transcription.md`, puis `restitution.md`.

Choisis l'action d'après la demande (`$ARGUMENTS` ou la phrase de l'utilisateur) :

## Démarrer l'écoute — « démarrer <matière> », « écoute le cours de maths »
1. Lance `cours.py demarrer "<matière>"` (« cours » si aucune matière n'est donnée : ne pose pas de question). Option `--micro N` si l'utilisateur veut un autre micro (`cours.py micros` les liste).
2. L'écoute tourne en arrière-plan, même si la conversation est fermée, et empêche le Mac de se mettre en veille. Dis à l'utilisateur : c'est parti, garde le Mac ouvert et près du prof, dis « fin du cours » quand c'est terminé.
3. Si le script répond ÉCHEC (micro), transmets le message tel quel.

## Statut — « où en est le cours », « ça enregistre ? »
Lance `cours.py statut` et résume en 2-3 lignes. Si une ALERTE apparaît (silence, micro arrêté), dis-le clairement.

## Fin du cours et restitution — « fin du cours », « arrête », « restitue »
1. Lance `cours.py arreter` avec un délai de 10 minutes (Bash `timeout: 600000`) : il finit la transcription des dernières minutes. Note le dossier affiché.
2. Lance l'agent **restituteur-cours** (outil Agent, `subagent_type: "restituteur-cours"`) avec le chemin absolu du dossier.
3. Donne à l'utilisateur sa réponse : l'essentiel, les devoirs/dates, et des liens vers `restitution.md` et `transcription.md`.

## Transcrire un enregistrement existant — « fichier <chemin> », « transcris ce vocal / cette vidéo »
1. Lance `cours.py fichier "<chemin>" "<matière>"` (audio ou vidéo : mp3, m4a, wav, mp4, mov…). Compte environ 1 minute de calcul pour 2 minutes d'audio : au-delà de 15 minutes d'audio, lance-le en arrière-plan (`run_in_background`) et attends la notification.
2. Puis restitution avec l'agent **restituteur-cours**, comme ci-dessus.

## Bon à savoir (à dire seulement si c'est utile)
- Tout reste sur le Mac : le son et le texte ne sont envoyés nulle part pendant l'écoute ; seule la restitution est rédigée par Claude.
- Langue : français par défaut ; `--langue auto` ou `--langue en` pour un cours dans une autre langue.
- Plus rapide mais moins précis : variable d'environnement `COURS_MODELE=small`.
- Cours en ligne (Zoom, Teams, YouTube) : le micro capte le haut-parleur du Mac, ça marche mais mieux vaut enregistrer la séance puis utiliser « fichier ».
- Respecte les règles de l'établissement : demander l'accord du prof avant d'enregistrer.
