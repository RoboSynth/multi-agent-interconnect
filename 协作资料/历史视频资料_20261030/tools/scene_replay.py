"""S05: real AIP task replay of the cloud F10 incident, driven by data/f10_replay.json.

Every packet is one real task; times follow the real timestamps through a
piecewise time warp (idle gap skipped, the 30-second verification compressed),
and the current playback speed is always shown on screen.
"""
import json
import math
from pathlib import Path

from engine import (C, DIM, GREEN, INK, RED, SUB, W, H, background, chip, dot, ease, ease_io, panel, seg,
                    text, text_width)

DATA = json.loads((Path(__file__).resolve().parents[1] / "data/f10_replay.json").read_text(encoding="utf-8"))
TASKS = DATA["tasks"]
REAL_END = TASKS[-1]["end"]
AMBER = (1.0, 0.74, 0.25)

COORD = (290, 470)
HUB = (760, 470)
DOMAINS = {"app": (1180, 250), "db": (1180, 420), "ops": (1180, 590), "ver": (1180, 760)}
NAMES = {"app": "应用智能体", "db": "数据库智能体", "ops": "运维智能体", "ver": "业务验证智能体"}
ROLE_ZH = {"app": "应用", "db": "数据库", "ops": "运维", "ver": "业务验证"}
MODIFY = {"ops.route_rollback", "db.restore_writes", "application.pool_rebuild"}
PHASES = [(0.0, 3.6, "① 能力确认"), (14.6, 23.3, "② 并行取证"), (23.3, 24.7, "③ 证据收敛"),
          (24.7, 28.3, "④ 按依赖修复"), (28.6, REAL_END, "⑤ 30 秒真实订单验证")]


def facts():
    """Log line shown when each task returns (F10: stale route + read-only database)."""
    seen, out = {}, []
    for task in TASKS:
        r, n = task["route"], seen.get(task["route"], 0)
        seen[r] = n + 1
        d = ROLE_ZH[task["domain"]]
        line, color = {
            "describe": (f"{d} · 能力与资源范围确认", SUB),
            "ops.containers": ("运维 · 应用容器运行中", SUB),
            "ops.route_status": ("运维 · 入口指向 v1 旧版本", RED) if n == 0 else ("运维 · 入口已回到 v2", GREEN),
            "application.status": ("应用 · 应用本身可达", SUB) if n == 0 else ("应用 · 新连接写入正常", GREEN),
            "db.read_only_status": ("数据库 · 只读模式开启", RED) if n == 0 else ("数据库 · 已恢复读写", GREEN),
            "db.blocking_sessions": ("数据库 · 无阻塞会话", SUB),
            "ops.route_rollback": ("修改 · 运维回退入口路由", AMBER),
            "db.restore_writes": ("修改 · 数据库恢复读写（签名审批）", AMBER),
            "application.pool_rebuild": ("修改 · 应用重建连接池", AMBER),
            "incident.verification": ("验证 · 30 秒 / 10 个完整流程通过", GREEN),
        }[r]
        out.append((line, color))
    return out


FACTS = facts()


