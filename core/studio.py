"""
Lumaroz Studio — Dexter's creative engine.

Everything Google AI Studio can make, behind one module, so a plugin asks for
"a picture of X" and never deals with model names, polling or file formats:

    generate_image   text → image(s)        Gemini native image, then Imagen 4
    edit_image       image(s) + words → image   Gemini native image editing,
                                                 multi-image composition
    generate_video   text / image → video   Veo 3.1 → Veo 3 → Veo 2
    generate_speech  text → voice-over      Gemini TTS, one or two speakers
    compose_music    words → music          Lyria RealTime
    research         question → grounded answer
                     Google Search, Google Maps, URL context, code execution,
                     dynamic thinking — with sources

THE LADDERS
    Same idea as core.gemini: each capability has an ordered list of models.
    A model that answers 429 rests for five minutes, one that is missing or not
    available to this key rests for six hours, one that is overloaded rests for
    thirty — and the next rung answers. Model names can be overridden without
    touching code by putting a list under `studio_models` in
    config/api_keys.json, e.g. {"studio_models": {"image": ["my-model"]}}.

    An error that is about the REQUEST (blocked by safety filters, an invalid
    argument) stops the ladder at once and is reported in plain words, because
    asking five more models the same forbidden question only wastes a minute.

FILES
    Everything made is saved to the Studio folder (~/Pictures/Lumaroz by
    default; `studio_dir` in the config overrides it) with a .txt beside it
    holding the prompt, which is what the Studio gallery shows as the caption.

Nothing here touches Qt. Every public function is synchronous and may take a
while — plugins run them on their own thread.
"""
from __future__ import annotations

import asyncio
import base64
import io
import json
import mimetypes
import re
import sys
import time
import wave
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Iterable, Optional

from core import gemini

# ── models ───────────────────────────────────────────────────────────────────
_LADDERS: dict[str, tuple[str, ...]] = {
    # Gemini native image models: generate AND edit, understand long prompts,
    # render text well, keep a character consistent across edits.
    # Cheapest first: 2.5 Flash Image is the one with free-tier allowance;
    # the Pro image model is billing-only and is tried last.
    "image": ("gemini-2.5-flash-image",
              "gemini-2.5-flash-image-preview",
              "gemini-3-pro-image-preview"),
    # Imagen: pure text-to-image, photographic quality, several at once.
    "imagen": ("imagen-4.0-generate-001",
               "imagen-4.0-fast-generate-001",
               "imagen-4.0-ultra-generate-001",
               "imagen-3.0-generate-002"),
    "imagen_ultra": ("imagen-4.0-ultra-generate-001",
                     "imagen-4.0-generate-001"),
    "imagen_fast": ("imagen-4.0-fast-generate-001",
                    "imagen-4.0-generate-001"),
    "video": ("veo-3.1-generate-preview",
              "veo-3.1-fast-generate-preview",
              "veo-3.0-generate-001",
              "veo-3.0-fast-generate-001",
              "veo-2.0-generate-001"),
    "video_fast": ("veo-3.1-fast-generate-preview",
                   "veo-3.0-fast-generate-001",
                   "veo-3.1-generate-preview",
                   "veo-2.0-generate-001"),
    "tts": ("gemini-2.5-flash-preview-tts",
            "gemini-2.5-pro-preview-tts"),
    "music": ("models/lyria-realtime-exp",),
    "research": ("gemini-3.5-pro", "gemini-3-pro-preview", "gemini-2.5-pro",
                 "gemini-3.5-flash", "gemini-2.5-flash", "gemini-flash-latest"),
}

ASPECT_RATIOS = ("1:1", "2:3", "3:2", "3:4", "4:3", "4:5", "5:4",
                 "9:16", "16:9", "21:9")
IMAGEN_RATIOS = ("1:1", "3:4", "4:3", "9:16", "16:9")
VIDEO_RATIOS = ("16:9", "9:16")

