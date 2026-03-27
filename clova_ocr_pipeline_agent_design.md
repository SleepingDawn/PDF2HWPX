좋다. 그럼 이제 **Clova OCR를 고정 OCR 엔진**으로 놓고, 전체 파이프라인과 agent 설계를 다시 잠그자.

핵심 방향은 이거다.

> **OCR 자체는 Clova OCR adapter가 책임지고,
> agent는 Clova 결과를 해석·보정·분기하는 역할만 맡는다.**

이렇게 가야 안정적이다.
Clova OCR 쪽에서 공식적으로 **General, Template, Document***도메인 유형을 제공하고, General 도메인은 표 추출 옵션을 켜면 표 영역을 자동 인식해 글자와 함께 구조화된 형태로 반환할 수 있다. 또 Template 도메인은 인식 영역 지정, 용어사전, 테스트/분석, beta/service 배포, 외부 검증 서버 같은 기능을 제공한다. 따라서 이 프로젝트에는 **기본은 General**,*그리고 같은 유형의 시험지가 반복될 때만 **Template를 선택적 보조**로 붙이는 구조가 가장 자연스럽다. ([NCloud Docs][1])

또 하나 중요한 점은, Clova General은 **jpg/png/pdf/tiff**를 지원하지만, 공식 가이드상 **API 호출 시 pdf는 최대 10페이지, Batch는 최대 30페이지**이고, 권장 해상도도 제시돼 있다. 그래서 이 프로젝트는 **PDF를 로컬에서 페이지 이미*로 렌더링한 뒤, 페이지 또는 crop 단위로 Clova OCR에 보내는 방식**이 더 안전하다. 이렇게 하면 페이지 수 제한 영향을 줄이고, 캐시·재시도·부분 재OCR도 쉬워진다. ([NCloud Docs][2])

---

# 1. Clova 반영 후 전체 구조

전체를 5개 층으로 나누는 게 가장 좋다.

## A. Deterministic core

순수 코드 계층이다.

담당:

* PDF 렌더링
* 페이지 이미지 저장
* 손글씨 마스크 생성
* 이미지 inpainting / upscale
* Clova OCR 호출
* HWPX 생성
* 로그/캐시/체크리스트 저장

## B. OCR evidence layer

Clova OCR 결과를 바로 agent에 넘기지 않고, **표준화된 evidence 패키지**로 바꾼다.

담당:

* OCR raw json 정규화
* line / word / bbox / table 후보 통합
* confidence 정리
* 페이지/블록 단위 evidence 생성

## C. Decision agents

애매한 판단만 맡는다.

담당:

* 시험 메타 추출
* 문제/해설 분리
* 대문항 경계 판정
* 블록 타입 재판정
* 수식/반응식 보정
* 해설 매핑
* 이미지 복원 정책
* QA triage

## D. Executors

agent 결정안을 실제 작업으로 실행한다.

담당:

* crop OCR 재실행
* 표 객체 구성
* 수식 변환
* 이미지 복원 실행
* 문항 객체 조립
* HWPX object tree 생성

## E. Validators

각 단계 출력이 유효한지 검사한다.

담당:

* schema validation
* 번호 정합성 검사
* 표 구조 검사
* 수식 문법 검사
* HWPX 생성 전 final consistency check

---

# 2. Clova OCR를 어디에 어떻게 끼울까

이 프로젝트에서 Clova는 “하나의 OCR 엔진”이 아니라 **세 가지 역할**로 쓴다.

## 2-1. Page-level rough OCR

목적:

* 문제/해설 분리
* 시험 메타 추출
* 문항 번호 후보 탐지
* 전체 레이아웃 초안

입력:

* 렌더링된 페이지 PNG

출력:

* line 단위 텍스트
* bbox
* confidence
* 표 후보가 있으면 table result

이 단계는 **빠르고 넓게** 훑는 단계다.

---

## 2-2. Block-level precise OCR

목적:

