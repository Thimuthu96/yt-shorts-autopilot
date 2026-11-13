import copy
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from autopilot import story as S  # noqa: E402

CAT = S.load_catalog()
V2 = json.loads((ROOT / "stories/sample/lighthouse.json").read_text())
V1 = json.loads((ROOT / "stories/sample/lighthouse-v1.json").read_text())


def mut(fn, base=V2):
    s = copy.deepcopy(base)
    fn(s)
    return S.validate(s, CAT)


def has(problems, text):
    assert any(text in x for x in problems), problems


def test_samples_clean():
    assert S.validate(V2, CAT) == []
    assert S.validate(V1, CAT) == []
    assert S.words(V2) == sum(len(b["text"].split()) for b in V2["beats"])


def test_missing_key():
    has(mut(lambda s: s.pop("sources")), "missing key 'sources'")


def test_slug_title_format_summary():
    has(mut(lambda s: s.update(slug="Bad Slug")), "bad slug")
    has(mut(lambda s: s.update(title="x" * 61)), "title too long")
    has(mut(lambda s: s.update(format="poem")), "unknown format")
    has(mut(lambda s: s.update(summary="One. Two. Three. Four.")), "summary")


def test_levels():
    has(mut(lambda s: s.update(format="levels")), "levels")


def test_word_counts():
    def short(s):
        for b in s["beats"][10:]:
            b["text"] = "Short text."
    has(mut(short), "too short")
    def long(s):
        for b in s["beats"]:
            b["text"] += " one two"
    has(mut(long), "too long")


def test_shot_word_limits():
    has(mut(lambda s: s["beats"][3].update(text="Word")), "beat 3: 1 words")
    has(mut(lambda s: s["beats"][3].update(text="a b c d e f g h i")), "beat 3: 9 words")
    has(mut(lambda s: s["beats"][0].update(text="a b c d e f g h i j k")), "beat 0: 11 words")


def test_shot_count():
    has(mut(lambda s: s.update(beats=s["beats"][:10])), "10 shots")


def test_catalog_values():
    has(mut(lambda s: s["beats"][3]["chars"][0].update(pose="dab")), "beat 3: unknown pose 'dab'")
    has(mut(lambda s: s["beats"][2]["set"].update(mood="neon")), "unknown mood")
    has(mut(lambda s: s["beats"][2]["set"].update(type="moon")), "unknown set")
    has(mut(lambda s: s["beats"][1]["fx"].append({"type": "lava"})), "unknown fx")
    has(mut(lambda s: s["beats"][1].__setitem__("transition", "wipe")), "unknown transition")
    has(mut(lambda s: s["beats"][1].setdefault("sfx", []).append({"type": "moo", "at": 0})), "unknown sfx")
    has(mut(lambda s: s["beats"][1]["cam"].update(move="spiral")), "unknown cam move")


def test_char_not_in_cast_and_first_beat():
    has(mut(lambda s: s["beats"][3]["chars"][0].update(id="ghost")), "not in cast")
    has(mut(lambda s: s["beats"][0].update(chars=[])), "beat 0: no character on screen")


def test_keep_remove():
    has(mut(lambda s: s["beats"][0].update(keep=True)), "beat 0: keep")
    def rm(s):
        s["beats"][1]["keep"] = True
        s["beats"][1]["remove"] = ["nobody"]
    has(mut(rm), "remove 'nobody'")


def test_cast_look():
    has(mut(lambda s: s["cast"]["mate"]["look"].update(hat="fez")), "unknown hat")
    has(mut(lambda s: s["cast"]["mate"]["look"].update(glasses="monocle")), "unknown glasses")
    has(mut(lambda s: s["cast"]["mate"]["look"].update(prop="axe")), "unknown held prop")
    has(mut(lambda s: s["cast"]["mate"]["look"].update(wings=1)), "unknown look key")
    assert mut(lambda s: s["cast"]["mate"]["look"].update(hat="top", glasses="round", prop="book")) == []


def test_fx_scale_period_sign_rot():
    fx = lambda s, d: s["beats"][1]["fx"].append(d)
    has(mut(lambda s: fx(s, {"type": "smoke", "period": 3})), "period only on beam")
    has(mut(lambda s: fx(s, {"type": "beam", "period": 0})), "period must be > 0")
    has(mut(lambda s: fx(s, {"type": "smoke", "scale": "big"})), "scale must be a number")
    assert mut(lambda s: fx(s, {"type": "smoke", "scale": 2})) == []
    has(mut(lambda s: s["beats"][1]["signs"].append({"text": "X", "pos": [0, 1, 0], "rot": [0, 1]})), "sign rot")
    assert mut(lambda s: s["beats"][1]["signs"].append({"text": "X", "pos": [0, 1, 0], "rot": [0, 0.2, 0]})) == []


