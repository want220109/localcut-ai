from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

from engine.project import atomic_json, keeps, transcript_audit, validate
from media.tools import binary, probe, verify_source
from subtitles.captions import ass, remap, srt
from subtitles.styles import selected_font
from engine import __version__


def frame_intervals(p):
    fps = p["source"]["fps"]
    result=[]
    for a,b in keeps(p):
        a = min(p["source"]["duration"],round(a*fps)/fps)
        b = min(p["source"]["duration"],round(b*fps)/fps)
        if b-a >= .5/fps:
            result.append([a,b])
    if not result:
        raise ValueError("출력할 영상 프레임이 없습니다.")
    if len(result)>300:
        raise ValueError("한 번에 300개 이하의 보존 구간을 출력할 수 있습니다. 일부 삭제 구간을 복원해 주세요.")
    return result


def dimensions(p):
    settings, source=p["settings"],p["source"]
    aspect = settings["aspect"]
    ratio = source["width"]/source["height"] if aspect=="source" else float(aspect.split(":")[0])/float(aspect.split(":")[1])
    if settings["resolution"]=="source":
        h=source["height"]
        if aspect != "source":
            h=min(1920 if aspect=="9:16" else 1080,source["height"])
    else:
        h=int(settings["resolution"])
        if aspect=="9:16":
            h=round(h*16/9)
    h=max(2,round(h/2)*2)
    w=max(2,round(h*ratio/2)*2)
    return w,h


def video_framing(settings, index, duration, width, height):
    # Alternate punch-in only after a cut, the same for the still and MP4.
    zoom = settings["zoom"] if index % 2 and duration >= 2 else 1
    filters = ["setsar=1"]
    if zoom > 1:
        filters.append(f"crop=w=trunc(iw/{zoom}/2)*2:h=trunc(ih/{zoom}/2)*2")
    filters.extend([f"scale={width}:{height}:force_original_aspect_ratio=increase", f"crop={width}:{height}", "format=yuv420p"])
    return ",".join(filters)


def subtitle_filter(settings):
    _, font_file = selected_font(settings)
    return "ass=filename=captions.ass" + (":fontsdir=fonts" if font_file else "")


def write_ass(captions, settings, width, height, directory):
    fallback = "Malgun Gothic" if sys.platform == "win32" else "Noto Sans CJK KR"
    (directory/"captions.ass").write_text(ass(captions,settings,width,height,fallback),encoding="utf-8")
    if settings["subtitles"] and captions:
        _, font_file = selected_font(settings)
        if font_file:
            (directory/"fonts").mkdir()
            shutil.copyfile(font_file,directory/"fonts"/font_file.name)


def build_graph(p, intervals, width, height):
    settings=p["settings"]
    has_audio=p["source"]["hasAudio"]
    fps=p["source"]["fps"]
    graph=[]
    for i,(a,b) in enumerate(intervals):
        vf=f"trim=start={a:.8f}:end={b:.8f},setpts=PTS-STARTPTS,fps={fps:.8f},"+video_framing(settings,i,b-a,width,height)
        graph.append(f"[0:v:0]{vf}[v{i}]")
        if has_audio:
            length=b-a
            graph.append(f"[0:a:0]atrim=start={a:.8f}:end={b:.8f},asetpts=PTS-STARTPTS,aresample=48000,"
                         f"apad=whole_dur={length:.8f},atrim=duration={length:.8f},"
                         f"afade=t=in:d=0.008,afade=t=out:st={max(0,length-.008):.8f}:d=0.008[a{i}]")
    labels="".join(f"[v{i}][a{i}]" if has_audio else f"[v{i}]" for i in range(len(intervals)))
    graph.append(labels+f"concat=n={len(intervals)}:v=1:a={1 if has_audio else 0}[joinedv]"+("[joineda]" if has_audio else ""))
    if settings["subtitles"] and p["captions"]:
        graph.append("[joinedv]"+subtitle_filter(settings)+"[outv]")
    else:
        graph.append("[joinedv]null[outv]")
    if has_audio:
        audio=[]
        if settings["denoise"]:
            audio += ["highpass=f=70", "afftdn=nf=-25:tn=1"]
        if settings["normalize"]:
            audio.append("loudnorm=I=-16:TP=-1.5:LRA=11")
        audio.append("aresample=48000")
        graph.append("[joineda]"+",".join(audio)+"[outa]")
    return ";\n".join(graph)


def render(p, directory, progress):
    validate(p)
    verify_source(p["source"])
    intervals=frame_intervals(p)
    width,height=dimensions(p)
    total=sum(b-a for a,b in intervals)
    free=shutil.disk_usage(directory).free
    if free<max(100*1024*1024,total*width*height*.12):
        raise RuntimeError("출력에 필요한 디스크 여유 공간이 부족합니다.")
    output=Path(directory)/("render-"+uuid.uuid4().hex[:12])
    output.mkdir()
    captions=remap(p["captions"],intervals)
    (output/"captions.srt").write_text(srt(captions),encoding="utf-8-sig")
    write_ass(captions,p["settings"],width,height,output)
    (output/"filters.txt").write_text(build_graph(p,intervals,width,height),encoding="utf-8")
    tmp=output/"edited.partial.mp4"
    crf={"high":"18","balanced":"21","small":"26"}[p["settings"]["quality"]]
    args=[binary("ffmpeg"),"-nostdin","-hide_banner","-y","-i",p["source"]["path"],
          "-filter_complex_threads","1","-filter_complex_script","filters.txt","-map","[outv]"]
    if p["source"]["hasAudio"]:
        args += ["-map","[outa]","-c:a","aac","-b:a","192k"]
    args += ["-c:v","libx264","-preset","medium","-crf",crf,"-threads","2","-pix_fmt","yuv420p",
             "-movflags","+faststart","-t",f"{total:.8f}","-progress","pipe:1","-nostats",str(tmp)]
    flags={"creationflags":subprocess.CREATE_NO_WINDOW} if sys.platform=="win32" else {}
    try:
        with (output/"ffmpeg.log").open("w",encoding="utf-8") as errors:
            worker=subprocess.Popen(args,cwd=output,stdout=subprocess.PIPE,stderr=errors,
                                    encoding="utf-8",errors="replace",**flags)
            try:
                for line in worker.stdout:
                    if line.startswith("out_time_us="):
                        try:
                            progress(min(94,100*float(line.partition("=")[2])/1e6/total),"MP4 인코딩 중")
                        except ValueError:
                            pass
                code=worker.wait()
            finally:
                if worker.poll() is None:
                    worker.kill()
                    worker.wait()
                worker.stdout.close()
        if code:
            raise RuntimeError("MP4 출력 실패: "+(output/"ffmpeg.log").read_text(encoding="utf-8")[-2200:])
        result=probe(tmp)
        if abs(result["duration"]-total)>max(.15,2/p["source"]["fps"]):
            raise RuntimeError("출력 길이가 편집 계획과 다릅니다. 로그를 확인해 주세요.")
        final=output/"edited.mp4"
        os.replace(tmp,final)
        result["path"]=str(final)
        audit=transcript_audit(p)
        manifest={"version":__version__,"revision":p["revision"],"source":p["source"],"output":result,
                  "intervals":intervals,"cuts":p["cuts"],"audit":audit,"captionCount":len(captions),"settings":p["settings"]}
        atomic_json(output/"report.json",manifest)
        progress(100,"출력 완료")
        return {"path":str(final),"srt":str(output/"captions.srt"),"report":str(output/"report.json"),
                "duration":result["duration"],"revision":p["revision"]}
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise
