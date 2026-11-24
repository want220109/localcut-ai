"""Download the verified 0.2.3 installer for isolated Windows upgrade tests."""
import hashlib
import json
import os
import subprocess
from pathlib import Path

if os.environ.get("GITHUB_ACTIONS")!="true":
    raise SystemExit("This fixture runs only in GitHub Actions")
repo=os.environ["GITHUB_REPOSITORY"]
asset_id=758226727
expected="3ecd6c88394cc72ff1ff4a48569b0e7a7a1acc5c93add3532f6b7598e40e67dc"
asset=json.loads(subprocess.check_output(["gh","api",f"repos/{repo}/releases/assets/{asset_id}"]))
if asset["name"]!="LocalCut-AI-0.2.3-x64-Setup.exe" or asset.get("digest")!="sha256:"+expected:
    raise SystemExit("Previous installer provenance mismatch")
destination=Path("previous/release")/asset["name"]
destination.parent.mkdir(parents=True,exist_ok=True)
with destination.open("wb") as output:
    subprocess.run(["gh","api",f"repos/{repo}/releases/assets/{asset_id}","-H","Accept: application/octet-stream"],stdout=output,check=True)
with destination.open("rb") as source:
    if destination.stat().st_size!=asset["size"] or hashlib.file_digest(source,"sha256").hexdigest()!=expected:
        raise SystemExit("Previous installer checksum mismatch")
print("Verified Windows upgrade baseline 0.2.3")
