"""
Lumaroz Studio — music. Instrumental tracks from a description with Google's
Lyria RealTime model, saved as WAV.
"""
from __future__ import annotations

PLUGIN = {
    "name": "compose_music",
    "description": (
        "Compose an original instrumental music track with Lumaroz Studio. Use "
        "when the user asks to make, compose or generate music, a beat, a "
        "soundtrack, background music or a jingle. Describe genre, instruments, "
        "mood and tempo, e.g. 'lo-fi hip hop, warm Rhodes piano, vinyl crackle, "
        "relaxed'. NOT for playing existing songs — use the media tools for that."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "description": {"type": "STRING", "description": "Genre, instruments, mood."},
            "seconds": {"type": "INTEGER", "description": "Length, 5-120. Default 30."},
            "bpm": {"type": "INTEGER", "description": "Optional tempo, 60-200."},
            "open_after": {"type": "BOOLEAN", "description": "Open the file when done."},
        },
        "required": ["description"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from plugins import _studio_common as sc
        from plugins.generate_speech import _open
        from core import studio
    except Exception as e:
        return f"The Studio could not start: {e}"

    p = parameters or {}
    desc = str(p.get("description") or "").strip()
    if not desc:
        return "Describe the music you'd like."
    try:
        seconds = int(p.get("seconds") or 30)
        bpm = int(p.get("bpm") or 0)
    except Exception:
        seconds, bpm = 30, 0

    def job():
        res = studio.compose_music(desc, seconds, bpm, log=lambda m: sc.log(player, m))
        path = res.paths[0]
        sc.log(player, f"track saved — {path}")
        if p.get("open_after"):
            _open(path)
        sc.say(player, f"The track is finished and saved in the Studio folder as {path.name}.")

    busy = sc.background("track", player, job)
    return busy or "Composing now — a track takes about as long as it plays. I'll let you know."
