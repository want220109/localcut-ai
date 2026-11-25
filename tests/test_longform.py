import pytest

from engine.longform import make_draft
from engine.project import Store
from engine.service import dispatch


def transcript_line(identifier, start, end, text, confidence=.98):
    return dict(id=identifier, start=start, end=end, text=text, confidence=confidence)


def pending(identifier, start, end, kind="silence", **options):
    return dict(id=identifier, start=start, end=end, kind=kind, reason="기존 후보",
                enabled=False, review=True, confidence=.94) | options


@pytest.fixture
def work(tmp_path, monkeypatch):
    monkeypatch.setattr("engine.service.verify_source", lambda source: None)
    store = Store(tmp_path)
    project = store.create(dict(path="source.mp4", duration=60, width=640, height=360, hasAudio=True))
    project.update(analyzed=True, scenes=[8, 40, 53], transcript=[
        transcript_line("1", 1, 4, "오늘은 집에서 피자를 만들어 보겠습니다."),
        transcript_line("2", 12, 16, "먼저 반죽에 들어갈 재료를 보여드릴게요."),
        transcript_line("3", 23, 25, "사 관을 먼저 넣고 저어줍니다."),
        transcript_line("4", 26, 28, "같은 말을 다시 하겠습니다."),
        transcript_line("5", 49, 52, "정리하면 먹기 전에 잠시 식히면 좋습니다."),
    ], cuts=[pending("gap", 17, 20), pending("music", 31, 36, "speech_gap", confidence=.6)])
    project["captions"] = [dict(line) for line in project["transcript"]]
    project["captions"][2].update(text="소금을 먼저 넣고 잘 저어줍니다.", textEdited=True)
    project["captions"][3].update(text="다시 말할게요, 소금을 먼저 넣고 잘 저어줍니다.", textEdited=True)
    # Use a separate introductory body cue as the representative anchor.
    project["captions"][1]["text"] = "먼저 반죽에 들어갈 재료와 준비 순서를 아주 천천히 하나씩 보여드릴게요."
    store.save(project)

    def call(action, **values):
        return dispatch(dict(root=str(tmp_path), id=project["id"], action=action, **values))

    return store, project, call


def test_draft_compares_corrected_dialogue_and_uses_cues_without_saving(work):
    store, project, call = work
    saved = store.directory(project["id"]) / "project.json"
    before = saved.read_bytes()
    draft = call("longformDraft", targetSeconds=54)["draft"]
    assert saved.read_bytes() == before
    assert [section["title"] for section in draft["sections"]] == ["도입", "본론", "마무리"]
    assert draft["sections"][1]["start"] == pytest.approx(11.98)
    assert draft["sections"][1]["excerpt"] == project["captions"][1]["text"]
    assert draft["sections"][2]["start"] == pytest.approx(48.98)
    by_kind = {candidate["kind"]: candidate for candidate in draft["candidates"]}
    assert by_kind["retake"]["start"] == pytest.approx(22.97)
    assert by_kind["retake"]["recommended"] and by_kind["silence"]["recommended"]
    assert not by_kind["speech_gap"]["recommended"]
    assert all(not cut["enabled"] for cut in project["cuts"])
    assert call("longformDraft", targetSeconds=59)["draft"]["candidates"][0]["recommended"] is False


def test_selection_reuses_existing_ranges_and_rejects_stale_or_unknown_cuts(work):
    store, project, call = work
    draft = call("longformDraft", targetSeconds=56)["draft"]
    revision = draft["revision"]
    with pytest.raises(ValueError, match="현재 초벌 편집안에 없는"):
        call("applyLongform", targetSeconds=56, revision=revision, selected=["fake"])
    result = call("applyLongform", targetSeconds=56, revision=revision, selected=["gap"])
    assert result["audit"]["outputDuration"] == 57
    updated = result["project"]
    assert [c["id"] for c in updated["cuts"] if c["enabled"]] == ["gap"]
    assert len(updated["cuts"]) == len(project["cuts"])
    assert updated["captions"] == project["captions"]
    with pytest.raises(ValueError, match="편집 내용이 바뀌었습니다"):
        call("applyLongform", targetSeconds=56, revision=revision, selected=["music"])
    assert call("undo")["audit"]["outputDuration"] == 60
    assert store.load(project["id"])["source"] == project["source"]


def test_keep_all_dialogue_without_evidence_and_do_not_duplicate_restored_cuts(work):
    _, project, _ = work
    project["scenes"].append(24)
    project["cuts"].append(pending("restored", 34, 35, "manual", enabled=True, review=False))
    project["captions"].append(transcript_line("extra", 18, 19, "편집 사용자가 고친 문장입니다."))
    assert make_draft(project, 10)["candidates"] == []
    project["transcript"] = []
    without_speech = make_draft(project, 10)
    assert without_speech["candidates"] == [] and not without_speech["hasDialogue"]
    assert without_speech["currentSeconds"] == 59


def test_first_draft_analyzes_but_keeps_old_edits_and_leaves_new_cuts_inactive(work, monkeypatch):
    store, project, call = work
    project["analyzed"] = False
    project["cuts"] = [pending("manual", 5, 6, "manual", enabled=True)]
    project["captions"] = [project["captions"][0]]
    store.save(project)
    monkeypatch.setattr("models.manager.ready", lambda *args, **kwargs: True)
    monkeypatch.setattr("engine.analysis.visual_analysis", lambda *args: ([], [{"value": 0, "time": 10}]))
    monkeypatch.setattr("engine.analysis.silence_ranges", lambda *args: [[7, 13]])
    monkeypatch.setattr("engine.analysis.transcribe", lambda *args: (project["transcript"], [], None))
    result = call("longformDraft", model="small", targetSeconds=55)
    updated = result["project"]
    assert updated["analyzed"]
    assert updated["cuts"][0] == project["cuts"][0]
    assert updated["captions"] == project["captions"]
    assert updated["settings"] == project["settings"]
    assert result["audit"]["outputDuration"] == 59
    assert result["draft"]["revision"] == updated["revision"]
    assert len(updated["cuts"]) > 1
    assert all(not c["enabled"] for c in updated["cuts"][1:])
