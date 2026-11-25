from __future__ import annotations

import math
import re
import subprocess
import sys
import wave

from media.tools import binary, extract_audio, run
from models.manager import model_path, ready


def silence_ranges(source, duration):
    result = run([binary("ffmpeg"), "-nostdin", "-hide_banner", "-nostats", "-i", source,
                  "-map", "0:a:0", "-af", "silencedetect=noise=-38dB:d=0.35", "-vn", "-f", "null", "-"])
    ranges, start = [], None
    for kind, value in re.findall(r"silence_(start|end):\s*([0-9.]+)", result.stderr):
        if kind == "start":
            start = float(value)
        elif start is not None:
            ranges.append([start, min(duration, float(value))])
            start = None
    if start is not None:
        ranges.append([start, duration])
    return ranges


def visual_analysis(source, duration, progress):
    import cv2
    import numpy as np
    from scenedetect.detectors import ContentDetector
    detector = ContentDetector(threshold=24, min_scene_len=4)
    args = [binary("ffmpeg"), "-nostdin", "-v", "error", "-i", source, "-an", "-vf", "fps=2,scale=160:90",
            "-pix_fmt", "bgr24", "-f", "rawvideo", "-"]
    flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
    # stderr to a temporary file prevents a pipe deadlock on corrupt media.
    import tempfile
    scenes, motion, previous, index = [], [], None, 0
    with tempfile.TemporaryFile() as errors:
        p = subprocess.Popen(args, stdout=subprocess.PIPE, stderr=errors, **flags)
        try:
            while True:
                data = p.stdout.read(160*90*3)
                if len(data) != 160*90*3:
                    break
                frame = np.frombuffer(data, dtype=np.uint8).reshape(90, 160, 3)
                for n in detector.process_frame(index, frame):
                    if n > 0:
                        scenes.append(round(n/2, 3))
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                change = float(np.mean(cv2.absdiff(gray, previous))/255) if previous is not None else 0
                motion.append({"time": index/2, "value": round(change, 5)})
                previous = gray
                index += 1
                if index % 60 == 0:
                    progress(12 + min(22, 22*index/2/duration), "장면 전환·움직임 분석 중")
            code = p.wait()
            if code or index == 0:
                errors.seek(0)
                raise RuntimeError("영상 장면 분석 실패: " + errors.read().decode(errors="replace")[-1000:])
        finally:
            if p.poll() is None:
                p.kill()
                p.wait()
            p.stdout.close()
    return scenes, motion


def transcribe(source, root, name, work, progress, *, model_verified=False):
    if not model_verified and not ready(root, name, verify=True):
        raise ValueError("한국어 음성 모델이 없습니다. 설정에서 모델 다운로드에 동의하거나 오프라인 모델 폴더를 가져와 주세요.")
    import ctranslate2
    import numpy as np
    from faster_whisper import WhisperModel
    from faster_whisper.vad import VadOptions, get_speech_timestamps
    audio_path = work / "analysis.wav"
    extract_audio(source["path"], audio_path)
    try:
        with wave.open(str(audio_path), "rb") as f:
            audio = np.frombuffer(f.readframes(f.getnframes()), dtype=np.int16).astype(np.float32)/32768
        # VAD also protects speech not recognized by ASR from being treated as dead air.
        speech = get_speech_timestamps(audio, VadOptions(min_silence_duration_ms=450))
        vad = [[s["start"]/16000, s["end"]/16000] for s in speech]
        device = "cuda" if ctranslate2.get_cuda_device_count() > 0 else "cpu"
        fallback = None
        def recognize(selected):
            model = WhisperModel(str(model_path(root, name)), device=selected,
                                 compute_type="float16" if selected == "cuda" else "int8", local_files_only=True,
                                 cpu_threads=4)
            segments, info = model.transcribe(audio, language="ko", beam_size=5, vad_filter=True,
                                             vad_parameters={"min_silence_duration_ms": 450}, word_timestamps=True,
                                             condition_on_previous_text=False)
            transcript = []
            # CUDA libraries can fail lazily on the first encode, so fallback covers iteration too.
            for s in segments:
                a, b = max(0, s.start), min(source["duration"], s.end)
                if b <= a or not s.text.strip():
                    continue
                confidence = min(1, math.exp(s.avg_logprob))*(1-s.no_speech_prob)
                transcript.append({"id": f"s{len(transcript)}", "start": a, "end": b,
                                   "text": re.sub(r"\s+", " ", s.text).strip(), "confidence": round(confidence, 3),
                                   "words": [{"start": max(a, w.start), "end": min(b, w.end), "text": w.word,
                                              "confidence": round(w.probability, 3)} for w in (s.words or []) if min(b,w.end)>max(a,w.start)]})
                progress(38+min(40,40*b/source["duration"]), "한국어 음성 인식 중 · " + ("GPU" if selected=="cuda" else "CPU"))
            return transcript,info
        try:
            transcript,info=recognize(device)
        except RuntimeError:
            if device != "cuda":
                raise
            device, fallback = "cpu", "GPU 드라이버/CUDA 라이브러리를 사용할 수 없어 CPU로 전환했습니다."
            progress(38,fallback)
            transcript,info=recognize("cpu")
        return transcript, vad, {"name": name, "device": device, "language": info.language, "fallback": fallback}
    finally:
        audio_path.unlink(missing_ok=True)
