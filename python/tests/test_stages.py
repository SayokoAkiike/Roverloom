"""The lobby's stage list matches the terrain sites and the race courses."""

import base64

from roverloom.race import COURSES
from roverloom.stages import STAGES, relief, stage_documents


def test_every_course_belongs_to_one_listed_stage():
    docs = stage_documents()
    listed = [c["id"] for d in docs for c in d["courses"]]
    assert sorted(listed) == sorted(COURSES)
    assert {d["id"] for d in docs} == set(STAGES)


def test_real_stages_have_a_place_on_mars_and_texts_in_both_languages():
    for doc in stage_documents():
        for key in ("name", "where", "season", "about"):
            assert doc[key]["en"] and doc[key]["ja"], (doc["id"], key)
        if doc["id"] != "generated":
            assert -180 <= doc["lon"] <= 180 and -90 <= doc["lat"] <= 90
            assert doc["courses"], doc["id"]


def test_relief_grid_decodes_to_the_stated_range():
    r = relief()
    raw = base64.b64decode(r["data"])
    assert len(raw) == r["width"] * r["height"] * 2
    values = [int.from_bytes(raw[i : i + 2], "little") for i in range(0, len(raw), 2)]
    # Values are rounded to one step
    assert abs(r["low_m"] + min(values) * r["step_m"] - r["elevation_min_m"]) <= r["step_m"]
    assert abs(r["low_m"] + max(values) * r["step_m"] - r["elevation_max_m"]) <= r["step_m"]
