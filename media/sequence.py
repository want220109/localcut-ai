from pathlib import Path
from base64 import b64encode
from shutil import disk_usage, rmtree
from tempfile import TemporaryDirectory
from uuid import uuid4

from engine.project import atomic_json
from engine.sequence import SEQUENCE_FPS, clip_intervals, seconds_intervals, sequence_audit
from media.render import dimensions, subtitle_filter, write_ass
from media.tools import binary, probe, run, verify_source
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


def frame_count(spans):
    return sum(end - start for start, end in spans)


def edge_intervals(spans, *, tail=False):
    remaining = 3 * SEQUENCE_FPS
    excerpt = []
    for start, end in reversed(spans) if tail else spans:
        length = min(end - start, remaining)
        excerpt.append((end - length, end) if tail else (start, start + length))
        remaining -= length
        if not remaining:
            break
    return list(reversed(excerpt)) if tail else excerpt


def encode_intervals(clip, spans, settings, width, height, audio, directory, names, *, preview=False):
    captions = remap(clip["captions"], seconds_intervals(spans))
    elapsed = 0
    for start, end in spans:
        offset, limit = elapsed / SEQUENCE_FPS, (elapsed + end - start) / SEQUENCE_FPS
        local = [{**cue, "start": max(offset, cue["start"]) - offset, "end": min(limit, cue["end"]) - offset}
                 for cue in captions if cue["start"] < limit and cue["end"] > offset]
        name = f"part-{len(names):04}.mov"
        work = directory / f"part-{len(names):04}"
        work.mkdir()
        encode_clip(clip, end - start, settings, width, height, audio, directory / name, work,
                    local, start=start, preview=preview)
        names.append(name)
        elapsed += end - start
    return captions


def preview_excerpts(project, excerpts, progress):
    width, height = dimensions(project)
    scale = min(1, 640 / max(width, height))
    width, height = max(2, round(width * scale / 2) * 2), max(2, round(height * scale / 2) * 2)
    audio = any(clip["source"]["hasAudio"] for clip, _ in excerpts)
    with TemporaryDirectory(prefix="localcut-connection-") as temporary:
        directory = Path(temporary)
        names = []
        for index, (clip, spans) in enumerate(excerpts):
            if spans:
                progress(index * 45, "편집 연결부 준비 중")
                encode_intervals(clip, spans, project["settings"], width, height, audio, directory, names, preview=True)
        output = directory / "connection.mp4"
        join_clips(directory, names, audio, output)
        if output.stat().st_size > 2 * 1024**2:
            raise RuntimeError("연결부 미리보기 파일이 너무 큽니다.")
        return b64encode(output.read_bytes()).decode("ascii")


def sequence_connection(project, left, right, progress):
    before = edge_intervals(clip_intervals(left), tail=True)
    after = edge_intervals(clip_intervals(right))
    video = preview_excerpts(project, [(left, before), (right, after)], progress)
    return {"video": video, "joinAt": frame_count(before) / SEQUENCE_FPS,
            "from": left["name"], "to": right["name"]}


def sequence_cut_preview(project, clip, cut_id, progress):
    cut = next((item for item in clip.get("cuts", []) if item["id"] == cut_id), None)
    if cut is None:
        raise ValueError("미리 볼 편집 구간을 다시 선택해 주세요.")
    verify_source(clip["source"])
    proposed = {**clip, "cuts": [dict(item, enabled=True) if item is cut else item for item in clip["cuts"]]}
    spans = clip_intervals(proposed)
    if not spans:
        raise ValueError("클립 전체를 삭제할 수 없습니다.")
    midpoint = (cut["start"] + cut["end"]) * SEQUENCE_FPS / 2
    before = edge_intervals([span for span in spans if span[1] <= midpoint], tail=True)
    after = edge_intervals([span for span in spans if span[0] >= midpoint])
    if not before and not after:
        raise ValueError("미리 볼 만큼 긴 편집 구간이 없습니다.")
    video = preview_excerpts(project, [(clip, before + after)], progress)
    return {"video": video, "joinAt": frame_count(before) / SEQUENCE_FPS}

def render_sequence(project, directory, progress):
    clips = [(clip, clip_intervals(clip)) for clip in project["clips"] if clip["enabled"]]
    total = sum(frame_count(spans) for _, spans in clips)
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
            for index, (clip, spans) in enumerate(clips):
                progress(2 + 89 * completed / total, f"클립 인코딩 중 ({index+1}/{len(clips)})")
                local = encode_intervals(clip, spans, settings, width, height, audio, segments, records)
                offset = completed / SEQUENCE_FPS
                captions.extend(dict(cue, start=cue["start"]+offset, end=cue["end"]+offset) for cue in local)
                completed += frame_count(spans)
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
