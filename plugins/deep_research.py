"""
Lumaroz Studio — deep research. A thinking Gemini model with Google Search,
Google Maps, URL reading and Python code execution switched on together, the
way AI Studio's playground runs it. The full answer, with numbered sources,
appears in the panel under Dexter's face; Dexter speaks the short version.
"""
from __future__ import annotations

PLUGIN = {
    "name": "deep_research",
    "description": (
        "Research a question thoroughly with live Google Search grounding, "
        "reading web pages, Google Maps for places, and running Python for "
        "calculations or charts — then show a full written answer with sources "
        "on screen. Use for questions that need current facts, comparisons, "
        "analysis, 'research', 'look into', 'find out everything about', "
        "summarising given URLs, places/restaurants/directions near somewhere "
        "(maps=true), or maths/data work and charts (code=true). Takes 10-60 "
        "seconds; the answer is read out briefly when ready. For a quick one-"
        "line fact prefer the plain web search tool."
    ),
    "parameters": {
        "type": "OBJECT",
        "properties": {
            "question": {"type": "STRING", "description": "The full research question."},
            "urls": {"type": "STRING",
                     "description": "Optional web addresses to read, separated by spaces."},
            "maps": {"type": "BOOLEAN", "description": "Use Google Maps (places, routes, local)."},
            "code": {"type": "BOOLEAN",
                     "description": "Allow running Python for maths, data or charts."},
            "depth": {"type": "STRING", "description": "'quick', 'balanced' or 'deep' (default)."},
            "use_file": {"type": "BOOLEAN",
                         "description": "Include the uploaded file (image/PDF) in the research."},
        },
        "required": ["question"],
    },
}


def _markdownish(ans) -> str:
    out = [ans.text.strip()]
    if ans.code_output:
        out.append("\n── computed ──\n" + "\n".join(o.strip() for o in ans.code_output)[:3000])
    if ans.sources:
        out.append("\n── sources ──")
        out += [f"[{i}] {t}  {u}" for i, (t, u) in enumerate(ans.sources[:12], 1)]
    if ans.images:
        out.append(f"\n{len(ans.images)} chart(s) saved to the Studio.")
    return "\n".join(out).strip()


def run(parameters: dict, player=None, session_memory=None) -> str:
    try:
        from plugins import _studio_common as sc
        from core import studio, gemini
    except Exception as e:
        return f"Research could not start: {e}"

    p = parameters or {}
    q = str(p.get("question") or "").strip()
    if not q:
        return "What should I research?"
    urls = [u for u in str(p.get("urls") or "").split() if u.startswith("http")]
    files = []
    if p.get("use_file") and player is not None:
        try:
            from pathlib import Path
            import mimetypes
            cur = player.current_file
            if cur and Path(cur).is_file():
                mime = mimetypes.guess_type(cur)[0] or "application/octet-stream"
                if mime.startswith("image/") or mime == "application/pdf":
                    files.append((Path(cur).read_bytes(), mime))
        except Exception:
            pass

    def job():
        sc.log(player, f"researching — {q[:80]}")
        ans = studio.research(q, urls, True, bool(p.get("maps")), bool(p.get("code")),
                              str(p.get("depth") or "deep"), files,
                              log=lambda m: sc.log(player, m))
        if player is not None:
            try:
                player.show_content(f"RESEARCH · {q[:48]}", _markdownish(ans))
            except Exception:
                pass
        for path in ans.images:
            sc.show_image(player, path, "Chart", q)
        sc.log(player, f"answered with {len(ans.sources)} source(s) ({ans.model})")
        brief = gemini.text(
            "Summarise this research answer in two short spoken sentences, no "
            "markdown, no URLs:\n\n" + ans.text[:6000], tier=gemini.FAST) or ""
        sc.say(player, "The research is on screen. Key points to say out loud: "
               + (brief.strip() or ans.text[:400]))

    busy = sc.background("research", player, job)
    return busy or "Researching that now with live Google sources — give me a moment."
