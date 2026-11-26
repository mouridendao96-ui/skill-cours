#!/usr/bin/env python3
"""Agent « cours » : écoute un cours au micro, le transcrit en direct avec Whisper
(en local, rien ne sort du Mac) et prépare la transcription pour la restitution.

Commandes :
  demarrer <matière> [--micro N] [--langue fr]   lance l'écoute en arrière-plan
  statut                                        où en est l'écoute
  arreter                                       arrête et finit la transcription
  fichier <chemin> [matière]                    transcrit un audio/vidéo existant
  micros                                        liste les micros disponibles
"""
import argparse
import datetime as dt
import json
import os
import queue
import re
import signal
import subprocess
import sys
import time
import unicodedata
from pathlib import Path

RACINE = Path(__file__).resolve().parents[4]          # racine du projet (le dossier qui contient .claude/)
DOSSIER_COURS = RACINE / "cours"
ETAT = DOSSIER_COURS / ".en_cours.json"
PY = RACINE / ".venv" / "bin" / "python"
SEG_SECONDES = int(os.environ.get("COURS_SEG", "300"))  # un fichier audio toutes les 5 min
MODELE = os.environ.get("COURS_MODELE", "large-v3-turbo")
THREADS = int(os.environ.get("COURS_THREADS", "4"))

os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")


# ---------------------------------------------------------------- utilitaires
def slug(texte):
    t = unicodedata.normalize("NFKD", texte).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "-", t.lower()).strip("-") or "cours"


def hms(secondes):
    s = int(secondes)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def vivant(pid):
    try:
        os.kill(int(pid), 0)
        return True
    except (OSError, TypeError, ValueError):
        return False


def lire_json(p, defaut=None):
    try:
        return json.loads(Path(p).read_text())
    except (OSError, ValueError):
        return defaut


def ecrire_json(p, data):
    tmp = Path(str(p) + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1))
    tmp.replace(p)


def nouveau_dossier(matiere):
    d = DOSSIER_COURS / f"{dt.datetime.now():%Y-%m-%d_%Hh%M}_{slug(matiere)}"
    (d / "audio").mkdir(parents=True, exist_ok=True)
    return d


def charger_modele(nom):
    from faster_whisper import WhisperModel
    try:  # d'abord le modèle déjà téléchargé : marche sans internet en classe
        return WhisperModel(nom, device="cpu", compute_type="int8",
                            cpu_threads=THREADS, local_files_only=True)
    except Exception:
        return WhisperModel(nom, device="cpu", compute_type="int8", cpu_threads=THREADS)


def transcrire_audio(modele, chemin, langue, offset=0.0, prompt=None, progression=False):
    segs, info = modele.transcribe(
        str(chemin), language=None if langue == "auto" else langue,
        vad_filter=True, beam_size=1, initial_prompt=prompt or None,
        condition_on_previous_text=False)  # évite les boucles « je vous dis… je vous dis… »
    sortie, palier = [], 0.05
    for s in segs:
        texte = s.text.strip()
        if texte:
            sortie.append({"debut": round(offset + s.start, 2),
                           "fin": round(offset + s.end, 2), "texte": texte})
        if progression and info.duration and s.end / info.duration >= palier:
            print(f"  … {int(100 * s.end / info.duration)} % ({hms(s.end)} / {hms(info.duration)})",
                  flush=True)
            palier = s.end / info.duration + 0.05
    return sortie, info.duration


# ---------------------------------------------------------------- assemblage
def assembler(dossier, en_cours=False):
    dossier = Path(dossier)
    meta = lire_json(dossier / "meta.json", {})
    morceaux = []
    for j in sorted((dossier / "audio").glob("seg_*.json")):
        morceaux += lire_json(j, {}).get("segments", [])

    paragraphes, courant, debut_par, fin_prec = [], [], None, None
    for s in morceaux:
        coupure = courant and (s["debut"] - fin_prec > 2.5 or s["debut"] - debut_par > 60)
        if coupure:
            paragraphes.append((debut_par, " ".join(courant)))
            courant = []
        if not courant:
            debut_par = s["debut"]
        courant.append(s["texte"])
        fin_prec = s["fin"]
    if courant:
        paragraphes.append((debut_par, " ".join(courant)))

    duree = morceaux[-1]["fin"] if morceaux else 0
    mots = sum(len(t.split()) for _, t in paragraphes)
    lignes = [
        f"# Transcription — {meta.get('matiere', 'cours')}",
        "",
        f"Date : {meta.get('debut', '?')[:16].replace('T', ' à ')} · Durée transcrite : {hms(duree)} · {mots} mots",
        "",
        "> Transcription automatique (Whisper, en local) : certains mots peuvent être mal reconnus.",
    ]
    if en_cours:
        lignes += ["", "_(écoute en cours — la transcription se complète toutes les 5 minutes)_"]
    lignes.append("")
    for debut, texte in paragraphes:
        lignes += [f"**[{hms(debut)}]** {texte}", ""]
    (dossier / "transcription.md").write_text("\n".join(lignes))
    return duree, mots


