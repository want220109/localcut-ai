"""Verify release companion checksums and join source archive parts. No extraction."""
import hashlib
import json
import shutil
from pathlib import Path


def main():
    root=Path(__file__).resolve().parent
    manifest=json.loads((root/"SOURCE-MANIFEST.json").read_text(encoding="utf-8"))
    records=manifest["files"]
    for item in records:
        filename=root/item["file"]
        if filename.parent!=root or not filename.is_file():
            raise ValueError("Missing source asset: "+item["file"])
        with filename.open("rb") as source:
            if filename.stat().st_size!=item["bytes"] or hashlib.file_digest(source,"sha256").hexdigest()!=item["sha256"]:
                raise ValueError("Source checksum mismatch: "+filename.name)
    for key in ["cacheParts","ffmpegBundleParts"]:
        parts=manifest[key]
        entries=[next(item for item in records if item["file"]==name) for name in parts]
        target=root/entries[0]["reassembledFile"]
        if target.parent!=root:
            raise ValueError("Invalid source archive path")
        with target.open("wb") as output:
            for entry in entries:
                with (root/entry["file"]).open("rb") as source:
                    shutil.copyfileobj(source,output,1024*1024)
        with target.open("rb") as source:
            if hashlib.file_digest(source,"sha256").hexdigest()!=entries[0]["reassembledSha256"]:
                raise ValueError("Reassembled source checksum mismatch")
        print("Verified",target.name)


if __name__=="__main__":
    main()
