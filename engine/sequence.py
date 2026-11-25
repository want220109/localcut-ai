from math import ceil, floor
from pathlib import Path
from uuid import uuid4

from engine.project import ID_RE, finite, merged_ranges, validate_items
from engine.transcript_edit import require_revision
from media.tools import probe, verify_source


MAX_CLIPS = 100
SEQUENCE_FPS = 30


def clip_intervals(clip):
    """Kept ranges in output frames, expressed in each clip's source timeline."""
    duration = clip["source"]["duration"]
    total_frames = max(1, round(duration * SEQUENCE_FPS))
    kept, cursor = [], 0
    for a, b in merged_ranges(clip.get("cuts", []), duration):
        start = min(total_frames, ceil(a * SEQUENCE_FPS - 1e-6))
        end = min(total_frames, floor(b * SEQUENCE_FPS + 1e-6))
        if b >= duration:
            end = total_frames
        if end <= start:
            continue
        if start > cursor:
            kept.append((cursor, start))
        cursor = end
    if cursor < total_frames:
        kept.append((cursor, total_frames))
    return kept


def clip_frames(clip):
    return sum(end - start for start, end in clip_intervals(clip))


def seconds_intervals(frames):
    return [(start / SEQUENCE_FPS, end / SEQUENCE_FPS) for start, end in frames]


def validate_clips(clips):
    if not isinstance(clips, list) or not 2 <= len(clips) <= MAX_CLIPS:
        raise ValueError("여러 원본 작업에는 2~100개 영상이 필요합니다.")
    identifiers = set()
    for clip in clips:
        if not ID_RE.fullmatch(clip["id"]) or clip["id"] in identifiers or type(clip["enabled"]) is not bool:
            raise ValueError("클립을 식별할 수 없습니다.")
        identifiers.add(clip["id"])
        duration = finite(clip["source"]["duration"], .001)
        validate_items(clip["captions"], duration)
        validate_items(clip.get("cuts", []), duration, cuts=True)
        if not clip_frames(clip):
            raise ValueError("클립 전체를 삭제할 수 없습니다.")
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
    from subtitles.captions import remap
    after = (cue["text"] for clip in clips if clip["enabled"]
             for cue in remap(clip["captions"], seconds_intervals(clip_intervals(clip))))
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



def needs_captions(clip):
    return not clip["analyzed"] and not clip["captions"]


def check_model(store, model):
    from models.manager import ready
    if not ready(store.root, model, verify=True):
        raise ValueError("모델 · 업데이트에서 한국어 음성 모델을 먼저 설치해 주세요.")


def recognize_clip(store, project, clip, model, progress):
    from engine.analysis import transcribe
    transcript, vad, result = transcribe(
        clip["source"], store.root, model, store.directory(project["id"]), progress, model_verified=True,
    )
    clip.update(speech={"transcript": transcript, "vad": vad}, model=result)
    return transcript


def analyze_clip(store, project, clip, model, progress, *, model_checked=False):
    source = clip["source"]
    verify_source(source)
    if source["hasAudio"]:
        from subtitles.captions import generate
        if "speech" not in clip:
            if not model_checked:
                check_model(store, model)
            recognize_clip(store, project, clip, model, progress)
        transcript = clip["speech"]["transcript"]
        clip["captions"] = generate(transcript, "basic", project["settings"])
    clip["analyzed"] = True


def process_clips(store, project, pending, progress, work, success_message):
    completed, failures = 0, []
    for index, clip in enumerate(pending, 1):
        def report(percent, message):
            progress(100 * (index - 1 + percent / 100) / len(pending),
                     f"클립 {index}/{len(pending)} · {clip['name']} · {message}")
        report(0, "영상 확인 중")
        try:
            updated = dict(clip)
            work(updated, report)
        except (ValueError, RuntimeError, OSError) as error:
            failures.append(f"{clip['name']} · {error}")
            continue
        clip.update(updated)
        project["revision"] += 1
        store.save(project, snapshot=completed == 0)
        completed += 1
        report(100, success_message)
    return project, failures


def analyze_sequence(store, project, request, progress):
    require_revision(project, request.get("revision"))
    pending = [clip for clip in project["clips"] if clip["enabled"] and needs_captions(clip)]
    model = request["model"]
    if any(clip["source"]["hasAudio"] and "speech" not in clip for clip in pending):
        progress(0, "한국어 음성 모델 확인 중")
        check_model(store, model)
    def work(clip, report):
        analyze_clip(store, project, clip, model, report, model_checked=True)
    return process_clips(store, project, pending, progress, work, "자막 처리 완료")


def analyze_sequence_edits(store, project, request, progress):
    from engine.analysis import silence_ranges, visual_analysis
    from engine.longform import intersects, occupied
    from engine.planner import plan

    require_revision(project, request.get("revision"))
    pending = [clip for clip in project["clips"] if clip["enabled"] and "cuts" not in clip]
    model = request["model"]
    if any(clip["source"]["hasAudio"] and "speech" not in clip for clip in pending):
        progress(0, "한국어 음성 모델 확인 중")
        check_model(store, model)

    def work(clip, report):
        source = clip["source"]
        verify_source(source)
        if source["hasAudio"] and "speech" not in clip:
            recognize_clip(store, project, clip, model, report)
        speech = clip.get("speech", {})
        # The planner annotates its input, so the cached ASR stays independent.
        transcript = [dict(item) for item in speech.get("transcript", [])]
        diagnostics = {}
        silences, scenes, motion = [], [], []
        if transcript:
            duration = source["duration"]
            scenes, motion = visual_analysis(source["path"], duration,
                                             lambda p, msg: report(79 + p * .35, msg))
            report(92, "긴 침묵과 대화 구간 비교 중")
            silences = silence_ranges(source["path"], duration)
        cuts, _ = plan(source, transcript, silences, scenes, motion, speech.get("vad", []), "basic", diagnostics)
        protected = occupied([*transcript, *clip["captions"]], source["duration"])
        for cut in cuts:
            if cut["kind"] != "silence":
                cut.update(enabled=False, review=True)
                continue
            # Keep corrected subtitles and whole utterances protected in the automatic pass.
            if cut["enabled"] and intersects(protected, cut["start"], cut["end"]):
                cut.update(enabled=False, review=True, reason="자막 또는 발화 시간과 겹치는 구간 · 검토 후 적용")
        clip.update(cuts=cuts, cutNote=diagnostics.get("noCutReason", "") if not cuts else "")

    return process_clips(store, project, pending, progress, work, "AI 편집점 분석 완료")


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
        if action == "sequenceCutPreview":
            from media.sequence import sequence_cut_preview
            return sequence_cut_preview(project, clip, request.get("cutId"), progress)
        if action == "sequenceSetCut":
            chosen = next((cut for cut in clip.get("cuts", []) if cut["id"] == request.get("cutId")), None)
            enabled = request.get("enabled")
            if chosen is None or type(enabled) is not bool:
                raise ValueError("편집 구간을 다시 선택해 주세요.")
            if chosen["enabled"] == enabled:
                return project
            chosen["enabled"] = enabled
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
            if not needs_captions(clip):
                return project
            analyze_clip(store, project, clip, request["model"], progress)
        if action == "sequenceCaption":
            caption = next((cue for cue in clip["captions"] if cue["id"] == request.get("captionId")), None)
            text = request.get("text")
            if caption is None or not isinstance(text, str) or len(text) > 10000:
                raise ValueError("수정할 자막 문구를 확인해 주세요.")
            caption.update(text=text, textEdited=True)
    project["revision"] += 1
    return store.save(project, snapshot=True)
