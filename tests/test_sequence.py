import base64
import hashlib
import json
from pathlib import Path
import subprocess

import pytest

from engine.project import Store
from engine.sequence import clip_frames
from engine.service import dispatch
from media.tools import binary, capture_time, probe


@pytest.fixture(scope="module")
def files(tmp_path_factory):
    directory = tmp_path_factory.mktemp("여러 원본")
    paths = []
    for name, color, size, fps, duration, stamp, audio in (
        ("첫 장면", "red", "320x180", 24, 1, "2025-05-02T01:03:00Z", True),
        ("세로 장면", "blue", "180x320", 25, 1.5, "2025-05-02T01:01:00Z", False),
        ("마지막", "green", "320x180", 30, .8, None, False),
    ):
        path = directory / (name + ".mp4")
        args = [binary("ffmpeg"), "-v", "error", "-f", "lavfi", "-i", f"color={color}:s={size}:r={fps}:d={duration}"]
        if audio:
            args += ["-f", "lavfi", "-i", f"sine=f=440:r=48000:d={duration}", "-c:a", "aac"]
        if stamp:
            args += ["-metadata", f"creation_time={stamp}"]
        args += ["-c:v", "libx264", "-threads", "2", "-pix_fmt", "yuv420p", str(path)]
        subprocess.run(args, check=True)
        paths.append(path)
    return paths


def test_capture_time_prefers_quicktime_and_compares_time_zones():
    assert capture_time({"com.apple.quicktime.creationdate": "2025-05-02T10:00:00+09:00",
                         "creation_time": "2025-05-01T10:00:00Z"}) == capture_time(
        {"creation_time": "2025-05-02T01:00:00Z"})
    assert capture_time({"creation_time": "invalid"}) is None


def test_sorting_fallback_exclusion_stale_update_and_undo(tmp_path, files):
    def call(action, **fields):
        return dispatch({"root": str(tmp_path), "action": action, **fields})
    p = call("createSequence", sources=[str(f) for f in files[:2]])["project"]
    assert p["sortOrder"] == "capture"
    assert [c["name"] for c in p["clips"]] == [files[1].name, files[0].name]
    assert call("get", id=p["id"])["project"]["clips"] == p["clips"]
    result = call("createSequence", sources=[str(f) for f in files])["project"]
    assert result["sortOrder"] == "import"
    assert [c["name"] for c in result["clips"]] == [f.name for f in files]
    with pytest.raises(ValueError, match="두 번"):
        call("createSequence", sources=[str(files[0])] * 2)
    left, right = p["clips"]
    rows = [{"id": right["id"], "enabled": True}, {"id": left["id"], "enabled": False}]
    edited = call("editSequence", id=p["id"], revision=0, rows=rows)
    assert edited["audit"]["outputDuration"] == 1
    assert edited["project"]["clips"][1]["source"] == left["source"]
    with pytest.raises(ValueError, match="다시 선택"):
        call("editSequence", id=p["id"], revision=0, rows=rows)
    with pytest.raises(ValueError, match="한 개 이상"):
        call("editSequence", id=p["id"], revision=1, rows=[dict(row, enabled=False) for row in rows])
    assert call("undo", id=p["id"])["project"]["clips"] == p["clips"]


@pytest.mark.integration
def test_sequence_mp4_video_order_mixed_orientation_audio_and_caption_sync(tmp_path, files):
    digests = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]
    def call(action, **fields):
        return dispatch({"root": str(tmp_path), "action": action, **fields})
    project = call("createSequence", sources=[str(path) for path in files[::-1]])["project"]
    clips = list(reversed(project["clips"]))
    for index, clip in enumerate(clips):
        clip["captions"] = [{"id": "c0", "start": .3, "end": .6, "text": f"장면 {index+1}"}]
    project["clips"] = clips
    clips[2]["enabled"] = False
    project["settings"]["resolution"] = "720"
    Store(tmp_path).save(project)
    identifier = project["id"]
    preview = call("sequencePreview", id=identifier, revision=0, clipId=clips[0]["id"])
    assert preview["path"] == str(files[0])
    edited = call("sequenceCaption", id=identifier, revision=0, clipId=clips[1]["id"], captionId="c0", text="교정한 세로 클립")
    preview = call("sequenceConnection", id=identifier, revision=1, clipId=clips[0]["id"])
    assert preview["joinAt"] == 1 and preview["to"] == files[1].name
    preview_file = tmp_path / "연결부.mp4"
    preview_file.write_bytes(base64.b64decode(preview["video"]))
    expected = sum(clip_frames(clip) for clip in clips if clip["enabled"]) / 30
    assert probe(preview_file)["duration"] == pytest.approx(expected, abs=.10)
    output = call("render", id=identifier)["project"]["output"]
    result = probe(output["path"])
    assert result["duration"] == pytest.approx(expected, abs=.10)
    assert (result["width"], result["height"], result["fps"], result["hasAudio"]) == (1280, 720, 30, True)

    def pixel(time, x, y):
        return subprocess.check_output([binary("ffmpeg"), "-v", "error", "-ss", str(time), "-i", output["path"],
                                        "-vf", f"crop=2:2:{x}:{y},format=rgb24", "-frames:v", "1", "-f", "rawvideo", "-"])[:3]
    assert pixel(.2, 640, 120)[0] > 220
    assert pixel(1.2, 640, 120)[2] > 220
    assert max(pixel(1.2, 40, 120)) < 15

    def sound(time):
        return subprocess.check_output([binary("ffmpeg"), "-v", "error", "-ss", str(time), "-i", output["path"],
                                        "-vn", "-t", "0.2", "-f", "s16le", "-"])
    assert any(sound(.3)) and not any(sound(1.3))
    captions = Path(output["srt"]).read_text(encoding="utf-8-sig")
    assert "00:00:01,300 --> 00:00:01,600\n교정한 세로 클립" in captions
    assert "장면 3" not in captions
    report = json.loads(Path(output["report"]).read_text(encoding="utf-8"))
    assert [row["start"] for row in report["timeline"]] == [0, 1]
    assert report["revision"] == edited["project"]["revision"]
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in files] == digests
