# PDF2HWPX

시험지 PDF를 분석해서 HWPX와 검토용 PDF를 생성하는 프로젝트다.

작업 전 경로 규칙은 반드시 [docs/WORKSPACE_RULES.md](/Users/seyong/Desktop/요섭쌤%20화학%20조교/PDF2HWPX/docs/WORKSPACE_RULES.md)를 따른다.

기본 실행 예시:

```bash
python -m src.main \
  --input samples/inbox/2024-3-1-세종과고-AP일반화학1-②기말.pdf \
  --config config/default.yaml
```

기본 산출 위치:
- 최종 산출물: `artifacts/exports/default/`
- 실행 아티팩트: `artifacts/runs/default/`
- OCR 캐시: `var/cache/clova/`

ODL 실험 예시:

```bash
python -m src.main \
  --input samples/inbox/2024-3-1-세종과고-AP일반화학1-②기말.pdf \
  --config config/opendataloader_experiment.yaml
```
