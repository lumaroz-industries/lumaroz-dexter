"""
Lumaroz Studio — images. Text-to-image and image editing on Google's image
models (Gemini native image, then Imagen 4). Results open full-size in the
Studio view and are saved to the Studio folder.
"""
from __future__ import annotations

PLUGIN = {
    "name": "create_image",
    "description": (
        "Create or edit images with Lumaroz Studio. Use whenever the user asks "
        "to draw, generate, imagine, design, paint, render or make a picture, "
        "logo, poster, wallpaper, thumbnail, sticker, icon or illustration — or "
        "to CHANGE an image: edit, restyle, recolour, remove or add something, "
        "change the background, combine photos, make a variation, or 'make it "
        "more X'. For edits, source='last' is the image you made most recently, "
        "'file' is the one the user uploaded, 'screen' is a screenshot. "
        "Rewrite the user's idea into a rich, specific visual prompt (subject, "
        "setting, lighting, composition, style) before calling. The picture "
        "appears on screen by itself; just say you're on it. If the user asks "
        "for a new wallpaper/background for you, set as_wallpaper=true."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "prompt": {"type": "STRING",
                       "description": "Detailed description of the image, or the edit to make."},
            "mode": {"type": "STRING",
                     "description": "'generate' (new image) or 'edit' (change an existing one). Default generate."},
            "source": {"type": "STRING",
                       "description": "For edit: 'last', 'file', 'screen' or a file path."},
            "aspect_ratio": {"type": "STRING",
                             "description": "1:1, 16:9, 9:16, 4:3, 3:4, 3:2, 2:3, 21:9. Default 1:1."},
            "count": {"type": "INTEGER", "description": "How many images, 1-4. Default 1."},
            "quality": {"type": "STRING",
                        "description": "'standard', 'fast', 'photo' (photorealistic) or 'ultra'. Default standard."},
            "style": {"type": "STRING",
                      "description": "Optional art style, e.g. 'cinematic', 'anime', 'watercolor', '3D render'."},
            "avoid": {"type": "STRING", "description": "Optional things to keep out of the image."},
            "as_wallpaper": {"type": "BOOLEAN",
                             "description": "True when the user wants it as Dexter's animated live wallpaper (forces 16:9)."},
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
        return "Tell me what you'd like me to create."
    mode = str(p.get("mode") or "generate").strip().lower()
    ar = str(p.get("aspect_ratio") or "1:1").strip()
    try:
        count = int(p.get("count") or 1)
    except Exception:
        count = 1
    quality = str(p.get("quality") or "standard").strip().lower()
    style = str(p.get("style") or "")
    avoid = str(p.get("avoid") or "")
    source = str(p.get("source") or "")
    as_wallpaper = bool(p.get("as_wallpaper"))
    if as_wallpaper:
        ar, count = "16:9", 1

    if mode == "edit":
        try:
            image = sc.resolve_image(source, player)
        except studio.StudioError as e:
            return str(e)
        except Exception as e:
            return f"I couldn't read that image: {e}"

        def job():
            sc.log(player, f"editing — {prompt[:80]}")
            res = studio.edit_image(prompt, [image], ar if p.get("aspect_ratio") else "")
            for path in res.paths:
                sc.show_image(player, path, "Edited", prompt)
            sc.log(player, f"saved {res.paths[0].name} ({res.model})")
            sc.say(player, "The edited image is ready and on screen in the Studio.")

        busy = sc.background("image edit", player, job)
        return busy or "Editing it now — it'll appear in the Studio in a few seconds."

    def job():
        sc.log(player, f"imagining — {prompt[:80]}")
        res = studio.generate_image(prompt, ar, count, quality, style, avoid,
                                    log=lambda m: sc.log(player, m))
        if as_wallpaper:
            if player is not None and hasattr(player, "set_wallpaper"):
                player.set_wallpaper(str(res.paths[0]))
            sc.log(player, f"live wallpaper set — {res.paths[0].name} ({res.model})")
            sc.say(player, "The new live wallpaper is in place behind you.")
            return
        for i, path in enumerate(res.paths):
            title = "Creation" if len(res.paths) == 1 else f"Creation {i + 1}/{len(res.paths)}"
            sc.show_image(player, path, title, prompt)
        sc.log(player, f"saved {len(res.paths)} image(s) to {res.paths[0].parent} ({res.model})")
        n = len(res.paths)
        sc.say(player, f"{'The image is' if n == 1 else f'All {n} images are'} ready "
                       "and on screen in the Studio.")

    busy = sc.background("image", player, job)
    return busy or "On it — creating that now. It'll appear in the Studio in a few seconds."