# Prebuilt Gemini voices, as listed in AI Studio's speech playground.
VOICES = ("Zephyr", "Puck", "Charon", "Kore", "Fenrir", "Leda", "Orus", "Aoede",
          "Callirrhoe", "Autonoe", "Enceladus", "Iapetus", "Umbriel", "Algieba",
          "Despina", "Erinome", "Algenib", "Rasalgethi", "Laomedeia", "Achernar",
          "Alnilam", "Schedar", "Gacrux", "Pulcherrima", "Achird",
          "Zubenelgenubi", "Vindemiatrix", "Sadachbia", "Sadaltager", "Sulafat")


class StudioError(Exception):
    """A failure worth saying out loud. The message is user-facing."""


@dataclass
class Creation:
    paths: list[Path] = field(default_factory=list)
    model: str = ""
    text: str = ""                      # anything the model said alongside


@dataclass
class Answer:
    text: str = ""
    sources: list[tuple[str, str]] = field(default_factory=list)   # (title, uri)
    code: list[str] = field(default_factory=list)
    code_output: list[str] = field(default_factory=list)
    images: list[Path] = field(default_factory=list)
    queries: list[str] = field(default_factory=list)
    model: str = ""


# ── configuration ────────────────────────────────────────────────────────────
def _config() -> dict:
    try:
        from memory.config_manager import load_api_keys
        return load_api_keys() or {}
    except Exception:
        try:
            return json.loads(gemini._KEY_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}


def ladder(kind: str) -> tuple[str, ...]:
    override = (_config().get("studio_models") or {}).get(kind)
    if isinstance(override, (list, tuple)) and override:
        return tuple(str(m) for m in override)
    return _LADDERS[kind]


def output_dir() -> Path:
    """Where creations are saved. Created on demand; never raises."""
    custom = str(_config().get("studio_dir") or "").strip()
    candidates = []
    if custom:
        candidates.append(Path(custom).expanduser())
    pics = Path.home() / "Pictures"
    candidates += [pics / "Lumaroz", Path.home() / "Lumaroz"]
    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            continue
    return Path.cwd()


def _slug(text: str, n: int = 40) -> str:
    s = re.sub(r"[^a-zA-Z0-9]+", "_", text or "").strip("_").lower()
    return (s[:n].rstrip("_") or "creation")


def _save(data: bytes, prompt: str, ext: str, model: str, kind: str) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    base = output_dir() / f"{stamp}_{_slug(prompt)}"
    path = base.with_suffix(ext)
    i = 2
    while path.exists():
        path = Path(f"{base}_{i}{ext}")
        i += 1
    path.write_bytes(data)
    try:
        path.with_suffix(".txt").write_text(
            f"{prompt}\n\n— {kind} · Lumaroz Studio", encoding="utf-8")
    except Exception:
        pass
    return path


def _ext_for(mime: str) -> str:
    return {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp",
            "video/mp4": ".mp4", "audio/wav": ".wav"}.get(
        (mime or "").lower(), mimetypes.guess_extension(mime or "") or ".bin")


def last_creation(kinds: Iterable[str] = (".png", ".jpg", ".jpeg", ".webp")) -> Optional[Path]:
    """The newest file in the Studio folder with one of these extensions."""
    try:
        files = [f for f in output_dir().iterdir() if f.suffix.lower() in kinds]
        return max(files, key=lambda f: f.stat().st_mtime) if files else None
    except Exception:
        return None


def read_image(path: str | Path) -> tuple[bytes, str]:
    p = Path(path).expanduser()
    if not p.is_file():
        raise StudioError(f"I can't find the image {p.name}.")
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    if not mime.startswith("image/"):
        raise StudioError(f"{p.name} is not an image.")
    return p.read_bytes(), mime


def screenshot() -> tuple[bytes, str]:
    """The primary screen as PNG bytes."""
    try:
        import mss
        import mss.tools
        with mss.mss() as sct:
            shot = sct.grab(sct.monitors[1])
            return mss.tools.to_png(shot.rgb, shot.size), "image/png"
    except Exception as e:
        raise StudioError(f"I couldn't capture the screen: {e}")


