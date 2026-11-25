"""Prepare the editable long-form timeline and render a privately stored preview."""
from pathlib import Path
from uuid import uuid4

from engine.sequence import analyze_clip, check_model, needs_captions, plan_clip_edits, sequence_action
from engine.sequence_outline import new_outline
from engine.transcript_edit import require_revision
from media.tools import verify_source


def single_as_clip(project):
    source = project["source"]
    clip = {"id": uuid4().hex, "source": source, "name": Path(source["path"]).name,
            "enabled": True, "captions": project["captions"], "analyzed": project["analyzed"]}
    if project["transcript"] or project["analyzed"]:
        clip["speech"] = {"transcript": project["transcript"], "vad": []}
    if project["cuts"] or project["analyzed"]:
        clip["cuts"] = project["cuts"]
    return clip


def produce_longform(store, project, request, progress):
    require_revision(project, request.get("revision"))
    if "clips" not in project:
        project["clips"] = [single_as_clip(project)]
        project["sortOrder"] = "manual"
    included = [clip for clip in project["clips"] if clip["enabled"]]
    model = request["model"]
    progress(1, "원본과 작업 설정 확인 중")
    for clip in included:
        verify_source(clip["source"])
    captions = [clip for clip in included if needs_captions(clip)]
    edits = [clip for clip in included if "cuts" not in clip]
    if any(clip["source"]["hasAudio"] and "speech" not in clip for clip in [*captions, *edits]):
        check_model(store, model)

    first_run = not project.get("autoLongform")
    if first_run:
        settings = project["settings"]
        settings.update(aspect="16:9", normalize=True, subtitles=True)
        if settings["resolution"] == "source":
            settings["resolution"] = "1080"

    for index, clip in enumerate(captions):
        def report(percent, message):
            progress(4 + (index + percent / 100) * 34 / len(captions),
                     f"자막 생성 중 ({index + 1}/{len(captions)}) · {message}")
        report(0, clip["name"])
        analyze_clip(store, project, clip, model, report, model_checked=True)
    for index, clip in enumerate(edits):
        def report(percent, message):
            progress(39 + (index + percent / 100) * 18 / len(edits),
                     f"컷 분석 중 ({index + 1}/{len(edits)}) · {message}")
        report(0, clip["name"])
        plan_clip_edits(store, project, clip, model, report)

    if "sequenceOutline" not in project:
        progress(58, "유튜브 롱폼 순서 구성 중")
        project["sequenceOutline"] = new_outline(project)
        composition_changed = True
    else:
        composition_changed = False

    if first_run or captions or edits or composition_changed:
        project.update(autoLongform=True, analyzed=True, revision=project["revision"] + 1)
        # Retain the prepared timeline so a failed preview can resume without another ASR pass.
        store.save(project, snapshot=True)

    progress(60, "전체 초안 영상 만드는 중")
    result = sequence_action(store, project, {"action": "render"},
                             lambda percent, message: progress(60 + percent * .39, message))
    progress(100, "자동 제작 초안 준비 완료")
    return result
