# Windows 빌드·승인·자동 업데이트

## 최초 연결

대상 저장소는 `want220109/localcut-ai`이며 공개 저장소입니다. 저장소 소유 계정과 현재 연결 계정이 일치하고 쓰기 권한을 확인했습니다. 앱 업데이트 주소도 같은 저장소를 사용합니다. Windows 빌드는 main push·버전 tag·수동 실행으로 시작하며, 빌드 자체는 릴리스를 게시하지 않습니다. 실제 빌드와 배포 상태는 STATUS를 참고하세요.

1. 소스를 사용자가 선택한 GitHub 저장소에 올립니다. 대용량 `.venv`, `node_modules`, 모델과 개인 영상을 커밋하지 않습니다.
2. Actions를 활성화합니다. Settings → Environments에 `production` 환경을 만들고 **required reviewers**를 지정합니다. 환경 이름만 있다고 승인 보호가 자동 설정되는 것은 아닙니다.
3. 필요하면 `WINDOWS_CSC_LINK`, `WINDOWS_CSC_KEY_PASSWORD`를 Actions secrets에 넣고 `WINDOWS_PUBLISHER_NAME`을 변수로 설정합니다. 개인 토큰·관리자 암호는 프로그램에 포함하지 않습니다. 인증서가 없으면 시험용 설치본은 서명 없이 만들어집니다.
4. `Windows installer` 워크플로를 수동 실행합니다. 성공한 뒤 `LocalCut-AI-Windows-x64` artifact를 받습니다. ZIP 안 `release/*Setup.exe`가 Windows 설치본입니다.