# ── the ladder runner ────────────────────────────────────────────────────────
def _request_error(err: str) -> Optional[str]:
    """A user-facing sentence if the error is about the request itself."""
    low = err.lower()
    if any(k in low for k in ("safety", "blocked", "prohibited", "responsible ai",
                              "violat", "raimediafiltered", "filtered")):
        return ("Google's safety filters declined that request. "
                "Try rephrasing it.")
    if "api key not valid" in low or "api_key_invalid" in low:
        return "The Google API key was rejected. Check it in Setup."
    if "billing" in low or "requires a paid" in low or "only available on paid" in low:
        return None   # treat like "gone": a different model may be on the free tier
    if "invalid_argument" in low or " 400" in err or err.startswith("400"):
        return None   # often a model-specific field; let the next rung try
    return None


def _not_on_free_tier(err: str) -> bool:
    low = err.lower().replace(" ", "")
    return "limit:0" in low or "limit\":0" in low or "free_tier" in low and "limit" in low


def _run_ladder(kind: str, attempt: Callable[[str], object],
                log: Callable[[str], None] = print):
    """Call attempt(model) down the ladder until one returns."""
    errors: list[str] = []
    models = [m for m in ladder(kind) if not gemini._cooling(m)] or list(ladder(kind))
    for model in models:
        try:
            out = attempt(model)
            return model, out
        except StudioError:
            raise
        except Exception as e:                       # noqa: BLE001
            err = f"{type(e).__name__}: {e}"
            errors.append(f"{model}: {err[:160]}")
            log(f"[Studio] {model} failed — {err[:200]}")
            said = _request_error(err)
            if said:
                raise StudioError(said)
            if gemini.is_quota_error(err) and _not_on_free_tier(err):
                # 429 with "limit: 0": the free tier does not include this model
                # at all. It will not recover in five minutes — rest it for hours.
                gemini._cool(model, gemini._GONE_SECONDS)
            elif gemini.is_quota_error(err):
                gemini._cool(model, gemini._COOLDOWN_SECONDS)
            elif gemini.is_gone_error(err) or "billing" in err.lower() or "paid" in err.lower():
                gemini._cool(model, gemini._GONE_SECONDS)
            elif gemini.is_unavailable_error(err):
                gemini._cool(model, gemini._UNAVAILABLE_SECONDS)
    if errors and all(gemini.is_quota_error(e) for e in errors):
        raise StudioError("Every model for that is out of quota right now. "
                          "Try again in a few minutes.")
    raise StudioError("None of Google's models could do that just now"
                      + (f" ({errors[-1][:120]})" if errors else "."))


def _client(timeout_ms: int, api_version: str = ""):
    from google import genai
    from google.genai import types
    key = gemini.api_key()
    if not key:
        raise StudioError("No Google API key is set. Add one in Setup.")
    opts = dict(timeout=max(gemini.MIN_TIMEOUT_MS, int(timeout_ms)))
    if api_version:
        opts["api_version"] = api_version
    return genai.Client(api_key=key, http_options=types.HttpOptions(**opts))


def _parts(resp) -> list:
    try:
        return list(resp.candidates[0].content.parts or [])
    except Exception:
        return []


def _finish_reason(resp) -> str:
    try:
        return str(resp.candidates[0].finish_reason or "")
    except Exception:
        try:
            return str(resp.prompt_feedback.block_reason or "")
        except Exception:
            return ""


# ── the free, keyless image fallback ─────────────────────────────────────────
#
# Google's image models are rate-limited, and on a free key they may allow few
# requests a day or none at all. So when Google cannot make the picture, Dexter
# makes it with Pollinations — a free public text-to-image service that needs
# no account and no key — rather than answering "out of quota".
#
# `studio_image_source` in config/api_keys.json chooses:
#     "auto"    Google first, the free generator when Google can't (default)
#     "free"    always the free generator — never spends any Google quota
#     "google"  Google only; never send a prompt anywhere else
#
# Privacy: in "auto" and "free" the prompt text is sent to pollinations.ai.
FREE_IMAGE_URL = "https://image.pollinations.ai/prompt/{prompt}"
FREE_MODEL_TAG = "pollinations (free)"

