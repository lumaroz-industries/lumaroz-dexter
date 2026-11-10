"""
Lumaroz live wallpaper control — switch the animated background behind
Dexter's face between the painted 夜の牙 scene and any picture.
"""
from __future__ import annotations

PLUGIN = {
    "name": "live_wallpaper",
    "description": (
        "Change Dexter's own animated live wallpaper (the scene behind the face "
        "in this app — not the computer's desktop wallpaper). target='scene' "
        "returns to the Lumaroz Japanese night scene; 'last' uses the latest "
        "Studio image; 'file' uses the uploaded image; or a file path. To make "
        "a brand-new wallpaper, use create_image with as_wallpaper=true instead."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "target": {"type": "STRING", "description": "'scene', 'last', 'file' or a path."},
        },
        "required": ["target"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    if player is None or not hasattr(player, "set_wallpaper"):
        return "The wallpaper can only be changed from the desktop app."
    target = str((parameters or {}).get("target") or "scene").strip()
    if target.lower() in ("scene", "default", "japanese", "lumaroz", "reset"):
        player.set_wallpaper("")
        return "Back to the Lumaroz night scene."
    try:
        from core import studio
        from pathlib import Path
        if target.lower() in ("last", "latest", "that", "it"):
            path = studio.last_creation()
            if path is None:
                return "I haven't created any images yet."
        elif target.lower() in ("file", "uploaded", "upload"):
            cur = getattr(player, "current_file", None)
            if not cur:
                return "There's no image in the upload box."
            path = Path(cur)
        else:
            path = Path(target).expanduser()
        studio.read_image(path)            # validates it is a readable image
    except Exception as e:
        return str(e)
    player.set_wallpaper(str(path))
    return f"Done — {path.name} is now my live wallpaper."
