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


def test_batch_captions_preserve_edits_and_skip_excluded_clips(tmp_path, files, monkeypatch):
    def call(action, **fields):
        return dispatch({"root": str(tmp_path), "action": action, **fields})

    project = call("createSequence", sources=[str(path) for path in files])["project"]
    red, portrait, green = project["clips"]
    red["captions"] = [{"id": "c0", "start": .1, "end": .6, "text": "교정한 자막", "textEdited": True}]
    green["enabled"] = False
    Store(tmp_path).save(project)

    def unexpected_model(*args, **kwargs):
        pytest.fail("Silent clips and existing captions must bypass the model")

    monkeypatch.setattr("models.manager.ready", unexpected_model)
    result = call("sequenceAnalyzeAll", id=project["id"], revision=0, model="small")
    assert not result["captionFailures"]
    updated = result["project"]
    assert updated["revision"] == 1
    assert updated["clips"][0]["captions"] == red["captions"]
    assert updated["clips"][1] == dict(portrait, analyzed=True)
    assert updated["clips"][2] == green
    assert call("sequenceAnalyzeAll", id=project["id"], revision=1, model="small")["project"] == updated


def test_batch_captions_retry_retains_successful_clips(tmp_path, files, monkeypatch):
    def call(action, **fields):
        return dispatch({"root": str(tmp_path), "action": action, **fields})

    project = call("createSequence", sources=[str(path) for path in files])["project"]
    project["clips"][1]["source"]["hasAudio"] = True
    Store(tmp_path).save(project)
    requested, checked = [], []
    fail_portrait = True

    def ready(root, name, verify):
        checked.append((name, verify))
        return True

    def transcribe(source, root, model, work, progress, *, model_verified):
        assert model_verified
        requested.append(source["path"])
        if source["path"] == str(files[1]) and fail_portrait:
            raise RuntimeError("오디오 실패")
        return [{"id": "s1", "start": .2, "end": .8, "text": "음성을 인식했습니다", "confidence": .9}], [], {"name": model}

    monkeypatch.setattr("models.manager.ready", ready)
    monkeypatch.setattr("engine.analysis.transcribe", transcribe)
    result = call("sequenceAnalyzeAll", id=project["id"], revision=0, model="small")
    updated = Store(tmp_path).load(project["id"])
    assert [clip["analyzed"] for clip in updated["clips"]] == [True, False, True]
    assert result["captionFailures"] == [f"{files[1].name} · 오디오 실패"]
    first_captions = updated["clips"][0]["captions"]
    assert first_captions[0]["text"] == "음성을 인식했습니다"
    assert checked == [("small", True)]

    fail_portrait = False
    result = call("sequenceAnalyzeAll", id=project["id"], revision=updated["revision"], model="small")
    assert not result["captionFailures"]
    assert all(clip["analyzed"] for clip in result["project"]["clips"])
    assert result["project"]["clips"][0]["captions"] == first_captions
    assert requested == list(map(str, (files[0], files[1], files[1])))
    assert checked == [("small", True), ("small", True)]
    undone = call("undo", id=project["id"])["project"]
    assert undone["clips"] == updated["clips"]


