<div align="center">

# 牙 &nbsp; D E X T E R

### Lumaroz Intelligence ・ 夜の牙

**A real-life JARVIS for your desktop: it talks, sees, acts, and creates.**
Images, video, voice, music and deep research, all from one conversation.

*A Lumaroz AI product, crafted by **Chaitanya Payghan**.*

</div>

---

## ✦ What Dexter is

Dexter is a voice-first personal AI that lives on your desktop as a holographic
face over an animated Japanese night scene. You talk to it the way you'd talk
to a person. It answers in a natural voice, in your language, and while it
talks it gets real work done: it opens apps, drives the browser, handles files,
reads your screen, remembers you, and makes things in **Lumaroz Studio**.

> *"Dexter, make me a poster of a samurai under a blood moon in 9:16."*
> *"Now make it snow."*
> *"Bring it to life as a video."*
> *"Research the best mechanical keyboards under $150 and compare them."*
> *"Make me a new wallpaper of a rainy Kyoto street."*

## ✦ Lumaroz Studio · 工房

Everything Google AI Studio can make, built into Dexter and driven by voice.
Each creation opens full-size in the **Studio** view (press **F9**) and is
saved to `~/Pictures/Lumaroz`, with its prompt saved alongside it.

| | Capability | What you say |
|---|---|---|
| 🎨 | **Image generation**: Gemini native image ("Nano Banana" / Pro), with a free keyless fallback; Imagen 4 on Vertex keys. 1 to 4 images, 10 aspect ratios | *"Create a cyberpunk Tokyo alley, cinematic, 16:9"* |
| 🖌️ | **Image editing and composition**: change, restyle, remove, add, recolour, or combine several photos | *"Make it night-time"*, *"Put this logo on a hoodie"* |
| 🎬 | **Video generation**: Veo 3.1, then Veo 3 and Veo 2, with native sound. Text-to-video or image-to-video, 16:9 or 9:16 | *"Animate that image, slow push-in, rain falling"* |
| 🎙️ | **Studio voice-overs**: 30 Gemini TTS voices, performance direction, two-speaker podcasts | *"Record this as a calm narration in the Charon voice"* |
| 🎵 | **Music**: original instrumental tracks with Lyria RealTime | *"Compose 30 seconds of lo-fi with warm Rhodes, 80 bpm"* |
| 🔎 | **Deep research**: a thinking model with Google Search grounding, URL reading, Google Maps and Python code execution, with numbered sources | *"Research…"*, *"Read these links and summarise"*, *"Best ramen near Shibuya"* |
| 🌐 | **Live Google Search**: the conversation itself is grounded in Google Search for quick facts | *"Who won last night?"* |

**Images never stop at "out of quota".** Dexter tries the cheapest Gemini
image model first (2.5 Flash Image). If Google can't make the picture (free-tier
limits, no billing, no key), it switches to a **free keyless generator**
(Pollinations / FLUX) and still delivers the image. Choose the behaviour with
`studio_image_source` in `config/api_keys.json`:

| Value | Behaviour |
|---|---|
| `"auto"` *(default)* | Google first, free generator when Google can't |
| `"free"` | Always the free generator: uses no Google quota at all |
| `"google"` | Google only: prompts are never sent anywhere else |

In `auto` and `free`, the prompt text is sent to pollinations.ai. Without a key
the free generator makes **one image every 45 seconds** (Dexter waits for it
automatically) and adds a small watermark. A free key from
<https://enter.pollinations.ai> removes both: add `"pollinations_key": "…"` to
`config/api_keys.json`. Editing an existing image still needs Google.

Imagen 4 only works with a Google Cloud (Vertex AI) key. The Google SDK refuses
it with an AI Studio key, so Dexter skips it unless `"studio_vertex": true` is set.

Every capability runs on a **model ladder**. If a model is out of quota,
missing for your key or overloaded, Dexter rests it for a while and moves on to
the next one. A free-tier key still gets real work done, and new models can be
swapped in from config without touching code:

```json
{ "studio_models": { "image": ["gemini-2.5-flash-image"], "video": ["veo-3.0-fast-generate-001"] } }
```

## ✦ The live wallpaper · 夜の牙

The scene behind Dexter's face is painted in code and never stops moving:

- a **blood moon** that breathes and brightens with Dexter's voice, with cloud wisps sliding across it
- three ranges of **misty mountains**, a **five-storey pagoda** with flickering lanterns, and a **torii** on the far shore
- **momiji branches** that sway in the wind, with **maple leaves falling** and tumbling on gusts
- a **lake** that mirrors the scene with live ripples and a glittering moon path
- drifting **mist** and rising **embers**

**Any picture can be a live wallpaper.** Right-click the scene and choose
*"Use my own image as live wallpaper…"*. Dexter adds a slow, looping camera
drift, breathing light, mist, falling leaves and embers on top. You can also
just ask: *"Dexter, make me a wallpaper of Mount Fuji at dawn."*

