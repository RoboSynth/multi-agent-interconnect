"""Motion-graphics renderer for the competition video (PIL frames -> ffmpeg).

Each scene is a function scene(t, d) -> PIL.Image drawn at 1920x1080. Narration
lines are synthesized first so every scene lasts exactly as long as its voice.
Usage: python render.py <scene-id ...|all> --out <dir>
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont

W, H, FPS = 1920, 1080, 30
FONT_R = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"
FONT_B = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
VOICE = "zh-CN-YunyangNeural"

BG = (11, 18, 32)
GRID = (24, 34, 54)
INK = (232, 238, 248)
SUB = (148, 163, 190)
RED = (239, 83, 80)
COLORS = {"coord": (77, 128, 255), "app": (46, 196, 120), "db": (255, 138, 61),
          "ops": (156, 110, 255), "ver": (34, 200, 220), "wt": (220, 228, 240)}
_fonts = {}


def font(size, bold=False):
    key = (size, bold)
    if key not in _fonts:
        _fonts[key] = ImageFont.truetype(FONT_B if bold else FONT_R, size, index=2)  # SC
    return _fonts[key]


def ease(x):
    x = max(0.0, min(1.0, x))
    return 1 - (1 - x) ** 3


def seg(t, start, length):
    return ease((t - start) / length)


def mix(c, k, bg=BG):
    return tuple(int(bg[i] + (c[i] - bg[i]) * k) for i in range(3))


def canvas():
    img = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(img)
    for x in range(0, W, 80):
        d.line([(x, 0), (x, H)], fill=GRID, width=1)
    for y in range(0, H, 80):
        d.line([(0, y), (W, y)], fill=GRID, width=1)
    return img, d


def text(d, xy, s, size, color=INK, bold=False, anchor="la", k=1.0):
    d.text(xy, s, font=font(size, bold), fill=mix(color, k), anchor=anchor)


def card(d, box, color, k=1.0, fill_k=0.16, radius=22, width=3):
    d.rounded_rectangle(box, radius=radius, fill=mix(color, fill_k * k), outline=mix(color, k), width=width)


def lock(d, cx, cy, color, k=1.0, s=1.0):
    c = mix(color, k)
    d.arc([cx - 16 * s, cy - 34 * s, cx + 16 * s, cy - 2 * s], 180, 360, fill=c, width=int(5 * s))
    d.rounded_rectangle([cx - 24 * s, cy - 10 * s, cx + 24 * s, cy + 24 * s], radius=int(6 * s), fill=c)


def subtitle(img, line):
    if not line:
        return
    d = ImageDraw.Draw(img)
    f = font(40)
    w = d.textlength(line, font=f)
    x0, y0 = (W - w) / 2 - 28, H - 128
    overlay = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    ImageDraw.Draw(overlay).rounded_rectangle([x0, y0, x0 + w + 56, y0 + 70], radius=14, fill=(0, 0, 0, 150))
    img.paste(Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB"))
    ImageDraw.Draw(img).text((W / 2, y0 + 35), line, font=f, fill=INK, anchor="mm")


def flow(d, a, b, color, progress, t, width=4):
    """Line a->b drawn to progress, with a travelling packet once complete."""
    if progress <= 0:
        return
    x = a[0] + (b[0] - a[0]) * progress
    y = a[1] + (b[1] - a[1]) * progress
    d.line([a, (x, y)], fill=mix(color, 0.8), width=width)
    if progress >= 1:
        p = (t * 0.7) % 1
        px, py = a[0] + (b[0] - a[0]) * p, a[1] + (b[1] - a[1]) * p
        d.ellipse([px - 9, py - 9, px + 9, py + 9], fill=color)


# ---------------------------------------------------------------- scenes

def s_hook(t, dur):
    img, d = canvas()
    pulse = 0.88 + 0.12 * math.sin(t * 5)
    k = seg(t, 0, 0.6)
    text(d, (W / 2, 150), "订单提交失败", 76, RED, True, "mm", k * pulse)
    text(d, (W / 2, 232), "HTTP 502  ·  写入失败  ·  结果未知", 34, SUB, False, "mm", k)
    orgs = [("应用团队", "app", "应用部署权限"), ("数据库服务方", "db", "数据库管理员账号"), ("网关与容器运维", "ops", "Docker 主机权限")]
    for i, (name, key, cred) in enumerate(orgs):
        kk = seg(t, 1.0 + i * 0.45, 0.7)
        x = 200 + i * 540 + (1 - kk) * 60
        card(d, [x, 340, x + 440, 640], COLORS[key], kk)
        text(d, (x + 220, 410), name, 44, INK, True, "mm", kk)
        lock(d, x + 220, 510, COLORS[key], kk)
        text(d, (x + 220, 590), cred, 28, SUB, False, "mm", kk)
    kk = seg(t, dur * 0.55, 0.8)
    if kk > 0:
        card(d, [560, 700, 1360, 880], COLORS["coord"], kk)
        text(d, (960, 760), "把所有凭据交给一个“万能”排障智能体？", 38, INK, True, "mm", kk)
        text(d, (960, 825), "跨组织场景：不可接受", 32, RED, True, "mm", kk)
        x = seg(t, dur * 0.55 + 1.0, 0.5)
        if x > 0:  # Strike through the question only, then stamp the verdict.
            d.line([(600, 762), (600 + 720 * x, 762)], fill=RED, width=5)
    return img


NODES = {"coord": (330, 540), "wt": (960, 540), "app": (1560, 260), "db": (1620, 540),
         "ops": (1560, 820), "ver": (960, 860)}
LABELS = {"coord": ("协调智能体", "零资源凭据"), "wt": ("梧桐平台", "注册 · 发现 · AIP · AMP"),
          "app": ("应用智能体", "应用域内执行"), "db": ("数据库主 / 备", "MCP + 权限守卫"),
          "ops": ("运维智能体", "MCP + 权限守卫"), "ver": ("业务验证智能体", "真实订单流程")}


def s_arch(t, dur):
    img, d = canvas()
    text(d, (W / 2, 90), "凭据不出域的跨组织故障协同智能体", 54, INK, True, "mm", seg(t, 0, 0.8))
    order = ["wt", "coord", "app", "db", "ops", "ver"]
    for i, key in enumerate(order[1:]):
        flow(d, NODES[key], NODES["wt"], COLORS[key], seg(t, 2.0 + i * 0.5, 0.8), t + i * 0.2)
    for i, key in enumerate(order):
        k = seg(t, 0.4 + i * 0.35, 0.6)
        cx, cy = NODES[key]
        wbox = 200 if key != "wt" else 230
        card(d, [cx - wbox, cy - 70, cx + wbox, cy + 70], COLORS[key], k, 0.22 if key == "wt" else 0.16)
        text(d, (cx, cy - 18), LABELS[key][0], 38, INK, True, "mm", k)
        text(d, (cx, cy + 30), LABELS[key][1], 26, SUB, False, "mm", k)
    for i, step in enumerate(["注册", "发现", "互联", "访问"]):
        k = seg(t, dur * 0.45 + i * 0.6, 0.5)
        x = 560 + i * 200
        card(d, [x, 170, x + 160, 230], COLORS["wt"], k, 0.10, 30, 2)
        text(d, (x + 80, 200), step, 30, INK, True, "mm", k)
    return img


RESULTS = [("盲修剧本", 12, (130, 140, 160)), ("固定流程", 15, (120, 150, 210)),
           ("模型自由调用", 9, (180, 120, 120)), ("证据驱动调度（本作品）", 15, COLORS["coord"])]


def s_results(t, dur):
    img, d = canvas()
    text(d, (120, 100), "60 次对照实验 · 5 类真实故障 · 严格 30 秒 / 10 个完整订单流程验收", 40, INK, True, "la", seg(t, 0, 0.6))
    base, top = 820, 260
    for i, (name, n, color) in enumerate(RESULTS):
        k = seg(t, 0.6 + i * 0.35, 1.0)
        x = 160 + i * 230
        h = (base - top) * n / 15 * k
        d.rounded_rectangle([x, base - h, x + 150, base], radius=10, fill=color)
        text(d, (x + 75, base - h - 36), f"{round(n * k)}/15", 34, INK, True, "mm", k)
        for j, part in enumerate(name.replace("（", "\n（").split("\n")):
            text(d, (x + 75, base + 40 + j * 36), part, 26, SUB if i < 3 else INK, i == 3, "mm", k)
    d.line([(130, base), (1080, base)], fill=SUB, width=2)
    stats = [("0", "无关的高风险操作", "盲修 6 次 · 自由调用 20 次"),
             ("−67%", "读取敏感会话数据", "6 次 对 固定流程 18 次"),
             ("−96%", "模型 token", "1.2 万 对 自由调用 31 万")]
    for i, (big, label, note) in enumerate(stats):
        k = seg(t, dur * 0.35 + i * 0.9, 0.7)
        y = 240 + i * 200
        card(d, [1140, y, 1820, y + 160], COLORS["coord"], k)
        text(d, (1185, y + 80), big, 68, COLORS["coord"], True, "lm", k)
        text(d, (1420, y + 58), label, 34, INK, True, "lm", k)
        text(d, (1420, y + 108), note, 26, SUB, False, "lm", k)
    return img


SCENES = {
    "01-hook": (s_hook, ["订单突然无法提交。", "应用、数据库、网关分属三个团队，各自握着自己的凭据。",
                         "把所有密码交给一个万能的排障智能体？在跨组织场景里，这不可接受。"]),
    "02-arch": (s_arch, ["我们做了一个凭据不出域的跨组织故障协同智能体。",
                         "七个智能体在梧桐平台注册，经发现服务自动找到彼此，通过 AIP 群组协作。",
                         "协调者不持有任何资源凭据，修改只在各自的域内执行，高风险操作必须人工审批。"]),
    "08-results": (s_results, ["在五类真实故障、六十次对照实验中，证据驱动调度和固定流程一样，十五次全部恢复，",
                               "但没有一次无关的高风险操作，读取敏感数据减少三分之二；",
                               "相比让大模型自由调用工具，恢复从九次提高到十五次，token 减少百分之九十六。"]),
}


async def tts(line, path):
    import edge_tts
    await edge_tts.Communicate(line, VOICE, rate="+4%").save(str(path))


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
                         capture_output=True, text=True, check=True).stdout
    return float(json.loads(out)["format"]["duration"])


def render(scene_id, out):
    draw, lines = SCENES[scene_id]
    work = out / scene_id
    work.mkdir(parents=True, exist_ok=True)
    timeline, cursor, parts = [], 0.6, []
    for i, line in enumerate(lines):
        clip = work / f"line{i}.mp3"
        if not clip.exists():
            asyncio.run(tts(line, clip))
        length = duration(clip)
        timeline.append((cursor, cursor + length, line))
        parts.append((cursor, clip))
        cursor += length + 0.35
    total = cursor + 0.8
    # Narration track: each line placed at its start time.
    inputs, filters = [], []
    for i, (start, clip) in enumerate(parts):
        inputs += ["-i", str(clip)]
        filters.append(f"[{i}]adelay={int(start * 1000)}|{int(start * 1000)}[a{i}]")
    filters.append("".join(f"[a{i}]" for i in range(len(parts))) + f"amix=inputs={len(parts)}:normalize=0,apad[a]")
    voice = work / "voice.wav"
    subprocess.run(["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", ";".join(filters),
                    "-map", "[a]", "-t", f"{total:.2f}", str(voice)], check=True)
    video = out / f"{scene_id}.mp4"
    proc = subprocess.Popen(["ffmpeg", "-y", "-v", "error", "-f", "rawvideo", "-pix_fmt", "rgb24",
                             "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-", "-i", str(voice),
                             "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p",
                             "-c:a", "aac", "-b:a", "192k", "-shortest", str(video)], stdin=subprocess.PIPE)
    for f in range(int(total * FPS)):
        t = f / FPS
        img = draw(t, total)
        line = next((s for a, b, s in timeline if a <= t <= b + 0.2), "")
        subtitle(img, line)
        proc.stdin.write(img.tobytes())
    proc.stdin.close()
    proc.wait()
    (out / f"{scene_id}.subtitles.json").write_text(json.dumps(
        [{"start": round(a, 2), "end": round(b, 2), "text": s} for a, b, s in timeline], ensure_ascii=False, indent=1),
        encoding="utf-8")
    return video, total


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("scenes", nargs="+")
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    ids = list(SCENES) if args.scenes == ["all"] else args.scenes
    for scene_id in ids:
        video, total = render(scene_id, args.out)
        print(scene_id, f"{total:.1f}s", video)


if __name__ == "__main__":
    main()