_AR_SIZES = {"1:1": (1024, 1024), "16:9": (1344, 768), "9:16": (768, 1344),
             "4:3": (1152, 864), "3:4": (864, 1152), "3:2": (1216, 832),
             "2:3": (832, 1216), "4:5": (896, 1120), "5:4": (1120, 896),
             "21:9": (1536, 640)}


def image_source() -> str:
    v = str(_config().get("studio_image_source", "auto") or "auto").lower()
    return v if v in ("auto", "free", "google") else "auto"


_free_lock = __import__("threading").Lock()
_free_last = 0.0
FREE_SPACING_S = 46          # anonymous limit: 1 image / 45 s per IP


def _free_images(prompt: str, aspect_ratio: str, count: int,
                 log: Callable[[str], None] = print) -> list[tuple[bytes, str]]:
    """Make images on Pollinations. Anonymous use is limited to one image
    every 45 seconds per IP (it answers 402 FREE_LIMIT "Retry after Ns"), so
    requests are spaced and a refusal waits the time it names. A free key from
    enter.pollinations.ai (`pollinations_key` in the config) lifts the limit
    and removes the watermark."""
    global _free_last
    import random
    from urllib.parse import quote
    import requests
    key = str(_config().get("pollinations_key") or "").strip()
    w, h = _AR_SIZES.get(aspect_ratio, (1024, 1024))
    if not key and count > 1:
        log("[Studio] free generator without a key makes one image at a time "
            f"(45 s apart) — making 1 of {count}.")
        count = 1
    headers = {"User-Agent": "Lumaroz-Dexter/1.0"}
    if key:
        headers["Authorization"] = f"Bearer {key}"
    out = []
    for _ in range(count):
        url = FREE_IMAGE_URL.format(prompt=quote(prompt[:1500], safe=""))
        params = {"width": w, "height": h, "seed": random.randint(1, 2**31 - 1),
                  "model": "flux", "enhance": "true"}
        if key:
            params["nologo"] = "true"
        last = ""
        for attempt in range(4):
            with _free_lock:                         # one request at a time
                if not key:
                    wait = FREE_SPACING_S - (time.monotonic() - _free_last)
                    if wait > 0:
                        log(f"[Studio] free generator: waiting {wait:.0f}s for its rate limit…")
                        time.sleep(wait)
                try:
                    r = requests.get(url, params=params, timeout=180, headers=headers)
                except Exception as e:                # noqa: BLE001
                    r, last = None, f"{type(e).__name__}: {e}"
                _free_last = time.monotonic()
            if r is not None:
                ctype = r.headers.get("content-type", "")
                if r.status_code == 200 and ctype.startswith("image/") and len(r.content) > 2048:
                    out.append((r.content, ctype.split(";")[0]))
                    break
                body = r.text[:400] if "json" in ctype or "text" in ctype else ""
                last = f"HTTP {r.status_code} {body}".strip()
                if r.status_code in (400, 401, 403):
                    break
            m = re.search(r"retry after (\d+)\s*s", last, re.I)
            pause = min(60, int(m.group(1)) + 1) if m else (10 * (attempt + 1))
            log(f"[Studio] free generator busy ({last[:90]}) — retrying in {pause}s")
            time.sleep(pause)
            _free_last = 0.0 if m else _free_last    # the wait above already covered it
    if not out:
        raise StudioError("The free image generator is busy right now — "
                          "try again in a minute.")
    return out


# ── images ───────────────────────────────────────────────────────────────────
def _style_prompt(prompt: str, style: str, negative: str) -> str:
    out = prompt.strip()
    if style:
        out += f"\n\nStyle: {style.strip()}."
    if negative:
        out += f"\nAvoid: {negative.strip()}."
    return out


