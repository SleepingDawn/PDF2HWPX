from __future__ import annotations

from PIL import Image

from src.executors import NanoBananaRefiner


def test_nanobanana_refiner_copies_crop_in_passthrough_mode(tmp_path) -> None:
    crop_path = tmp_path / "crop.png"
    Image.new("RGB", (80, 60), color="white").save(crop_path)

    refiner = NanoBananaRefiner({"backend": "nanobanana", "enabled": False})
    image_object = refiner.refine(
        image_id="img1",
        crop_path=crop_path,
        output_dir=tmp_path / "out",
        page_no=1,
        crop_bbox=[0, 0, 80, 60],
        content_type="image",
    )

    assert image_object.refinement_mode == "nanobanana_passthrough"
    assert image_object.source_kind == "image"
    assert image_object.clean_path.endswith("img1.png")
