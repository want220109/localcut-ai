"""Fail closed on a missing, altered or mismatched updater artifact."""
import base64
import hashlib
import json
import re
import sys
from pathlib import Path

import yaml


def verify(directory, version):
    directory=Path(directory)
    manifest=yaml.safe_load((directory/"latest.yml").read_text(encoding="utf-8"))
    if manifest.get("version")!=version or not re.fullmatch(r"\d+\.\d+\.\d+",version):
        raise ValueError("Stable update version does not match the build")
    files=manifest.get("files",[])
    expected=f"LocalCut-AI-{version}-x64-Setup.exe"
    if len(files)!=1 or files[0].get("url")!=expected or manifest.get("path")!=expected:
        raise ValueError("Unexpected update payload")
    installer=directory/expected
    with installer.open("rb") as source:
        if source.read(2)!=b"MZ":
            raise ValueError("Update payload is not a Windows executable")
    sha512=hashlib.file_digest(installer.open("rb"),"sha512").digest()
    if base64.b64encode(sha512).decode()!=files[0].get("sha512") or manifest.get("sha512")!=files[0].get("sha512") or files[0].get("size")!=installer.stat().st_size:
        raise ValueError("Installer integrity check failed")
    if not Path(str(installer)+".blockmap").is_file():
        raise ValueError("Updater blockmap missing")
    return {"version":version,"installer":expected,"bytes":installer.stat().st_size,"sha256":hashlib.file_digest(installer.open("rb"),"sha256").hexdigest(),"sha512":files[0]["sha512"]}


if __name__=="__main__":
    print(json.dumps(verify(sys.argv[1],sys.argv[2]),indent=2))
