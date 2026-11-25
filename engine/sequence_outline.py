"""Suggest and review long-form sections on the already edited clip timeline."""
from bisect import bisect_left, bisect_right
from math import floor
import re

from engine.longform import BODY_CUE, ENDING_CUE, occupied
from engine.planner import IMPORTANT
from engine.sequence import (MAX_CLIPS, SEQUENCE_FPS, clip_intervals, frame_count, intersect_intervals,
                             seconds_intervals, sequence_timeline, slice_intervals, source_frames)
from engine.transcript_edit import require_revision
from media.tools import verify_source
from subtitles.captions import remap


MAX_SECTIONS = MAX_CLIPS + 2
ROLES = ("도입", "본론", "마무리")
OPENING = re.compile(r"^(?:여러분[,. ]*안녕하세요|안녕하세요|오늘(?:은| 영상은| 영상에서는))")
CLOSING = re.compile(r"^(?:시청해\s*주셔서|다음\s*영상에서|(?:오늘\s*)?영상은\s*여기까지|이상으로|마무리하겠습니다)")
CLOSING_BOUNDARY = re.compile(f"(?:{CLOSING.pattern}|{ENDING_CUE.pattern})")


def clip_placement(lines, length):
    first = [line for line in lines[:3] if line["start"] <= length * .25]
    opening = any(OPENING.search(line["text"]) and not CLOSING.search(line["text"]) for line in first)
    closing = any(CLOSING.search(line["text"]) for line in first)
    if opening and not closing and not any(CLOSING.search(line["text"]) for line in lines[-3:]):
        return 0
    if closing and not opening:
        return 2
    return 1


def boundary(lines, clip_edges, speech, length, limits, preferred, cue):
    lower, upper = (length * limit for limit in limits)
    target = length * preferred
    options = []
    for line in lines:
        frame = floor(line["start"] * SEQUENCE_FPS + 1e-6)
        time = frame / SEQUENCE_FPS
        previous = bisect_left(speech, [time - .002]) - 1
        crosses_speech = previous >= 0 and speech[previous][1] > time + .002
        if lower <= frame <= upper and not crosses_speech:
            matched = bool(cue.search(line["text"]))
            edge = bisect_right(clip_edges, frame) - 1
            if edge >= 0 and lower <= clip_edges[edge] and frame - clip_edges[edge] <= 9:
                frame = clip_edges[edge]
            options.append((0 if matched else 2, abs(frame - target), frame,
                            "교정 자막의 전환 표현" if matched else "새 발화가 시작되는 위치"))
    options.extend((1, abs(frame - target), frame, "클립이 이어지는 위치")
                   for frame in clip_edges if lower <= frame <= upper)
    if not options:
        return None
    priority, _, position, reason = min(options)
    return position, reason, priority == 0


def new_outline(project):
    sources = []
    for clip in project["clips"]:
        if clip["enabled"]:
            spans = clip_intervals(clip)
            captions = remap(clip["captions"], seconds_intervals(spans))
            placement = clip_placement(captions, frame_count(spans) / SEQUENCE_FPS)
            sources.append((placement, clip, spans, captions))

    clips, lines, utterances, offset = [], [], [], 0
    placements = {}
    for placement, clip, spans, captions in sorted(sources, key=lambda item: item[0]):
        end = offset + frame_count(spans)
        placements.setdefault(placement, offset)
        clips.append((clip, spans, offset, end))
        recognized = remap(clip.get("speech", {}).get("transcript", []), seconds_intervals(spans))
        for target, cues in ((lines, captions), (utterances, recognized)):
            target.extend(dict(line, start=line["start"] + offset / SEQUENCE_FPS,
                               end=line["end"] + offset / SEQUENCE_FPS) for line in cues)
        offset = end

    speech = occupied([*lines, *utterances], offset / SEQUENCE_FPS)
    edges = [start for _, _, start, _ in clips if start]
    has_opening = 0 in placements
    intro_reason = "교정 자막의 도입 표현" if has_opening else "영상의 첫 장면"
    boundaries = [(0, ROLES[0], intro_reason)]
    closing_start = placements.get(2, 0)
    body_start = placements.get(1, 0)
    body = boundary(lines, edges, speech, closing_start or offset, (.06, .55), .20, BODY_CUE)
    if body and body[2]:
        boundaries.append((body[0], ROLES[1], body[1]))
    elif has_opening and 0 < body_start < (closing_start or offset) * .65:
        boundaries.append((body_start, ROLES[1], "도입 클립 뒤의 본문"))
    elif body:
        boundaries.append((body[0], ROLES[1], body[1]))
    if closing_start:
        boundaries.append((closing_start, ROLES[2], "교정 자막의 마무리 표현"))
    else:
        closing = boundary(lines, edges, speech, offset, (.56, .99), .80, CLOSING_BOUNDARY)
        if closing and closing[0] > boundaries[-1][0]:
            boundaries.append((closing[0], ROLES[2], closing[1]))
    boundaries.append((offset, "", ""))

    rows = []
    for (start, role, reason), (end, _, _) in zip(boundaries, boundaries[1:]):
        for clip, spans, clip_start, clip_end in clips:
            if clip_start >= end or clip_end <= start:
                continue
            section = slice_intervals(spans, start - clip_start, end - clip_start)
            first, last = section[0][0], section[-1][1]
            captions = remap(clip["captions"], seconds_intervals(section))
            anchor = max(captions, key=lambda line: (bool(IMPORTANT.search(line["text"])),
                                                      min(len(line["text"]), 85)), default=None)
            rows.append({"id": f"{clip['id']}-{first}-{last}", "clipId": clip["id"], "role": role, "enabled": True,
                         "startFrame": first, "endFrame": last, "reason": reason,
                         "excerpt": anchor["text"][:120] if anchor else "",
                         "previewFrame": round(anchor["start"] * SEQUENCE_FPS) if anchor else 0})
    return rows


