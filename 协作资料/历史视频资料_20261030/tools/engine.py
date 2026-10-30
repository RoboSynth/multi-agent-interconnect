"""Vector motion-graphics engine: cairo drawing, PIL glow, edge-tts voice, ffmpeg output.

Scenes are callables scene(ctx, t, total) drawing on a cairo context at 1920x1080.
"""
from __future__ import annotations

import asyncio
import json
import math
import subprocess
import wave
from pathlib import Path

import cairo
import numpy as np
from PIL import Image, ImageFilter

W, H, FPS = 1920, 1080, 30
FAMILY = "Noto Sans CJK SC"
VOICE = "zh-CN-YunyangNeural"

BG0, BG1 = (0.035, 0.055, 0.10), (0.02, 0.03, 0.06)
INK = (0.92, 0.94, 0.98)
SUB = (0.58, 0.64, 0.75)
DIM = (0.30, 0.36, 0.48)
RED = (0.94, 0.33, 0.32)
GREEN = (0.20, 0.82, 0.52)
C = {"coord": (0.33, 0.52, 1.0), "app": (0.18, 0.78, 0.48), "db": (1.0, 0.56, 0.24),
     "ops": (0.62, 0.45, 1.0), "ver": (0.16, 0.80, 0.88), "wt": (0.86, 0.90, 0.96)}


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def ease_io(x):
    x = max(0.0, min(1.0, x))
    return 4 * x ** 3 if x < .5 else 1 - (-2 * x + 2) ** 3 / 2


def seg(t, start, length):
    return ease((t - start) / length)


def rgba(c, a=1.0):
    return (*c, a)


# ------------------------------------------------------------------ drawing

def background(cx, t=0.0):
    g = cairo.RadialGradient(W * .35, H * .3, 50, W * .5, H * .5, W * .8)
    g.add_color_stop_rgb(0, *BG0)
    g.add_color_stop_rgb(1, *BG1)
    cx.set_source(g)
    cx.paint()
    cx.set_source_rgba(1, 1, 1, .035)
    for x in range(40, W, 48):
        for y in range(40, H, 48):
            cx.arc(x, y, 1.2, 0, 2 * math.pi)
            cx.fill()


def rounded(cx, x, y, w, h, r):
    cx.new_sub_path()
    cx.arc(x + w - r, y + r, r, -math.pi / 2, 0)
    cx.arc(x + w - r, y + h - r, r, 0, math.pi / 2)
    cx.arc(x + r, y + h - r, r, math.pi / 2, math.pi)
    cx.arc(x + r, y + r, r, math.pi, 3 * math.pi / 2)
    cx.close_path()


def panel(cx, x, y, w, h, color, a=1.0, r=20, fill=.12, stroke=2.0):
    rounded(cx, x, y, w, h, r)
    g = cairo.LinearGradient(x, y, x, y + h)
    g.add_color_stop_rgba(0, *color, fill * 1.4 * a)
    g.add_color_stop_rgba(1, *color, fill * .6 * a)
    cx.set_source(g)
    cx.fill_preserve()
    cx.set_source_rgba(*color, .85 * a)
    cx.set_line_width(stroke)
    cx.stroke()