@pytest.mark.integration
def test_caption_preview_uses_selected_clip_and_preserves_project(tmp_path, files):
    def call(action, **fields):
        return dispatch({"root": str(tmp_path), "action": action, **fields})
    p = call("createSequence", sources=[str(path) for path in files])["project"]
    red, portrait, _ = p["clips"]
    for clip in (red, portrait):
        clip["captions"] = [{"id": "first", "start": .25, "end": .75, "text": "저장된 문구"}]
    p["settings"]["resolution"] = "720"
    store = Store(tmp_path)
    store.save(p)
    filename = store.directory(p["id"]) / "project.json"
    original = filename.read_bytes()
    values = dict(id=p["id"], revision=0, clipId=portrait["id"])
    first = call("captionFrame", **values, draft=portrait["captions"][0])
    edited = call("captionFrame", **values, draft=dict(portrait["captions"][0], text="정지 화면에서 수정한 자막"))
    assert edited["image"] != first["image"]
    assert edited["sourceTime"] == .5
    png = base64.b64decode(edited["image"].split(",", 1)[1])
    pixels = subprocess.check_output([binary("ffmpeg"), "-v", "error", "-i", "pipe:0", "-vf",
                                     "crop=2:2:20:100,format=rgb24", "-frames:v", "1", "-f", "rawvideo", "-"], input=png)
    assert max(pixels) < 15
    center = subprocess.check_output([binary("ffmpeg"), "-v", "error", "-i", "pipe:0", "-vf",
                                     "crop=2:2:480:100,format=rgb24", "-frames:v", "1", "-f", "rawvideo", "-"], input=png)
    assert center[2] > 220
    assert filename.read_bytes() == original
    with pytest.raises(ValueError, match="다시 선택"):
        call("captionFrame", **dict(values, revision=1), draft=portrait["captions"][0])
    with pytest.raises(ValueError, match="클립"):
        call("captionFrame", **dict(values, clipId="missing"), draft=portrait["captions"][0])


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


@pytest.mark.integration
def test_sequence_ai_cuts_preview_toggle_and_export(tmp_path, files, monkeypatch):
    source = tmp_path / "중간에 긴 침묵이 있는 원본.mp4"
    subprocess.run([binary("ffmpeg"), "-v", "error",
                    "-f", "lavfi", "-i", "color=red:s=320x180:r=25:d=10",
                    "-f", "lavfi", "-i", "sine=f=440:r=48000:d=10",
                    "-af", "volume=0:enable='between(t,2.8,6.35)'",
                    "-c:v", "libx264", "-threads", "2", "-pix_fmt", "yuv420p", "-c:a", "aac", str(source)],
                   check=True)
    original = hashlib.sha256(source.read_bytes()).hexdigest()

    def call(action, **fields):
        return dispatch({"root": str(tmp_path), "action": action, **fields})

    project = call("createSequence", sources=[str(source), str(files[1])])["project"]
    project["settings"]["resolution"] = "720"
    left, right = project["clips"]
    transcript = [
        {"id": "s0", "start": .6, "end": 2.7, "text": "오늘 먹은 메뉴를 소개합니다", "confidence": .95},
        {"id": "s1", "start": 6.45, "end": 8.45, "text": "오늘 먹은 메뉴를 소개합니다", "confidence": .96},
    ]
    left.update(analyzed=True, speech={"transcript": transcript, "vad": [[.55, 2.75], [6.4, 8.5]]},
                captions=[{"id": "c0", "start": .6, "end": 2.7, "text": "오늘의 메뉴입니다", "textEdited": True},
                          {"id": "c1", "start": 6.45, "end": 8.45, "text": "이제 메뉴를 보여드려요", "textEdited": True}])
    right["captions"] = [{"id": "c0", "start": .2, "end": .8, "text": "두 번째 클립"}]
    Store(tmp_path).save(project)
    key = {"id": project["id"], "clipId": left["id"]}

    def unexpected_model(*args, **kwargs):
        pytest.fail("Saved ASR should be reused for edit analysis")

    monkeypatch.setattr("models.manager.ready", unexpected_model)
    analyzed = call("sequenceAnalyzeEdits", id=key["id"], revision=0, model="small")
    assert not analyzed["editFailures"]
    clips = analyzed["project"]["clips"]
    assert clips[0]["captions"] == left["captions"] and clips[0]["speech"]["transcript"] == transcript
    assert clips[1]["cuts"] == [] and "오디오가 없어" in clips[1]["cutNote"]
    silence = next(cut for cut in clips[0]["cuts"] if cut["kind"] == "silence" and cut["enabled"])
    retake = next(cut for cut in clips[0]["cuts"] if cut["kind"] == "retake")
    assert retake["review"] and not retake["enabled"]
    assert 8 < analyzed["audit"]["outputDuration"] < 9
    revision = analyzed["project"]["revision"]

    preview = call("sequenceCutPreview", **key, revision=revision, cutId=silence["id"])
    preview_path = tmp_path / "편집점 미리보기.mp4"
    preview_path.write_bytes(base64.b64decode(preview["video"]))
    assert 2.8 < preview["joinAt"] <= 3 and 5.8 < probe(preview_path)["duration"] < 6.15
    assert Store(tmp_path).load(key["id"])["revision"] == revision
    with pytest.raises(ValueError, match="다시 선택"):
        call("sequenceSetCut", **key, revision=revision - 1, cutId=silence["id"], enabled=False)

    output = call("render", id=key["id"])["project"]["output"]
    assert probe(output["path"])["duration"] == pytest.approx(analyzed["audit"]["outputDuration"], abs=.08)
    assert probe(output["path"])["hasAudio"]
    report = json.loads(Path(output["report"]).read_text(encoding="utf-8"))
    captions = Path(output["srt"]).read_text(encoding="utf-8-sig")
    assert all(text in captions for text in ("오늘의 메뉴입니다", "이제 메뉴를 보여드려요", "두 번째 클립"))
    assert 6.5 < report["timeline"][1]["start"] < 7.5
    assert "00:00:06,450" not in captions

    restored = call("sequenceSetCut", **key, revision=revision, cutId=silence["id"], enabled=False)
    original_length = (clip_frames(left) + clip_frames(right)) / 30
    assert restored["audit"]["outputDuration"] == original_length
    assert restored["project"]["output"]["revision"] != restored["project"]["revision"]
    retry = call("sequenceAnalyzeEdits", id=key["id"], revision=restored["project"]["revision"], model="small")
    assert retry["audit"]["outputDuration"] == original_length
    assert hashlib.sha256(source.read_bytes()).hexdigest() == original


