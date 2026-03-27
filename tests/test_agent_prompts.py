from __future__ import annotations

from src.agents import (
    AnswerAlignmentAgent,
    BlockTypingAgent,
    ExamMetaAgent,
    FormulaRepairAgent,
    QATriageAgent,
    QuestionSegmentationAgent,
    QuestionSplitAgent,
    SectionSplitAgent,
    load_agent_prompts,
)


def test_agent_prompts_are_centrally_registered() -> None:
    prompts = load_agent_prompts()
    expected = {
        "exam_meta_agent",
        "section_split_agent",
        "question_segmentation_agent",
        "question_split_agent",
        "block_typing_agent",
        "answer_alignment_agent",
        "formula_repair_agent",
        "qa_triage_agent",
    }
    assert expected.issubset(prompts)
    assert all(prompts[name] for name in expected)


def test_agents_load_prompt_from_registry() -> None:
    assert "Extract exam metadata" in ExamMetaAgent().prompt
    assert "Split question pages" in SectionSplitAgent(keywords=[]).prompt
    assert "Confirm top-level question anchors" in QuestionSegmentationAgent().prompt
    assert "Resolve final question order" in QuestionSplitAgent().prompt
    assert "Reclassify ambiguous blocks" in BlockTypingAgent().prompt
    assert "Align answer-note blocks" in AnswerAlignmentAgent().prompt
    assert "Normalize OCR equations" in FormulaRepairAgent().prompt
    assert "Convert low-level issues" in QATriageAgent().prompt