def test_events():
    ev = lambda s, d: s["beats"][2].setdefault("events", []).append(d)
    has(mut(lambda s: ev(s, {"at_word": 99, "do": "shake"})), "at_word 99 out of range")
    has(mut(lambda s: ev(s, {"at_word": 0, "do": "dance"})), "unknown event 'dance'")
    has(mut(lambda s: ev(s, {"at_word": 0, "do": "expr", "who": "gus"})), "expr needs 'expr'")
    has(mut(lambda s: ev(s, {"at_word": 0, "do": "expr", "who": "zed", "expr": "happy"})), "unknown id 'zed'")
    has(mut(lambda s: ev(s, {"at_word": 0, "do": "act", "who": "gus", "act": "run_to"})), "act run_to needs 'pos'")


def test_cam_rules():
    def ots(s):
        s["beats"][1]["cam"].update(frame="ots", subject="gus", move="push")
    has(mut(ots), "ots frame can't push")
    def pov(s):
        s["beats"][1]["cam"].update(frame="pov", subject="gus", move="pull")
    has(mut(pov), "pov frame can't pull")
    has(mut(lambda s: s["beats"][1]["cam"].update(frame="close", subject=None)), "needs a subject")
    has(mut(lambda s: s["beats"][1]["cam"].update(frame="close", subject="nope")), "unknown cam subject")


def test_static_no_events():
    def f(s):
        s["beats"][4]["events"] = []
        s["beats"][4]["cam"]["move"] = "static"
    has(mut(f), "no events and a static camera")


def test_cut_limit():
    def f(s):
        for b in s["beats"][:4]:
            b["cam"]["cut"] = True
    has(mut(f), "too many cuts")


def test_framing_v1_uses_022():
    def far(s, x):
        s["beats"][0]["chars"][0]["pos"][0] = x
    base = copy.deepcopy(V1)
    c = base["beats"][0]["cam"]
    lim22 = 0.22 * c["dist"]
    x = c["target"][0] + lim22 + 0.3  # outside 0.22, inside 0.325
    has(mut(lambda s: far(s, x), base), "out of frame")


def test_sources_hashtags():
    has(mut(lambda s: s.update(sources=[{"url": "http://a", "title": "a"}])), "need ≥ 2 sources")
    has(mut(lambda s: s.update(hashtags=["#a", "#b"])), "hashtags")
    has(mut(lambda s: s.update(hashtags=["#a", "#b", "#Shorts"])), "hashtags")


def test_narration_rules():
    assert S.gus_narration_problems("It was built in 1823.") == []
    assert S.gus_narration_problems("At 14:30 in October it will hit $150,000, buy now") == []
    assert S.gus_narration_problems("I think it works.")[0].startswith("first person")
    def f(s):
        s["beats"][3]["text"] = "I think so too"
    has(mut(f), "narration: first person")



def test_levels_v2_counts_levels_not_shots():
    def lv(s):
        s["format"] = "levels"
        for k, i in enumerate((0, 6, 12, 18, 24)):
            s["beats"][i]["level"] = k + 1
    assert not [x for x in mut(lv) if "level" in x]


def test_two_shot_needs_look_at():
    def f(s):
        s["beats"][5]["cam"] = {"frame": "two_shot", "subject": "captain", "move": "push"}
    has(mut(f), "needs look_at")


@pytest.mark.parametrize("bad", [
    [], "x", {"beats": "x"},
    lambda s: s["beats"].__setitem__(3, "a shot"),
    lambda s: s["beats"][2].update(props="lighthouse"),
    lambda s: s["beats"][2].update(events=[1, 2]),
    lambda s: s["beats"][2].update(chars=None, cam=["x"]),
    lambda s: s.update(cast=[]),
    lambda s: s.update(sources=["https://a"]),
    lambda s: s["beats"][2].update(events=[{"do": "act", "act": ["x"], "who": {}, "at_word": "1"}]),
    lambda s: s["beats"][2]["set"].update(type=["coast"]),
])
def test_malformed_shapes_never_raise(bad):
    if callable(bad):
        s = copy.deepcopy(V2)
        bad(s)
    else:
        s = bad
    p = S.validate(s, CAT)
    assert p and all(isinstance(x, str) for x in p)
