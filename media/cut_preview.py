"""Join up to three seconds from either side of a saved edit into a short local clip."""
import base64
import math
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.transcript_edit import require_revision
from media.render import build_graph, dimensions, frame_intervals, write_ass
from media.tools import binary, probe, run, verify_source
from subtitles.captions import remap


def cut_preview(project, revision, cut_id):
    require_revision(project, revision)
    cut = next((cut for cut in project["cuts"] if cut["id"] == cut_id and cut["enabled"]), None)
    if cut is None:
        raise ValueError("삭제가 적용된 컷을 선택해 주세요.")
    source = project["source"]
    verify_source(source)
    intervals = frame_intervals(project)
    midpoint = (cut["start"] + cut["end"]) / 2
    for i, ((left_start, left_end), (right_start, right_end)) in enumerate(zip(intervals, intervals[1:])):
        if left_end <= midpoint <= right_start and right_start > left_end:
            break
    else:
        raise ValueError("연결부를 보려면 컷 앞뒤에 보존된 영상이 있어야 합니다.")

    fps = source["fps"]
    window = math.floor(fps * 3 + 1e-6) / fps
    clips = [(max(left_start, left_end-window), left_end),
             (right_start, min(right_end, right_start+window))]
    context = [(i, left_end-left_start), (i+1, right_end-right_start)]
    jump = left_end-clips[0][0]
    length = jump+clips[1][1]-right_start
    width, height = dimensions(project)
    scale = min(1, 960/max(width, height))
    width, height = max(2, round(width*scale/2)*2), max(2, round(height*scale/2)*2)
    with TemporaryDirectory(prefix="localcut-cut-") as temporary:
        directory = Path(temporary)
        if project["settings"]["subtitles"] and project["captions"]:
            write_ass(remap(project["captions"], clips), project["settings"], width, height, directory)
        graph = build_graph(project, clips, width, height, seeked_segments=context)
        (directory/"filters.txt").write_text(graph, encoding="utf-8")
        args = [binary("ffmpeg"), "-nostdin", "-v", "error"]
        for a, b in clips:
            # Input-side seek avoids decoding the potentially long removed gap.
            args.extend(["-ss", f"{a:.8f}", "-t", f"{b-a:.8f}", "-i", source["path"]])
        args += ["-filter_complex_threads", "1", "-filter_complex_script", "filters.txt", "-map", "[outv]"]
        if source["hasAudio"]:
            args += ["-map", "[outa]", "-c:a", "aac", "-b:a", "96k"]
        output = directory/"connection.mp4"
        args += ["-c:v", "libx264", "-preset", "veryfast", "-crf", "25", "-maxrate", "1000k",
                 "-bufsize", "1000k", "-threads", "2", "-movflags", "+faststart",
                 "-t", f"{length:.8f}", str(output)]
        run(args, cwd=directory, timeout=90)
        duration = probe(output)["duration"]
        if abs(duration-length) > max(.15, 2/fps) or duration <= jump or output.stat().st_size > 2*1024*1024:
            raise ValueError("연결부 미리보기의 영상 길이나 크기를 확인할 수 없습니다.")
        video = base64.b64encode(output.read_bytes()).decode("ascii")
    return {"video": video, "joinAt": jump, "cutStart": left_end, "cutEnd": right_start,
            "before": clips[0], "after": clips[1]}
