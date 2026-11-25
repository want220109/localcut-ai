"""Build a reviewable, chronological outline from the current edit and local analysis."""
from bisect import bisect_left, bisect_right, insort
from hashlib import sha256
import re

from engine.planner import IMPORTANT, overlap
from engine.project import keeps, merged_ranges


MAX_CANDIDATES = 60
BODY_CUE = re.compile(r"^(?:먼저|첫째|우선|본격적으로|이제 시작|본론)")
ENDING_CUE = re.compile(r"^(?:정리하면|정리하자면|마지막으로|결론|마무리|시청해)")
RETAKE_PREFIX = re.compile(r"^(?:아니|다시\s*(?:말할게요|말하겠습니다|할게요)|정정합니다)[,.!?\s]+")


def intersects(ranges, start, end):
    index = bisect_left(ranges, [end])
    return index > 0 and ranges[index - 1][1] > start


def occupied(items, duration):
    return merged_ranges(({**item, "enabled": True} for item in items), duration)


def section_boundary(lines, scenes, groups, low, high, preferred, cue):
    def inside_speech(t):
        return intersects(groups, t - .005, t + .005)

    # A chapter can start at a spoken cue even if a scene change is unavailable.
    options = [
        (0 if cue.search(line["text"]) else 2, line["start"] - .02,
         "대본의 전환 표현을 기준으로 나눴습니다." if cue.search(line["text"]) else "발화 시작에 맞춰 나눴습니다.")
        for line in lines if low <= line["start"] - .02 <= high and not inside_speech(line["start"] - .02)
    ]
    options.extend((1, t, "발화 사이의 장면 전환을 기준으로 나눴습니다.")
                   for t in scenes if low <= t <= high and not inside_speech(t))
    if options:
        _, timestamp, reason = min(options, key=lambda option: (option[0], abs(option[1] - preferred)))
        return timestamp, reason
    return preferred, "대본과 장면 전환에서 경계가 확인되지 않아 시간 기준으로 나눴습니다."


def outline(project, lines, kept, speech):
    duration = project["source"]["duration"]
    scenes = project.get("scenes", [])
    body, body_reason = section_boundary(lines, scenes, speech, duration * .08, duration * .42,
                                         duration * .2, BODY_CUE)
    end, end_reason = section_boundary(lines, scenes, speech, duration * .64, duration * .96,
                                       duration * .8, ENDING_CUE)
    sections, anchors = [], []
    for title, start, stop, reason in (
        ("도입", 0, body, "영상 주제나 상황을 소개하는 첫 구간입니다."),
        ("본론", body, end, body_reason),
        ("마무리", end, duration, end_reason),
    ):
        matching = [line for line in lines if start <= (line["start"] + line["end"]) / 2 < stop]
        anchor = max(matching, key=lambda line: (bool(IMPORTANT.search(line["text"])),
                                                 min(len(line["text"]), 75), line["start"]), default=None)
        if anchor:
            anchors.append(anchor)
        sections.append({
            "title": title, "start": start, "end": stop, "reason": reason,
            "previewTime": anchor["start"] if anchor else start,
            "excerpt": anchor["text"][:110] if anchor else "",
            "retainedSeconds": sum(overlap(a, b, start, stop) for a, b in kept),
        })
    return sections, anchors


def repeated_lines(transcript, lines, scenes):
    """Only propose adjacent, complete utterances with the same corrected wording."""
    starts = [line["start"] for line in lines]
    phrases = []
    for spoken in transcript:
        start, end = spoken["start"], spoken["end"]
        lo, hi = bisect_left(starts, start - .025), bisect_left(starts, end)
        within = [line for line in lines[lo:hi] if line["end"] <= end + .025]
        if not within or within[0]["start"] > start + .25 or max(line["end"] for line in within) < end - .25:
            phrases.append(("", ""))
            continue
        text = " ".join(line["text"] for line in within)
        phrases.append((re.sub(r"[\W_]", "", RETAKE_PREFIX.sub("", text)).lower(), text))
    previous_end = 0
    for index, (left, right) in enumerate(zip(transcript, transcript[1:])):
        normalized, text = phrases[index]
        repeated, next_text = phrases[index + 1]
        start, end = left["start"], left["end"]
        clear_pause = start >= previous_end + .065 and right["start"] >= end + .065
        previous_end = max(previous_end, end)
        if not (len(normalized) >= 8 and normalized == repeated and clear_pause and right["start"] - end <= 4):
            continue
        if min(left.get("confidence", 0), right.get("confidence", 0)) < .8:
            continue
        if IMPORTANT.search(text) or IMPORTANT.search(next_text) or bisect_left(scenes, start - .1) != bisect_right(scenes, end + .1):
            continue
        start, end = max(0, start - .03), end + .03
        identifier = "longform-" + sha256(f"{start:.6f}:{end:.6f}".encode()).hexdigest()[:20]
        yield {"id": identifier, "start": start, "end": end, "kind": "retake", "confidence": .82,
               "reason": "교정된 대본에서 같은 발언이 바로 이어집니다. 뒤 발언을 남기는 후보입니다.",
               "review": True, "enabled": False}


