from __future__ import annotations

import base64
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from engine.project import finite
from media.render import dimensions, frame_intervals, subtitle_filter, video_framing, write_ass
from media.tools import binary, verify_source
from subtitles.captions import remap


def caption_frame(project, draft):
    """Render one frame using the current edits and an unsaved caption draft."""
    source = project["source"]
    saved = next((cue for cue in project["captions"] if cue["id"] == draft.get("id")), None)
    if saved is None:
        raise ValueError("이 작업에서 선택한 자막을 찾을 수 없습니다.")
    text = draft.get("text")
    if not isinstance(text, str) or len(text) > 10000:
        raise ValueError("자막은 10,000자 이내로 입력해 주세요.")
    start = finite(draft.get("start"), 0, source["duration"])
    end = finite(draft.get("end"), 0, source["duration"])
    if end <= start:
        raise ValueError("종료 시간을 시작 시간보다 뒤로 지정해 주세요.")

    replacement = saved
    if (text, start, end) != (saved["text"], saved["start"], saved["end"]):
        replacement = {**saved, "text": text, "start": start, "end": end, "textEdited": True}
    captions = [replacement if cue["id"] == saved["id"] else cue for cue in project["captions"]]
    intervals = frame_intervals(project)
    cues = [cue for cue in remap(captions, intervals, include_ids=True) if cue["id"] == saved["id"]]

    midpoint = (start + end) / 2
    source_time = midpoint
    index, length = 0, 0
    spans, offset, midpoint_output = [], 0.0, None
    for i, (a, b) in enumerate(intervals):
        spans.append((i, a, b - a, offset))
        if a <= midpoint < b:
            midpoint_output = offset + midpoint - a
            index, length = i, b - a
        offset += b - a

    cue = next((cue for cue in cues if midpoint_output is not None and cue["start"] <= midpoint_output < cue["end"]), None)
    if cue is None and cues:
        cue = max(cues, key=lambda value: value["end"] - value["start"])
        cue_midpoint = (cue["start"] + cue["end"]) / 2
        for i, a, duration, output_start in spans:
            if output_start <= cue_midpoint < output_start + duration:
                source_time = a + cue_midpoint - output_start
                index, length = i, duration
                break

    settings = project["settings"]
    message = None
    if not settings["subtitles"]:
        message = "자막 사용이 꺼져 있습니다."
    elif cue is None and text.strip():
        message = "이 자막은 현재 편집 결과에 표시되지 않습니다."

    verify_source(source)
    width, height = dimensions(project)
    # Apply the real output styling before downscaling the already composed frame.
    ratio = min(1, 960 / max(width, height))
    preview_width, preview_height = max(2, round(width * ratio)), max(2, round(height * ratio))
    video_filter = "setpts=PTS-STARTPTS," + video_framing(settings, index, length, width, height)
    with TemporaryDirectory(prefix="localcut-caption-") as folder:
        directory = Path(folder)
        if cue is not None and settings["subtitles"]:
            write_ass([{"start": 0, "end": 1, "text": cue["text"]}], settings, width, height, directory)
            video_filter += "," + subtitle_filter(settings)
        video_filter += f",scale={preview_width}:{preview_height}"
        source_time = min(source_time, max(0, source["duration"] - 1 / source["fps"]))
        args = [binary("ffmpeg"), "-nostdin", "-v", "error", "-filter_threads", "1", "-ss", f"{source_time:.8f}",
                "-i", source["path"], "-map", "0:v:0", "-an", "-vf", video_filter, "-frames:v", "1",
                "-c:v", "png", "-threads", "1", "-f", "image2pipe", "pipe:1"]
        flags = {"creationflags": subprocess.CREATE_NO_WINDOW} if sys.platform == "win32" else {}
        try:
            result = subprocess.run(args, cwd=directory, capture_output=True, timeout=30, **flags)
        except subprocess.TimeoutExpired as error:
            raise RuntimeError("정지 화면을 만드는 데 시간이 너무 오래 걸렸습니다.") from error
        if result.returncode or not result.stdout.startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError("해당 장면의 정지 화면을 만들지 못했습니다.")

    encoded = base64.b64encode(result.stdout).decode("ascii")
    return {"image": "data:image/png;base64," + encoded, "sourceTime": source_time, "message": message}
