"""
Lumaroz Studio — video. Text-to-video and image-to-video on Google Veo
(3.1 → 3 → 2), with native sound on Veo 3. Plays in the HUD when done.
"""
from __future__ import annotations

PLUGIN = {
    "name": "create_video",
    "description": (
        "Generate a short AI video clip (about 8 seconds, with sound) with "
        "Lumaroz Studio. Use when the user asks to make, generate, animate or "
        "film a video, clip, animation, cinematic shot, or to 'bring this image "
        "to life'. To animate a picture use source='last' (your latest image), "
        "'file' (the uploaded one) or 'screen'. Write a vivid prompt: subject, "
        "action, camera movement, lighting, mood and any dialogue or sound. "
        "Rendering takes one to five minutes; say so, and the clip plays on "
        "screen by itself when it is ready. NOT for playing an existing video "
        "or YouTube — use the video player tools for that."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING", "description": "Detailed description of the clip."},
            "source": {"type": "STRING",
                       "description": "Optional starting image: 'last', 'file', 'screen' or a path."},
            "aspect_ratio": {"type": "STRING", "description": "'16:9' (default) or '9:16'."},
            "fast": {"type": "BOOLEAN", "description": "True for the quicker, cheaper model."},
            "avoid": {"type": "STRING", "description": "Optional things to keep out."},
        },
        "required": ["prompt"],
    },
}


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from plugins import _studio_common as sc
        from core import studio
    except Exception as e:
        return f"The Studio could not start: {e}"

    p = parameters or {}
    prompt = str(p.get("prompt") or "").strip()
    if not prompt:
        return "Tell me what the video should show."
    image = None
    if str(p.get("source") or "").strip():
        try:
            image = sc.resolve_image(str(p.get("source")), player)
        except studio.StudioError as e:
            return str(e)
        except Exception as e:
            return f"I couldn't read that image: {e}"

    def job():
        sc.log(player, f"directing — {prompt[:80]}")
        res = studio.generate_video(
            prompt, image, str(p.get("aspect_ratio") or "16:9"),
            fast=bool(p.get("fast")), negative=str(p.get("avoid") or ""),
            log=lambda m: sc.log(player, m), progress=lambda m: sc.log(player, m))
        path = res.paths[0]
        sc.log(player, f"saved {path.name} ({res.model})")
        if player is not None and hasattr(player, "show_video"):
            try:
                player.show_video(str(path), "Lumaroz Studio", muted=False)
            except TypeError:
                player.show_video(str(path), "Lumaroz Studio")
            except Exception as e:
                sc.log(player, f"could not play it: {e}")
        sc.say(player, "The video is ready and playing on screen.")

    busy = sc.background("video", player, job)
    return busy or ("Rolling camera — the video takes a minute or two to render. "
                    "I'll play it the moment it's done.")
