from engine.project import Store
from engine.service import dispatch


def ids(listing):
    return {item["id"] for item in listing}


def test_hide_and_restore_only_change_recent_list_visibility(tmp_path):
    store = Store(tmp_path)
    original = tmp_path / "원본.mp4"
    original.write_bytes(b"source")
    first = store.create({"path": str(original), "duration": 4, "width": 640, "height": 360})
    second = store.create({"path": "another.mp4", "duration": 3, "width": 640, "height": 360})
    project_file = store.directory(first["id"]) / "project.json"
    exported = project_file.with_name("export.mp4")
    exported.write_bytes(b"output")
    saved = project_file.read_bytes()

    def call(operation):
        return dispatch({"root": str(tmp_path), "action": "changeHistory", "operation": operation, "id": first["id"]})

    hidden = call("hide")
    assert ids(hidden["recent"]) == {second["id"]}
    assert ids(hidden["hidden"]) == {first["id"]}
    assert Store(tmp_path).history() == hidden
    assert call("hide") == hidden
    assert project_file.read_bytes() == saved
    assert original.read_bytes() == b"source" and exported.read_bytes() == b"output"

    store.edit(first["id"], {"name": "작업을 계속 편집"})
    assert Store(tmp_path).history()["hidden"][0]["name"] == "작업을 계속 편집"
    restored = call("restore")
    assert ids(restored["recent"]) == {first["id"], second["id"]} and restored["hidden"] == []
    assert Store(tmp_path).list() == restored["recent"]


def test_clear_preserves_prior_hidden_items_and_new_jobs_show_up(tmp_path):
    store = Store(tmp_path)
    projects = [store.create({"path": f"{i}.mp4", "duration": 3, "width": 640, "height": 360}) for i in range(3)]
    store.change_history("hide", projects[0]["id"])
    cleared = store.change_history("clear")
    assert cleared["recent"] == [] and ids(cleared["hidden"]) == {p["id"] for p in projects}
    fresh = store.create({"path": "fresh.mp4", "duration": 3, "width": 640, "height": 360})
    assert ids(Store(tmp_path).list()) == {fresh["id"]}
    assert not Store(tmp_path).change_history("restoreAll")["hidden"]
    assert ids(Store(tmp_path).list()) == {p["id"] for p in [*projects, fresh]}