def micro_integre_mac():
    """Choisit le micro intégré du Mac (jamais un micro Bluetooth, trop instable)."""
    import sounddevice as sd
    noms_integres = ("macbook", "built-in", "intégré")
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and any(n in d["name"].lower() for n in noms_integres):
            return i
    return sd.default.device[0]  # repli si aucun micro intégré trouvé


# ---------------------------------------------------------------- processus de fond
def proc_enregistrer(dossier, micro):
    import numpy as np
    import sounddevice as sd
    import soundfile as sf

    audio = Path(dossier) / "audio"
    (audio / ".pid").write_text(str(os.getpid()))
    dev = micro if micro is not None else micro_integre_mac()
    sr = int(sd.query_devices(dev, "input")["default_samplerate"])
    q, arret = queue.Queue(), {"stop": False}

    def stop(*_):
        arret["stop"] = True
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)

    def rappel(indata, frames, t, status):
        q.put(indata.copy())

    idx, ecrits, par_seg = 0, 0, sr * SEG_SECONDES
    ouvrir = lambda i: sf.SoundFile(str(audio / f"seg_{i:03d}.flac"), "w", sr, 1,
                                    format="FLAC", subtype="PCM_16")
    f = ouvrir(idx)
    crete, t_niveau = 0, time.time()
    with sd.InputStream(device=dev, samplerate=sr, channels=1, dtype="int16", callback=rappel):
        ecrire_json(audio / ".niveau", {"crete": 0, "maj": time.time(), "micro": sd.query_devices(dev)["name"]})
        while not arret["stop"]:
            try:
                bloc = q.get(timeout=0.5)
            except queue.Empty:
                continue
            f.write(bloc)
            ecrits += len(bloc)
            crete = max(crete, int(np.abs(bloc).max()))
            if time.time() - t_niveau > 5:
                ecrire_json(audio / ".niveau", {"crete": crete, "maj": time.time(),
                                                "micro": sd.query_devices(dev)["name"]})
                crete, t_niveau = 0, time.time()
            if ecrits >= par_seg:
                f.close()
                idx, ecrits = idx + 1, 0
                f = ouvrir(idx)
    while not q.empty():
        f.write(q.get())
    f.close()
    (audio / "FIN").write_text(dt.datetime.now().isoformat())


def proc_transcrire(dossier):
    import soundfile as sf

    dossier = Path(dossier)
    audio = dossier / "audio"
    meta = lire_json(dossier / "meta.json", {})
    modele = charger_modele(meta.get("modele", MODELE))
    while True:
        fichiers = sorted(audio.glob("seg_*.flac"))
        pid = (audio / ".pid").read_text() if (audio / ".pid").exists() else None
        fini = (audio / "FIN").exists() or (pid is not None and not vivant(pid))
        a_faire = [i for i, f in enumerate(fichiers)
                   if not f.with_suffix(".json").exists() and (i < len(fichiers) - 1 or fini)]
        if not a_faire:
            if fini:
                break
            time.sleep(10)
            continue
        for i in a_faire:
            f = fichiers[i]
            offset = sum(sf.info(str(p)).duration for p in fichiers[:i])
            prec = lire_json(fichiers[i - 1].with_suffix(".json"), {}) if i else {}
            prompt = " ".join(s["texte"] for s in prec.get("segments", []))[-200:]
            try:
                segs, _ = transcrire_audio(modele, f, meta.get("langue", "fr"), offset, prompt)
            except Exception as e:  # segment vide ou illisible : on continue
                print(f"segment {f.name} ignoré : {e}", flush=True)
                segs = []
            ecrire_json(f.with_suffix(".json"), {"fichier": f.name, "debut": offset, "segments": segs})
            assembler(dossier, en_cours=not fini)
    assembler(dossier)
    (audio / "TRANSCRIT").write_text(dt.datetime.now().isoformat())


