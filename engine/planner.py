from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from engine.project import merged_ranges

STYLES = json.loads(Path(__file__).with_name("styles.json").read_text(encoding="utf-8"))
IMPORTANT = re.compile(r"중요|핵심|주의|반드시|결론|요약|첫째|둘째|마지막|하지 마|안 됩니다|주의사항|기억")
RESTART = re.compile(r"^(?:아니[,. ]*|다시\s*(?:말|할|시작)|정정|잠깐[,. ]*다시)")


def overlap(a, b, c, d):
    return max(0, min(b, d)-max(a, c))


def cut(a, b, kind, reason, confidence, review=False):
    return {"id": uuid.uuid4().hex[:12], "start": round(a, 3), "end": round(b, 3), "kind": kind,
            "reason": reason, "confidence": confidence, "review": review, "enabled": not review}


def score_transcript(transcript):
    counts = Counter(t for s in transcript for t in re.findall(r"[가-힣a-zA-Z0-9]{2,}", s["text"]))
    for s in transcript:
        tokens = re.findall(r"[가-힣a-zA-Z0-9]{2,}", s["text"])
        s["important"] = bool(IMPORTANT.search(s["text"]))
        s["score"] = round(sum(counts[t] for t in set(tokens))/max(1,len(tokens)) + 3*s["important"], 3)


def plan(source, transcript, silences, scenes, motion, vad, style):
    cfg = STYLES[style]
    duration = source["duration"]
    score_transcript(transcript)
    cuts, warnings = [], []
    if not source["hasAudio"]:
        return [], ["오디오가 없어 대화 기반 자동 삭제를 하지 않았습니다. 장면 정보와 수동 편집을 사용할 수 있습니다."]
    if not transcript:
        return [], ["인식된 대화가 없어 자동 삭제를 보류했습니다. 무음 영상의 중요한 장면을 보존합니다."]
    # Silence, ASR, VAD and image evidence must agree before a gap is removed.
    protected = [[max(0,s["start"]-.18), min(duration,s["end"]+.18)] for s in transcript]
    protected += [[max(0,a-.12), min(duration,b+.12)] for a,b in vad]
    for a, b in silences:
        if b-a < cfg["silence_min"]:
            continue
        start, end = a+cfg["padding"], b-cfg["padding"]
        if end-start < cfg["min_cut"]:
            continue
        if any(overlap(start,end,c,d)>0 for c,d in protected):
            continue
        movement = [m["value"] for m in motion if a <= m["time"] <= b]
        visual_event = any(a-.5 <= s <= b+.5 for s in scenes)
        uncertain = visual_event or not movement or max(movement) > .035
        cuts.append(cut(start,end,"silence", "장면 변화 또는 움직임이 있는 무음 · 보존 권장" if uncertain else "대본·음성 감지·정지 화면으로 확인한 긴 침묵", .55 if uncertain else .94, uncertain))
    for left, right in zip(transcript, transcript[1:]):
        if right["start"]-left["end"] > 4:
            continue
        a = re.sub(r"\W", "", left["text"]).lower()
        b = re.sub(r"\W", "", RESTART.sub("", right["text"])).lower()
        similarity = SequenceMatcher(None, a, b).ratio()
        if len(a) >= 8 and similarity >= .86:
            confident = min(left.get("confidence",0), right.get("confidence",0)) >= .85
            explicit = bool(RESTART.search(right["text"])) and similarity >= .96
            automatic = explicit and confident and not left["important"]
            cuts.append(cut(max(0,left["start"]-.04),min(duration,left["end"]+.04),"retake",
                            "명시적 재녹음 신호와 같은 문장" if automatic else "반복 발언 후보 · 강조 표현일 수 있어 검토 필요",
                            .96 if automatic else .65, not automatic))
        elif RESTART.search(right["text"]):
            cuts.append(cut(left["start"],left["end"],"mistake","말실수·다시 말하기 후보 · 문맥 확인 필요",.5,True))
    # Avoid aggressive pacing, very short kept fragments, and deleting important lines.
    removed = 0
    last = 0
    for c in sorted(cuts, key=lambda x:x["start"]):
        if not c["enabled"]:
            continue
        removed += c["end"]-c["start"]
        if removed/duration > cfg["max_removed"] or (0 < c["start"]-last < cfg["min_keep"]):
            c.update(enabled=False, review=True, reason=c["reason"]+" · 과도한 컷 방지로 검토 전환")
        else:
            last = c["end"]
    if style == "shorts" and duration > cfg["shorts_seconds"]:
        best = max(transcript,key=lambda s:s["score"])
        start = max(0,best["start"]-8)
        # Sentence boundaries preserve coherent speech in the highlight proposal.
        candidates = [s["start"] for s in transcript if s["start"] <= start]
        start = max(candidates,default=0)
        ends = [s["end"] for s in transcript if start < s["end"] <= start+cfg["shorts_seconds"]]
        end = max(ends,default=min(duration,start+cfg["shorts_seconds"]))
        if start > .1:
            cuts.append(cut(0,start,"highlight","쇼츠 핵심 문장 앞부분 제외 제안 · 문맥 검토 후 적용",.6,True))
        if duration-end > .1:
            cuts.append(cut(end,duration,"highlight","쇼츠 핵심 문장 뒷부분 제외 제안 · 문맥 검토 후 적용",.6,True))
        warnings.append("쇼츠 길이 제안은 핵심어 빈도와 중요 표현 점수로 선정했습니다. 검토 목록에서 적용하면 길이를 줄일 수 있습니다.")
    if any(s.get("confidence",0)<.6 for s in transcript):
        warnings.append("음성 인식 신뢰도가 낮은 문장이 있습니다. 해당 대화는 보존했으며 자막을 확인해 주세요.")
    warnings.append("의미 분석은 핵심어·재녹음 신호 기반의 보수적 규칙입니다. 시각적 중요도와 말실수를 완전히 이해하는 모델은 아닙니다.")
    return sorted(cuts,key=lambda c:c["start"]), warnings
