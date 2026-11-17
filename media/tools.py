from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path

EXTENSIONS = {".mp4", ".mov", ".avi", ".mkv"}


def binary(name):
    suffix = ".exe" if sys.platform == "win32" else ""
    configured = os.environ.get("LOCALCUT_MEDIA_DIR")
    if configured:
        path = Path(configured) / (name + suffix)
        if path.is_file():
            return str(path)
        raise RuntimeError(f"필수 구성요소 {name}를 찾지 못했습니다. 앱을 다시 설치해 주세요.")
    result = shutil.which(name)
    if not result:
        raise RuntimeError(f"{name} 실행 파일이 없습니다.")
    return result


def run(args, **kwargs):
    kwargs.setdefault("encoding", "utf-8")
    kwargs.setdefault("errors", "replace")
    kwargs.setdefault("capture_output", True)
    if sys.platform == "win32":
        kwargs["creationflags"] = subprocess.CREATE_NO_WINDOW
    result = subprocess.run(args, **kwargs)
    if result.returncode:
        raise RuntimeError("영상 처리 실패: " + result.stderr[-2500:])
    return result


def probe(filename):
    path = Path(filename).resolve(strict=True)
    if path.suffix.lower() not in EXTENSIONS or not path.is_file():
        raise ValueError("MP4, MOV, AVI, MKV 영상만 지원합니다.")
    data = json.loads(run([binary("ffprobe"), "-v", "error", "-show_streams", "-show_format", "-of", "json", str(path)]).stdout)
    video = next((s for s in data["streams"] if s["codec_type"] == "video" and not s.get("disposition", {}).get("attached_pic")), None)
    if not video:
        raise ValueError("영상 스트림이 없는 파일입니다.")
    duration = float(data.get("format", {}).get("duration") or video.get("duration") or 0)
    if not math.isfinite(duration) or duration <= 0 or duration > 24*60*60:
        raise ValueError("영상 길이를 확인할 수 없거나 24시간을 초과했습니다.")
    n, _, d = video.get("avg_frame_rate", "30/1").partition("/")
    fps = float(n) / (float(d or 1) or 1)
    rotation = next((int(s.get("rotation", 0)) for s in video.get("side_data_list", []) if "rotation" in s), int(video.get("tags", {}).get("rotate", 0)))
    w, h = video["width"], video["height"]
    if abs(rotation) % 180 == 90:
        w, h = h, w
    return {"path": str(path), "duration": duration, "width": w, "height": h,
            "fps": fps if 0 < fps <= 240 else 30, "aspect": f"{w // math.gcd(w,h)}:{h // math.gcd(w,h)}",
            "hasAudio": any(s["codec_type"] == "audio" for s in data["streams"]),
            "audioCodec": next((s["codec_name"] for s in data["streams"] if s["codec_type"]=="audio"),None),
            "bytes": path.stat().st_size, "mtimeNs": path.stat().st_mtime_ns,
            "codec": video.get("codec_name", "unknown")}


def verify_source(source):
    path = Path(source["path"])
    if not path.is_file():
        raise ValueError("원본 영상을 찾을 수 없습니다. 원래 위치에 복원해 주세요.")
    stat = path.stat()
    if stat.st_size != source["bytes"] or stat.st_mtime_ns != source["mtimeNs"]:
        raise ValueError("원본 파일이 변경되었습니다. 새 작업으로 다시 불러와 주세요.")


def extract_audio(source, target):
    run([binary("ffmpeg"), "-nostdin", "-v", "error", "-y", "-i", source, "-map", "0:a:0",
         "-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(target)])