def _gemini_image(model: str, contents: list, aspect_ratio: str, size: str):
    from google.genai import types
    img_cfg = {}
    if aspect_ratio in ASPECT_RATIOS:
        img_cfg["aspect_ratio"] = aspect_ratio
    if size and "pro" in model:
        img_cfg["image_size"] = size           # "1K" | "2K" | "4K" on Pro
    cfg = types.GenerateContentConfig(
        response_modalities=["TEXT", "IMAGE"],
        image_config=types.ImageConfig(**img_cfg) if img_cfg else None,
    )
    client = _client(180_000)       # keep a reference: a dropped Client closes itself
    resp = client.models.generate_content(model=model, contents=contents, config=cfg)
    images, words = [], []
    for part in _parts(resp):
        blob = getattr(part, "inline_data", None)
        if blob is not None and getattr(blob, "data", None):
            data = blob.data
            if isinstance(data, str):
                data = base64.b64decode(data)
            images.append((data, blob.mime_type or "image/png"))
        elif getattr(part, "text", None) and not getattr(part, "thought", False):
            words.append(part.text)
    if not images:
        reason = _finish_reason(resp)
        said = " ".join(words).strip()
        if "SAFETY" in reason or "PROHIBITED" in reason or "IMAGE_SAFETY" in reason:
            raise StudioError("Google's safety filters declined that image. "
                              "Try rephrasing it.")
        raise RuntimeError(f"no image returned ({reason}) {said[:120]}")
    return images, " ".join(words).strip()


def generate_image(prompt: str, aspect_ratio: str = "1:1", count: int = 1,
                   quality: str = "standard", style: str = "", negative: str = "",
                   log: Callable[[str], None] = print) -> Creation:
    """Text → image. `quality`: fast | standard | ultra | photo.

    'photo' and 'ultra' lead with Imagen (photographic, several at once);
    everything else leads with Gemini native image (best prompt-following and
    text rendering) and falls back to Imagen."""
    from google.genai import types
    prompt = (prompt or "").strip()
    if not prompt:
        raise StudioError("Tell me what to create.")
    count = max(1, min(4, int(count or 1)))
    if quality in ("photo", "ultra") and not style:
        style = ("photorealistic, shot on a full-frame camera, natural light, "
                 "fine detail, shallow depth of field")
    full = _style_prompt(prompt, style, negative)

    def via_gemini(model):
        out = []
        words = ""
        for _ in range(count):
            imgs, words = _gemini_image(model, [full], aspect_ratio,
                                        "2K" if quality in ("ultra", "photo") else "")
            out += imgs
        return out[:count], words

    def via_imagen(model):
        ar = aspect_ratio if aspect_ratio in IMAGEN_RATIOS else "1:1"
        cfg = dict(number_of_images=count, aspect_ratio=ar)
        if negative and "imagen-3" in model:
            cfg["negative_prompt"] = negative
        client = _client(180_000)
        resp = client.models.generate_images(
            model=model, prompt=_style_prompt(prompt, style, "" if "imagen-3" in model else negative),
            config=types.GenerateImagesConfig(**cfg))
        imgs = [(g.image.image_bytes, g.image.mime_type or "image/png")
                for g in (resp.generated_images or []) if g.image and g.image.image_bytes]
        if not imgs:
            raise StudioError("Google's safety filters declined that image. "
                              "Try rephrasing it.")
        return imgs, ""

    # Imagen: the google-genai SDK refuses generate_images with an AI Studio
    # key ("only supported in ... Enterprise Agent Platform mode"), so it is
    # offered only when the config says the key is a Vertex one.
    imagen_kind = {"ultra": "imagen_ultra", "fast": "imagen_fast"}.get(quality, "imagen")
    order = [("image", via_gemini)]
    if _config().get("studio_vertex"):
        order = ([(imagen_kind, via_imagen)] + order if quality in ("ultra", "photo")
                 else order + [(imagen_kind, via_imagen)])

    def via_free():
        imgs = _free_images(full, aspect_ratio, count, log)
        paths = [_save(d, prompt, _ext_for(m), FREE_MODEL_TAG, "image · free generator")
                 for d, m in imgs]
        return Creation(paths=paths, model=FREE_MODEL_TAG)

    source = image_source()
    if source == "free" or (source == "auto" and not gemini.api_key()):
        return via_free()

    last_err: Optional[StudioError] = None
    for kind, fn in order:
        try:
            model, (imgs, words) = _run_ladder(kind, fn, log)
            paths = [_save(d, prompt, _ext_for(m), model, "image") for d, m in imgs]
            return Creation(paths=paths, model=model, text=words)
        except StudioError as e:
            if "safety" in str(e).lower():
                raise                      # never route around a safety refusal
            if "api key" in str(e).lower() and source == "google":
                raise
            last_err = e
    if source == "auto":
        log(f"[Studio] Google could not make it ({last_err}) — using the free generator.")
        return via_free()
    raise last_err or StudioError("I couldn't create that image.")


def edit_image(instruction: str, images: list[tuple[bytes, str]],
               aspect_ratio: str = "", log: Callable[[str], None] = print) -> Creation:
    """Image(s) + instruction → new image. One image edits it; several are
    composed ("put the dog from the first photo on the beach in the second")."""
    from google.genai import types
    instruction = (instruction or "").strip()
    if not instruction:
        raise StudioError("Tell me how to change the image.")
    if not images:
        raise StudioError("I need an image to edit — drop one in, or make one first.")
    contents = [types.Part.from_bytes(data=d, mime_type=m) for d, m in images[:3]]
    contents.append(instruction)

    def attempt(model):
        return _gemini_image(model, contents, aspect_ratio, "")

    model, (imgs, words) = _run_ladder("image", attempt, log)
    paths = [_save(d, f"edit: {instruction}", _ext_for(m), model, "edit") for d, m in imgs]
    return Creation(paths=paths, model=model, text=words)


# ── video ────────────────────────────────────────────────────────────────────
def generate_video(prompt: str, image: Optional[tuple[bytes, str]] = None,
                   aspect_ratio: str = "16:9", fast: bool = False,
                   negative: str = "", resolution: str = "",
                   log: Callable[[str], None] = print,
                   progress: Callable[[str], None] = lambda _m: None,
                   max_wait_s: float = 600.0) -> Creation:
    """Text (and optionally a starting image) → an MP4 with sound on Veo 3."""
    from google.genai import types
    prompt = (prompt or "").strip()
    if not prompt:
        raise StudioError("Tell me what the video should show.")
    ar = aspect_ratio if aspect_ratio in VIDEO_RATIOS else "16:9"

    def attempt(model):
        client = _client(120_000)
        cfg = dict(aspect_ratio=ar, number_of_videos=1)
        if negative:
            cfg["negative_prompt"] = negative
        if resolution and "veo-3" in model:
            cfg["resolution"] = resolution
        kwargs = dict(model=model, prompt=prompt,
                      config=types.GenerateVideosConfig(**cfg))
        if image:
            kwargs["image"] = types.Image(image_bytes=image[0], mime_type=image[1])
        op = client.models.generate_videos(**kwargs)
        progress(f"Rendering on {model.split('-generate')[0]}…")
        t0 = time.monotonic()
        while not op.done:
            if time.monotonic() - t0 > max_wait_s:
                raise StudioError("The video took too long to render. Try a shorter idea.")
            time.sleep(8)
            op = client.operations.get(op)
        if getattr(op, "error", None):
            raise RuntimeError(str(op.error))
        vids = getattr(op.response, "generated_videos", None) or []
        if not vids:
            raise StudioError("Google's safety filters declined that video. "
                              "Try rephrasing it.")
        video = vids[0].video
        data = getattr(video, "video_bytes", None)
        if not data:
            data = client.files.download(file=video)
            if not isinstance(data, (bytes, bytearray)):
                data = getattr(video, "video_bytes", None)
        if not data:
            raise RuntimeError("video finished but could not be downloaded")
        return bytes(data)

    model, data = _run_ladder("video_fast" if fast else "video", attempt, log)
    path = _save(data, prompt, ".mp4", model, "video")
    return Creation(paths=[path], model=model)


