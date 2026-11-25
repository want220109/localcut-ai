from pathlib import Path
from base64 import b64encode
from shutil import disk_usage, rmtree
from tempfile import TemporaryDirectory
from uuid import uuid4

from engine.project import atomic_json
from engine.sequence import SEQUENCE_FPS, clip_frames, sequence_audit
from media.render import dimensions, subtitle_filter, write_ass
from media.tools import binary, probe, run
from subtitles.captions import remap, srt


def sequence_framing(width, height):
    return (f"scale={width}:{height}:force_original_aspect_ratio=decrease:force_divisible_by=2,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,setsar=1,format=yuv420p")


def encode_clip(clip, frames, settings, width, height, audio, output, directory, captions, *, start=0, preview=False):
    source = clip["source"]
    length = frames / SEQUENCE_FPS
    video = (f"[0:V:0]setpts=PTS-STARTPTS,fps={SEQUENCE_FPS},{sequence_framing(width, height)},"
             f"tpad=stop_mode=clone:stop=-1,trim=end_frame={frames}")
    if settings["subtitles"] and captions:
        write_ass(captions, settings, width, height, directory)
        video += "," + subtitle_filter(settings)
    graph = video + "[video]"
    if audio:
        samples = frames * (48000 // SEQUENCE_FPS)
        track = ("[0:a:0]aresample=48000:async=1:first_pts=0,aformat=channel_layouts=stereo,apad"
                 if source["hasAudio"] else "anullsrc=r=48000:cl=stereo")
        graph += f";{track},atrim=end_sample={samples}[audio]"
    args = [binary("ffmpeg"), "-nostdin", "-v", "error"]
    if start:
        args += ["-ss", f"{start / SEQUENCE_FPS:.9f}"]
    args += ["-i", source["path"], "-filter_complex_threads", "1",
            "-filter_complex", graph, "-map", "[video]"]
    if audio:
        args += ["-map", "[audio]", "-c:a", "pcm_s16le", "-ar", "48000", "-ac", "2"]
    crf = {"high": "18", "balanced": "21", "small": "26"}[settings["quality"]]
    args += ["-c:v", "libx264", "-preset", "fast", "-threads", "2", "-video_track_timescale", "30000",
             "-t", f"{length:.9f}"]
    if preview:
        args += ["-maxrate", "1000k", "-bufsize", "1000k"]
    args.append(str(output))
    run(args, cwd=directory)


def join_clips(directory, names, audio, destination):
    (directory / "clips.txt").write_text("".join(f"file '{name}'\n" for name in names), encoding="ascii")
    args = [binary("ffmpeg"), "-nostdin", "-v", "error", "-f", "concat", "-safe", "1",
            "-i", "clips.txt", "-map", "0:v:0", "-c:v", "copy"]
    if audio:
        args += ["-map", "0:a:0", "-c:a", "aac", "-b:a", "192k"]
    args += ["-movflags", "+faststart", str(destination)]
    run(args, cwd=directory)


def sequence_connection(project, left, right, progress):
    width, height = dimensions(project)
    scale = min(1, 640 / max(width, height))
    width, height = max(2, round(width * scale / 2) * 2), max(2, round(height * scale / 2) * 2)
    audio = left["source"]["hasAudio"] or right["source"]["hasAudio"]
    before, after = (min(3 * SEQUENCE_FPS, clip_frames(clip)) for clip in (left, right))
    start = clip_frames(left) - before
    with TemporaryDirectory(prefix="localcut-connection-") as temporary:
        directory = Path(temporary)
        names = []
        for index, (clip, frames, offset) in enumerate(((left, before, start), (right, after, 0))):
            progress(index * 45, "클립 연결부 준비 중")
            name = f"clip-{index}.mov"
            names.append(name)
            work = directory / str(index)
            work.mkdir()
            captions = remap(clip["captions"], [(offset / SEQUENCE_FPS, (offset+frames) / SEQUENCE_FPS)])
            encode_clip(clip, frames, project["settings"], width, height, audio, directory / name, work,
                        captions, start=offset, preview=True)
        output = directory / "connection.mp4"
        join_clips(directory, names, audio, output)
        if output.stat().st_size > 2 * 1024**2:
            raise RuntimeError("연결부 미리보기 파일이 너무 큽니다.")
        video = b64encode(output.read_bytes()).decode("ascii")
    return {"video": video, "joinAt": before / SEQUENCE_FPS, "from": left["name"], "to": right["name"]}


def render_sequence(project, directory, progress):
    clips = [(clip, clip_frames(clip)) for clip in project["clips"] if clip["enabled"]]
    total = sum(frames for _, frames in clips)
    audio = any(clip["source"]["hasAudio"] for clip, _ in clips)
    width, height = dimensions(project)
    if disk_usage(directory).free < max(100 * 1024**2, total / SEQUENCE_FPS * width * height * .21):
        raise RuntimeError("출력에 필요한 디스크 여유 공간이 부족합니다.")
    output = Path(directory) / f"render-{uuid4().hex[:12]}"
    output.mkdir()
    final = output / "edited.mp4"
    captions, timeline, completed = [], [], 0
    settings = project["settings"]
    try:
        with TemporaryDirectory(prefix="segments-", dir=output) as temporary:
            segments = Path(temporary)
            records = []
            for index, (clip, frames) in enumerate(clips):
                progress(2 + 89 * completed / total, f"클립 인코딩 중 ({index+1}/{len(clips)})")
                name = f"clip-{index:03}.mov"
                work = segments / str(index)
                work.mkdir()
                local = remap(clip["captions"], [(0, frames / SEQUENCE_FPS)])
                encode_clip(clip, frames, settings, width, height, audio, segments / name, work, local)
                records.append(name)
                offset = completed / SEQUENCE_FPS
                captions.extend(dict(cue, start=cue["start"]+offset, end=cue["end"]+offset) for cue in local)
                completed += frames
                timeline.append({"id": clip["id"], "name": clip["name"], "start": offset,
                                 "end": completed / SEQUENCE_FPS})
            progress(94, "클립과 오디오 연결 중")
            join_clips(segments, records, audio, final)
            result = probe(final)
            if abs(result["duration"] - total / SEQUENCE_FPS) > .12:
                raise RuntimeError("출력 길이가 편집 순서와 다릅니다.")
        (output / "captions.srt").write_text(srt(captions), encoding="utf-8-sig")
        atomic_json(output / "report.json", {"revision": project["revision"], "clips": project["clips"],
                    "timeline": timeline, "output": result, "audit": sequence_audit(project["clips"]),
                    "captionCount": len(captions), "settings": settings})
    except BaseException:
        rmtree(output, ignore_errors=True)
        raise
    progress(100, "출력 완료")
    return {"path": str(final), "srt": str(output / "captions.srt"), "report": str(output / "report.json"),
            "duration": result["duration"], "revision": project["revision"]}