* 문항 본문 정밀 OCR
* 표 내부 셀 텍스트 OCR
* 해설 본문 OCR
* 문항 번호/소문항 번호 주변 재인식

입력:

* block crop 이미지

출력:

* 더 높은 품질의 OCR 결과
* block type별 후처리용 텍스트

이 단계는 **정교하게** 읽는 단계다.

---

## 2-3. Optional Template OCR

목적:

* 같은 학교/같은 시험지 포맷이 반복될 때
* 문제 번호, 배점, 머리말, 학교정보, 정답 섹션 같은 고정 위치를 더 안정적으로 뽑기

공식 문서 기준 Template 도메인은 인식 영역 지정, 용어사전, 테스트/분석, beta/service 배포를 지원하므로, **시험지 양식이 반복될 때만** 이점을 크게 볼 수 있다. 초반 MVP에서는 필수가 아니고, 2차 고도화에서 붙이는 게 맞다. ([NCloud Docs][3])

---

# 3. 재정비된 전체 pipeline

## Stage 0. Intake

코드가 수행한다.

입력:

* `input.pdf`

출력:

* run id
* work directory
* output basename

작업:

* 파일명 토큰화
* 작업 폴더 생성
* config 로드

---

## Stage 1. PDF render

코드가 수행한다.

입력:

* PDF

출력:

* `pages/page_0001.png` ...
* page metadata

작업:

* 페이지별 고해상도 렌더링
* 썸네일 생성
* per-page hash 생성

---

## Stage 2. Page OCR with Clova

코드 + OCR adapter가 수행한다.

입력:

* page image

출력:

* `ocr/page_0001_raw.json`
* `ocr/page_0001_norm.json`

작업:

* Clova General OCR 호출
* 필요 시 table extraction 옵션 사용
* raw response 저장
* normalized OCR schema로 변환

General 도메인에서 표 추출 옵션을 켤 수 있으므로, rough/page OCR 단계에서도 표 후보를 같이 수집하는 게 좋다. ([NCloud Docs][2])

---

## Stage 3. Global structure reasoning

여기서 agent가 개입한다.

담당:

* 시험 메타 추출
* 문제/해설 분리
* 대문항 시작 후보 정리

출력:

* `exam_meta.json`
* `section_split.json`
* `question_anchors.json`

---

## Stage 4. Question packaging

코드가 수행한다.

입력:

* global decisions
* page OCR results

출력:

* `questions/q001/package.json`
* 각 문항 crop / block asset

작업:

* 문항 단위 package 생성
* 페이지 넘김 연결
* answer section이 있으면 note 후보도 함께 연결

---

## Stage 5. Question-level fine analysis

코드 + 일부 agent.

작업:

* fine block segmentation
* block crop OCR 재실행
* 표 후보 정밀화
* 수식 후보 분리
* 이미지/표/텍스트/unknown 블록 분류

출력:

* per-question refined block list

---

## Stage 6. Specialized reasoning loop

여기서 핵심 agent들이 개입한다.

담당:

* block typing 재판정
* formula / chem repair
* answer alignment
* image restoration policy
* QA triage

출력:

* 문항별 최종 render items
* note items
* uncertainty list

---

## Stage 7. Restoration / object building

코드가 수행한다.

작업:

* 이미지 inpaint / upscale
* 표 객체 생성
* 수식 객체용 내부 표현 생성
* note block 조립

출력:

* render-ready `QuestionRenderModel`
* render-ready `AnswerNoteRenderModel`

---

## Stage 8. Layout planning

코드가 수행한다.

작업:

* 좌/우 2단 배치
* 문항 시작 단 결정
* 표/이미지 fit-to-column
* overflow 처리

출력:

* `layout_plan.json`

---

## Stage 9. HWPX writing

코드가 수행한다.

작업:

* 본문 생성
* 문항 번호 + 미주 표식
* 수식 객체 삽입
* 표 객체 삽입
* 이미지 삽입
* 꼬리표 삽입
* endnote 생성

출력:

* `.hwpx`

---

## Stage 10. QA checklist

코드가 수행한다.

