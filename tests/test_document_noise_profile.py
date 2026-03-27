from src.evidence.document_noise_profile import build_document_noise_profile, is_noise_line
from src.models.ocr import NormalizedOCRPage, OCRLine


def test_document_noise_profile_detects_repeated_footer_lines() -> None:
    pages = {
        1: NormalizedOCRPage(
            page_no=1,
            image_path="p1.png",
            width=2480,
            height=3505,
            lines=[
                OCRLine(line_id="l1", text="1. question", bbox=[100, 300, 300, 350], confidence=0.99),
                OCRLine(line_id="l2", text="이 시험문제의 저작권은 세종과학고등학교에 있으며,", bbox=[385, 3342, 2094, 3399], confidence=0.99),
                OCRLine(line_id="l3", text="세종과학고등학교 총 7쪽 중 1쪽 다음 면에 계속됩니다.", bbox=[222, 3399, 2256, 3458], confidence=0.99),
            ],
        ),
        2: NormalizedOCRPage(
            page_no=2,
            image_path="p2.png",
            width=2480,
            height=3505,
            lines=[
                OCRLine(line_id="l1", text="2. question", bbox=[100, 300, 300, 350], confidence=0.99),
                OCRLine(line_id="l2", text="이 시험문제의 저작권은 세종과학고등학교에 있으며,", bbox=[385, 3342, 2094, 3399], confidence=0.99),
                OCRLine(line_id="l3", text="세종과학고등학교 총 7쪽 중 2쪽 다음 면에 계속됩니다.", bbox=[222, 3399, 2256, 3458], confidence=0.99),
            ],
        ),
    }

    profile = build_document_noise_profile(pages)

    assert profile.footer_top == 3342
    assert profile.footer_patterns
    assert is_noise_line(profile, "세종과학고등학교 총 7쪽 중 3쪽 다음 면에 계속됩니다.", [222, 3399, 2256, 3458], 3505)
    assert not is_noise_line(profile, "2. question", [100, 300, 300, 350], 3505)