class Replay:
    def prepare(self, total, timeline):
        self.total = total
        a, b = 1.4, total - 4.2
        span = b - a
        # (real seconds, video seconds) keyframes; the 11 s idle gap is skipped.
        self.keys = [(0.0, a), (3.6, a + span * .16), (14.6, a + span * .21),
                     (28.6, a + span * .66), (REAL_END, b)]

    def v(self, r):
        for (r0, v0), (r1, v1) in zip(self.keys, self.keys[1:]):
            if r <= r1:
                if r < r0:  # inside the skipped gap
                    return v0
                return v0 + (v1 - v0) * (r - r0) / (r1 - r0) if r1 > r0 else v0
        return self.keys[-1][1]

    def real(self, t):
        if t <= self.keys[0][1]:
            return 0.0, 1.0
        for (r0, v0), (r1, v1) in zip(self.keys, self.keys[1:]):
            if t <= v1:
                speed = (r1 - r0) / (v1 - v0)
                return r0 + (t - v0) * speed, speed
        return REAL_END, 1.0

    def times(self, task):
        s = self.v(task["start"])
        e = max(self.v(task["end"]), s + .7)
        return s, e

    def sfx_times(self):
        out = []
        for task in TASKS:
            s, e = self.times(task)
            out += [s + .5, e + .5]
        return out

    # ---------------------------------------------------------- geometry
    @staticmethod
    def path_point(points, s):
        """Point at fraction s along a polyline."""
        lengths = [math.dist(a, b) for a, b in zip(points, points[1:])]
        target = s * sum(lengths)
        for (a, b), length in zip(zip(points, points[1:]), lengths):
            if target <= length:
                k = target / length if length else 0
                return a[0] + (b[0] - a[0]) * k, a[1] + (b[1] - a[1]) * k
            target -= length
        return points[-1]

    @staticmethod
    def route(domain):
        x, y = DOMAINS[domain]
        mid = (HUB[0] + 170, HUB[1] + (y - HUB[1]) * .55)
        return [COORD, (HUB[0] - 110, HUB[1]), (HUB[0] + 110, HUB[1]), mid, (x - 150, y)]

    # ---------------------------------------------------------- draw
    def draw(self, cx, gx, t, total):
        background(cx, t)
        real, speed = self.real(t)
        intro = seg(t, 0, .8)
        text(cx, 110, 92, "真实运行回放 · 复合故障", 46, INK, intro, True)
        text(cx, 110, 146, "梧桐平台 AIP 群组 · 云端 · 每个光点是一个真实任务（数据来自双端 access 日志）", 24, SUB, intro)
        self.draw_clock(cx, t, real, speed, intro)

        # links
        for domain in DOMAINS:
            pts = self.route(domain)
            cx.move_to(*pts[2])
            for p in pts[3:]:
                cx.line_to(*p)
            cx.set_source_rgba(*C[domain], .18 * intro)
            cx.set_line_width(2)
            cx.stroke()
        cx.move_to(*COORD)
        cx.line_to(HUB[0] - 110, HUB[1])
        cx.set_source_rgba(*C["coord"], .25 * intro)
        cx.set_line_width(2)
        cx.stroke()

        active = {}
        for task in TASKS:
            s, e = self.times(task)
            if s <= t <= e + .5:
                active.setdefault(task["domain"], []).append(task)

        # nodes
        k = seg(t, .2, .8)
        dot(cx, *COORD, 74, C["coord"], .14 * k)
        cx.arc(*COORD, 74, 0, 2 * math.pi)
        cx.set_source_rgba(*C["coord"], .9 * k)
        cx.set_line_width(3)
        cx.stroke()
        text(cx, COORD[0], COORD[1] - 10, "协调", 34, INK, k, True, "center")
        text(cx, COORD[0], COORD[1] + 26, "零资源凭据", 20, SUB, k, align="center")
        panel(cx, HUB[0] - 110, HUB[1] - 64, 220, 128, C["wt"], k, r=22, fill=.10)
        text(cx, HUB[0], HUB[1] - 16, "梧桐平台", 32, INK, k, True, "center")
        text(cx, HUB[0], HUB[1] + 26, "AMQPS · ADP · AMP", 19, SUB, k, align="center")
        for i, (domain, (x, y)) in enumerate(DOMAINS.items()):
            kk = seg(t, .4 + i * .15, .7)
            busy = domain in active
            pulse = .5 + .5 * math.sin(t * 9) if busy else 0
            panel(cx, x - 150, y - 52, 300, 104, C[domain], kk, r=18, fill=.12 + .10 * pulse)
            text(cx, x - 120, y - 12, NAMES[domain], 28, INK, kk, True)
            dot(cx, x + 118, y - 14, 8, C[domain] if busy else DIM, kk)
            if busy:
                dot(gx, x + 118, y - 14, 16, C[domain], .9)
                text(cx, x - 120, y + 26, active[domain][-1]["route"], 20, C[domain], kk)
            else:
                text(cx, x - 120, y + 26, "空闲", 20, DIM, kk)

        # packets: request (coordinator colour) and reply (domain colour)
        for task in TASKS:
            s, e = self.times(task)
            pts = self.route(task["domain"])
            if s <= t <= s + .55:
                p = self.path_point(pts, ease_io((t - s) / .55))
                color = AMBER if task["route"] in MODIFY else C["coord"]
                dot(cx, *p, 9, color)
                dot(gx, *p, 18, color, .9)
            if e <= t <= e + .55:
                p = self.path_point(pts[::-1], ease_io((t - e) / .55))
                dot(cx, *p, 8, C[task["domain"]])
                dot(gx, *p, 16, C[task["domain"]], .8)

        self.draw_phase(cx, real, t)
        self.draw_log(cx, t)
        self.draw_timeline(cx, t, real)
        self.draw_summary(cx, gx, t, total)

    def draw_clock(self, cx, t, real, speed, a):
        seconds = 3 * 3600 + 60 + 52.542 + real + 8 * 3600  # Beijing time of t0 = 11:01:52.54
        h, m, s = int(seconds // 3600) % 24, int(seconds // 60) % 60, seconds % 60
        text(cx, 1810, 86, f"{h:02d}:{m:02d}:{s:05.2f}", 44, INK, a, True, "right")
        gap = 3.6 < real < 14.6
        label = "北京时间 2026-10-20" + ("   跳过空闲" if gap else "" if speed < 1.5 else f"   ×{speed:.0f} 加速")
        text(cx, 1810, 134, label, 22, AMBER if speed >= 1.5 else SUB, a, align="right")

    def draw_phase(self, cx, real, t):
        for a, b, label in PHASES:
            if a <= real <= b + .3:
                k = min(1, (real - a) * 4 + .2)
                chip(cx, HUB[0], 300, label, C["wt"], min(1, k), 28, "center")
                return
        if 3.6 < real < 14.6 or (self.keys[1][1] < t < self.keys[2][1]):
            chip(cx, HUB[0], 300, "⋯ 跳过 11 秒空闲", DIM, 1, 24, "center")

    def draw_log(self, cx, t):
        x0, y0, w, hgt = 1400, 196, 430, 620
        panel(cx, x0, y0, w, hgt, C["wt"], seg(t, .6, .8), r=18, fill=.05, stroke=1.2)
        text(cx, x0 + 24, y0 + 34, "证据与动作", 24, SUB, seg(t, .6, .8), True)
        shown = [(i, self.times(task)[1]) for i, task in enumerate(TASKS) if self.times(task)[1] + .45 <= t]
        rows = shown[-12:]
        for j, (i, e) in enumerate(rows):
            line, color = FACTS[i]
            k = seg(t, e + .45, .4)
            y = y0 + 80 + j * 44
            dot(cx, x0 + 30, y, 6, color, k)
            text(cx, x0 + 48, y, line, 21, INK if color != SUB else SUB, k)

    def draw_timeline(self, cx, t, real):
        x0, x1, y = 140, 1780, 892
        cx.set_source_rgba(1, 1, 1, .12)
        cx.rectangle(x0, y - 2, x1 - x0, 4)
        cx.fill()
        scale = lambda r: x0 + (x1 - x0) * r / REAL_END
        for task in TASKS:
            xs, xe = scale(task["start"]), max(scale(task["end"]), scale(task["start"]) + 5)
            done = task["start"] <= real
            cx.rectangle(xs, y - 12, xe - xs, 24)
            cx.set_source_rgba(*(AMBER if task["route"] in MODIFY else C[task["domain"]]), .9 if done else .22)
            cx.fill()
        px = scale(min(real, REAL_END))
        cx.rectangle(px - 1.5, y - 26, 3, 52)
        cx.set_source_rgba(*INK, .9)
        cx.fill()
        text(cx, x0, y + 40, "0 s", 18, SUB)
        text(cx, x1, y + 40, f"{REAL_END:.0f} s", 18, SUB, align="right")
        text(cx, scale(43), y + 40, "真实订单流程 30 秒", 18, SUB, align="center")

    def draw_summary(self, cx, gx, t, total):
        k = seg(t, total - 3.6, .6)
        if k <= 0:
            return
        cx.set_source_rgba(0.02, 0.03, 0.06, .88 * k)
        cx.rectangle(0, 0, W, H)
        cx.fill()
        from engine import rounded
        rounded(cx, 380, 320, 1160, 360, 28)
        cx.set_source_rgba(0.03, 0.08, 0.07, k)
        cx.fill()
        panel(cx, 380, 320, 1160, 360, GREEN, k, r=28, fill=.10, stroke=3)
        text(cx, 960, 405, "业务已恢复", 60, GREEN, k, True, "center")
        dot(gx, 960, 405, 60, GREEN, .35 * k)
        stats = [("17", "个平台任务"), ("3", "次修改"), ("0", "次多余操作"), ("0", "份凭据离开所属域")]
        for i, (n, label) in enumerate(stats):
            x = 520 + i * 293
            text(cx, x, 525, n, 64, INK, k, True, "center")
            text(cx, x, 595, label, 24, SUB, k, align="center")


SCENE = Replay()
LINES = ["这是云端一次真实故障处理的回放，每个光点都是梧桐平台上的一个真实任务。",
         "协调者先确认四个参与者的能力，再并行向运维、应用和数据库取证。",
         "证据显示：入口被指回了旧版本，同时数据库处于只读模式。",
         "三项修复按依赖依次执行，其中恢复读写经过签名审批。",
         "最后用三十秒真实订单流程确认恢复：十七个任务，三次修改，没有一次多余操作。"]
