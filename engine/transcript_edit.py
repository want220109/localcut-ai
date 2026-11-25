"""Apply selected, saved subtitle ranges to the project's existing cut timeline."""
from bisect import bisect_right
from uuid import uuid4

from engine.project import merged_ranges


def require_revision(project, revision):
    if type(revision) is not int or revision != project["revision"]:
        raise ValueError("편집 내용이 바뀌었습니다. 다시 선택해 주세요.")


def range_parts(start, end, blocks, block_ends):
    """Split a source range at its intersections with sorted, merged blocks."""
    cursor = start
    for index in range(bisect_right(block_ends, start), len(blocks)):
        a, b = blocks[index]
        if a >= end:
            break
        if cursor < a:
            yield cursor, a, False
        cursor = min(end, b)
        yield max(start, a), cursor, True
    if cursor < end:
        yield cursor, end, False


def edit_transcript(store, project, revision, line_ids, operation):
    require_revision(project, revision)
    if (operation not in {"exclude", "restore"} or not isinstance(line_ids, list) or not line_ids
            or any(not isinstance(line_id, str) for line_id in line_ids)):
        raise ValueError("편집할 대본 줄을 선택해 주세요.")
    lines = {line["id"]: line for line in project["captions"] or project["transcript"]}
    selected = set(line_ids)
    if not selected <= lines.keys():
        raise ValueError("선택한 대본 줄을 찾을 수 없습니다. 다시 선택해 주세요.")

    duration = project["source"]["duration"]
    spans = merged_ranges((dict(lines[line_id], enabled=True) for line_id in selected), duration)
    if operation == "exclude":
        cuts = list(project["cuts"])
        blocks = merged_ranges(cuts, duration)
        ends = [end for _, end in blocks]
        for start, end in spans:
            for a, b, removed in range_parts(start, end, blocks, ends):
                if not removed:
                    cuts.append({"id": uuid4().hex[:12], "start": a, "end": b, "enabled": True,
                                 "review": False, "kind": "manual", "confidence": 1,
                                 "reason": "대본에서 선택한 영상 구간"})
    else:
        cuts = []
        ends = [end for _, end in spans]
        for cut in project["cuts"]:
            if not cut["enabled"]:
                cuts.append(cut)
                continue
            parts = list(range_parts(cut["start"], cut["end"], spans, ends))
            if not any(restored for _, _, restored in parts):
                cuts.append(cut)
                continue
            original = next((i for i, (_, _, restored) in enumerate(parts) if not restored), 0)
            for index, (a, b, restored) in enumerate(parts):
                piece = dict(cut, id=cut["id"] if index == original else uuid4().hex[:12], start=a, end=b)
                if restored:
                    piece.update(enabled=False, review=False, reason="대본에서 선택해 복원한 영상 구간")
                cuts.append(piece)

    if cuts == project["cuts"]:
        return project
    # Reject selections that leave no video frame or too many segments for the exporter.
    from media.render import frame_intervals
    frame_intervals({**project, "cuts": cuts})
    return store.edit(project["id"], {"cuts": sorted(cuts, key=lambda cut: cut["start"])})