# ── speech ───────────────────────────────────────────────────────────────────
def _wav(pcm: bytes, rate: int = 24000, channels: int = 1) -> bytes:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as w:
        w.setnchannels(channels)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buf.getvalue()


def _voice(name: str) -> str:
    for v in VOICES:
        if v.lower() == (name or "").strip().lower():
            return v
    return "Kore"


def generate_speech(text: str, voice: str = "Kore", direction: str = "",
                    speakers: Optional[dict[str, str]] = None,
                    log: Callable[[str], None] = print) -> Creation:
    """Text → WAV. `direction` is a performance note ("warm, slow, like a
    bedtime story"). `speakers` maps speaker names in the script to voices for a
    two-person dialogue: {"Ava": "Kore", "Leo": "Puck"}."""
    from google.genai import types
    text = (text or "").strip()
    if not text:
        raise StudioError("Give me the words to speak.")
    script = f"{direction.strip()}:\n{text}" if direction else text

    if speakers and len(speakers) >= 2:
        speech = types.SpeechConfig(multi_speaker_voice_config=types.MultiSpeakerVoiceConfig(
            speaker_voice_configs=[
                types.SpeakerVoiceConfig(speaker=name, voice_config=types.VoiceConfig(
                    prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=_voice(v))))
                for name, v in list(speakers.items())[:2]]))
    else:
        speech = types.SpeechConfig(voice_config=types.VoiceConfig(
            prebuilt_voice_config=types.PrebuiltVoiceConfig(voice_name=_voice(voice))))

    def attempt(model):
        client = _client(180_000)
        resp = client.models.generate_content(
            model=model, contents=script,
            config=types.GenerateContentConfig(response_modalities=["AUDIO"],
                                               speech_config=speech))
        for part in _parts(resp):
            blob = getattr(part, "inline_data", None)
            if blob is not None and blob.data:
                data = blob.data if isinstance(blob.data, bytes) else base64.b64decode(blob.data)
                m = re.search(r"rate=(\d+)", blob.mime_type or "")
                return _wav(data, int(m.group(1)) if m else 24000)
        raise RuntimeError(f"no audio returned ({_finish_reason(resp)})")

    model, wav = _run_ladder("tts", attempt, log)
    path = _save(wav, text[:60], ".wav", model, "speech")
    return Creation(paths=[path], model=model)


# ── music ────────────────────────────────────────────────────────────────────
def compose_music(description: str, seconds: int = 30, bpm: int = 0,
                  log: Callable[[str], None] = print) -> Creation:
    """Words → an instrumental WAV through Lyria RealTime (48 kHz stereo)."""
    from google.genai import types
    description = (description or "").strip()
    if not description:
        raise StudioError("Describe the music you want.")
    seconds = max(5, min(120, int(seconds or 30)))
    target = seconds * 48000 * 2 * 2      # 48 kHz, stereo, 16-bit

    async def _run(model):
        client = _client(60_000, api_version="v1alpha")
        chunks: list[bytes] = []
        got = 0
        async with client.aio.live.music.connect(model=model) as session:
            await session.set_weighted_prompts(
                prompts=[types.WeightedPrompt(text=description, weight=1.0)])
            cfg = {}
            if bpm:
                cfg["bpm"] = max(60, min(200, int(bpm)))
            if cfg:
                await session.set_music_generation_config(
                    config=types.LiveMusicGenerationConfig(**cfg))
            await session.play()
            deadline = time.monotonic() + seconds * 3 + 30
            async for msg in session.receive():
                sc = getattr(msg, "server_content", None)
                for ch in (getattr(sc, "audio_chunks", None) or []):
                    if ch.data:
                        chunks.append(ch.data)
                        got += len(ch.data)
                if got >= target or time.monotonic() > deadline:
                    break
            try:
                await session.stop()
            except Exception:
                pass
        if not chunks:
            raise RuntimeError("no music came back")
        return _wav(b"".join(chunks)[:target], 48000, 2)

    def attempt(model):
        return asyncio.run(_run(model))

    model, wav = _run_ladder("music", attempt, log)
    path = _save(wav, description, ".wav", model, "music")
    return Creation(paths=[path], model=model)