Windows workflow는 requirements 설치 → 고정 URL/SHA-256 FFmpeg 준비 → Python/Node 테스트 → 업데이트 저장소 설정 → UI 빌드 → Electron 앱 실제 테스트 → Python 런타임 동결 → 동결 런타임 검증 → NSIS 생성 → `/S` 설치 → **설치된 앱의 bundled 엔진으로 실제 출력 테스트**를 실행합니다. [0.2.0 원격 실행](https://github.com/want220109/localcut-ai/actions/runs/44018941776)에서 모든 단계가 성공했습니다. 설치본과 업데이트 manifest의 SHA-512·크기 및 빌드 출처도 별도로 검증했으며, 이 결과는 온라인 업그레이드 성공을 의미하지 않습니다.

모델 다운로드는 설치본 생성 중 수행하지 않습니다. 사용자가 동의한 첫 실행에서만 받습니다. 모델 다운로드·한국어 음성 정확도와 업데이트 E2E는 빌드 성공만으로 검증되었다고 판단하지 않습니다.

## 새 버전 배포

1. 수정·테스트 후 `package.json`, `engine/__init__.py`, health 버전·테스트 기대값, CHANGELOG를 같은 버전으로 맞춥니다. 베타는 `0.2.0-beta.1` 같은 prerelease를 사용합니다. 향후 단일 버전 생성기로 통합하는 것을 권장합니다.
2. `v0.2.0` 또는 `v0.2.0-beta.1` 태그를 생성합니다. 태그의 Windows 빌드가 성공해야 합니다.
3. 검토자는 테스트 결과와 실제 Windows GUI, ASR, 자막, 업그레이드 데이터 보존을 확인합니다.
4. `Publish approved Windows build`에 성공한 Windows run ID, 같은 tag, 채널, `PUBLISH`를 입력합니다. `production` 보호 환경 승인 후 실행됩니다. 빌드 SHA·워크플로 경로·저장소가 일치하지 않으면 거부합니다.
5. 워크플로는 해당 artifact만 내려받아 GitHub Release에 설치본, blockmap, update yml을 게시합니다. 이미 게시한 버전의 파일은 덮어쓰지 않습니다. **실제 공개 배포를 수행하는 작업이므로 관리자 명시 승인이 필요합니다.**

공개 배포 전 FFmpeg GPL 구성의 해당 빌드·의존 라이브러리에 대응하는 소스를 같은 릴리스 또는 지속 접근 가능한 배포 경로에 제공하고 고지를 확인해야 합니다. 현재는 이 자료를 외부에 배포하지 않았으며 공개 릴리스를 진행할 수 있는 상태로 선언하지 않습니다. 자세한 사항은 THIRD_PARTY를 따릅니다.

## 앱 업데이트 동작

빌드 시 `scripts/configure-release.mjs`가 `GITHUB_REPOSITORY`에서 고정 GitHub feed 설정을 생성하고 main bundle에 포함합니다. 시작 시 버전 확인, 내용은 일반 텍스트로 표시합니다. `autoDownload=false`, `autoInstallOnAppQuit=false`이며 사용자가 다운로드와 설치를 각각 선택합니다. main 프로세스의 작업 잠금이 설치를 다시 검사하므로 renderer 상태만으로 보호하지 않습니다.

GitHub provider는 HTTPS를 사용하며 electron-updater가 update manifest의 SHA-512를 검증합니다. 서명 인증서와 publisherName이 설정된 배포는 Windows 게시자 서명도 검증합니다. 코드 서명 없는 파일에는 게시자 진위 보증이 없으며 SHA만으로 배포 계정 탈취를 방어할 수 없습니다. 서명은 정식 배포 시 운영자가 준비해야 합니다.

안정 사용자는 stable release를, 사용자가 선택한 beta 채널은 prerelease도 확인합니다. 자동 다운그레이드는 껐습니다. 모델·작업은 설치 디렉터리 밖 userData에 저장하고 제거·업그레이드 시 삭제하지 않습니다. 다운로더 실패는 현재 앱을 종료하지 않으며 재확인으로 재시도할 수 있습니다.

## 사설 저장소

기본 구현의 공개 GitHub Release feed는 **비공개 저장소를 바로 지원하지 않습니다.** GitHub PAT를 클라이언트에 넣지 마세요. 소스는 비공개로 유지하면서 바이너리만 별도 공개 배포 저장소에 두거나, 관리자 인증을 갖춘 HTTPS 배포 서비스가 서명된 짧은 수명의 다운로드 URL·manifest를 제공하게 구성합니다. 후자는 서버와 인증 방식이 결정된 후 generic provider로 구현해야 하며 현재 미구현입니다. private repo용 토큰을 일반 사용자에게 배포하는 설계는 사용하지 않습니다.

## 실패·이전 안정 버전 복구

- 다운로드 실패·해시 불일치: 설치 금지, 기존 버전 계속 사용, 업데이트 확인 후 재시도.
- 설치 실패: 작업 폴더를 보존한 채 확인된 설치본으로 재설치. 오류와 Windows 이벤트를 수집합니다.
- 새 버전 결함: 새 릴리스를 철회하고 버전이 증가한 수정판을 우선 배포합니다. 이전 signed installer는 immutable release에 계속 보관합니다.
- 수동 복구: 앱 종료 → `%APPDATA%/LocalCut AI/workspace` 백업 → 이전 안정 installer 실행 → 작업 열기. schema 1을 유지하는 버전 사이만 호환성을 보장하도록 테스트합니다. 자동 롤백 기능은 없습니다.

## Windows 수동 검증

깨끗한 Windows 10/11 x64 CPU PC에서 설치·시작 메뉴·제거, 모델 동의·취소·재시도, MP4/MOV/AVI/MKV와 휴대폰 회전/VFR 영상, 한국어 실제 발화, 원본·편집본 시청, 자막 글꼴과 음성 동기화, 작업 재실행·원본 이동 오류를 확인합니다. CUDA PC에서는 GPU 활성화와 CPU fallback을 확인합니다.

실제 버전 A/B 두 개를 배포하여 시작 시 확인·릴리스 내용·다운로드·작업 중 설치 차단·명시 설치·재시작·설정/작업 보존을 확인합니다. 손상 다운로드, 네트워크 끊김, 디스크 부족, 이전 installer 복구도 확인합니다. 현재 이 Windows/온라인 업데이트 검증은 **미실행**입니다.