작업:

* `[불확실]` 표식 반영
* `_checklist.txt` 생성

출력:

* `basename.hwpx`
* `basename_checklist.txt`

---

# 4. 코드 스키마

추천 디렉토리 구조는 이렇게 잡자.

```text
exam_hwpx_builder/
├─ config/
│  ├─ default.yaml
│  ├─ clova.yaml
│  └─ thresholds.yaml
├─ src/
│  ├─ main.py
│  ├─ pipeline.py
│  ├─ orchestrator/
│  │  ├─ controller.py
│  │  └─ state.py
│  ├─ adapters/
│  │  ├─ clova_general.py
│  │  ├─ clova_template.py
│  │  └─ hwpx_writer.py
│  ├─ ingest/
│  │  ├─ pdf_renderer.py
│  │  ├─ page_manifest.py
│  │  └─ filename_meta.py
│  ├─ evidence/
│  │  ├─ ocr_normalizer.py
│  │  ├─ page_evidence.py
│  │  └─ question_evidence.py
│  ├─ analysis/
│  │  ├─ section_split.py
│  │  ├─ question_anchor.py
│  │  ├─ block_segmentation.py
│  │  └─ handwriting_mask.py
│  ├─ agents/
│  │  ├─ exam_meta_agent.py
│  │  ├─ section_split_agent.py
│  │  ├─ question_seg_agent.py
│  │  ├─ block_typing_agent.py
│  │  ├─ formula_repair_agent.py
│  │  ├─ answer_align_agent.py
│  │  ├─ restoration_policy_agent.py
│  │  └─ qa_triage_agent.py
│  ├─ executors/
│  │  ├─ block_ocr_executor.py
│  │  ├─ table_builder.py
│  │  ├─ formula_builder.py
│  │  ├─ image_restorer.py
│  │  └─ note_builder.py
│  ├─ layout/
│  │  ├─ measure.py
│  │  ├─ planner.py
│  │  └─ inline_fit.py
│  ├─ models/
│  │  ├─ common.py
│  │  ├─ ocr.py
│  │  ├─ evidence.py
│  │  ├─ decisions.py
│  │  └─ render.py
│  ├─ validators/
│  │  ├─ schema.py
│  │  ├─ numbering.py
│  │  ├─ formula.py
│  │  ├─ table.py
│  │  └─ final_consistency.py
│  └─ qa/
│     ├─ uncertainty.py
│     └─ checklist.py
├─ work/
└─ output/
```

---

# 5. 공통 데이터 모델

아래 6개는 공통으로 쓴다.

## 5-1. NormalizedOCRPage

Clova raw response를 표준화한 페이지 단위 모델이다.

```json
{
  "page_no": 1,
  "image_path": "work/pages/page_0001.png",
  "width": 2480,
  "height": 3508,
  "lines": [
    {
      "line_id": "p1_l1",
      "text": "2024학년도 1학기 기말고사",
      "bbox": [120, 84, 840, 140],
      "confidence": 0.98
    }
  ],
  "words": [
    {
      "word_id": "p1_w1",
      "text": "2024학년도",
      "bbox": [120, 84, 280, 140],
      "confidence": 0.98
    }
  ],
  "tables": [
    {
      "table_id": "p1_t1",
      "bbox": [300, 1200, 1800, 1750],
      "confidence": 0.82
    }
  ],
  "raw_ref": "work/ocr/page_0001_raw.json"
}
```

---

## 5-2. PageEvidence

```json
{
  "page_no": 1,
  "ocr_page_ref": "work/ocr/page_0001_norm.json",
  "thumbnail_path": "work/thumbs/page_0001.jpg",
  "keyword_hits": ["기말고사", "1교시", "정답과 풀이"],
  "question_anchor_candidates": [
    {"text": "1.", "bbox": [130, 420, 180, 470], "score": 0.93}
  ],
  "answer_anchor_candidates": [
    {"text": "정답과 풀이", "bbox": [220, 150, 680, 220], "score": 0.96}
  ],
  "has_table_candidate": true,
  "has_dense_handwriting": false
}
```

