from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path

from engine.project import merged_ranges, aligned_words

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


def subtract_ranges(ranges, blocked, duration):
    def union(values):
        return merged_ranges([{"start":a,"end":b,"enabled":True} for a,b in values],duration)
    result=[]
    protected=union(blocked)
    for a,b in union(ranges):
        cursor=a
        for c,d in protected:
            if d<=cursor:
                continue
            if c>=b:
                break
            if c>cursor:
                result.append([cursor,min(c,b)])
            cursor=max(cursor,d)
            if cursor>=b:
                break
        if cursor<b:
            result.append([cursor,b])
    return result


def speech_protection(transcript, vad, duration):
    protected=[]
    word_segments=0
    for segment in transcript:
        words=aligned_words(segment)
        if words and not segment["important"]:
            word_segments+=1
            protected.extend([[max(0,w["start"]-.18),min(duration,w["end"]+.18)] for w in words])
        else:
            # Incomplete/uncertain word timing must not expose unrecognized speech to cuts.
            protected.append([max(0,segment["start"]-.18),min(duration,segment["end"]+.18)])
    protected.extend([[max(0,a-.12),min(duration,b+.12)] for a,b in vad])
    return protected,word_segments


def plan(source, transcript, silences, scenes, motion, vad, style, diagnostics=None):
    cfg = STYLES[style]
    duration = source["duration"]
    score_transcript(transcript)
    cuts, warnings = [], []
    report=diagnostics if diagnostics is not None else {}
    report.clear()
    report.update(style=style,detectedSilences=len(silences),speechIntervals=len(vad),wordTimingSegments=0,
                  silenceCandidates=0,nonSpeechCandidates=0,noCutReason="")
    if not source["hasAudio"]:
        report["noCutReason"]="오디오가 없어 대화 기반 자동 삭제를 하지 않았습니다. 장면 정보와 수동 편집을 사용할 수 있습니다."
        return [], [report["noCutReason"]]
    if not transcript:
        report["noCutReason"]="인식된 대화가 없어 자동 삭제를 보류했습니다. 무음 영상의 중요한 장면을 보존합니다."
        return [], [report["noCutReason"]]
    # Silence, ASR, VAD and image evidence must agree before a gap is removed.
    protected,report["wordTimingSegments"]=speech_protection(transcript,vad,duration)
    for a, b in subtract_ranges(silences,protected,duration):
        if b-a < cfg["silence_min"]:
            continue
        start, end = a+cfg["padding"], b-cfg["padding"]
        if end-start < cfg["min_cut"]:
            continue
        movement = [m["value"] for m in motion if a <= m["time"] <= b]
        visual_event = any(a-.5 <= s <= b+.5 for s in scenes)
        uncertain = visual_event or not movement or max(movement) > .035
        cuts.append(cut(start,end,"silence", "장면 변화 또는 움직임이 있는 무음 · 보존 권장" if uncertain else "대본·음성 감지·정지 화면으로 확인한 긴 침묵", .55 if uncertain else .94, uncertain))
        report["silenceCandidates"]+=1
    # Background sound can prevent silencedetect from reporting a gap. VAD-only gaps
    # are useful review candidates, never evidence for deleting music/actions automatically.
    if vad:
        # Keep introductions/outros out of VAD-only proposals: require speech on both sides.
        speech_bounds=[[min(a for a,b in vad),max(b for a,b in vad)]]
        for a,b in subtract_ranges(speech_bounds,protected+silences,duration):
            start,end=a+cfg["padding"],b-cfg["padding"]
            if b-a>=cfg["silence_min"] and end-start>=cfg["min_cut"]:
                cuts.append(cut(start,end,"speech_gap","음성 감지상 대화가 없는 구간 · 배경음과 행동 장면을 검토한 뒤 적용",.6,True))
                report["nonSpeechCandidates"]+=1
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
    accepted=[]
    for c in sorted(cuts, key=lambda x:x["start"]):
        if not c["enabled"]:
            continue
        proposed=accepted+[c]
        removed=sum(b-a for a,b in merged_ranges(proposed,duration))
        retained=subtract_ranges([[0,duration]],[[x["start"],x["end"]] for x in proposed],duration)
        if removed/duration > cfg["max_removed"] or any(b-a<cfg["min_keep"] for a,b in retained):
            c.update(enabled=False, review=True, reason=c["reason"]+" · 과도한 컷 방지로 검토 전환")
        else:
            accepted.append(c)
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
    report["automaticCuts"]=sum(c["enabled"] for c in cuts)
    report["reviewCuts"]=sum(c["review"] and not c["enabled"] for c in cuts)
    if not report["automaticCuts"]:
        report["noCutReason"]=(f"검토 제안 {report['reviewCuts']}개가 보존 중입니다. 삭제 적용 전에는 원본 길이를 유지합니다." if report["reviewCuts"] else
                               "음성 감지와 대본을 함께 확인했지만 삭제할 만큼 긴 발화 공백을 찾지 못했습니다.")
        warnings.append(report["noCutReason"])
    warnings.append("의미 분석은 핵심어·재녹음 신호 기반의 보수적 규칙입니다. 시각적 중요도와 말실수를 완전히 이해하는 모델은 아닙니다.")
    return sorted(cuts,key=lambda c:c["start"]), warnings