# ── grounded research ────────────────────────────────────────────────────────
def research(question: str, urls: Optional[list[str]] = None, search: bool = True,
             maps: bool = False, code: bool = False, depth: str = "deep",
             files: Optional[list[tuple[bytes, str]]] = None,
             log: Callable[[str], None] = print) -> Answer:
    """A thinking model with Google's tools switched on, the way AI Studio's
    playground does it. Returns the answer and every source it leaned on."""
    from google.genai import types
    question = (question or "").strip()
    if not question:
        raise StudioError("What should I look into?")
    urls = [u for u in (urls or []) if str(u).startswith(("http://", "https://"))]

    def _tools(with_maps: bool, with_code: bool) -> list:
        t = []
        if search:
            t.append(types.Tool(google_search=types.GoogleSearch()))
        if urls or search:
            t.append(types.Tool(url_context=types.UrlContext()))
        if with_maps:
            t.append(types.Tool(google_maps=types.GoogleMaps()))
        if with_code:
            t.append(types.Tool(code_execution=types.ToolCodeExecution()))
        return t

    prompt = question
    if urls:
        prompt += "\n\nUse these pages:\n" + "\n".join(urls)
    contents: list = [types.Part.from_bytes(data=d, mime_type=m) for d, m in (files or [])[:4]]
    contents.append(prompt)
    budget = {"quick": 0, "balanced": 4096, "deep": -1}.get(depth, -1)

    def attempt(model):
        client = _client(240_000)
        tries = [(maps, code), (False, code), (False, False)]
        last = None
        for with_maps, with_code in tries:
            # Pro models cannot switch thinking off; give them the minimum.
            b = 128 if ("pro" in model and budget == 0) else budget
            think = types.ThinkingConfig(thinking_budget=b)
            cfg = types.GenerateContentConfig(
                tools=_tools(with_maps, with_code) or None,
                thinking_config=think,
                system_instruction=(
                    "You are Dexter, a research assistant made by Lumaroz AI. "
                    "Answer precisely, lead with the answer, then the detail. "
                    "Use Markdown headings and bullet points where they help."),
            )
            try:
                return client.models.generate_content(model=model, contents=contents, config=cfg)
            except Exception as e:                   # tool mix not allowed → fewer tools
                last = e
                if "INVALID_ARGUMENT" not in str(e) and "400" not in str(e):
                    raise
        raise last

    model, resp = _run_ladder("research", attempt, log)
    ans = Answer(model=model)
    texts = []
    for part in _parts(resp):
        if getattr(part, "thought", False):
            continue
        if getattr(part, "text", None):
            texts.append(part.text)
        ec = getattr(part, "executable_code", None)
        if ec is not None and getattr(ec, "code", None):
            ans.code.append(ec.code)
        cr = getattr(part, "code_execution_result", None)
        if cr is not None and getattr(cr, "output", None):
            ans.code_output.append(cr.output)
        blob = getattr(part, "inline_data", None)
        if blob is not None and getattr(blob, "data", None) and \
                (blob.mime_type or "").startswith("image/"):
            ans.images.append(_save(blob.data, f"chart: {question}",
                                    _ext_for(blob.mime_type), model, "chart"))
    ans.text = "\n".join(texts).strip()
    try:
        gm = resp.candidates[0].grounding_metadata
    except Exception:
        gm = None
    if gm is not None:
        ans.queries = list(getattr(gm, "web_search_queries", None) or [])
        seen = set()
        for ch in (getattr(gm, "grounding_chunks", None) or []):
            src = getattr(ch, "web", None) or getattr(ch, "maps", None) \
                or getattr(ch, "retrieved_context", None)
            uri = getattr(src, "uri", "") if src else ""
            if uri and uri not in seen:
                seen.add(uri)
                ans.sources.append((getattr(src, "title", "") or uri, uri))
    if not ans.text and not ans.code_output:
        raise StudioError("The research came back empty. Try asking it differently.")
    return ans