@pytest.mark.integration
def test_longform_outline_reorders_corrected_sections_and_updates_video_and_captions(tmp_path, files):
    from engine.sequence import sequence_timeline

    original_sources = [hashlib.sha256(path.read_bytes()).hexdigest() for path in files]

    def call(action, **fields):
        return dispatch({"root": str(tmp_path), "action": action, **fields})

    project = call("createSequence", sources=[str(files[2]), str(files[1]), str(files[0])])["project"]
    closing, body, opening = project["clips"]
    fallback = call("sequenceOutlineDraft", id=project["id"], revision=0, fresh=True)
    assert not fallback["hasCaptions"]
    assert [row["clipId"] for row in fallback["rows"]] == [clip["id"] for clip in project["clips"]]
    for clip, start, end, text in (
        (closing, .066, .65, "시청해 주셔서 감사합니다"),
        (body, .1, 1.35, "먼저 작업에 필요한 두 가지를 소개합니다"),
        (opening, .1, .8, "안녕하세요 오늘의 브이로그입니다"),
    ):
        clip.update(analyzed=True, captions=[{"id": "c0", "start": start, "end": end, "text": text, "textEdited": True}])
    # Existing AI cuts must survive generation and confirmation.
    opening["cuts"] = [{"id": "kept-edit", "start": .84, "end": .96, "kind": "silence", "enabled": True, "review": False}]
    project["settings"]["resolution"] = "720"
    store = Store(tmp_path)
    store.save(project)
    key = {"id": project["id"], "revision": project["revision"]}
    filename = store.directory(key["id"]) / "project.json"
    original_data = filename.read_bytes()

    draft = call("sequenceOutlineDraft", **key, fresh=True)
    rows = draft["rows"]
    assert draft["hasCaptions"]
    assert [row["role"] for row in rows] == ["도입", "본론", "마무리"]
    assert [row["clipId"] for row in rows] == [opening["id"], body["id"], closing["id"]]
    assert rows[0]["excerpt"] == opening["captions"][0]["text"]
    assert filename.read_bytes() == original_data

    preview = call("sequenceOutlinePreview", **key, fresh=True, rowId=rows[1]["id"])
    preview_file = tmp_path / "본론 미리보기.mp4"
    preview_file.write_bytes(base64.b64decode(preview["video"]))
    assert probe(preview_file)["duration"] == pytest.approx(rows[1]["seconds"], abs=.08)
    assert filename.read_bytes() == original_data

    excluded = [{"id": row["id"], "enabled": False} for row in rows]
    with pytest.raises(ValueError, match="한 개 이상"):
        call("sequenceApplyOutline", **key, fresh=True, rows=excluded)
    assert filename.read_bytes() == original_data
    with pytest.raises(ValueError, match="다시 선택"):
        call("sequenceApplyOutline", id=key["id"], revision=key["revision"] + 1, fresh=True, rows=excluded)

    selected = [{"id": row["id"], "enabled": row["role"] != "본론"} for row in reversed(rows)]
    fixed = call("sequenceApplyOutline", **key, fresh=True, rows=selected)
    assert [item["id"] for item, _ in sequence_timeline(fixed["project"])] == [closing["id"], opening["id"]]
    assert fixed["project"]["clips"] == project["clips"]
    assert fixed["audit"]["outputDuration"] == pytest.approx(rows[0]["seconds"] + rows[2]["seconds"])
    assert fixed["audit"]["after"].splitlines() == [closing["captions"][0]["text"], opening["captions"][0]["text"]]
    result = call("render", id=key["id"])["project"]["output"]
    assert probe(result["path"])["duration"] == pytest.approx(fixed["audit"]["outputDuration"], abs=.08)

    def pixel(time):
        return subprocess.check_output([binary("ffmpeg"), "-v", "error", "-ss", str(time), "-i", result["path"],
                                        "-vf", "crop=2:2:640:120,format=rgb24", "-frames:v", "1", "-f", "rawvideo", "-"])[:3]

    initial = pixel(.25)
    assert initial[1] > 90 and initial[0] < 20
    assert pixel(rows[2]["seconds"] + .25)[0] > 220
    assert "시청해 주셔서 감사합니다" in Path(result["srt"]).read_text(encoding="utf-8-sig")
    assert "먼저 작업" not in Path(result["srt"]).read_text(encoding="utf-8-sig")
    report = json.loads(Path(result["report"]).read_text(encoding="utf-8"))
    assert [row["id"] for row in report["timeline"]] == [closing["id"], opening["id"]]
    reopened = call("sequenceOutlineDraft", id=key["id"], revision=fixed["project"]["revision"], fresh=False)
    assert [(row["id"], row["enabled"]) for row in reopened["rows"]] == [(row["id"], row["enabled"]) for row in selected]
    cleared = call("sequenceClearOutline", id=key["id"], revision=fixed["project"]["revision"])
    assert "sequenceOutline" not in cleared["project"] and cleared["project"]["clips"] == project["clips"]
    undone = call("undo", id=key["id"])["project"]
    assert undone["sequenceOutline"] == fixed["project"]["sequenceOutline"]
    assert [hashlib.sha256(path.read_bytes()).hexdigest() for path in files] == original_sources


