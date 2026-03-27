# Workspace Rules

## 목적

이 문서는 이 저장소의 입력, 출력, 캐시, 실험 산출물을 어디에 두어야 하는지 고정한다.
새 코드, 새 스크립트, 새 실험은 이 규칙을 깨지 않아야 한다.

## 최상위 폴더 규칙

루트에는 아래 성격의 폴더만 둔다.

- `src/`
  - 애플리케이션 코드
- `tests/`
  - 테스트 코드
- `config/`
  - 실행 프로파일
- `docs/`
  - 운영 규칙, 설계 문서, 사용 문서
- `scripts/`
  - 반복 실행용 보조 스크립트
- `samples/`
  - 사람이 직접 넣는 입력/참조 샘플
- `artifacts/`
  - 실행 결과와 중간 산출물
- `var/`
  - 캐시와 임시 운영 데이터

루트에 직접 두지 않는 것:

- 실행마다 생기는 `output_*`, `work_*`
- ad-hoc probe 폴더
- 최종 산출 HWPX/PDF 파일
- 샘플 PDF/HWP/HWPX 원본

## 입력 규칙

입력은 모두 `samples/` 아래에 둔다.

- `samples/inbox/`
  - 실제로 파이프라인에 넣는 입력 PDF
- `samples/reference/`
  - 비교용 원본 HWP, HWPX, PDF
- `samples/scratch/`
  - 일회성 수동 디버깅 입력

파일명 규칙:

- 공백은 허용하되, 가능하면 원본 파일명을 유지한다.
- 문서 식별은 파일명 자체로 한다.
- 코드에서 문서별 run id를 만들 때만 timestamp를 덧붙인다.

## 출력 규칙

최종 사용자 산출물은 모두 `artifacts/exports/` 아래에 둔다.

- `artifacts/exports/default/`
  - 기본 파이프라인 결과
- `artifacts/exports/opendataloader/`
  - ODL 실험 결과
- `artifacts/exports/<profile>/`
  - 새 실험 프로파일 결과

각 실행 프로파일 폴더에 둘 수 있는 파일:

- `<stem>.hwpx`
- `<stem>.pdf`
  - HWPX 렌더 비교용 PDF 또는 preview PDF
- `<stem>_checklist.txt`

한 문서의 최종 산출물은 항상 같은 프로파일 폴더에 모아 둔다.

## 실행 아티팩트 규칙

중간 산출물은 모두 `artifacts/runs/` 아래에 둔다.

구조:

```text
artifacts/runs/<profile>/<document_stem>_<timestamp>/
```

예시:

```text
artifacts/runs/default/2024-3-1-세종과고-AP일반화학1-②기말_20260327_124035/
artifacts/runs/opendataloader/2024-3-1-세종과고-AP일반화학1-②기말_20260327_124035/
```

run 내부 표준 하위 폴더:

- `pages/`
- `thumbs/`
- `ocr/`
- `evidence/`
- `decisions/`
- `questions/`
- `crops/`
- `layout/`
- `opendataloader/`
  - ODL 사용 시에만 생성

규칙:

- run 폴더 이름은 문서 stem + timestamp를 사용한다.
- 서로 다른 실험은 반드시 다른 profile 루트로 분리한다.
- A/B 비교는 같은 문서를 서로 다른 profile에서 실행한다.

## 캐시 규칙

캐시는 모두 `var/` 아래에 둔다.

- `var/cache/clova/`
  - Clova OCR 캐시
- `var/cache/<backend>/`
  - 다른 backend 캐시

규칙:

- 캐시는 최종 산출물이 아니다.
- 캐시는 git에 포함하지 않는다.
- 캐시 스키마가 바뀌면 하위 폴더를 버전별로 분리하거나 비운다.

## 실험 규칙

새 backend, 새 agent, 새 split 로직 실험은 반드시 config profile로 분리한다.

예시:

- `config/default.yaml`
- `config/opendataloader_experiment.yaml`
- `config/<new_profile>.yaml`

profile별 기본 경로 원칙:

- exports: `artifacts/exports/<profile>/`
- runs: `artifacts/runs/<profile>/`

실험 결과를 임시 폴더에 만들지 않는다.

## CLI 규칙

`src/main.py`의 기본 경로는 문서 규칙과 일치해야 한다.

기본값:

- `--output-dir`: `artifacts/exports/default`
- `--work-dir`: `artifacts/runs/default`

실험은 config만 바꾸더라도 profile별 경로를 명시하거나 config의 app 경로와 맞춰야 한다.

## 새 파일을 둘 위치

판단 기준:

- 코드면 `src/`
- 테스트면 `tests/`
- 사용자/운영 문서면 `docs/`
- 반복 스크립트면 `scripts/`
- 입력 샘플이면 `samples/`
- 생성 산출물이면 `artifacts/`
- 캐시면 `var/`

애매하면 루트에 새 폴더를 만들지 말고 `docs/WORKSPACE_RULES.md`를 먼저 갱신한다.

## 레거시 폴더 처리 원칙

현재 이미 존재하는 아래 폴더는 레거시로 본다.

- `output_*`
- `work_*`
- `odl_probe/`

앞으로 새 실행은 이 이름들을 다시 만들지 않는다.
기존 레거시 폴더는 필요 시 정리 대상이지만, 정리 전에는 비교/검증 근거로 남겨둘 수 있다.