# ---------------------------------------------------------------- commandes
def cmd_micros(_):
    import sounddevice as sd
    defaut = sd.default.device[0]
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0:
            print(f"{i}: {d['name']}{'  (par défaut)' if i == defaut else ''}")


def cmd_demarrer(a):
    etat = lire_json(ETAT)
    if etat and vivant(etat.get("pid_enregistrement")):
        sys.exit(f"Un cours est déjà en écoute : {etat['dossier']}\n"
                 f"Arrête-le d'abord avec : cours.py arreter")
    dossier = nouveau_dossier(a.matiere)
    ecrire_json(dossier / "meta.json", {"matiere": a.matiere, "debut": dt.datetime.now().isoformat(),
                                        "langue": a.langue, "modele": MODELE, "source": "micro"})
    journal = open(dossier / "journal.log", "a")
    cmd_enr = [str(PY), __file__, "_enregistrer", str(dossier)]
    if a.micro is not None:
        cmd_enr += ["--micro", str(a.micro)]
    enr = subprocess.Popen(cmd_enr, stdout=journal, stderr=journal, start_new_session=True)
    trans = subprocess.Popen([str(PY), __file__, "_transcrire", str(dossier)],
                             stdout=journal, stderr=journal, start_new_session=True)
    # empêche le Mac de se mettre en veille tant que l'écoute tourne
    subprocess.Popen(["caffeinate", "-i", "-w", str(enr.pid)], start_new_session=True)
    ecrire_json(ETAT, {"dossier": str(dossier), "pid_enregistrement": enr.pid,
                       "pid_transcription": trans.pid, "debut": time.time()})

    niveau = dossier / "audio" / ".niveau"
    for _ in range(40):  # jusqu'à 20 s pour ouvrir le micro
        if niveau.exists() or enr.poll() is not None:
            break
        time.sleep(0.5)
    if enr.poll() is not None or not niveau.exists():
        if enr.poll() is None:
            enr.terminate()
        trans.terminate()
        ETAT.unlink(missing_ok=True)
        sys.exit("ÉCHEC : le micro n'a pas pu s'ouvrir.\n"
                 "Vérifie Réglages Système › Confidentialité et sécurité › Micro : Claude doit être autorisé.\n"
                 f"Détails : {dossier / 'journal.log'}")
    print(f"ÉCOUTE DÉMARRÉE — {a.matiere}")
    print(f"Micro : {lire_json(niveau, {}).get('micro', '?')}")
    print(f"Dossier : {dossier}")
    print(f"Transcription en direct : {dossier / 'transcription.md'} (mise à jour toutes les 5 min)")


def cmd_statut(_):
    etat = lire_json(ETAT)
    if not etat:
        print("Aucun cours en écoute.")
        return
    dossier = Path(etat["dossier"])
    audio = dossier / "audio"
    meta = lire_json(dossier / "meta.json", {})
    niv = lire_json(audio / ".niveau", {})
    nb_audio = len(list(audio.glob("seg_*.flac")))
    nb_trans = len(list(audio.glob("seg_*.json")))
    print(f"Cours : {meta.get('matiere')} — écoute depuis {hms(time.time() - etat['debut'])}")
    print(f"Enregistrement : {'actif' if vivant(etat['pid_enregistrement']) else 'ARRÊTÉ'}"
          f" · micro : {niv.get('micro', '?')}")
    crete = niv.get("crete", 0)
    if time.time() - niv.get("maj", 0) > 30:
        print("ALERTE : le niveau du micro n'est plus mis à jour.")
    elif crete < 30:
        print(f"ALERTE : le micro ne capte que du silence (crête {crete}). Vérifie l'autorisation micro.")
    else:
        print(f"Niveau micro : OK (crête {crete})")
    print(f"Blocs de 5 min : {nb_audio} enregistrés, {nb_trans} transcrits")
    t = dossier / "transcription.md"
    if t.exists():
        derniers = [l for l in t.read_text().splitlines() if l.startswith("**[")][-3:]
        if derniers:
            print("Derniers passages :")
            print("\n".join(derniers))