def test_longform_outline_splits_a_clip_at_saved_text_boundaries_and_preserves_existing_cut(files, tmp_path):
    from engine.sequence_outline import new_outline

    project = dispatch({"root": str(tmp_path), "action": "createSequence", "sources": [str(path) for path in files]})["project"]
    clip = project["clips"][0]
    # Place both explicit transitions within a single continuous video.
    clip["source"] = dict(clip["source"], duration=30)
    for other in project["clips"][1:]:
        other["source"] = dict(other["source"], duration=1)
    clip["captions"] = [
        {"id": "c0", "start": .1, "end": 2.5, "text": "오늘은 주제를 설명합니다"},
        {"id": "c1", "start": 5, "end": 7, "text": "먼저 준비물을 살펴봅니다"},
        {"id": "c2", "start": 26, "end": 28, "text": "정리하면 이렇습니다"},
    ]
    clip["cuts"] = [{"id": "d0", "start": 8, "end": 11, "enabled": True, "review": False}]
    drafts = new_outline(project)
    own = [row for row in drafts if row["clipId"] == clip["id"]]
    assert [(row["role"], row["startFrame"], row["endFrame"]) for row in own] == [
        ("도입", 0, 150), ("본론", 150, 780), ("마무리", 780, 900),
    ]
    assert sum(row["endFrame"] - row["startFrame"] for row in own) == 30 * 30
