"""Validate a successful Windows build and export immutable Actions outputs."""
import base64
import json
import os
import re
import subprocess

repo=os.environ["GITHUB_REPOSITORY"]
run_id=os.environ["RUN_ID"]
if not re.fullmatch(r"\d+",run_id):
    raise SystemExit("Invalid build ID")
run=json.loads(subprocess.check_output(["gh","api",f"repos/{repo}/actions/runs/{run_id}"]))
if run["conclusion"]!="success" or run["path"]!=".github/workflows/windows.yml" or run["head_repository"]["full_name"]!=repo or run["head_branch"]!="main":
    raise SystemExit("Untrusted or failed build")
sha=run["head_sha"]
file=json.loads(subprocess.check_output(["gh","api",f"repos/{repo}/contents/package.json?ref={sha}"]))
version=json.loads(base64.b64decode(file["content"]))["version"]
if not re.fullmatch(r"\d+\.\d+\.\d+",version):
    raise SystemExit("This preparation workflow handles stable builds only")
with open(os.environ["GITHUB_OUTPUT"],"a",encoding="utf-8") as output:
    output.write(f"sha={sha}\nrun={run_id}\nversion={version}\n")
print("Verified candidate",version,sha,run_id)