---

## 5-3. QuestionPackage

```json
{
  "question_no": 3,
  "question_pages": [2, 3],
  "page_ranges": [
    {"page_no": 2, "bbox": [0, 980, 2480, 3400]},
    {"page_no": 3, "bbox": [0, 0, 1100, 1200]}
  ],
  "rough_text": "...",
  "candidate_blocks": [],
  "answer_pages": [9],
  "note_candidate_ref": null,
  "state": "packaged"
}
```

---

## 5-4. BlockEvidence

```json
{
  "block_id": "q3_b5",
  "question_no": 3,
  "page_no": 2,
  "bbox": [220, 1420, 1180, 1710],
  "crop_path": "work/crops/q3_b5.png",
  "ocr_text": "2H2 + O2 -> 2H2O",
  "ocr_confidence": 0.76,
  "type_candidates": [
    {"type": "chem_equation", "score": 0.68},
    {"type": "text", "score": 0.22}
  ],
  "has_handwriting_overlap": false,
  "table_candidate": false
}
```

---

## 5-5. RenderItem

```json
{
  "item_id": "q3_i2",
  "type": "chem_equation",
  "source_block_id": "q3_b5",
  "content": "2H_2 + O_2 \\rightarrow 2H_2O",
  "target_repr": "hancom_equation",
  "uncertain": false
}
```

---

## 5-6. Issue

```json
{
  "question_no": 3,
  "block_id": "q3_b5",
  "severity": "medium",
  "category": "equation",
  "message": "반응식 아래첨자 추론 포함",
  "asset": "work/crops/q3_b5.png"
}
```

---

# 6. OCR adapter 계층

여기가 Clova 도입 후 가장 중요하게 바뀌는 부분이다.

## 6-1. `ClovaGeneralAdapter`

역할:

* page/block 이미지를 Clova General OCR에 전송
* raw response 저장
* normalized OCR model로 변환
* retry / timeout / cache 관리

입력:

* image path
* language options
* table extraction flag

출력:

* `NormalizedOCRPage` 또는 `NormalizedOCRBlock`

호출 규칙:

* 페이지 rough OCR 때 항상 호출
* block precise OCR 때 필요 블록만 호출

fallback:

1. 동일 이미지 1회 재시도
2. 이미지 리사이즈 후 재시도
3. tile crop로 나눠 재시도
4. 실패 시 issue 기록 + `[불확실]`

---

## 6-2. `ClovaTemplateAdapter`

역할:

* 고정 양식 시험지에서 특정 위치를 안정적으로 추출
* 템플릿 기반 field extraction

호출 규칙:

* 같은 학교/같은 유형 시험지가 반복되고
* template가 준비된 경우에만 사용

fallback:

* template miss 시 General OCR 결과로 복귀

공식 문서상 Template는 지정 영역 추출과 용어사전, 배포 관리가 가능하므로, 반복 양식이 쌓인 뒤에 붙이는 게 맞다. ([NCloud Docs][3])

---

# 7. Agent별 설계

이제 핵심이다.
각 agent마다 **입력 스키마 / 출력 스키마 / 호출 조건 / fallback**을 고정해보자.

---

## Agent 1. ExamMetaAgent

### 역할

첫 장 OCR과 파일명에서 꼬리표용 메타를 확정한다.

### 입력 스키마

```json
{
  "filename_tokens": ["2024", "3", "1", "세종과고", "AP일반화학1", "②기말"],
  "first_page_lines": [
    {"text": "2024학년도 1학기 기말고사", "bbox": [120, 80, 800, 140]},
    {"text": "세종과학고등학교 3학년 AP 일반 화학Ⅰ", "bbox": [120, 150, 980, 210]}
  ],
  "keyword_hits": ["기말고사", "세종과학고등학교", "3학년", "1학기"],
  "prior_meta": null
}
```

### 출력 스키마

