"""Repair model files for the installed 0.1.0 app without rebuilding its EXE.

Only downloads pinned public model files after the user's prior download request.
Videos, audio and transcripts are never read or uploaded by this utility.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import traceback
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from engine.project import atomic_json
from models.manager import install, model_path, ready


def validate_cpu_model(directory):
    from faster_whisper import WhisperModel
    model=WhisperModel(str(directory),device="cpu",compute_type="int8",cpu_threads=4,local_files_only=True)
    # Constructor loads the actual native weights and tokenizer. No speech is inferred.
    del model


def check_app_closed():
    if sys.platform!="win32":
        return
    result=subprocess.run(["powershell.exe","-NoLogo","-NoProfile","-Command",
                           "if (Get-Process -Name 'LocalCut AI' -ErrorAction SilentlyContinue) { exit 10 }; exit 0"],
                          capture_output=True,text=True,creationflags=subprocess.CREATE_NO_WINDOW)
    if result.returncode==10:
        raise RuntimeError("LocalCut AI를 먼저 정상 종료한 뒤 복구를 다시 실행해 주세요. 작업 중인 앱은 강제로 종료하지 않습니다.")
    if result.returncode:
        raise RuntimeError("앱 종료 여부를 확인하지 못했습니다. 오류: "+result.stderr[-1000:])


def find_data_root(appdata):
    # Electron's default folder can use productName or package.name depending on
    # how the app was started. Prefer the single folder holding the prior download.
    roots=[Path(appdata)/name/"workspace" for name in ("LocalCut AI","localcut-ai")]
    roots=[p for p in roots if p.is_dir()]
    cached=[p for p in roots if (p/"download-cache").is_dir()]
    if len(cached)==1:
        return cached[0]
    if len(roots)==1:
        return roots[0]
    if len(roots)>1:
        raise RuntimeError("앱 작업 폴더가 여러 개 있어 자동 선택을 보류했습니다. model-repair-results/RESULT.txt 내용을 알려 주세요.")
    raise RuntimeError("앱 작업 폴더를 찾지 못했습니다. LocalCut AI를 한 번 실행하고 종료한 뒤 다시 시도해 주세요.")


def main(argv=None):
    parser=argparse.ArgumentParser(description="Repair the Korean speech model without rebuilding LocalCut")
    parser.add_argument("--model",choices=["small","tiny"],default="small")
    parser.add_argument("--data-root",type=Path)
    args=parser.parse_args(argv)
    if hasattr(sys.stdout,"reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    results=ROOT/"model-repair-results"
    results.mkdir(exist_ok=True)
    report={"status":"RUNNING","model":args.model,"nativeCpuLoadVerified":False,
            "speechRecognitionTest":"NOT_RUN","mediaUploaded":False}
    atomic_json(results/"result.json",report)
    try:
        check_app_closed()
        if args.data_root:
            data_root=args.data_root.resolve()
        elif sys.platform=="win32" and os.environ.get("APPDATA"):
            data_root=find_data_root(os.environ["APPDATA"])
        else:
            raise RuntimeError("Windows 앱의 저장 위치를 확인할 수 없습니다. Windows PC에서 실행해 주세요.")
        if not data_root.is_dir():
            raise RuntimeError("설치된 앱의 작업 폴더를 찾지 못했습니다. LocalCut AI를 한 번 실행하고 종료한 후 다시 시도해 주세요.")
        print("로컬 음성 모델 복구 · 프로그램 재설치/재빌드 없음",flush=True)
        print("기존 다운로드 캐시를 재사용합니다. 필요한 모델 파일만 받으며 영상과 대본은 전송하지 않습니다.",flush=True)
        def progress(percent,message):
            print(f"[{percent:.0f}%] {message}",flush=True)
        install(data_root,args.model,progress,legacy_json=True,validator=validate_cpu_model)
        if not ready(data_root,args.model,verify=True):
            raise RuntimeError("복구 후 모델 무결성 검증에 실패했습니다.")
        report.update(status="MODEL_REPAIRED_AND_CPU_LOADED",nativeCpuLoadVerified=True,
                      directory=str(model_path(data_root,args.model)))
        message=("모델 복구와 실제 CPU 모델 불러오기 검증이 완료되었습니다.\n"
                 "LocalCut AI를 다시 실행한 뒤 모델 준비 상태를 확인하고 짧은 한국어 영상을 분석해 주세요.\n"
                 "실제 발화의 한국어 인식 정확도는 아직 검증하지 않았습니다.\n")
        code=0
    except Exception as exc:
        report.update(status="FAILED",error=str(exc))
        (results/"details.log").write_text(traceback.format_exc(),encoding="utf-8")
        message="모델 복구 중단: "+str(exc)+"\nmodel-repair-results/RESULT.txt 내용을 채팅에 알려 주세요.\n"
        code=1
    atomic_json(results/"result.json",report)
    (results/"RESULT.txt").write_text(message,encoding="utf-8-sig")
    print(message,flush=True)
    return code


if __name__=="__main__":
    raise SystemExit(main())
