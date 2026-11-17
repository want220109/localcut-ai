import copy

import pytest

from engine.planner import plan
from engine.project import Store, keeps, transcript_audit, validate, cut_summary
from subtitles.captions import ass, generate, remap, srt, stamp


@pytest.fixture
def source():
    return {"path":"fixture.mp4","duration":12.0,"width":640,"height":360,"fps":30,"aspect":"16:9","hasAudio":True,"bytes":100,"mtimeNs":1}


def speech(start=1,end=3,text="오늘은 영상 편집 방법을 설명합니다.",confidence=.95):
    return {"id":f"s{start}","start":start,"end":end,"text":text,"confidence":confidence,"words":[]}


def motion(value=0):
    return [{"time":t/2,"value":value} for t in range(24)]


def test_silence_needs_agreement(source):
    cuts,_=plan(source,[speech()],[[4,7]],[],motion(),[[1,3]],"basic")
    assert len(cuts)==1 and cuts[0]["enabled"]
    assert cuts[0]["start"]==4.25 and cuts[0]["end"]==6.75
    for scenes,moves,vad in [([5],motion(),[]),([],motion(.1),[]),([],[],[])]:
        cuts,_=plan(source,[speech()],[[4,7]],scenes,moves,vad,"basic")
        assert cuts and not cuts[0]["enabled"] and cuts[0]["review"]
    cuts,_=plan(source,[speech()],[[4,7]],[],motion(),[[4.5,6]],"basic")
    assert cuts==[]  # VAD hears something the transcript missed.


def test_no_transcript_or_no_audio_preserves_video(source):
    assert plan(source,[],[[0,12]],[],motion(),[],"fast")[0]==[]
    source["hasAudio"]=False
    assert plan(source,[speech()],[[4,7]],[],motion(),[],"fast")[0]==[]


def test_repeated_sentences_need_explicit_restart(source):
    text="오늘은 영상 편집 방법을 설명합니다."
    cuts,_=plan(source,[speech(text=text),speech(3.5,5.5,text)],[],[],motion(),[],"basic")
    assert len(cuts)==1 and cuts[0]["review"] and not cuts[0]["enabled"]
    cuts,_=plan(source,[speech(text=text),speech(3.5,5.5,"다시 말하겠습니다. 다른 내용을 말합니다.")],[],[],motion(),[],"basic")
    assert all(not c["enabled"] for c in cuts)


def test_low_confidence_and_important_repetitions_preserved(source):
    for text,confidence in [("반드시 중요한 내용을 기억하세요.",.99),("영상 편집 방법을 설명합니다.",.4)]:
        cuts,_=plan(source,[speech(text=text,confidence=confidence),speech(3.5,5.5,"아니 "+text)],[],[],motion(),[],"basic")
        assert all(not c["enabled"] for c in cuts)


def test_high_confidence_explicit_retake_can_be_cut(source):
    text="영상 편집 방법을 설명합니다."
    cuts,_=plan(source,[speech(2,4,text),speech(4.5,6.5,"아니 "+text)],[],[],motion(),[],"basic")
    assert len(cuts)==1 and cuts[0]["enabled"] and cuts[0]["kind"]=="retake"


def test_shorts_is_reviewable(source):
    source["duration"]=120
    cuts,_=plan(source,[speech(),speech(60,65,"핵심은 중요한 이야기를 보존하는 것입니다.")],[],[],motion(),[],"shorts")
    assert any(c["kind"]=="highlight" for c in cuts)
    assert all(c["review"] and not c["enabled"] for c in cuts)