def validate_outline(project):
    rows = project["sequenceOutline"]
    if not isinstance(rows, list) or not 1 <= len(rows) <= MAX_SECTIONS:
        raise ValueError("롱폼 구성의 구간을 확인해 주세요.")
    clips = {clip["id"]: clip for clip in project["clips"]}
    identifiers, by_clip = set(), {}
    for row in rows:
        clip = clips.get(row["clipId"])
        identifier, start, end = row["id"], row["startFrame"], row["endFrame"]
        if (clip is None or identifier in identifiers or row["role"] not in ROLES or type(row["enabled"]) is not bool
                or type(start) is not int or type(end) is not int or not 0 <= start < end <= source_frames(clip)):
            raise ValueError("롱폼 구성의 구간을 확인해 주세요.")
        identifiers.add(identifier)
        by_clip.setdefault(clip["id"], []).append((start, end))
    for spans in by_clip.values():
        spans.sort()
        if any(end > following for (_, end), (following, _) in zip(spans, spans[1:])):
            raise ValueError("롱폼 구성이 같은 원본 구간을 두 번 사용했습니다.")
    if not sequence_timeline(project):
        raise ValueError("최종 영상에 포함할 구간을 한 개 이상 선택해 주세요.")


def review_outline(project, fresh):
    rows = project["sequenceOutline"] if not fresh and "sequenceOutline" in project else new_outline(project)
    clips = {clip["id"]: clip for clip in project["clips"]}
    review = []
    for row in rows:
        clip = clips[row["clipId"]]
        spans = intersect_intervals(clip_intervals(clip), row["startFrame"], row["endFrame"])
        review.append({**row, "name": clip["name"], "seconds": frame_count(spans) / SEQUENCE_FPS if clip["enabled"] else 0})
    return {"revision": project["revision"], "rows": review,
            "hasCaptions": any(cue["text"].strip() for clip in clips.values() if clip["enabled"] for cue in clip["captions"])}


def outline_action(store, project, request, progress):
    require_revision(project, request.get("revision"))
    action = request["action"]
    if action == "sequenceClearOutline":
        if "sequenceOutline" not in project:
            return project
        del project["sequenceOutline"]
    else:
        fresh = request.get("fresh", False)
        draft = review_outline(project, fresh)
        if action == "sequenceOutlineDraft":
            return draft
        candidates = {row["id"]: row for row in draft["rows"]}
        if action == "sequenceOutlinePreview":
            row = candidates.get(request.get("rowId"))
            if row is None or row["seconds"] <= 0:
                raise ValueError("미리 볼 구성 구간을 다시 선택해 주세요.")
            clip = next(clip for clip in project["clips"] if clip["id"] == row["clipId"])
            verify_source(clip["source"])
            spans = intersect_intervals(clip_intervals(clip), row["startFrame"], row["endFrame"])
            start = min(max(0, frame_count(spans) - 3 * SEQUENCE_FPS),
                        max(0, row["previewFrame"] - SEQUENCE_FPS))
            excerpt = slice_intervals(spans, start, start + 6 * SEQUENCE_FPS)
            from media.sequence import preview_excerpts
            return {"video": preview_excerpts(project, [(clip, excerpt)], progress),
                    "seconds": frame_count(excerpt) / SEQUENCE_FPS}
        ordered = request.get("rows")
        if (not isinstance(ordered, list) or len(ordered) != len(candidates) or
                any(not isinstance(row, dict) or not isinstance(row.get("id"), str) or
                    type(row.get("enabled")) is not bool for row in ordered) or
                {row["id"] for row in ordered} != candidates.keys()):
            raise ValueError("현재 초안의 구간과 순서를 다시 확인해 주세요.")
        project["sequenceOutline"] = []
        for row in ordered:
            candidate = candidates[row["id"]].copy()
            candidate.pop("name")
            candidate.pop("seconds")
            candidate["enabled"] = row["enabled"]
            project["sequenceOutline"].append(candidate)
    project["revision"] += 1
    return store.save(project, snapshot=True)
