import hashlib
import importlib.util
from pathlib import Path


def test_runtime_notices_include_native_dependencies_and_match_copied_bytes(tmp_path):
    path=Path(__file__).resolve().parents[1]/"scripts/collect-notices.py"
    spec=importlib.util.spec_from_file_location("notice_collector",path)
    module=importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    target=tmp_path/"notices"
    result=module.collect(target)
    distributions={d["name"].lower().replace("_","-"):d for d in result["distributions"]}
    for name in ["ctranslate2","faster-whisper","onnxruntime","av","opencv-python-headless","numpy","tokenizers","flatbuffers","scenedetect","pyinstaller"]:
        assert distributions[name]["notices"],name
    assert b"PYTHON SOFTWARE FOUNDATION LICENSE" in (target/"Python-LICENSE.txt").read_bytes().upper()
    for name,digest in result["files"].items():
        assert ".." not in Path(name).parts
        assert hashlib.sha256((target/name).read_bytes()).hexdigest()==digest