def test_store_undo_and_audit(tmp_path,source):
    store=Store(tmp_path)
    p=store.create(source)
    p["transcript"]=[{**speech(),"important":True},speech(6,8,"다른 문장입니다.")]
    store.save(p)
    cuts=[{"id":"c1","start":0,"end":4,"enabled":True,"review":False},
          {"id":"c2","start":3,"end":6.5,"enabled":True,"review":False}]
    p=store.edit(p["id"],{"cuts":cuts})
    assert keeps(p)==[[6.5,12.0]]
    audit=transcript_audit(p)
    assert audit["importantRemoved"]==1 and len(audit["partial"])==1
    assert "다른 문장" not in audit["after"]
    assert store.load(p["id"])["cuts"]==cuts
    assert store.undo(p["id"])["cuts"]==[]
    with pytest.raises(ValueError):store.edit(p["id"],{"source":{"path":"malicious"}})
    with pytest.raises(ValueError):store.load("../escape")


def test_invalid_edits_do_not_corrupt_saved_data(tmp_path,source):
    store=Store(tmp_path);p=store.create(source)
    for changes in [{"settings":{"fontSize":float("nan")}}, {"settings":{"color":"{\\an8}"}},
                    {"cuts":[{"id":"x","start":0,"end":12,"enabled":True,"review":False}]},
                    {"cuts":[{"id":"x","start":3,"end":2,"enabled":True,"review":False}]}]:
        with pytest.raises(ValueError):store.edit(p["id"],changes)
        assert store.load(p["id"])["revision"]==0


def test_caption_retime_after_cut():
    cues=[{"id":"x","start":1,"end":3,"text":"앞 문장"},{"id":"y","start":7,"end":9,"text":"뒤 문장"}]
    mapped=remap(cues,[[0,4],[6,12]])
    assert mapped[1]=={"start":5.0,"end":7.0,"text":"뒤 문장"}
    assert "00:00:05,000 --> 00:00:07,000" in srt(mapped)
    assert stamp(59.9996)=="00:01:00,000"


def test_word_timing_and_partial_caption():
    segments=[{**speech(0,4,"안녕하세요 반갑습니다"),"words":[{"start":0,"end":1,"text":"안녕하세요"},{"start":3,"end":4,"text":" 반갑습니다"}]}]
    cues=generate(segments)
    mapped=remap(cues,[[2,4]])
    assert len(mapped)==1 and mapped[0]["text"]=="반갑습니다" and mapped[0]["start"]==1


def test_ass_does_not_interpret_user_formatting(tmp_path,source):
    p=Store(tmp_path).create(source)
    data=ass([{"start":0,"end":1,"text":"{\\an8} 실제 대사"}],p["settings"],640,360)
    assert "{\\an8}" not in data and "실제 대사" in data
    assert "Malgun Gothic" in data


def test_background_sound_gap_is_found_but_needs_review(source):
    diagnostics={}
    cuts,_=plan(source,[speech(.5,2.5),speech(7.5,10.5)],[],[],motion(),[[.5,2.5],[7.5,10.5]],"basic",diagnostics)
    assert len(cuts)==1 and cuts[0]["kind"]=="speech_gap"
    assert cuts[0]["review"] and not cuts[0]["enabled"]
    assert cuts[0]["start"]>2.5 and cuts[0]["end"]<7.5
    assert diagnostics["nonSpeechCandidates"]==1 and diagnostics["automaticCuts"]==0
    assert "검토 제안 1개" in diagnostics["noCutReason"]
    # An isolated sentence is not a reason to propose removing a long visual outro.
    assert plan(source,[speech()],[],[],motion(),[[1,3]],"basic")[0]==[]