```json
{
  "year": "2024",
  "school": "세종과학고등학교",
  "grade": "3학년",
  "semester": "1학기",
  "exam_type": "기말",
  "subject": "AP 일반 화학Ⅰ",
  "tagline": "(2024년 세종과학고등학교 3학년 1학기 기말)",
  "field_sources": {
    "year": "first_page",
    "school": "first_page",
    "grade": "first_page",
    "semester": "first_page",
    "exam_type": "first_page"
  },
  "confidence": 0.93,
  "needs_review": false
}
```

### 호출 조건

* 항상 1회 호출
* 첫 장 OCR 결과가 있으면 바로 호출
* 첫 장 OCR이 비어도 파일명만으로 호출

### fallback

1. first page 우선
2. 부족하면 filename fallback
3. 그래도 없으면 해당 필드 `null`
4. tagline 생성 불가면 생략

---

## Agent 2. SectionSplitAgent

### 역할

문제 파트와 해설 파트를 분리한다.

### 입력 스키마

```json
{
  "pages": [
    {
      "page_no": 7,
      "top_lines": ["17. ...", "- 끝 -"],
      "keyword_hits": ["- 끝 -"],
      "anchor_scores": {"question_style": 0.92, "answer_style": 0.05}
    },
    {
      "page_no": 8,
      "top_lines": ["정답과 풀이", "1)"],
      "keyword_hits": ["정답과 풀이"],
      "anchor_scores": {"question_style": 0.08, "answer_style": 0.96}
    }
  ],
  "question_count_hint": 17
}
```

### 출력 스키마

```json
{
  "has_answer_section": true,
  "question_pages": [1,2,3,4,5,6,7],
  "answer_pages": [8,9,10],
  "split_page": 8,
  "evidence": [
    "page 7 contains '- 끝 -'",
    "page 8 starts with '정답과 풀이'",
    "page 8 numbering resembles answer style"
  ],
  "confidence": 0.97,
  "needs_review": false
}
```

### 호출 조건

* rough OCR 후 항상 1회 호출

### fallback

1. 키워드 기반 split 성공 → 채택
2. 키워드 약하면 numbering pattern 사용
3. 끝까지 불명확하면 `has_answer_section=false`로 두고 issue 기록

---

## Agent 3. QuestionSegmentationAgent

### 역할

`1.`, `2.` 등 대문항 anchor를 확정하고 문항 범위를 정한다.

### 입력 스키마

```json
{
  "page_evidences": [
    {
      "page_no": 1,
      "question_anchor_candidates": [
        {"text": "1.", "bbox": [120, 430, 180, 480], "score": 0.96},
        {"text": "(1)", "bbox": [180, 700, 250, 750], "score": 0.41}
      ]
    }
  ],
  "section_split": {
    "question_pages": [1,2,3,4,5,6,7]
  },
  "expected_question_style": "number_dot"
}
```

### 출력 스키마

```json
{
  "question_anchors": [
    {"question_no": 1, "page_no": 1, "bbox": [120, 430, 180, 480]},
    {"question_no": 2, "page_no": 1, "bbox": [1280, 430, 1340, 480]}
  ],
  "sequence_ok": true,
  "missing_numbers": [],
  "uncertain_anchors": [],
  "confidence": 0.89
}
```

### 호출 조건

* rough OCR anchor detector confidence < threshold 이면 호출
* anchor detector가 충분히 명확하면 skip 가능

### fallback

1. 규칙 기반 anchors 그대로 사용
2. 불연속/중복 있으면 agent 호출
3. 그래도 불명확하면 conservative split + `[불확실]`

---

## Agent 4. BlockTypingAgent

### 역할

block이 text / equation / chem_equation / table / image / unknown 중 무엇인지 재판정한다.

### 입력 스키마

```json
{
  "block_id": "q4_b3",
  "ocr_text": "2H2 + O2 -> 2H2O",
  "bbox": [420, 1180, 1220, 1320],
  "type_candidates": [
    {"type": "text", "score": 0.33},
    {"type": "chem_equation", "score": 0.55}
  ],
  "surrounding_text": "다음 반응식을 완성하시오.",
  "has_table_lines": false,
  "has_image_texture": false
}
```

