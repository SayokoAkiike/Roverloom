"""The race stages for the lobby's stage select: where each is on Mars, what it shows, its sources.

Places and dates come from the HiRISE products and captions listed in docs/stages.md. The stage
texts describe the game's look; where it follows a published observation, the observation is
named. Nothing here is a measurement.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from roverloom.race import COURSES

REPO = Path(__file__).resolve().parents[3]

# Stage texts, English and Japanese. lon is east-positive, -180..180; lat planetocentric.
STAGES: dict[str, dict[str, Any]] = {
    "generated": {
        "name": {"en": "Practice crater", "ja": "練習用クレーター"},
        "where": {"en": "Generated ground, no download", "ja": "生成した地面（ダウンロード不要）"},
        "season": {"en": "Afternoon", "ja": "午後"},
        "about": {
            "en": (
                "A small generated crater floor with gates, sand, boost pads and a supply pad. "
                "Short laps: the place to learn the rules."
            ),
            "ja": (
                "ゲート、砂地、ブーストパッド、補給パッドがそろった小さな練習場。1周が短いので、ま"
                "ずここでルールを覚えるのがおすすめ。"
            ),
        },
        "beginner": True,
    },
    "gale": {
        "name": {"en": "Gale Crater", "ja": "ゲール・クレーター"},
        "where": {
            "en": "Gale crater floor, near the Curiosity rover's region",
            "ja": "ゲール・クレーターの底（キュリオシティの活動地域の近く）",
        },
        "season": {"en": "Afternoon", "ja": "午後"},
        "about": {
            "en": (
                "Pin flags round an outcrop knoll on the crater floor; Aeolis Mons (Mount Sharp) "
                "rises on the horizon."
            ),
            "ja": (
                "クレーターの底の小丘を回る旗のコース。地平線にはアイオリス山（シャープ山）がそび"
                "える。"
            ),
        },
        "hirise": "ESP_063319_1745",
        "beginner": True,
    },
    "noctis": {
        "name": {"en": "Noctis Labyrinthus", "ja": "ノクティス迷路"},
        "where": {
            "en": "A trough of the 'labyrinth of the night', at the west end of Valles Marineris",
            "ja": "マリネリス峡谷の西端、「夜の迷宮」の谷底",
        },
        "season": {"en": "Afternoon", "ja": "午後"},
        "about": {
            "en": (
                "Layered rock on a trough floor some 3 km below its rims; walls 2 to 4 km high "
                "stand 8 to 15 km away on every side (MOLA)."
            ),
            "ja": (
                "高原から約3 km下の谷底。層状の岩が露出し、8〜15 km先には高さ2〜4 kmの崖が四方を囲"
                "む（MOLAの標高データより）。"
            ),
        },
        "hirise": "ESP_027526_1685",
    },
    "amazonis": {
        "name": {"en": "Amazonis Planitia", "ja": "アマゾニス平原"},
        "where": {
            "en": "One of the smoothest plains on Mars, beside a pit chain",
            "ja": "火星で最も平らな平原のひとつ。ピットの列のそば",
        },
        "season": {"en": "Afternoon", "ja": "午後"},
        "about": {
            "en": (
                "Dust-mantled young lava plains with few rocks, past a channel to the rim of a "
                "deep pit."
            ),
            "ja": "塵に覆われた若い溶岩平原。岩は少なく、水路を越えて深いピットの縁まで走る。",
        },
        "hirise": "ESP_025893_2025",
    },
    "lyot": {
        "name": {"en": "Lyot winter dunes", "ja": "真冬の砂丘（リオ・クレーター）"},
        "where": {
            "en": "Lyot Crater dune field, 49 N, in northern winter",
            "ja": "リオ・クレーターの砂丘帯（北緯49度）、北半球の真冬",
        },
        "season": {"en": "Winter, sun 7 degrees up", "ja": "真冬、太陽高度7度"},
        "about": {
            "en": (
                "Dark crescent dunes on a bright crater floor, frosted with CO2 and water ice, as "
                "HiRISE saw them two days after the winter solstice."
            ),
            "ja": (
                "明るいクレーターの床に黒い三日月形の砂丘。冬至の2日後にHiRISEが撮った姿のように、"
                "二酸化炭素と水の氷の霜に覆われる。"
            ),
        },
        "hirise": "ESP_074942_2295",
    },
    "olympia": {
        "name": {"en": "Ghost forest", "ja": "幽霊の森（北極砂丘帯）"},
        "where": {
            "en": "North polar dunes, Olympia Undae, 80 N, in spring",
            "ja": "北極を囲む砂丘帯（北緯80度）、春",
        },
        "season": {"en": "Spring, low polar sun", "ja": "春、低い極地の太陽"},
        "about": {
            "en": (
                "Frost over the ground; dark dune sand shows through in spots and streaks down "
                "the frosted slopes, like trees on snow. They are sand, not trees: they cast no "
                "shadow."
            ),
            "ja": (
                "霜に覆われた大地。黒い砂丘の砂が斑点状に現れ、霜の斜面を筋になって流れ落ちて、雪"
                "の上の木立のように見える。正体は砂で、影がないので木ではない。"
            ),
        },
        "hirise": "ESP_062937_2605",
    },
}

# Large named regions, for orientation on the map.
# Approximate centres from the IAU names (east longitude).
LANDMARKS = [
    ("Olympus Mons", 18.6, -133.8),
    ("Tharsis Montes", 1.0, -112.0),
    ("Valles Marineris", -14.0, -59.0),
    ("Chryse Planitia", 28.4, -40.0),
    ("Acidalia Planitia", 46.7, -22.0),
    ("Argyre Planitia", -49.7, -43.4),
    ("Arabia Terra", 21.0, 5.0),
    ("Syrtis Major", 8.4, 69.5),
    ("Isidis Planitia", 12.9, 87.0),
    ("Hellas Planitia", -42.4, 70.5),
    ("Utopia Planitia", 46.7, 117.5),
    ("Elysium Mons", 25.0, 147.2),
    ("Terra Sirenum", -39.7, -150.0),
    ("Planum Boreum", 86.0, 0.0),
    ("Planum Australe", -84.0, 160.0),
]


def stage_documents() -> list[dict[str, Any]]:
    """Every stage with its place, courses and texts, for the lobby page."""
    sites = json.loads((REPO / "scripts/terrain/sites.json").read_text(encoding="utf-8"))
    out = []
    for key, text in STAGES.items():
        doc: dict[str, Any] = {"id": key, **text, "courses": []}
        if key != "generated":
            site = sites[key]
            lon, lat = site.get("center_lonlat") or _report_center(site["report"])
            doc |= {"lon": lon, "lat": lat, "product": site["product"], "light": _light(key)}
        for cid, course in COURSES.items():
            if course.ground == key:
                doc["courses"].append(
                    {
                        "id": cid,
                        "name": course.name,
                        "length_m": round(course.lap_length_m() * course.laps),
                        "laps": course.laps,
                        "flags": len(course.checkpoints),
                    }
                )
        out.append(doc)
    return out


def _report_center(report: str) -> list[float]:
    info = json.loads((REPO / report / "site.json").read_text(encoding="utf-8"))
    return list(info["center_lon_lat_deg"])


def _light(stage: str) -> str:
    return {"lyot": "winter", "olympia": "polar"}.get(stage, "afternoon")


def relief() -> dict[str, Any]:
    """The whole-Mars MOLA relief (scripts/terrain/mars_relief.py) for the lobby's map and globe."""
    path = Path(__file__).parent / "preview" / "mars_relief.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data
