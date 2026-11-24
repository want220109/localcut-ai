"""Download the verified 0.2.4 installer for isolated Windows upgrade tests."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS")!="true":
    raise SystemExit("This fixture runs only in GitHub Actions")
repo=os.environ["GITHUB_REPOSITORY"]
asset_id=785374331
expected="fabe07b0c65e195648d27b13d86febe2882d5a11ea37c0c7484d8b50f30700cd"
asset=json.loads(subprocess.check_output(["gh","api",f"repos/{repo}/releases/assets/{asset_id}"]))
if asset["name"]!="LocalCut-AI-0.2.4-x64-Setup.exe" or asset.get("digest")!="sha256:"+expected:
    raise SystemExit("Previous installer provenance mismatch")
destination=Path("previous/release")/asset["name"]
destination.parent.mkdir(parents=True,exist_ok=True)
with destination.open("wb") as output:
    subprocess.run(["gh","api",f"repos/{repo}/releases/assets/{asset_id}","-H","Accept: application/octet-stream"],stdout=output,check=True)
with destination.open("rb") as source:
    if destination.stat().st_size!=asset["size"] or hashlib.file_digest(source,"sha256").hexdigest()!=expected:
        raise SystemExit("Previous installer checksum mismatch")
print("Verified Windows upgrade baseline 0.2.4")