### 출력 스키마

```json
{
  "block_id": "q4_b3",
  "final_type": "chem_equation",
  "confidence": 0.87,
  "reasons": [
    "surrounding context indicates reaction equation",
    "arrow-like token detected"
  ],
  "needs_review": false
}
```

### 호출 조건

* block type candidate 1위와 2위 score 차이가 작을 때
* text/equation/table/image 구분이 애매할 때
* 표 OCR 결과가 비정상일 때

### fallback

1. high-margin candidate면 agent skip
2. low-margin이면 agent 호출
3. 그래도 불명확하면 `unknown` 유지 + issue 기록

---

## Agent 5. FormulaRepairAgent

### 역할

수학 수식과 선형 화학 반응식을 최종 내부 표현으로 정규화한다.

### 입력 스키마

```json
{
  "block_id": "q4_b3",
  "block_type": "chem_equation",
  "ocr_text": "2H2 + O2 -> 2H2O",
  "surrounding_text": "다음 반응식을 완성하시오.",
  "raw_crop_path": "work/crops/q4_b3.png",
  "symbol_hints": ["arrow", "subscript_candidate"],
  "domain_hint": "chemistry"
}
```

### 출력 스키마

```json
{
  "block_id": "q4_b3",
  "kind": "chem_equation",
  "normalized_repr": "2H_2 + O_2 \\rightarrow 2H_2O",
  "target_repr_type": "hancom_equation_source",
  "target_repr": "2H_{2} + O_{2} rightarrow 2H_{2}O",
  "confidence": 0.83,
  "flags": ["subscript_inferred"],
  "needs_review": false
}
```

### 호출 조건

* equation / chem_equation 블록은 원칙적으로 모두 통과
* 단, 규칙 기반 정규화가 확실하면 lightweight path
* 문법 실패 / chemistry ambiguity면 full agent path

### fallback

1. 규칙 기반 normalizer 먼저
2. 실패 시 agent repair
3. 여전히 불명확하면 원문 OCR 텍스트를 유지하되 `[불확실]`

---

## Agent 6. AnswerAlignmentAgent

### 역할

해설 구간에서 대문항별 미주를 분리하고 question 번호와 매핑한다.

### 입력 스키마

```json
{
  "answer_pages": [8,9,10],
  "answer_blocks": [
    {"text": "1)", "page_no": 8, "bbox": [120, 210, 180, 250]},
    {"text": "(1) 정답 : ...", "page_no": 8, "bbox": [180, 260, 880, 320]}
  ],
  "expected_question_numbers": [1,2,3,4,5,6,7,8]
}
```

### 출력 스키마

```json
{
  "note_map": [
    {"question_no": 1, "start_block_id": "a8_b1", "end_block_id": "a8_b9"},
    {"question_no": 2, "start_block_id": "a8_b10", "end_block_id": "a8_b17"}
  ],
  "missing_notes": [7],
  "extra_notes": [],
  "confidence": 0.91,
  "needs_review": false
}
```

### 호출 조건

* answer section 존재 시 항상 호출

### fallback

1. numbering 매핑이 정상 → 사용
2. 일부 누락 → 해당 question note 없음 처리
3. 전체 불명확 → 미주 생성 생략 + issue 기록

---

## Agent 7. RestorationPolicyAgent

### 역할

이미지 블록에 대해 원본 유지 / inpaint / upscale 조합을 결정한다.

### 입력 스키마

```json
{
  "image_id": "q8_img2",
  "crop_path": "work/crops/q8_img2.png",
  "mask_path": "work/masks/q8_img2_mask.png",
  "handwriting_overlap_ratio": 0.12,
  "edge_density": 0.81,
  "contains_graph_labels": true,
  "contains_structure_diagram": false
}
```

### 출력 스키마

