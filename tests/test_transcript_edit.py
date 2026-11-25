import pytest

from engine.project import Store, merged_ranges
from engine.service import dispatch


@pytest.fixture
def project(tmp_path):
    store = Store(tmp_path)
    work = store.create({"path": "sample.mp4", "duration": 12, "fps": 24, "width": 640, "height": 360})
    work["captions"] = [
        {"id": "intro", "start": 1, "end": 2, "text": "교정한 도입", "textEdited": True},
        {"id": "middle", "start": 4, "end": 5, "text": "중간 발언"},
        {"id": "last", "start": 9, "end": 10, "text": "마무리"},
    ]
    work["cuts"] = [
        {"id": "wide", "start": 3, "end": 7, "enabled": True, "review": False, "reason": "기존 컷"},
        {"id": "overlap", "start": 4.5, "end": 6, "enabled": True, "review": True, "reason": "겹친 컷"},
        {"id": "pending", "start": 8, "end": 9.5, "enabled": False, "review": True},
    ]
    store.save(work)

    def call(action, **values):
        return dispatch({"root": str(tmp_path), "action": action, "id": work["id"], **values})

    return work, call


def test_exclude_separate_lines_and_restore_overlapping_cut_only_where_selected(project):
    work, call = project
    result = call("editTranscript", revision=0, operation="exclude", lineIds=["intro", "last"])
    p = result["project"]
    assert merged_ranges(p["cuts"], 12) == [[1, 2], [3, 7], [9, 10]]
    assert result["audit"]["outputDuration"] == 6
    assert p["captions"] == work["captions"]
    assert p["source"] == work["source"]
    assert p["output"] is None
    result = call("editTranscript", revision=1, operation="restore", lineIds=["intro", "middle"])
    p = result["project"]
    assert merged_ranges(p["cuts"], 12) == [[3, 4], [5, 7], [9, 10]]
    assert result["audit"]["outputDuration"] == 8
    assert next(c for c in p["cuts"] if c["id"] == "pending") == work["cuts"][-1]
    assert len({cut["id"] for cut in p["cuts"]}) == len(p["cuts"])
    assert call("undo")["audit"]["outputDuration"] == 6


def test_noop_stale_revision_and_unknown_row_leave_project_untouched(project):
    work, call = project
    same = call("editTranscript", revision=0, operation="exclude", lineIds=["middle"])
    assert same["project"] == work
    with pytest.raises(ValueError, match="다시 선택"):
        call("editTranscript", revision=1, operation="restore", lineIds=["middle"])
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        call("editTranscript", revision=0, operation="exclude", lineIds=["missing"])
    assert call("get")["project"] == work


def test_full_source_exclusion_is_rejected(project):
    work, call = project
    work = call("edit", changes={"captions": [{"id": "all", "start": 0, "end": 12, "text": "모든 영상"}]})["project"]
    with pytest.raises(ValueError, match="출력할 영상 프레임"):
        call("editTranscript", revision=work["revision"], operation="exclude", lineIds=["all"])
    assert call("get")["project"] == work


def test_analyzed_project_without_captions_uses_saved_transcript(project, tmp_path):
    work, call = project
    work["captions"] = []
    work["transcript"] = [{"id": "raw", "start": 1, "end": 2, "text": "원본 대본", "confidence": .95}]
    Store(tmp_path).save(work)
    result = call("editTranscript", revision=0, operation="exclude", lineIds=["raw"])
    assert merged_ranges(result["project"]["cuts"], 12) == [[1, 2], [3, 7]]
