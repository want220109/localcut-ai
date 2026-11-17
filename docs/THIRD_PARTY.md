# 제3자 구성요소와 비용

LocalCut 자체 소스는 MIT입니다. 각 패키지의 라이선스·NOTICE와 배포 조건은 별도로 적용됩니다. `package-lock.json`, `requirements*.txt`, `constraints.txt`가 의존성을 기록합니다. 0.2.3부터 실제 Windows 빌드 환경의 Python·설치된 배포물 라이선스 전문을 `resources/notices`에 수집하고 `manifest.json`에 버전·출처·SHA-256을 기록합니다. 릴리스마다 실제 빌드에서 갱신하며 이 파일을 정식 SPDX/CycloneDX SBOM으로 표현하지 않습니다.

| 구성요소 | 라이선스·고지 | 사용 |
|---|---|---|
| Electron, React, TypeScript, Vite, electron-builder, electron-updater | MIT (각 bundled dependencies 별도) | 데스크톱, 빌드, 업데이트 |
| Python | PSF | bundled runtime |
| PyInstaller | GPL + 상용 배포를 허용하는 bootloader 예외 | Python 프로그램 동결 |
| faster-whisper, CTranslate2 | MIT | 로컬 음성 인식 |
| Whisper small/tiny 모델 | MIT, OpenAI Whisper 및 Systran 변환 모델 고지 | 동의 후 다운로드 |
| Silero VAD, ONNX Runtime | MIT | faster-whisper 내 ONNX 모델과 런타임 |
| PySceneDetect | BSD-3-Clause | 장면 전환 |
| OpenCV | Apache-2.0, bundled dependencies 별도 | 프레임 처리 |
| PyAV | BSD-3-Clause; bundled FFmpeg 라이브러리 고지 별도 | 음성 모델 런타임 |
| FFmpeg GPL build, libx264 및 포함 라이브러리 | GPLv3 또는 해당 배포 파일에 기재된 조건 | 별도 프로세스 H.264/AAC·자막 |
| 맑은 고딕 | Windows 시스템 글꼴, 앱에서 재배포하지 않음 | Windows 한국어 자막 |
| Noto Sans CJK | SIL OFL, 개발 Linux 시스템에 설치된 글꼴 사용 | Cloud 검증 |
| 나눔고딕 Regular/Bold | SIL OFL 1.1, NAVER Corporation, 원본 파일·라이선스 포함 | 롱폼·쇼츠·릴스 UI와 MP4 자막 |
| Black Han Sans | SIL OFL 1.1, 원본 파일·라이선스 포함 | 제목체·강조 자막 |

자막 글꼴은 Google Fonts 공식 저장소에서 Git blob 해시와 SHA-256을 검증해 가져왔습니다. `assets/fonts/SOURCES.json`에 출처·체크섬을, `LICENSE-NanumGothic.txt`와 `LICENSE-BlackHanSans.txt`에 라이선스 전문을 포함합니다. TTF 내용은 수정하지 않았습니다. 소스와 동결 엔진에 포함되며 별도 글꼴 구매나 사용자 PC에서의 다운로드가 필요 없습니다.

## FFmpeg 배포

Windows 미디어 도구는 `scripts/prepare-media.py`에 고정한 FFmpeg-Builds release에서 받습니다. SHA-256을 검증한 뒤 두 실행 파일과 아카이브의 license 파일만 추출합니다. 원래 URL·체크섬·태그를 provenance.json에 기록합니다. 해당 고정 아카이브가 업스트림에서 사라지면 새 해시를 검토해 업데이트해야 합니다. 임의의 최신 바이너리를 자동 신뢰하지 않습니다.

이 빌드는 GPL 구성을 사용합니다. 바이너리를 재배포할 때 FFmpeg와 해당 빌드에 링크된 라이브러리의 **정확한 대응 소스·패치·빌드 스크립트·라이선스**를 함께 제공해야 합니다. 0.2.3의 미공개 Release 초안에는 아래 자료를 실제로 업로드하고 크기와 SHA-256을 검증했습니다. 관리자는 설치본과 이 자료를 함께 검토·게시합니다. 공개 여부는 STATUS를 참고하세요.

- 전체 FFmpeg 소스 이력 bundle: 선정된 commit `f1acb0a2666c78d92688f4c3d2803a132f5590f6`을 포함합니다.
- 정확한 FFmpeg-Builds 소스·패치·빌드 스크립트: `c9fe5114060e507409f7ee07edfd82efaf25d767` snapshot입니다.
- 해당 2026-11-15 빌드의 dependency source cache: 공식 run `43712307594`의 artifact `14160712668`을 공식 ZIP SHA-256 `8ce88272603786d738be990a92e60dcfa9816bd774a81ac7edf61293e0f1c23c`과 대조했습니다. 3개 part로 나누었으며 전체 복원 해시를 기록합니다.
- CPython 3.12.10, PyAV 19.0.2, OpenCV headless 4.11.0.86, PyInstaller 6.16.0의 원본 source archives와 실제 Windows runtime notices입니다. PyPI source archives는 PyPI SHA-256과 대조했습니다.

`SOURCE-MANIFEST.json`에 자료의 출처·버전·해시와 빌드 연결을 기록하고 `reassemble-sources.py`로 part 검증·결합을 지원합니다. 이 자료에는 개인 영상·사용자 작업·모델 가중치·인증 정보를 넣지 않습니다. 앱의 업데이트 manifest에는 설치본만 기재하므로 소스 자료를 일반 앱 업데이트 때 내려받지 않습니다.

임시 Actions source-transfer artifact는 검증된 Release 복사본이 확인된 뒤에만 지웁니다. 릴리스의 영구 자료는 유지하고, 이후 같은 FFmpeg 빌드는 릴리스 자료를 해시 검증해 재사용할 수 있습니다. 업스트림 Actions artifact의 만료에만 의존하지 않습니다.

참고: https://ffmpeg.org/legal.html · https://github.com/FFmpeg-Builds/FFmpeg-Builds · FFmpeg commit `f1acb0a266` (선정된 8.1 빌드 파일명 기준). 설치본과 같은 서버에 대응 소스 아카이브를 보관하고 릴리스 고지에서 연결하는 방식을 권장합니다. 개인 영상·모델·비밀키를 소스 아카이브에 포함하지 마세요.

## 비용

기본 편집·음성 인식에 유료 API 비용이나 Codex 구독은 필요 없습니다. 모델 최초 다운로드의 네트워크 비용, PC 저장 공간·전력은 사용자가 부담합니다. GitHub Actions/Artifacts/사설 저장소의 무료 한도 초과, 사내 배포 서버, 선택적 코드 서명 인증서에는 비용이 발생할 수 있습니다. 결제나 인증서 구매는 진행하지 않았습니다.