```json
{
  "image_id": "q8_img2",
  "policy": "inpaint_then_upscale",
  "apply_inpaint": true,
  "apply_upscale": true,
  "preserve_original_if_artifact": true,
  "confidence": 0.79,
  "needs_review": false
}
```

### 호출 조건

* 이미지/그래프/구조식 블록 중
* 손글씨 마스크가 있거나
* 해상도 향상이 필요한 경우

### fallback

1. overlap 작고 단순 배경이면 코드 기본 정책
2. overlap 크거나 그래프 축/라벨과 겹치면 agent 호출
3. 위험하면 `preserve_original`

---

## Agent 8. QATriageAgent

### 역할

전체 이슈를 사람이 검토하기 쉬운 형태로 정리하고 `[불확실]` 부착 여부를 확정한다.

### 입력 스키마

```json
{
  "issues": [
    {
      "question_no": 7,
      "category": "table",
      "confidence": 0.54,
      "message": "table grid inconsistent"
    }
  ],
  "document_stats": {
    "question_count": 17,
    "uncertain_question_count": 2
  }
}
```

### 출력 스키마

```json
{
  "document_status": "best_effort_ready",
  "issues": [
    {
      "question_no": 7,
      "severity": "high",
      "category": "table",
      "insert_marker": true,
      "checklist_message": "표 구조 복원이 불완전할 수 있어 원문 대조 필요"
    }
  ]
}
```

### 호출 조건

* final render 직전 항상 1회 호출

### fallback

* agent 실패 시 단순 threshold 기반 severity rule 적용

---

# 8. Agent 호출 조건을 한 번에 정리

이건 실제 orchestrator에서 가장 중요하다.

## 항상 호출

* ExamMetaAgent
* SectionSplitAgent
* AnswerAlignmentAgent(해설이 있을 때)
* QATriageAgent

## 조건부 호출

* QuestionSegmentationAgent
  → question anchor detector가 불안정할 때

* BlockTypingAgent
  → block type이 애매할 때

* FormulaRepairAgent
  → equation/chem block이거나, 규칙 기반 정규화 실패 시

* RestorationPolicyAgent
  → 손글씨와 중요 그래픽이 겹치거나 복원 위험이 있을 때

---

# 9. Fallback 규칙을 시스템 차원에서 다시 정리

## OCR 계층 fallback

Clova 고정 원칙을 유지한다.

1. Clova General page OCR
2. 실패 시 이미지 리사이즈 후 재시도
3. 실패 시 crop/tile 분할 OCR
4. 그래도 실패 시 해당 블록 `[불확실]`

즉, **OCR 엔진 자체를 바꾸지 않는다.**

---

## 구조 해석 fallback

1. 규칙 기반 detector
2. agent 보정
3. validator 통과 시 반영
4. 미통과 시 conservative 결정 + issue

---

## 수식 fallback

1. 규칙 기반 정규화
2. FormulaRepairAgent
3. 문법 검사
4. 실패 시 OCR 원문을 텍스트로 남기지 말고 `[불확실]` 표시 후 checklist 기록

   * 네 요구사항상 수식/반응식은 반드시 수식 객체화가 목표이므로, 실패를 숨기면 안 된다.

---

## 표 fallback

1. Clova table result + geometry build
2. Table ambiguity 시 block typing / repair
3. validator fail 시 편집 가능한 표로 억지 생성하지 말고 `[불확실]`

표는 General에서 구조화 결과를 받을 수 있으니 rough 후보는 Clova가, 실제 HWPX 표 조립은 로컬 builder가 맡는 분리가 좋다. ([NCloud Docs][2])

---

## 이미지 복원 fallback

1. light inpaint
2. artifact check
3. upscale
4. artifact 크면 원본 유지
5. 필요 시 `[불확실]`

---

# 10. Controller state machine

아래처럼 가면 된다.

