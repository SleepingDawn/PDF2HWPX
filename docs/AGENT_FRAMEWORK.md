# Agent Framework

이 프로젝트의 agentic framework는 아래 경계를 고정한다.

## 1. Deterministic Core

코드만 수행한다.

- PDF intake / run path 생성
- page render / thumbnail 생성
- Clova OCR 호출 / cache / raw,norm 저장
- HWPX / preview PDF 생성
- schema / numbering / formula / table validator 실행

이 계층은 판단을 하지 않는다. 입력을 가공하고 산출물을 쓴다.

## 2. Evidence Layer

코드만 수행한다.

- OCR raw -> normalized schema 변환
- page evidence 생성
- document noise profile 생성
- ODL 같은 외부 parser 결과를 후보 evidence로 병합

이 계층은 후보를 모은다. 최종 결론을 내리지 않는다.

## 3. Decision Agents

애매한 판단만 담당한다.

- `ExamMetaAgent`
- `SectionSplitAgent`
- `QuestionSegmentationAgent`
- `QuestionSplitAgent`
- `BlockTypingAgent`
- `FormulaRepairAgent`
- `AnswerAlignmentAgent`
- `QATriageAgent`

원칙:

- adapter는 decision을 직접 만들지 않는다.
- evidence layer는 question anchor, section split, block type 같은 최종 결정을 직접 만들지 않는다.
- agent는 fallback이 필요하더라도 새 anchor를 fabricate하지 않는다.

## 4. Executors

agent 결정을 실행한다.

- precise block OCR
- table object build
- formula object build
- nanobanana refine interface
- note build

## 5. Render / QA

코드만 수행한다.

- render model 생성
- layout planning
- HWPX writing
- checklist / verification

## Current Flow

현재 controller의 실행 순서는 아래와 같다.

1. intake
2. render_pages
3. analyze_layout
4. describe_template_usage
5. ocr_pages_with_clova
6. build_noise_profile
7. build_page_evidence
8. resolve_exam_meta
9. resolve_section_split
10. resolve_question_anchors
11. package_questions
12. refine_questions
13. build_notes
14. plan_layout
15. run_qa_triage
16. write_outputs

이 순서에서 ODL은 후보 anchor를 evidence로만 공급하고, 최종 anchor 결정은 항상 question agents가 담당해야 한다.
