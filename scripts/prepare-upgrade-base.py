"""Download the verified 0.2.7 installer for isolated Windows upgrade tests."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS")!="true":
    raise SystemExit("This fixture runs only in GitHub Actions")
repo=os.environ["GITHUB_REPOSITORY"]
version="0.2.7"
filename=f"LocalCut-AI-{version}-x64-Setup.exe"
expected="d58903d1cd5a189c9a8fe2347769ea37945faa8a6b73ea28e77637c3d2799684"
release=json.loads(subprocess.check_output(["gh","api",f"repos/{repo}/releases/tags/v{version}"]))
asset=next((item for item in release["assets"] if item["name"]==filename), None)
if release["draft"] or release["prerelease"] or not asset or asset.get("digest")!="sha256:"+expected:
    raise SystemExit("Previous installer provenance mismatch")
asset_id=asset["id"]
destination=Path("previous/release")/asset["name"]
destination.parent.mkdir(parents=True,exist_ok=True)
with destination.open("wb") as output:
    subprocess.run(["gh","api",f"repos/{repo}/releases/assets/{asset_id}","-H","Accept: application/octet-stream"],stdout=output,check=True)
with destination.open("rb") as source:
    if destination.stat().st_size!=asset["size"] or hashlib.file_digest(source,"sha256").hexdigest()!=expected:
        raise SystemExit("Previous installer checksum mismatch")
print(f"Verified Windows upgrade baseline {version}")
