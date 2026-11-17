import json
import os
import re
import subprocess
from pathlib import Path

tag=os.environ["TAG"]
version=json.loads(Path("package.json").read_text())["version"]
if tag!="v"+version:
    raise SystemExit("Tag must match package.json version")
if not re.fullmatch(r"\d+",os.environ["RUN_ID"]):
    raise SystemExit("Invalid workflow run ID")
run=json.loads(subprocess.check_output(["gh","api",f"repos/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['RUN_ID']}"],text=True))
head=subprocess.check_output(["git","rev-parse","HEAD"],text=True).strip()
if run["conclusion"]!="success" or run["head_sha"]!=head or run["path"]!=".github/workflows/windows.yml":
    raise SystemExit("Build must be a successful Windows installer run for this exact tag commit")
if run["head_repository"]["full_name"]!=os.environ["GITHUB_REPOSITORY"]:
    raise SystemExit("Build must originate from this repository")
channel=os.environ.get("CHANNEL",os.environ.get("INPUT_CHANNEL",""))
if (channel=="beta") != ("-" in version):
    raise SystemExit("Beta requires a prerelease version; stable requires a normal version")
print("Verified Windows build provenance for",tag,head)
