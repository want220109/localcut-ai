# LocalCut AI · AI 자동 영상 편집기

Windows 10/11 x64를 위한 **로컬 우선 데스크톱 편집기 v0.2.0**입니다. Electron/React 화면과 Python/FFmpeg 엔진을 실제 구현했습니다. Codex 구독, OpenAI 키 또는 유료 API를 사용하지 않습니다.

**현재 배포 상태:** [GitHub Windows 빌드·설치 테스트](https://github.com/want220109/localcut-ai/actions/runs/44018941776)가 통과했습니다. Python 52개·Node 3개 테스트, 동결 엔진, 실제 NSIS 설치, 설치된 앱의 편집·MP4 저장·재실행을 검증했습니다. [설치본 ZIP](https://github.com/want220109/localcut-ai/actions/runs/44018941776/artifacts/14299694882)을 받아 압축을 풀고 `release/LocalCut-AI-0.2.0-x64-Setup.exe`를 실행하세요. Actions 다운로드에는 GitHub 로그인이 필요합니다. GitHub 공개 릴리스는 아직 없으며 실제 발화 인식 정확도·사용자 PC 업그레이드·온라인 업데이트 검증은 남아 있습니다. 검증 기록은 [개발 결과](docs/STATUS.md)를 확인하세요.

## 사용자 기능

0.2.0에는 **유튜브 롱폼·쇼츠·인스타 릴스 자막 프리셋 6종**, 무료 번들 글꼴, 위치 여백·단어 강조·두 줄 배치가 포함됩니다. [자막 프리셋과 업데이트 방법](docs/SUBTITLE_PRESETS.md)을 참고하세요.

Windows PC에서 무료로 직접 빌드·설치·테스트하려면 소스 ZIP을 모두 압축 푼 뒤 `START-WINDOWS-TEST.cmd`를 실행하세요. [Windows 빠른 시작](docs/WINDOWS_QUICKSTART.md)에 절차와 테스트 범위가 있습니다. 실행기는 준비되어 있으며 실제 Windows 실행 결과 확인이 필요합니다.

- MP4/MOV/AVI/MKV 선택·드래그, 메타데이터, 원본/결과 재생
- 한국어 faster-whisper + Silero VAD 로컬 추론; 명시적 동의 후 모델 다운로드/오프라인 가져오기
- PySceneDetect, 움직임, 실제 침묵, 대본 신뢰도·재녹음 신호를 함께 쓰는 보수적 편집
- 기본·빠른·쇼츠 설정; 불확실한 삭제와 60초 쇼츠 구성을 검토 제안으로 표시
- 컷 타임라인, 수동 시간 조정·복원, 원본/보존/삭제 대본 비교
- 단어 시간에 따른 한국어 자막 분할, 직접 수정, SRT 저장, MP4에 자막 삽입
- 음량 균일화·소음 완화·컷 경계 페이드·중앙 크롭·줌·출력 화질/비율
- 작업 자동 저장·최근 작업·이전 변경 되돌리기, 원본 변경 감지
- 무료 규칙 기반 한국어 수정 요청, 업데이트 채널/다운로드/명시적 재시작

## 개발 실행

Node.js 22.12 이상, Python 3.12, FFmpeg/FFprobe가 필요합니다. **최종 Windows 설치본에는 Python과 FFmpeg가 포함되므로 사용자는 별도로 설치하지 않습니다.**

```bash
python -m venv .venv
# Windows: .venv\Scripts\python -m pip install -r requirements-dev.txt -c constraints.txt
.venv/bin/python -m pip install -r requirements-dev.txt -c constraints.txt
npm ci
npm run desktop
```

Linux에서 `npm run desktop`은 데스크톱 디스플레이가 필요합니다. 관리형 Cloud의 읽기 전용 홈에서는 `XDG_CACHE_HOME`을 쓰기 가능한 경로로 설정하세요. Electron 다운로드가 프록시를 요구하는 경우 `ELECTRON_GET_USE_PROXY=1`, `GLOBAL_AGENT_HTTP_PROXY`, `electron_config_cache`를 해당 환경에 맞게 지정합니다. Windows 설치본에는 이러한 설정이 필요 없습니다.

브라우저 UI 미리보기는 `npm run dev`로 열 수 있습니다. **브라우저 모드에는 편집 엔진 연결이 없으며 실제 편집은 Electron 앱에서 합니다.**

## 테스트·빌드

```bash
.venv/bin/python -m pytest -q
npm test
node scripts/electron-smoke.cjs
.venv/bin/python scripts/build-engine.py
.venv/bin/python scripts/frozen-smoke.py
```

Windows에서는 `python scripts/prepare-media.py`, `python scripts/build-engine.py`, `npm run pack:win` 순으로 설치본을 만듭니다. Actions의 **Windows installer** 워크플로는 이 과정, Windows 엔진 테스트, 소스 앱과 설치된 앱의 Electron 테스트를 실행한 뒤 Artifacts에 결과를 저장합니다. 위 성공한 Actions 산출물에 `release/LocalCut-AI-0.2.0-x64-Setup.exe`가 포함되어 있습니다.

## 문서

- [설치·사용 설명서](docs/USER_GUIDE.md)
- [구조·유지보수](docs/ARCHITECTURE.md)
- [배포·업데이트·복구](docs/RELEASE.md)
- [검증 결과와 미완료 항목](docs/STATUS.md)
- [외부 스킬 조사](docs/SKILL_REVIEW.md)
- [오픈소스·모델 라이선스](docs/THIRD_PARTY.md)
- [변경 기록](CHANGELOG.md)
