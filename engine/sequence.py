from pathlib import Path
from uuid import uuid4

from engine.project import ID_RE, finite, validate_items
from engine.transcript_edit import require_revision
from media.tools import probe, verify_source


MAX_CLIPS = 100
SEQUENCE_FPS = 30


def clip_frames(clip):
    return max(1, round(clip["source"]["duration"] * SEQUENCE_FPS))


def validate_clips(clips):
    if not isinstance(clips, list) or not 2 <= len(clips) <= MAX_CLIPS:
        raise ValueError("여러 원본 작업에는 2~100개 영상이 필요합니다.")
    identifiers = set()
    for clip in clips:
        if not ID_RE.fullmatch(clip["id"]) or clip["id"] in identifiers or type(clip["enabled"]) is not bool:
            raise ValueError("클립을 식별할 수 없습니다.")
        identifiers.add(clip["id"])
        validate_items(clip["captions"], finite(clip["source"]["duration"], .001))
    if not any(clip["enabled"] for clip in clips):
        raise ValueError("영상을 한 개 이상 포함해 주세요.")


def create_sequence(store, paths):
    if (not isinstance(paths, list) or not 2 <= len(paths) <= MAX_CLIPS
            or any(not isinstance(path, str) for path in paths)):
        raise ValueError("영상 파일 2~100개를 선택해 주세요.")
    clips, seen = [], set()
    for path in paths:
        source = probe(path)
        actual = Path(source["path"])
        if actual in seen:
            raise ValueError("같은 영상 파일이 두 번 선택됐습니다.")
        seen.add(actual)
        clips.append({"id": uuid4().hex, "source": source, "name": actual.name, "enabled": True,
                      "captions": [], "analyzed": False})
    by_capture = all(clip["source"].get("capturedAt") is not None for clip in clips)
    if by_capture:
        clips.sort(key=lambda clip: clip["source"]["capturedAt"])
    return store.create(clips[0]["source"], clips=clips, sort_order="capture" if by_capture else "import")


def sequence_audit(clips):
    length = sum(clip_frames(clip) for clip in clips if clip["enabled"]) / SEQUENCE_FPS
    before = (cue["text"] for clip in clips for cue in clip["captions"])
    after = (cue["text"] for clip in clips if clip["enabled"] for cue in clip["captions"])
    return {"before": "\n".join(before), "after": "\n".join(after), "outputDuration": length,
            "removed": [], "partial": [], "importantRemoved": 0}


def edit_sequence(project, rows):
    if not isinstance(rows, list) or len(rows) != len(project["clips"]):
        raise ValueError("클립 순서를 확인해 주세요.")
    by_id = {clip["id"]: clip for clip in project["clips"]}
    clips = []
    for row in rows:
        clip = by_id.pop(row.get("id"), None)
        if clip is None or type(row.get("enabled")) is not bool:
            raise ValueError("클립의 순서 또는 포함 상태를 확인해 주세요.")
        clips.append(dict(clip, enabled=row["enabled"]))
    validate_clips(clips)
    if [(c["id"], c["enabled"]) for c in clips] != [(c["id"], c["enabled"]) for c in project["clips"]]:
        project.update(clips=clips, sortOrder="manual")


def sequence_action(store, project, request, progress):
    action = request["action"]
    if action == "render":
        from media.sequence import render_sequence
        for clip in project["clips"]:
            if clip["enabled"]:
                verify_source(clip["source"])
        project["output"] = render_sequence(project, store.directory(project["id"]), progress)
        return store.save(project)
    require_revision(project, request.get("revision"))
    if action == "editSequence":
        edit_sequence(project, request.get("rows"))
    else:
        clip = next((clip for clip in project["clips"] if clip["id"] == request.get("clipId")), None)
        if clip is None:
            raise ValueError("클립을 다시 선택해 주세요.")
        if action == "sequenceConnection":
            from media.sequence import sequence_connection
            included = [item for item in project["clips"] if item["enabled"]]
            following = next((b for a, b in zip(included, included[1:]) if a["id"] == clip["id"]), None)
            if following is None:
                raise ValueError("다음에 이어질 포함 클립이 없습니다.")
            verify_source(clip["source"])
            verify_source(following["source"])
            return sequence_connection(project, clip, following, progress)
        if action == "sequencePreview":
            from media.preview import compatible_preview
            source = clip["source"]
            verify_source(source)
            directory = store.directory(project["id"]) / "clip-previews" / clip["id"]
            directory.mkdir(parents=True, exist_ok=True)
            target = directory / "source-preview.mp4"
            if target.is_file():
                return {"path": str(target)}
            return {"path": compatible_preview(source, directory, progress) or source["path"]}
        if action == "sequenceAnalyze":
            from engine.analysis import transcribe
            from models.manager import ready
            from subtitles.captions import generate
            if clip["analyzed"]:
                return project
            source = clip["source"]
            verify_source(source)
            if source["hasAudio"]:
                model = request["model"]
                if not ready(store.root, model, verify=True):
                    raise ValueError("모델 · 업데이트에서 한국어 음성 모델을 먼저 설치해 주세요.")
                transcript, _, result = transcribe(source, store.root, model, store.directory(project["id"]), progress)
                clip["captions"] = generate(transcript, "basic", project["settings"])
                clip["model"] = result
            clip["analyzed"] = True
        if action == "sequenceCaption":
            caption = next((cue for cue in clip["captions"] if cue["id"] == request.get("captionId")), None)
            text = request.get("text")
            if caption is None or not isinstance(text, str) or len(text) > 10000:
                raise ValueError("수정할 자막 문구를 확인해 주세요.")
            caption.update(text=text, textEdited=True)
    project["revision"] += 1
    return store.save(project, snapshot=True)
