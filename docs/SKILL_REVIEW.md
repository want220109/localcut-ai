# 영상 스킬 조사 기록 (2026-11-16)

## 환경 조사

Cloud skill 목록의 설치 스킬과 executor skill 목록을 조사했습니다. executor 전용 설치 스킬은 없었고 영상 편집 전용 스킬은 활성 목록에 없었습니다. 공식 skill 설치 도구는 노출된 도구에서 찾지 못했습니다. 설치된 `gh`도 `gh skill` 하위 명령을 지원하지 않았습니다. 제3자 `npx skills`를 공식 Codex 설치기로 표현하지 않습니다.

Python 3.12, Node 24, FFmpeg/FFprobe 7.1.5, GitHub CLI, Chromium을 확인했습니다. `cloud-environment-runtime` 스킬은 환경·패키지·네트워크 지침에 사용했습니다. 제품 런타임에는 스킬이 필요하지 않습니다.

## 참고 저장소 검토

GitHub connector로 두 저장소의 존재·메타데이터, README, SKILL.md를 읽었습니다. social-media 쪽의 `transcribe.py`, `edit_video.py` 주요 구현도 읽었습니다. 전체 보안 감사나 실제 실행 검증을 했다는 의미는 아닙니다.

| 저장소 | 확인한 라이선스 | 유지보수 관찰 | 기능·Windows 관련 관찰 | 결정 |
|---|---|---|---|---|
| [social-media-skills/video-editing-skill](https://github.com/social-media-skills/video-editing-skill) | MIT (GitHub metadata) | 2026-11-11 push, 조사 시 archived 아님 | Python/FFmpeg/Pillow, faster-whisper 선택, Windows 안내. 기본 transcriber의 auto 경로는 API 키가 있으면 외부 API를 우선할 수 있음. 에이전트가 편집 JSON과 의미 판단을 작성하며 소셜 게시 기능 포함 | 자동 설치·코드 편입 안 함. 독립 앱·강제 로컬 정책과 결합하기 위해 자체 엔진 구현 |
| [yerinsabraham/video-edit-skill](https://github.com/yerinsabraham/video-edit-skill) | Apache-2.0 (GitHub metadata) | 2026-10-04 push, 조사 시 archived 아님 | whisper.cpp, Python, Node, HyperFrames, 선택적 MediaPipe. Windows/CI 지원을 README에서 주장. 첫 실행 설치와 외부 자산 다운로드가 넓고 에이전트 계획에 의존 | 설치 스크립트 실행 안 함. 제품에 불필요한 종속성을 피하고 자체 엔진 구현 |

두 저장소는 실제로 존재합니다. Windows CI 지원은 각 README의 설명이며 이 세션에서 해당 저장소의 CI를 직접 실행하지 않았습니다. 문서와 일부 코드를 읽은 범위 밖의 보안·품질은 검증하지 않았습니다. 별점 수·최근 수정만으로 안전성을 보증하지 않습니다.

**설치한 외부 영상 편집 스킬: 없음.** 프로젝트 내 자체 엔진을 개발했습니다. 설치한 개발 의존성은 requirements와 package lock에 기록했고 최종 프로그램은 Codex 환경·구독 또는 제3자 스킬 설치에 의존하지 않습니다.