def test_complete_word_timing_can_expose_a_confirmed_internal_pause(source):
    segment=speech(1,10.5,"첫 번째 문장입니다. 다음 문장을 이어갑니다.")
    segment["words"]=[{"start":1,"end":2.5,"text":"첫 번째 문장입니다.","confidence":.95},
                      {"start":8,"end":10.5,"text":"다음 문장을 이어갑니다.","confidence":.95}]
    args=(source,[segment],[[3,7.5]],[],motion(),[[1,2.5],[8,10.5]],"basic")
    diagnostics={}
    cuts,_=plan(*args,diagnostics)
    assert len(cuts)==1 and cuts[0]["enabled"]
    assert cuts[0]["start"]==3.25 and cuts[0]["end"]==7.25
    assert diagnostics["wordTimingSegments"]==1
    # Missing/low-confidence words fall back to protecting the entire ASR segment.
    for words in [segment["words"][:1],[{**w,"confidence":.4} for w in segment["words"]]]:
        candidate=copy.deepcopy(segment);candidate["words"]=words
        assert plan(source,[candidate],[[3,7.5]],[],motion(),[[1,2.5],[8,10.5]],"basic")[0]==[]
    # VAD still protects speech even when the transcript's word list missed it.
    cuts,_=plan(source,[segment],[[3,7.5]],[],motion(),[[1,2.5],[4,6],[8,10.5]],"basic")
    assert not any(c["enabled"] for c in cuts)


def test_rejected_cut_does_not_consume_the_removal_budget(source):
    source["duration"]=20
    moves=[{"time":t/2,"value":0} for t in range(40)]
    cuts,_=plan(source,[speech()],[[3,14],[15,18]],[],moves,[[1,3]],"basic")
    assert len(cuts)==2
    assert not cuts[0]["enabled"] and cuts[0]["review"]
    assert cuts[1]["enabled"]


def test_summary_uses_merged_deletions_and_explains_pending_edits(tmp_path,source):
    p=Store(tmp_path).create(source)
    p["analyzed"]=True
    p["analysisSummary"]={"style":"basic"}
    p["cuts"]=[{"id":"a","start":2,"end":5,"enabled":True,"review":False},
               {"id":"b","start":4,"end":6,"enabled":True,"review":False},
               {"id":"c","start":8,"end":9,"enabled":False,"review":True}]
    summary=cut_summary(p)
    assert summary["appliedCount"]==2 and summary["intervalCount"]==1
    assert summary["removedDuration"]==4 and summary["outputDuration"]==8
    assert summary["reviewCount"]==1
    p["cuts"][0]["enabled"]=p["cuts"][1]["enabled"]=False
    summary=cut_summary(p)
    assert summary["removedDuration"]==0 and summary["outputDuration"]==source["duration"]
    assert "검토 제안 1개" in summary["noCutReason"]
    p["style"]="fast"
    assert cut_summary(p)["analysisNeedsRefresh"]
    p.pop("analysisSummary")
    assert not cut_summary(p)["analysisNeedsRefresh"]


def test_audit_preserves_words_when_only_an_internal_pause_is_cut(tmp_path,source):
    p=Store(tmp_path).create(source)
    segment=speech(1,10.5,"첫 문장입니다. 다음 문장입니다.")
    segment["words"]=[{"start":1,"end":2.5,"text":"첫 문장입니다.","confidence":.95},
                      {"start":8,"end":10.5,"text":"다음 문장입니다.","confidence":.95}]
    p["transcript"]=[segment]
    p["cuts"]=[{"id":"pause","start":3.25,"end":7.25,"enabled":True,"review":False}]
    audit=transcript_audit(p)
    assert audit["after"]==segment["text"]
    assert audit["partial"]==[] and audit["removed"]==[]


def test_audit_does_not_hide_removal_of_a_very_short_word(tmp_path,source):
    p=Store(tmp_path).create(source)
    segment=speech(1,4,"안 됩니다.")
    segment["words"]=[{"start":1,"end":1.01,"text":"안", "confidence":.95},
                      {"start":2,"end":4,"text":"됩니다.","confidence":.95}]
    p["transcript"]=[segment]
    p["cuts"]=[{"id":"word","start":.8,"end":1.2,"enabled":True,"review":False}]
    audit=transcript_audit(p)
    assert audit["after"]=="" and len(audit["partial"])==1
    assert audit["partial"][0]["retained"]>.98
