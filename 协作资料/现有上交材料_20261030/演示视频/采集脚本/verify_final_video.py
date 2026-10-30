"""Check a finished video against the official file specifications, locally.

Usage: python verify_final_video.py path/to/final.mp4 [--report result.json]
Requires ffprobe and ffmpeg on PATH, explicit flags, or the local toolchain config.
Exit codes: 0 = technical checks passed, 1 = failed, 2 = missing/tool error.
Content, privacy and audio intelligibility still need a complete human review.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from fractions import Fraction
import json
from pathlib import Path
import shutil
import subprocess


MIN_SECONDS = 180.0
MAX_SECONDS = 300.0
MAX_BYTES = 300_000_000  # Conservative decimal interpretation of the official 300 MB.
MP4_BRANDS = {"isom", "iso2", "iso3", "iso4", "iso5", "iso6", "iso7", "iso8", "iso9",
              "mp41", "mp42", "avc1", "dash", "msdh", "msix", "M4V ", "F4V "}


def resolve_tool(name: str, override: str | None) -> str:
    if override:
        return override
    found = shutil.which(name)
    if found:
        return found
    config_path = Path("D:/Tools/ClaudeToolchain/config/tools.json")
    if config_path.is_file():
        config = json.loads(config_path.read_text(encoding="utf-8-sig"))
        if config.get(name):
            return config[name]
    raise FileNotFoundError(f"{name} unavailable; pass --{name} or add it to PATH")


def seconds(value: object) -> float | None:
    try:
        parsed = float(value)
        return parsed if 0 <= parsed < float("inf") else None
    except (TypeError, ValueError):
        return None


def check_video(path: Path, ffprobe: str | None, ffmpeg: str | None) -> tuple[dict, int]:
    result = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "file": path.name,
        "status": "missing",
        "official_source": "https://www.aicomp.cn/tracks/tracks-5/5169.html",
        "source_location": "附件1，第2页，第4项演示视频；匿名和真实性要求见第1页",
        "scope": "Local final-file specifications and full audio/video decode only",
        "limits": {"format": "MP4", "duration_seconds_inclusive": [MIN_SECONDS, MAX_SECONDS],
                   "maximum_bytes": MAX_BYTES, "size_interpretation": "300 MB = 300,000,000 bytes"},
        "manual_review_required": [
            "完整、清楚展示梧桐平台注册、发现、互联、访问流程",
            "清楚展示作品功能、实现流程与应用效果",
            "包含平台后台访问数据截图，标明真实来源和统计时间",
            "逐段核对数据、来源、不同采集时点及倍速/省略标注",
            "完整观看画面与声音：不含学校名、学校LOGO、指导教师信息及其他需保护的身份或凭据",
            "检查字幕可读、旁白清晰、关键请求和返回结果可辨认",
        ],
        "upload_performed": False,
    }
    if not path.is_file():
        result["error"] = "Final video file does not exist; no compliance pass recorded."
        return result, 2

    checks = {
        "mp4_extension": path.suffix.lower() == ".mp4",
        "size_at_most_300MB": 0 < path.stat().st_size <= MAX_BYTES,
    }
    result["bytes"] = path.stat().st_size
    result["checks"] = checks
    try:
        probe_tool = resolve_tool("ffprobe", ffprobe)
        decode_tool = resolve_tool("ffmpeg", ffmpeg)
        probe_run = subprocess.run(
            [probe_tool, "-v", "error", "-show_format", "-show_streams", "-of", "json", str(path)],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        if probe_run.returncode:
            result.update(status="failed", error="ffprobe could not read the media file",
                          probe_error=probe_run.stderr[-2000:])
            return result, 1
        probe = json.loads(probe_run.stdout)
        media_format = probe.get("format", {})
        tags = media_format.get("tags", {})
        major_brand = tags.get("major_brand", "")
        compatible = tags.get("compatible_brands", "")
        compatible_brands = [compatible[i:i + 4] for i in range(0, len(compatible), 4)]
        # ffprobe uses one demuxer name for MOV/MP4/3GP. Check the actual file brands too.
        checks["mp4_container"] = (
            "mp4" in media_format.get("format_name", "").split(",")
            and major_brand in MP4_BRANDS
        )
        result["container"] = {"format_name": media_format.get("format_name"),
                               "major_brand": major_brand, "compatible_brands": compatible_brands}
        if not checks["mp4_container"]:
            result["container_note"] = "Not a recognized MP4 brand; an extension alone is insufficient."

        duration = seconds(media_format.get("duration"))
        result["duration_seconds"] = duration
        checks["duration_3_to_5_minutes"] = duration is not None and MIN_SECONDS <= duration <= MAX_SECONDS
        streams = [stream for stream in probe.get("streams", [])
                   if stream.get("codec_type") == "video" and not stream.get("disposition", {}).get("attached_pic")]
        checks["has_video_stream"] = bool(streams)
        if not streams:
            result["status"] = "failed"
            return result, 1

        stream = streams[0]
        video_duration = seconds(stream.get("duration"))
        if video_duration is not None:
            checks["video_track_3_to_5_minutes"] = MIN_SECONDS <= video_duration <= MAX_SECONDS
        rate = stream.get("avg_frame_rate", "0/1")
        try:
            fps = float(Fraction(rate))
        except (ValueError, ZeroDivisionError):
            fps = None
        result["video"] = {"codec": stream.get("codec_name"), "width": stream.get("width"),
                           "height": stream.get("height"), "frame_rate": rate,
                           "duration_seconds": video_duration}
        result["audio_streams"] = sum(s.get("codec_type") == "audio" for s in probe.get("streams", []))
        result["production_recommendations_not_official_requirements"] = {
            "1920x1080": (stream.get("width"), stream.get("height")) == (1920, 1080),
            "25_fps": fps == 25,
        }
        decode_run = subprocess.run(
            [decode_tool, "-hide_banner", "-nostdin", "-v", "error", "-xerror", "-i", str(path),
             "-map", f"0:{stream['index']}", "-map", "0:a?", "-f", "null", "-"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", check=False,
        )
        checks["full_video_and_audio_decode"] = decode_run.returncode == 0 and not decode_run.stderr.strip()
        if not checks["full_video_and_audio_decode"]:
            result["decode_error"] = decode_run.stderr[-2000:]
        result["status"] = "technical_checks_passed" if all(checks.values()) else "failed"
        result["overall_official_compliance"] = "not_determined_requires_manual_review"
        return result, 0 if all(checks.values()) else 1
    except (OSError, ValueError, KeyError) as exc:
        result.update(status="tool_error", error=str(exc))
        return result, 2


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video", type=Path, help="Finished MP4 file; source clips are not a final-video substitute")
    parser.add_argument("--report", type=Path, help="Optional JSON output; nothing is written by default")
    parser.add_argument("--ffprobe", help="Path to ffprobe")
    parser.add_argument("--ffmpeg", help="Path to ffmpeg")
    args = parser.parse_args()
    if args.report and args.report.resolve() == args.video.resolve():
        parser.error("--report must not overwrite the input video")
    result, code = check_video(args.video, args.ffprobe, args.ffmpeg)
    rendered = json.dumps(result, ensure_ascii=False, indent=2) + "\n"
    if args.report:
        args.report.write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return code


if __name__ == "__main__":
    raise SystemExit(main())
