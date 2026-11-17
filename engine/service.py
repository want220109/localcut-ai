from __future__ import annotations

import json
import os
import shutil
import sys
from pathlib import Path

from engine import __version__
from engine.commands import interpret
from engine.project import Store, transcript_audit
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
    if action=="create":
        from media.preview import compatible_preview
        p=store.create(probe(request["source"]))
        p["preview"]=compatible_preview(p["source"],store.directory(p["id"]),progress)
        return store.save(p)
    p=store.load(request["id"])
    if action=="get":
        return {"project":p,"audit":transcript_audit(p)}
    if action=="edit":
        p=store.edit(p["id"],request["changes"])
    elif action=="undo":
        p=store.undo(p["id"])
    elif action=="command":
        changes,message=interpret(p,request["text"])
        p=store.edit(p["id"],changes)
        return {"project":p,"audit":transcript_audit(p),"message":message}
    elif action=="analyze":
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
        cuts,warnings=plan(p["source"],transcript,silences,scenes,motion,vad,p["style"])
        if model and model.get("fallback"):
            warnings.append(model["fallback"])
        p.update(transcript=transcript,captions=generate(transcript,p["style"],p["settings"]),cuts=cuts,scenes=scenes,motion=motion,
                 warnings=warnings,model=model,analyzed=True,revision=p["revision"]+1)
        p["settings"]["zoom"]=STYLES[p["style"]]["zoom"]
        if p["style"]=="shorts":
            p["settings"]["aspect"]="9:16"
        p=store.save(p,snapshot=True)
        progress(100,"분석 완료 · 편집 구간을 검수해 주세요")
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
