---
name: cours
description: Agent qui écoute un cours au micro intégré de l'ordinateur (Mac, Windows ou Linux) ou au micro du téléphone (page web), le transcrit en direct (Whisper en local, ou reconnaissance vocale du téléphone) et le restitue à la fin (résumé, plan, définitions, devoirs, questions de révision). À utiliser pour les commandes courtes « cours <matière> » (ex. « cours maths »), « fin cours », « cours statut », « cours fichier <chemin> », « récupère le cours du téléphone », et aussi pour « écoute le cours », « fin du cours », « restitue le cours », ou pour transcrire un fichier audio/vidéo de cours.
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

Script : `.venv/bin/python .claude/skills/cours/scripts/cours.py` (Windows : `.venv\Scripts\python.exe` — le script le gère automatiquement) — à lancer depuis la racine du projet, le dossier qui contient `.claude/` et `.venv/`. Les cours sont rangés dans `cours/<date>_<matière>/` : `audio/`, `transcription.md`, puis `restitution.md`. Le micro intégré de l'ordinateur est toujours choisi par défaut (jamais un micro Bluetooth/sans fil, trop instable sur un enregistrement long).

Choisis l'action d'après la demande (`$ARGUMENTS` ou la phrase de l'utilisateur) :

## Démarrer l'écoute — « démarrer <matière> », « écoute le cours de maths »
1. Lance `cours.py demarrer "<matière>"` (« cours » si aucune matière n'est donnée : ne pose pas de question). Option `--micro N` si l'utilisateur veut un autre micro (`cours.py micros` les liste).
2. L'écoute tourne en arrière-plan, même si la conversation est fermée, et empêche l'ordinateur de se mettre en veille. Dis à l'utilisateur : c'est parti, garde l'ordinateur ouvert et près du prof, dis « fin du cours » quand c'est terminé.
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

## Enregistrer directement avec le téléphone (sans ordinateur allumé) — « cours sur le tel », « enregistre avec mon téléphone »
Une page web dédiée (artefact Claude, pas une appli) fait tout le travail sur le téléphone :
**https://claude.ai/artifact/WGNaNJqGwQ12fVRhkSW6jJ**
1. Dis à l'utilisateur d'ouvrir ce lien dans le navigateur du téléphone (Chrome sur Android ; Safari/Chrome sur iPhone, support plus limité), d'indiquer la matière dans le champ en haut, puis d'appuyer sur « Démarrer ». La page transcrit en direct avec la reconnaissance vocale du téléphone (rien à installer) et envoie chaque phrase transcrite dans la base de l'artefact au fur et à mesure — l'ordinateur peut rester éteint ou fermé pendant tout le cours.
2. Quand l'utilisateur appuie sur « Arrêter » sur le téléphone, la session est marquée terminée côté serveur.

## Récupérer un cours enregistré depuis le téléphone — « récupère le cours du téléphone », « synchronise »
1. Lis la collection `sessions` de cet artefact (outil ArtifactData, `action: "query"`, `url` ci-dessus, `collection: "sessions"`, `query.order_by: {field: "debut", direction: "desc"}`, `query.limit: 1`) pour trouver la dernière session (ou demande à l'utilisateur si plusieurs sont en attente). Note son `doc_id` et son champ `matiere`.
2. Lis toutes les lignes (`action: "list"`, `collection: "sessions/<doc_id>/lignes"`, `query.limit: 1000`) ; trie-les par `heure`.
3. Crée un dossier `cours/<date>_<matière>/` (même format que `nouveau_dossier` dans cours.py) et écris `transcription.md` à partir de ces lignes (même style que l'assemblage du script : titre, date, puis `**[heure]** texte` pour chaque ligne).
4. Lance l'agent **restituteur-cours** sur ce dossier, comme pour une écoute classique, puis donne la réponse à l'utilisateur.
5. Propose de supprimer la session de la base (`action: "delete"` sur chaque ligne puis sur la session) une fois la restitution récupérée, pour ne pas la relire par erreur la fois suivante — demande confirmation avant de supprimer.

## Démarrer ou arrêter l'écoute de l'ordinateur depuis le téléphone (en chat, pas la page web ci-dessus)
Le script `cours.py` tourne sur l'ordinateur (c'est lui qui a le micro), mais les commandes « cours maths », « fin du cours », « cours statut » peuvent être envoyées depuis le téléphone : active le Remote Control de Claude Code sur cette session, puis depuis l'app mobile Claude envoie les mêmes commandes — elles s'exécutent sur l'ordinateur resté ouvert près du prof. Rien à faire côté script. (Contrairement à la page web ci-dessus, cette méthode exige que l'ordinateur reste allumé.)

## Bon à savoir (à dire seulement si c'est utile)
- Tout reste sur l'ordinateur : le son et le texte ne sont envoyés nulle part pendant l'écoute ; seule la restitution est rédigée par Claude.
- Compatible Mac, Windows et Linux ; le micro intégré est toujours préféré à un micro Bluetooth/sans fil.
- Langue : français par défaut ; `--langue auto` ou `--langue en` pour un cours dans une autre langue.
- Plus rapide mais moins précis : variable d'environnement `COURS_MODELE=small`.
- Cours en ligne (Zoom, Teams, YouTube) : le micro capte le haut-parleur de l'ordinateur, ça marche mais mieux vaut enregistrer la séance puis utiliser « fichier ».
- Respecte les règles de l'établissement : demander l'accord du prof avant d'enregistrer.