def cmd_arreter(_):
    etat = lire_json(ETAT)
    if not etat:
        sys.exit("Aucun cours en écoute.")
    dossier = Path(etat["dossier"])
    audio = dossier / "audio"
    if vivant(etat["pid_enregistrement"]):
        os.kill(etat["pid_enregistrement"], signal.SIGTERM)
    for _ in range(30):
        if (audio / "FIN").exists() or not vivant(etat["pid_enregistrement"]):
            break
        time.sleep(0.5)
    # Heure de fin = arrêt de l'enregistrement (fichier FIN), pas la fin de la transcription.
    fin_enreg = (audio / "FIN").read_text().strip() if (audio / "FIN").exists() else dt.datetime.now().isoformat()
    meta = lire_json(dossier / "meta.json", {})
    meta["fin"] = fin_enreg
    ecrire_json(dossier / "meta.json", meta)
    print(f"Enregistrement arrêté après {hms(time.time() - etat['debut'])}. Fin de la transcription…", flush=True)
    t0 = time.time()
    while vivant(etat["pid_transcription"]):
        time.sleep(5)
        if time.time() - t0 > 30 and int(time.time() - t0) % 30 < 5:
            fait = len(list(audio.glob("seg_*.json")))
            total = len(list(audio.glob("seg_*.flac")))
            print(f"  … {fait}/{total} blocs transcrits", flush=True)
    if not (audio / "TRANSCRIT").exists():  # le transcripteur a planté : on finit ici
        proc_transcrire(dossier)
    duree, mots = assembler(dossier)
    ETAT.unlink(missing_ok=True)
    print(f"TRANSCRIPTION TERMINÉE — {hms(duree)}, {mots} mots")
    print(f"Dossier : {dossier}")
    print(f"Transcription : {dossier / 'transcription.md'}")


def cmd_fichier(a):
    source = Path(a.chemin).expanduser().resolve()
    if not source.exists():
        sys.exit(f"Fichier introuvable : {source}")
    matiere = a.matiere or source.stem
    dossier = nouveau_dossier(matiere)
    ecrire_json(dossier / "meta.json", {"matiere": matiere, "debut": dt.datetime.now().isoformat(),
                                        "langue": a.langue, "modele": MODELE, "source": str(source)})
    print(f"Transcription de {source.name} (modèle {MODELE})…", flush=True)
    modele = charger_modele(MODELE)
    segs, _ = transcrire_audio(modele, source, a.langue, progression=True)
    ecrire_json(dossier / "audio" / "seg_000.json", {"fichier": str(source), "debut": 0, "segments": segs})
    duree, mots = assembler(dossier)
    print(f"TRANSCRIPTION TERMINÉE — {hms(duree)}, {mots} mots")
    print(f"Dossier : {dossier}")
    print(f"Transcription : {dossier / 'transcription.md'}")


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sp = p.add_subparsers(dest="cmd", required=True)
    d = sp.add_parser("demarrer")
    d.add_argument("matiere")
    d.add_argument("--micro", type=int)
    d.add_argument("--langue", default="fr")
    sp.add_parser("statut")
    sp.add_parser("arreter")
    sp.add_parser("micros")
    f = sp.add_parser("fichier")
    f.add_argument("chemin")
    f.add_argument("matiere", nargs="?")
    f.add_argument("--langue", default="fr")
    e = sp.add_parser("_enregistrer")
    e.add_argument("dossier")
    e.add_argument("--micro", type=int)
    t = sp.add_parser("_transcrire")
    t.add_argument("dossier")
    a = p.parse_args()

    DOSSIER_COURS.mkdir(exist_ok=True)
    {"demarrer": cmd_demarrer, "statut": cmd_statut, "arreter": cmd_arreter,
     "micros": cmd_micros, "fichier": cmd_fichier,
     "_enregistrer": lambda a: proc_enregistrer(a.dossier, a.micro),
     "_transcrire": lambda a: proc_transcrire(a.dossier)}[a.cmd](a)


if __name__ == "__main__":
    main()