def make_draft(project, target):
    duration = project["source"]["duration"]
    kept = keeps(project)
    current = sum(b - a for a, b in kept)
    applied = merged_ranges(project["cuts"], duration)
    source_lines = project["captions"] or project["transcript"]
    lines = sorted(({**line, "text": line["text"].strip()} for line in source_lines
                    if line["text"].strip() and not intersects(applied, line["start"], line["end"])),
                   key=lambda line: line["start"])
    transcript = sorted(project["transcript"], key=lambda line: line["start"])
    speech = occupied([*transcript, *project["captions"]], duration)
    sections, anchors = outline(project, lines, kept, speech)
    protected = occupied([*anchors, *(line for line in lines if IMPORTANT.search(line["text"]))], duration)
    scenes = sorted(project.get("scenes", []))
    candidates = []
    if transcript and lines:
        originals = {cut["id"]: cut for cut in project["cuts"]}
        existing_ranges = occupied(project["cuts"], duration)
        retakes = sorted((cut for cut in project["cuts"]
                         if not cut["enabled"] and cut["review"] and cut["kind"] in {"retake", "mistake"}),
                         key=lambda cut: cut["start"])
        retake_starts = [cut["start"] for cut in retakes]
        for cut in repeated_lines(transcript, lines, scenes):
            index = bisect_left(retake_starts, cut["start"] - .025)
            prior = retakes[index] if index < len(retakes) else None
            if prior and abs(prior["start"] - cut["start"]) <= .025 and abs(prior["end"] - cut["end"]) <= .025:
                candidates.append((0, {**prior, "reason": cut["reason"]}, True))
            elif cut["id"] not in originals and not intersects(existing_ranges, cut["start"], cut["end"]):
                candidates.append((0, cut, False))
        for cut in project["cuts"]:
            if cut["enabled"] or not cut["review"]:
                continue
            start, end = cut["start"], cut["end"]
            if cut["kind"] in {"silence", "speech_gap"} and not intersects(speech, start, end):
                priority = 1 if cut["kind"] == "silence" and cut["confidence"] >= .9 else 2
                candidates.append((priority, cut, True))

    chosen, seconds, unavailable = [], 0.0, []
    required = max(0, current - target)
    for priority, cut, existing in sorted(candidates, key=lambda entry: (entry[0], entry[1]["start"], entry[1]["id"])):
        start, end = cut["start"], cut["end"]
        if intersects(applied, start, end) or intersects(unavailable, start, end) or intersects(protected, start, end):
            continue
        if end - start < .12 or end - start >= current - .001:
            continue
        recommended = priority < 2 and seconds + end - start <= min(required + .05, current * .2) and required > .05
        if recommended:
            seconds += end - start
        chosen.append({**cut, "existing": existing, "recommended": recommended})
        insort(unavailable, [start, end])
        if len(chosen) >= MAX_CANDIDATES:
            break
    return {"revision": project["revision"], "targetSeconds": target, "currentSeconds": current,
            "sections": sections, "candidates": sorted(chosen, key=lambda cut: cut["start"]),
            "hasDialogue": bool(transcript and lines)}


def apply_draft(store, project, target, revision, selected):
    if type(revision) is not int or revision != project["revision"]:
        raise ValueError("편집 내용이 바뀌었습니다. 롱폼 초벌 편집안을 다시 만들어 주세요.")
    if (not isinstance(selected, list) or not 1 <= len(selected) <= MAX_CANDIDATES or
            any(not isinstance(value, str) or len(value) > 128 for value in selected) or len(set(selected)) != len(selected)):
        raise ValueError("적용할 컷 후보를 확인해 주세요.")
    candidates = {cut["id"]: cut for cut in make_draft(project, target)["candidates"]}
    if not set(selected) <= candidates.keys():
        raise ValueError("현재 초벌 편집안에 없는 컷입니다. 다시 생성해 주세요.")
    cuts = [dict(cut, enabled=True) if cut["id"] in selected else cut for cut in project["cuts"]]
    for identifier in selected:
        cut = candidates[identifier]
        if not cut["existing"]:
            cuts.append({key: cut[key] for key in ("id", "start", "end", "kind", "confidence", "reason", "review")} |
                        {"enabled": True})
    return store.edit(project["id"], {"cuts": sorted(cuts, key=lambda cut: cut["start"])})
