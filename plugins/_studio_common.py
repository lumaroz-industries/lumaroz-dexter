"""
Shared plumbing for the Lumaroz Studio plugins (create_image, create_video,
generate_speech, compose_music, deep_research).

Studio work takes from five seconds to several minutes, and a plugin's run()
must return within a few seconds. So every Studio plugin does the same thing:
start the job on its own thread, return a short "on it" sentence at once, and
when the job is done show the result through `player` and ask Dexter to say
one line about it through `player.request_say`.

The loader skips this file because of its leading underscore.
"""
from __future__ import annotations

import threading
from pathlib import Path
from typing import Callable, Optional

_busy: dict[str, int] = {}
_busy_lock = threading.Lock()
MAX_PARALLEL = 3


def log(player, text: str) -> None:
    print(f"[Studio] {text}")
    if player is not None:
        try:
            player.write_log(f"STUDIO: {text}")
        except Exception:
            pass


def say(player, instruction: str) -> None:
    """Ask Dexter to tell the user something, phrased in their language."""
    fn = getattr(player, "request_say", None) if player is not None else None
    if callable(fn):
        try:
            fn(f"[Studio update — tell the user briefly, in one sentence] {instruction}")
        except Exception:
            pass


def show_image(player, path: Path, title: str, caption: str) -> None:
    if player is not None and hasattr(player, "show_image"):
        try:
            player.show_image(str(path), title, caption)
        except Exception as e:
            log(player, f"could not show {path.name}: {e}")


def background(kind: str, player, job: Callable[[], None]) -> Optional[str]:
    """Run job() on a daemon thread. Returns a refusal sentence if too many
    Studio jobs are already running, else None."""
    with _busy_lock:
        total = sum(_busy.values())
        if total >= MAX_PARALLEL:
            return (f"I'm already working on {total} creations — "
                    "give me a moment to finish those first.")
        _busy[kind] = _busy.get(kind, 0) + 1

    def _wrap():
        try:
            job()
        except Exception as e:                       # never let a thread die silently
            from core.studio import StudioError
            msg = str(e) if isinstance(e, StudioError) else f"something went wrong: {e}"
            log(player, f"{kind} failed — {msg}")
            say(player, f"The {kind} could not be made: {msg}")
        finally:
            with _busy_lock:
                _busy[kind] = max(0, _busy.get(kind, 1) - 1)

    threading.Thread(target=_wrap, daemon=True, name=f"studio-{kind}").start()
    return None


def resolve_image(source: str, player) -> Optional[tuple[bytes, str]]:
    """Turn a spoken source into image bytes.

    source: "last" (newest creation), "file" (whatever is in the drop zone),
    "screen" (a screenshot), "" (file if one is loaded, else last), or a path.
    Raises StudioError with a speakable message."""
    from core import studio
    src = (source or "").strip()
    low = src.lower()
    if low in ("screen", "screenshot", "my screen"):
        return studio.screenshot()
    current = None
    if player is not None:
        try:
            current = player.current_file
        except Exception:
            current = None
    if low in ("file", "uploaded", "upload", "dropped") or (not low and current):
        if current and Path(current).is_file():
            return studio.read_image(current)
        if low:
            raise studio.StudioError("There's no image in the upload box — drop one in first.")
    if low in ("", "last", "latest", "previous", "that", "it"):
        last = studio.last_creation()
        if last is None:
            raise studio.StudioError("I haven't made any images yet — "
                                     "tell me what to create first.")
        return studio.read_image(last)
    return studio.read_image(src)