Motion has three levels (**full · calm · still**) and can be switched off
entirely, all from the same right-click menu. Only the parts that move are
redrawn each frame, so it's light enough to leave running all day.

## ✦ Everything else Dexter does

| | |
|---|---|
| 🧑‍🎤 **Holographic face** | A real 3D head with lip-sync at ~50 mouth shapes a second, natural blinking, gaze and facial acting |
| 🗣️ **Natural voice** | Gemini Live native audio: low latency, interruptible (**Esc**), push-to-talk (**Ctrl+Space**) |
| 🌍 **Your language** | Replies in whatever language you speak |
| 🖥️ **Drives your computer** | Opens and focuses apps, types and clicks, controls the browser, handles files, changes settings |
| 👁️ **Sees** | Reads your screen and, if you allow it, your webcam |
| 🧠 **Remembers you** | Long-term memory you can browse and edit, with nothing silently forgotten |
| ↩️ **Undo** | Takes back files it moved, renamed or wrote, and settings it changed |
| ⚠️ **Real confirmation** | Shutdown, restart and similar actions wait for a button *you* press |
| 📺 **Video on the HUD** | YouTube, local files or any URL, played where the face is |
| 📱 **Phone dashboard** | Control Dexter from your phone over your own Wi-Fi |
| 🧩 **Plugins** | Drop one `.py` file into `plugins/` and Dexter learns a new skill |
| 🔌 **Bring your own engine** | Gemini Live, or your own STT + LLM + TTS (Ollama, LM Studio, OpenAI-compatible APIs, Whisper, Piper) |

## ✦ Quick start

```bash
python setup.py        # installs what YOUR OS needs, plus the browser engine
python main.py
```

On first launch Dexter asks for a **Google AI Studio API key**. Get one free at
<https://aistudio.google.com/apikey>. The key is stored locally in
`config/api_keys.json`, which is git-ignored and never committed. Video (Veo),
Imagen and some Pro models need billing enabled on the key. The ladder falls
back to free-tier models where it can.

### Wake word

Turn on **⚙ → Wake word** to keep Dexter asleep until called. openwakeword has
no pretrained "Hey Dexter" model, so it listens for the closest pretrained
phrase until you add one. Train a custom model with openwakeword's notebook and
save it as `config/wake/hey_dexter.onnx`. Every message in the app always names
the phrase the loaded model actually listens for.

## ✦ Requirements

| | |
|---|---|
| **OS** | Windows 10/11, macOS or Linux (on Wayland, typing, clicking and screen capture are restricted by the OS) |
| **Python** | 3.11, 3.12 or 3.13 |
| **Hardware** | Microphone and speakers. **No GPU needed**: the face, the wallpaper and the video player all render in software |
| **Key** | A Google AI Studio API key (not needed for a fully local engine) |

## ✦ Keyboard

| Key | Action |
|---|---|
| **F4** | Mute / unmute the microphone |
| **F9** | Open / close the Studio |
| **F11** | Fullscreen |
| **Esc** | Interrupt Dexter mid-sentence |
| **Ctrl+Space** | Push-to-talk (when enabled) |
| **Right-click the scene** | Live wallpaper menu |

## ✦ Project layout

```
main.py                  Live voice session, audio I/O, tool dispatch
ui.py                    The window: HUD, Studio gallery, panels, drawers
core/
  studio.py              Lumaroz Studio: image, video, speech, music, research, with model ladders
  live_wallpaper.py      The animated 夜の牙 scene and image-to-live-wallpaper engine
  gemini.py              One-shot model calls with deadlines and fallbacks
  avatar.py …            The holographic face
plugins/
  create_image.py        Generate / edit images (and set them as the wallpaper)
  create_video.py        Veo video
  generate_speech.py     Voice-overs and podcasts
  compose_music.py       Lyria music
  deep_research.py       Grounded research with sources
  live_wallpaper.py      Switch the wallpaper by voice
  _template.py           Start here to write your own skill
actions/                 Computer control: apps, browser, files, settings, …
providers/               Optional local or third-party engines
dashboard/               The phone remote
memory/                  Settings and long-term memory
```

Writing a plugin? Read `AGENTS.md` first. It's short, and it covers the rules
that keep a plugin from silently doing nothing.

---

## ✦ Credits & license

**Lumaroz AI · Dexter** is designed and developed by **Chaitanya Payghan**.

Dexter is built on the open-source *Mark-LVI* assistant by **FatihMakes**
(<https://github.com/FatihMakes/Mark-LVI>). That work is licensed under
[CC BY-NC 4.0](https://creativecommons.org/licenses/by-nc/4.0/), and Dexter is
shared under the same license. Lumaroz has modified it: the rebrand, the Lumaroz
interface and 夜の牙 live wallpaper, Lumaroz Studio, and the Google AI Studio
capabilities. See [`LICENSE`](LICENSE).

**Non-commercial use only.** This project may not be sold or used for
commercial purposes.
