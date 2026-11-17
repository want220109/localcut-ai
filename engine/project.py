from __future__ import annotations

import copy
import json
import math
import os
import re
import time
import uuid
from pathlib import Path

from subtitles.styles import with_defaults, validate_style

SCHEMA = 1
ID_RE = re.compile(r"^[a-f0-9]{32}$")


def finite(value, low=0, high=10**9):
    if isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value) or not low <= value <= high:
        raise ValueError("허용 범위를 벗어난 숫자입니다.")
    return float(value)


def atomic_json(path: Path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp-" + uuid.uuid4().hex)
    try:
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2, allow_nan=False)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def validate(p):
    if p.get("schema") != SCHEMA:
        raise ValueError("지원하지 않는 작업 파일 버전입니다. 원래 버전의 앱으로 열어 주세요.")
    if not ID_RE.fullmatch(p.get("id", "")):
        raise ValueError("잘못된 작업 ID입니다.")
    duration = finite(p["source"]["duration"], 0.001)
    if p["style"] not in {"basic", "fast", "shorts"}:
        raise ValueError("알 수 없는 편집 스타일입니다.")
    for key in ("cuts", "transcript", "captions"):
        if not isinstance(p[key], list) or len(p[key]) > 100000:
            raise ValueError("작업 데이터가 너무 크거나 손상되었습니다.")
        seen = set()
        for item in p[key]:
            a, b = finite(item["start"], 0, duration), finite(item["end"], 0, duration)
            if b <= a or item["id"] in seen:
                raise ValueError("구간 시작·종료 또는 ID가 잘못되었습니다.")
            seen.add(item["id"])
            if "text" in item and (not isinstance(item["text"], str) or len(item["text"]) > 10000):
                raise ValueError("자막이 너무 깁니다.")
            if key == "cuts" and (type(item.get("enabled")) is not bool or type(item.get("review")) is not bool):
                raise ValueError("삭제 구간 상태가 잘못되었습니다.")
    settings = p["settings"] = with_defaults(p["settings"])
    validate_style(settings)
    finite(settings["fontSize"], 18, 100)
    finite(settings["outline"], 0, 6)
    finite(settings["zoom"], 1, 1.2)
    if settings["resolution"] not in {"source", "720", "1080"} or settings["aspect"] not in {"source", "16:9", "9:16", "1:1"}:
        raise ValueError("출력 화면 설정이 잘못되었습니다.")
    if settings["quality"] not in {"high", "balanced", "small"} or settings["position"] not in {"bottom", "middle", "top"}:
        raise ValueError("자막 위치 또는 화질이 잘못되었습니다.")
    if not re.fullmatch(r"#[0-9a-fA-F]{6}", settings["color"]):
        raise ValueError("잘못된 자막 색상입니다.")
    for key in ("subtitles", "background", "denoise", "normalize"):
        if type(settings[key]) is not bool:
            raise ValueError("잘못된 출력 옵션입니다.")
    if not keeps(p):
        raise ValueError("영상 전체를 삭제할 수 없습니다.")
    return p


def merged_ranges(cuts, duration):
    ranges = sorted((max(0, c["start"]), min(duration, c["end"])) for c in cuts if c["enabled"])
    result = []
    for a, b in ranges:
        if b <= a:
            continue
        if result and a <= result[-1][1] + 1e-6:
            result[-1][1] = max(b, result[-1][1])
        else:
            result.append([a, b])
    return result


def keeps(p):
    duration = p["source"]["duration"]
    cursor, result = 0.0, []
    for a, b in merged_ranges(p["cuts"], duration):
        if a - cursor > 0.001:
            result.append([cursor, a])
        cursor = b
    if duration - cursor > 0.001:
        result.append([cursor, duration])
    return result


def output_duration(p):
    return sum(b-a for a, b in keeps(p))


def transcript_audit(p):
    intervals = keeps(p)
    before, after, removed, partial = [], [], [], []
    for s in p["transcript"]:
        before.append(s["text"])
        retained = sum(max(0, min(b, s["end"]) - max(a, s["start"])) for a, b in intervals)
        ratio = retained / (s["end"] - s["start"])
        if ratio >= .98:
            after.append(s["text"])
        elif ratio <= .02:
            removed.append({"id": s["id"], "text": s["text"], "important": s.get("important", False)})
        else:
            partial.append({"id": s["id"], "text": s["text"], "retained": round(ratio, 3)})
    return {"before": "\n".join(before), "after": "\n".join(after), "removed": removed, "partial": partial,
            "importantRemoved": sum(s["important"] for s in removed), "outputDuration": output_duration(p)}


class Store:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)

    def directory(self, project_id):
        if not isinstance(project_id, str) or not ID_RE.fullmatch(project_id):
            raise ValueError("잘못된 작업 ID입니다.")
        path = self.root / "jobs" / project_id
        if path.is_symlink():
            raise ValueError("작업 폴더에 심볼릭 링크를 사용할 수 없습니다.")
        return path

    def load(self, project_id):
        path = self.directory(project_id) / "project.json"
        if path.stat().st_size > 50*1024*1024:
            raise ValueError("작업 파일이 너무 큽니다.")
        return validate(json.loads(path.read_text(encoding="utf-8")))

    def save(self, p, snapshot=False):
        validate(p)
        directory = self.directory(p["id"])
        target = directory / "project.json"
        if snapshot and target.exists():
            atomic_json(directory / "previous.json", json.loads(target.read_text(encoding="utf-8")))
        p["updatedAt"] = time.time()
        atomic_json(target, p)
        return p

    def create(self, source):
        p = {"schema": SCHEMA, "id": uuid.uuid4().hex, "name": Path(source["path"]).stem,
             "createdAt": time.time(), "updatedAt": time.time(), "source": source, "style": "basic",
             "analyzed": False, "transcript": [], "captions": [], "cuts": [], "scenes": [], "motion": [],
             "warnings": [], "model": None, "output": None, "revision": 0,
             "settings": {"subtitles": True, "fontSize": 48, "color": "#FFFFFF", "outline": 2,
                          "background": False, "position": "bottom", "resolution": "source", "aspect": "source",
                          "quality": "balanced", "zoom": 1.0, "denoise": True, "normalize": True}}
        return self.save(p)

    def list(self):
        result = []
        for f in (self.root / "jobs").glob("*/project.json"):
            try:
                p = self.load(f.parent.name)
                result.append({k: p[k] for k in ("id", "name", "updatedAt", "analyzed")})
            except (ValueError, OSError, KeyError, TypeError):
                continue
        return sorted(result, key=lambda p: p["updatedAt"], reverse=True)

    def edit(self, project_id, changes):
        p = self.load(project_id)
        # Never accept source paths, generated output paths or arbitrary project keys from UI.
        allowed = {"style", "settings", "cuts", "captions", "name"}
        if set(changes) - allowed:
            raise ValueError("허용하지 않는 작업 변경입니다.")
        updated = copy.deepcopy(p)
        for key, value in changes.items():
            if key == "settings":
                if set(value) - set(p["settings"]):
                    raise ValueError("알 수 없는 설정입니다.")
                updated[key].update(value)
            else:
                updated[key] = value
        updated["revision"] += 1
        return self.save(updated, snapshot=True)

    def undo(self, project_id):
        p = json.loads((self.directory(project_id) / "previous.json").read_text(encoding="utf-8"))
        # An undo changes the edit revision so old previews are labelled as stale.
        p["revision"] = self.load(project_id)["revision"] + 1
        return self.save(p, snapshot=True)
