from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from engine import __version__
from engine.commands import interpret
from engine.project import Store, finite, transcript_audit
from media.tools import binary, probe, verify_source
from models.manager import install, status


def dispatch(request, progress=lambda percent,message:None):
    store=Store(request["root"])
    action=request["action"]
    if action=="health":
        return {"version":__version__,"ffmpeg":binary("ffmpeg"),"ffprobe":binary("ffprobe"),"models":status(store.root),
                "cpuNote":"GPU 가속은 CUDA 환경이 준비된 경우 자동 사용합니다. CPU에서도 실행되지만 긴 영상은 영상 길이보다 오래 걸릴 수 있습니다."}
    if action=="models":
        return status(store.root)
    if action=="selftest":
        import ctranslate2
        import numpy as np
        import faster_whisper
        import cv2
        from faster_whisper.vad import VadOptions, get_speech_timestamps
        speech=get_speech_timestamps(np.zeros(16000,dtype=np.float32),VadOptions())
        return {"asrRuntime":True,"sileroVad":speech==[],"opencv":cv2.__version__,"cudaDevices":ctranslate2.get_cuda_device_count()}
    if action=="install_model":
        return install(store.root,request["model"],progress,request.get("importDir"))
    if action=="list":
        return store.list()
    if action=="history":
        return store.history()
    if action=="changeHistory":
        return store.change_history(request.get("operation"), request.get("id"))
    if action=="create":
        from media.preview import compatible_preview
        p=store.create(probe(request["source"]))
        p["preview"]=compatible_preview(p["source"],store.directory(p["id"]),progress)
        return store.save(p)
    if action=="createSequence":
        from engine.sequence import create_sequence
        p=create_sequence(store, request.get("sources"))
        return {"project": p, "audit": transcript_audit(p)}
    p=store.load(request["id"])
    if action=="autoLongform":
        from engine.auto_longform import produce_longform
        p = produce_longform(store, p, request, progress)
        return {"project": p, "audit": transcript_audit(p)}
    if action=="captionFrame":
        from media.caption_frame import caption_frame
        clip = None
        if "clips" in p:
            from engine.transcript_edit import require_revision
            require_revision(p, request.get("revision"))
            clip = next((item for item in p["clips"] if item["id"] == request.get("clipId")), None)
            if clip is None:
                raise ValueError("클립을 다시 선택해 주세요.")
        return caption_frame(p, request["draft"], clip=clip)
    if "clips" in p:
        if action in {"sequenceOutlineDraft", "sequenceOutlinePreview", "sequenceApplyOutline", "sequenceClearOutline"}:
            from engine.sequence_outline import outline_action
            result = outline_action(store, p, request, progress)
            if action in {"sequenceOutlineDraft", "sequenceOutlinePreview"}:
                return result
            return {"project": result, "audit": transcript_audit(result)}
        if action == "sequenceAnalyzeAll":
            from engine.sequence import analyze_sequence
            p, failures = analyze_sequence(store, p, request, progress)
            return {"project": p, "audit": transcript_audit(p), "captionFailures": failures}
        if action == "sequenceAnalyzeEdits":
            from engine.sequence import analyze_sequence_edits
            p, failures = analyze_sequence_edits(store, p, request, progress)
            return {"project": p, "audit": transcript_audit(p), "editFailures": failures}
        if action in {"editSequence", "sequencePreview", "sequenceConnection", "sequenceAnalyze", "sequenceCaption",
                      "sequenceCutPreview", "sequenceSetCut", "sequenceAdjustCut", "render"}:
            from engine.sequence import sequence_action
            result = sequence_action(store, p, request, progress)
            if action in {"sequencePreview", "sequenceConnection", "sequenceCutPreview"}:
                return result
            return {"project": result, "audit": transcript_audit(result)}
        if action not in {"get", "edit", "undo"} or (action == "edit" and set(request["changes"]) - {"settings", "name"}):
            raise ValueError("여러 원본 작업에서 지원하는 편집을 선택해 주세요.")
    if action=="cutPreview":
        from media.cut_preview import cut_preview
        return cut_preview(p, request.get("revision"), request.get("cutId"))
    if action=="get":
        return {"project":p,"audit":transcript_audit(p)}
    if action=="edit":
        p=store.edit(p["id"],request["changes"])
    elif action=="editTranscript":
        from engine.transcript_edit import edit_transcript
        p=edit_transcript(store, p, request.get("revision"), request.get("lineIds"), request.get("operation"))
    elif action=="undo":
        p=store.undo(p["id"])
    elif action=="command":
        changes,message=interpret(p,request["text"])
        p=store.edit(p["id"],changes)
        return {"project":p,"audit":transcript_audit(p),"message":message}
    elif action in {"analyze", "longformDraft", "applyLongform"}:
        from engine.longform import apply_draft, make_draft
        if action != "analyze":
            target = finite(request.get("targetSeconds"), .001, p["source"]["duration"])
            if action == "applyLongform":
                verify_source(p["source"])
                p = apply_draft(store, p, target, request.get("revision"), request.get("selected"))
                return {"project": p, "audit": transcript_audit(p)}
            if p["analyzed"]:
                verify_source(p["source"])
                return {"draft": make_draft(p, target)}
        from engine.analysis import silence_ranges, transcribe, visual_analysis
        from engine.planner import STYLES, plan
        from subtitles.captions import generate
        verify_source(p["source"])
        directory=store.directory(p["id"])
        progress(2,"원본 확인 중")
        transcript,vad,model=[],[],None
        if p["source"]["hasAudio"]:
            # Check model before expensive visual analysis; never downgrade to silence-only editing.
            from models.manager import ready
            if not ready(store.root,request.get("model","small"),verify=True):
                raise ValueError("음성 모델이 없습니다. 설정에서 다운로드 동의 또는 오프라인 모델 가져오기를 먼저 진행해 주세요.")
        scenes,motion=visual_analysis(p["source"]["path"],p["source"]["duration"],progress)
        silences=[]
        if p["source"]["hasAudio"]:
            progress(36,"침묵·음성 감지 준비 중")
            silences=silence_ranges(p["source"]["path"],p["source"]["duration"])
            transcript,vad,model=transcribe(p["source"],store.root,request.get("model","small"),directory,progress)
        progress(85,"문맥·반복·중요 표현을 비교해 편집점 선정 중")
        analysis_summary={}
        draft_mode = action == "longformDraft"
        style = "basic" if draft_mode else p["style"]
        cuts,warnings=plan(p["source"],transcript,silences,scenes,motion,vad,style,analysis_summary)
        captions = generate(transcript, style, p["settings"])
        if draft_mode:
            from engine.longform import intersects, occupied
            present = occupied(p["cuts"], p["source"]["duration"])
            cuts = [*p["cuts"], *(dict(cut, enabled=False, review=True) for cut in cuts
                                  if not intersects(present, cut["start"], cut["end"]))]
            captions = p["captions"] or captions
            analysis_summary.update(style=p["style"], automaticCuts=sum(c["enabled"] for c in cuts),
                                    reviewCuts=sum(c["review"] and not c["enabled"] for c in cuts))
        if model and model.get("fallback"):
            warnings.append(model["fallback"])
        p.update(transcript=transcript,captions=captions,cuts=cuts,scenes=scenes,motion=motion,
                 warnings=warnings,model=model,analyzed=True,analysisSummary=analysis_summary,revision=p["revision"]+1)
        if not draft_mode:
            p["settings"]["zoom"]=STYLES[p["style"]]["zoom"]
            if p["style"]=="shorts":
                p["settings"]["aspect"]="9:16"
        p=store.save(p,snapshot=True)
        progress(100,"분석 완료 · 편집 구간을 검수해 주세요")
        if draft_mode:
            return {"project": p, "audit": transcript_audit(p), "draft": make_draft(p, target)}
    elif action=="render":
        from media.render import render
        p["output"]=render(p,store.directory(p["id"]),progress)
        store.save(p)
    else:
        raise ValueError("지원하지 않는 엔진 명령입니다.")
    return {"project":p,"audit":transcript_audit(p)}


def main():
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    def send(data):
        print(json.dumps(data,ensure_ascii=False,allow_nan=False),flush=True)
    def progress(percent,message):
        send({"type":"progress","percent":round(percent,1),"message":message})
    try:
        line=sys.stdin.buffer.readline(2*1024*1024+1)
        if len(line)>2*1024*1024:
            raise ValueError("명령 데이터가 너무 큽니다.")
        request=json.loads(line.decode("utf-8"))
        # Keep stdout reserved for framed protocol, including during native library imports.
        import contextlib
        with contextlib.redirect_stdout(sys.stderr):
            def framed_progress(percent,message):
                sys.__stdout__.write(json.dumps({"type":"progress","percent":round(percent,1),"message":message},ensure_ascii=False)+"\n")
                sys.__stdout__.flush()
            result=dispatch(request,framed_progress)
        send({"type":"result","data":result})
    except Exception as exc:
        send({"type":"error","message":str(exc)})
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