def text(cx, x, y, s, size, color=INK, a=1.0, bold=False, align="left", valign="middle"):
    cx.select_font_face(FAMILY, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    cx.set_font_size(size)
    ext = cx.text_extents(s)
    fe = cx.font_extents()
    dx = {"left": 0, "center": -ext.x_advance / 2, "right": -ext.x_advance}[align]
    dy = {"middle": (fe[0] - fe[1]) / 2, "top": fe[0], "baseline": 0}[valign]
    cx.move_to(x + dx, y + dy)
    cx.set_source_rgba(*color, a)
    cx.show_text(s)
    return ext.x_advance


def text_width(cx, s, size, bold=False):
    cx.select_font_face(FAMILY, cairo.FONT_SLANT_NORMAL, cairo.FONT_WEIGHT_BOLD if bold else cairo.FONT_WEIGHT_NORMAL)
    cx.set_font_size(size)
    return cx.text_extents(s).x_advance


def chip(cx, x, y, s, color, a=1.0, size=24, align="left"):
    w = text_width(cx, s, size) + 28
    x0 = x if align == "left" else x - w / 2 if align == "center" else x - w
    panel(cx, x0, y - size * .9, w, size * 1.8, color, a, r=size * .9, fill=.22, stroke=1.5)
    text(cx, x0 + 14, y, s, size, INK, a)
    return w


def dot(cx, x, y, r, color, a=1.0):
    cx.arc(x, y, r, 0, 2 * math.pi)
    cx.set_source_rgba(*color, a)
    cx.fill()


def subtitle(cx, line):
    if not line:
        return
    size = 38
    w = text_width(cx, line, size) + 64
    rounded(cx, (W - w) / 2, H - 118, w, 66, 14)
    cx.set_source_rgba(0, 0, 0, .55)
    cx.fill()
    text(cx, W / 2, H - 85, line, size, INK, 1, align="center")


class Glow:
    """Shapes drawn here are blurred and added on top of the frame."""
    def __init__(self):
        self.surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W // 2, H // 2)
        self.cx = cairo.Context(self.surface)
        self.cx.scale(.5, .5)

    def clear(self):
        self.cx.save()
        self.cx.set_operator(cairo.OPERATOR_CLEAR)
        self.cx.paint()
        self.cx.restore()


def compose(surface, glow):
    base = np.ndarray((H, W, 4), np.uint8, surface.get_data()).copy()
    rgb = base[..., [2, 1, 0]].astype(np.float32)
    if glow is not None:
        g = np.ndarray((H // 2, W // 2, 4), np.uint8, glow.surface.get_data())
        img = Image.fromarray(g[..., [2, 1, 0]].copy()).filter(ImageFilter.GaussianBlur(14)).resize((W, H))
        rgb = np.minimum(255, rgb + np.asarray(img, np.float32) * 1.6)
    return rgb.astype(np.uint8)


# ------------------------------------------------------------------ audio

async def _tts(line, path):
    import edge_tts
    await edge_tts.Communicate(line, VOICE, rate="+2%").save(str(path))


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def narrate(lines, work, lead=0.6, gap=0.35):
    timeline, cursor = [], lead
    for i, line in enumerate(lines):
        clip = work / f"line{i}.mp3"
        if not clip.exists():
            asyncio.run(_tts(line, clip))
        length = duration(clip)
        timeline.append((cursor, cursor + length, line, clip))
        cursor += length + gap
    return timeline, cursor


def blips(times, total, path, freq=1320):
    """Soft UI ticks, synthesized (no third-party sound assets)."""
    rate = 48000
    out = np.zeros(int(total * rate) + rate, np.float32)
    n = int(.06 * rate)
    env = np.exp(-np.linspace(0, 9, n))
    tone = (np.sin(2 * np.pi * freq * np.arange(n) / rate) * .5 +
            np.sin(2 * np.pi * freq * 1.5 * np.arange(n) / rate) * .2) * env * .09
    for t in times:
        i = int(t * rate)
        if 0 <= i < len(out) - n:
            out[i:i + n] += tone
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes((np.clip(out, -1, 1) * 32767).astype(np.int16).tobytes())


def mix_audio(timeline, total, work, extra=()):
    inputs, filters, labels = [], [], []
    for i, (start, _, _, clip) in enumerate(timeline):
        inputs += ["-i", str(clip)]
        ms = int(start * 1000)
        filters.append(f"[{i}]adelay={ms}|{ms}[v{i}]")
        labels.append(f"[v{i}]")
    for j, path in enumerate(extra):
        k = len(timeline) + j
        inputs += ["-i", str(path)]
        labels.append(f"[{k}]")
    filters.append("".join(labels) + f"amix=inputs={len(labels)}:normalize=0,apad[a]")
    out = work / "audio.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters),
                    "-map", "[a]", "-t", f"{total:.2f}", "-ar", "48000", str(out)], check=True)
    return out


# ------------------------------------------------------------------ render

def render(scene, lines, out_dir, name, *, sfx_times=None):
    work = out_dir / name
    work.mkdir(parents=True, exist_ok=True)
    timeline, cursor = narrate(lines, work)
    total = cursor + 1.0
    scene.prepare(total, timeline) if hasattr(scene, "prepare") else None
    extra = []
    if hasattr(scene, "sfx_times"):
        blips(scene.sfx_times(), total, work / "sfx.wav")
        extra.append(work / "sfx.wav")
    audio = mix_audio(timeline, total, work, extra)
    video = out_dir / f"{name}.mp4"
    proc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(audio),
                             "-c:v", "libx264", "-preset", "slow", "-crf", "16", "-pix_fmt", "yuv420p",
                             "-c:a", "aac", "-b:a", "192k", "-shortest", "-movflags", "+faststart", str(video)],
                            stdin=subprocess.PIPE)
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    glow = Glow()
    for f in range(int(total * FPS)):
        t = f / FPS
        cx = cairo.Context(surface)
        glow.clear()
        scene.draw(cx, glow.cx, t, total)
        line = next((s for a, b, s, _ in timeline if a <= t <= b + .25), "")
        subtitle(cx, line)
        surface.flush()
        proc.stdin.write(compose(surface, glow).tobytes())
    proc.stdin.close()
    proc.wait()
    (out_dir / f"{name}.srt").write_text(srt(timeline), encoding="utf-8")
    return video, total


def srt(timeline):
    def ts(x):
        ms = int(round(x * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    return "\n".join(f"{i + 1}\n{ts(a)} --> {ts(b)}\n{s}\n" for i, (a, b, s, _) in enumerate(timeline))


def still(scene, t, total, path, line=""):
    surface = cairo.ImageSurface(cairo.FORMAT_ARGB32, W, H)
    glow = Glow()
    if hasattr(scene, "prepare"):
        scene.prepare(total, [])
    cx = cairo.Context(surface)
    scene.draw(cx, glow.cx, t, total)
    subtitle(cx, line)
    surface.flush()
    Image.fromarray(compose(surface, glow)).save(path)
