# LocalCut AI maintenance

- This is an offline Windows desktop app. Do not add cloud inference, video uploads, paid APIs or a Codex runtime dependency without the user's explicit request.
- Preserve original videos. UI edits cannot modify source/output paths. Keep OS operations behind the allowlisted preload/IPC boundary.
- Treat `engine/styles.json` as the editable style policy and `models/catalog.json` as the reviewed model catalog. Uncertain cuts must remain disabled review suggestions.
- Keep JSON schema compatibility. Migrate with backup before increasing the schema. Never remove userData during upgrades.
- For an engine change run `.venv/bin/python -m pytest -q`. For UI/main/updater changes run `npm test` and `node scripts/electron-smoke.cjs` with a working display; Linux CI uses Xvfb.
- Build the frozen engine with `python scripts/build-engine.py`, validate with `python scripts/frozen-smoke.py`, and use Windows Actions for the Windows installer. A Linux ELF executable is not a Windows installer.
- Report real ASR, CUDA, Windows installation and live online update tests separately. Do not claim a prepared workflow has run. Review `docs/STATUS.md` and update it with fresh evidence.
- Public publication requires explicit user/admin authorization. Configure required reviewers on GitHub's production environment; the YAML environment name alone does not enforce approval.
