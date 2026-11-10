"""
Lumaroz Studio — speech. Studio-quality voice-overs and two-voice podcasts
with Gemini TTS, saved as WAV files.
"""
from __future__ import annotations

PLUGIN = {
    "name": "generate_speech",
    "description": (
        "Produce a voice-over AUDIO FILE with Lumaroz Studio's 30 studio "
        "voices — narration, an advert read, an audiobook passage, an "
        "announcement, or a two-person podcast/dialogue. Use when the user asks "
        "to record, narrate, voice, or make an audio/MP3/WAV of some text. "
        "For a dialogue write the script as lines 'Name: text' and give the two "
        "speakers' voices. Voices include Kore (firm), Puck (upbeat), Charon "
        "(informative), Zephyr (bright), Fenrir (excitable), Leda (youthful), "
        "Aoede (breezy), Enceladus (breathy), Algieba (smooth), Sulafat (warm). "
        "NOT for talking to the user — you already speak."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "text": {"type": "STRING", "description": "The words or the 'Name: line' script."},
            "voice": {"type": "STRING", "description": "Voice for a single narrator. Default Kore."},
            "direction": {"type": "STRING",
                          "description": "Performance note, e.g. 'Say cheerfully and fast'."},
            "speaker1": {"type": "STRING", "description": "Dialogue: first speaker's name."},
            "voice1": {"type": "STRING", "description": "Dialogue: first speaker's voice."},
            "speaker2": {"type": "STRING", "description": "Dialogue: second speaker's name."},
            "voice2": {"type": "STRING", "description": "Dialogue: second speaker's voice."},
            "open_after": {"type": "BOOLEAN", "description": "Open the file when done."},
        },
        "required": ["text"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from plugins import _studio_common as sc
        from core import studio
    except Exception as e:
        return f"The Studio could not start: {e}"

    p = parameters or {}
    text = str(p.get("text") or "").strip()
    if not text:
        return "Give me the words to record."
    speakers = None
    if p.get("speaker1") and p.get("speaker2"):
        speakers = {str(p["speaker1"]): str(p.get("voice1") or "Kore"),
                    str(p["speaker2"]): str(p.get("voice2") or "Puck")}

    def job():
        res = studio.generate_speech(text, str(p.get("voice") or "Kore"),
                                     str(p.get("direction") or ""), speakers,
                                     log=lambda m: sc.log(player, m))
        path = res.paths[0]
        sc.log(player, f"voice-over saved — {path}")
        if p.get("open_after"):
            _open(path)
        sc.say(player, f"The recording is saved in the Studio folder as {path.name}.")

    busy = sc.background("recording", player, job)
    return busy or "Recording it now — I'll tell you when the file is ready."


def _open(path) -> None:
    import subprocess
    import sys
    import os
    try:
        if sys.platform == "win32":
            os.startfile(str(path))                  # noqa: S606
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])
    except Exception as e:
        print(f"[Studio] could not open {path}: {e}")