```python
class PipelineController:
    def run(self, pdf_path: str) -> RunResult:
        state = self.intake(pdf_path)
        state = self.render_pages(state)
        state = self.ocr_pages_with_clova(state)
        state = self.build_page_evidence(state)

        state = self.resolve_exam_meta(state)
        state = self.resolve_section_split(state)
        state = self.resolve_question_anchors(state)

        state = self.package_questions(state)

        for q in state.questions:
            q = self.refine_question_blocks(q)
            q = self.run_block_typing(q)
            q = self.run_formula_repairs(q)
            q = self.run_image_restoration_policy(q)
            q = self.execute_restoration_and_build_items(q)
            state.update_question(q)

        if state.has_answer_section:
            state = self.align_answer_notes(state)
            state = self.build_notes(state)

        state = self.plan_layout(state)
        state = self.run_qa_triage(state)
        state = self.write_hwpx(state)
        state = self.write_checklist(state)
        return state.result
```

---

# 11. 왜 이 구조가 Clova OCR와 잘 맞는가

이 설계의 장점은 세 가지다.

첫째, **Clova를 OCR 서비스로 고정하면서도 전체 파이프라인이 OCR vendor 종속으로 무너지지 않는다.**
adapter가 raw response를 내부 표준 schema로 바꾸기 때문이다.

둘째, **General OCR와 Template OCR를 동시에 수용할 수 있다.**
기본은 General, 반복 양식이 쌓이면 특정 필드에만 Template를 붙일 수 있다. Template는 지정 영역·용어사전·배포 관리가 가능하므로, 학교별 반복 시험지에서 이점이 있다. ([NCloud Docs][3])

셋째, **API 제약을 로컬 렌더링 전략으로 흡수할 수 있다.**
공식 가이드에 pdf 페이지 수 제한이 있으므로, 페이지 이미지를 로컬에서 만들고 보내는 전략이 재시도와 부분 처리에 더 유리하다. ([NCloud Docs][2])

---

# 12. MVP에서 먼저 만들 핵심 agent 5개

처음부터 8개 다 만들지 말고, 우선 이 5개만 만들면 된다.

1. ExamMetaAgent
2. SectionSplitAgent
3. QuestionSegmentationAgent
4. FormulaRepairAgent
5. QATriageAgent

그리고 나머지는 2차로 붙인다.

6. BlockTypingAgent
7. AnswerAlignmentAgent
8. RestorationPolicyAgent

이 순서가 좋다.

---

# 13. 지금 바로 코드로 들어갈 때 우선순위

실제 구현 순서는 이렇게 추천한다.

### 1순위

* ClovaGeneralAdapter
* OCR normalization schema
* PageEvidence builder
* ExamMetaAgent
* SectionSplitAgent
* QuestionPackaging

### 2순위

* QuestionSegmentationAgent
* fine block OCR executor
* FormulaRepairAgent
* render model

### 3순위

* note alignment
* restoration policy
* layout planner
* HWPX writer
* checklist writer

---

여기까지가 **Clova OCR 반영 후 전체 pipeline + code schema + agent contract**의 1차 고정안이다.

다음 단계로는 두 갈래가 가장 자연스럽다.
하나는 **Pydantic 모델과 실제 Python 클래스 시그니처**까지 내리는 것이고,
다른 하나는 **`default.yaml` / `clova.yaml` / `thresholds.yaml` 설계**를 먼저 고정하는 것이다.

**Q1. 다음 답변에서 각 데이터 모델을 `Pydantic` 기준으로 실제 Python 코드 형태로 내려줄까?**
**Q2. 아니면 먼저 `default.yaml`, `clova.yaml`, `thresholds.yaml`의 실제 항목과 기본값을 설계할까?**
**Q3. 또는 바로 `ClovaGeneralAdapter + PageEvidenceBuilder + ExamMetaAgent` 3개를 MVP 코드 뼈대로 먼저 써줄까?**

[1]: https://guide.ncloud-docs.com/docs/clovaocr-domain?utm_source=chatgpt.com "Domain - 사용 가이드"
[2]: https://guide.ncloud-docs.com/docs/clovaocr-general "General"
[3]: https://guide.ncloud-docs.com/docs/en/clovaocr-template?utm_source=chatgpt.com "Template"
