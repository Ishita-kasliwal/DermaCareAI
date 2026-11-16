"""Caring, plain result wording (Task 6)."""

import re
import uuid

from app.services import tone

JARGON = re.compile(r"probabilit|inconclusive|classif|atopic|melanocytic|lesion|neoplas|confidence score|model",
                    re.I)


def _all_texts():
    for name, v in vars(tone).items():
        if not name.isupper():
            continue
        if isinstance(v, list) and v and isinstance(v[0], str):
            yield from v
        elif isinstance(v, dict):
            for opts in v.values():
                yield from opts
    yield tone.SCORE_NOTE


def test_no_jargon_in_any_wording():
    for text in _all_texts():
        assert not JARGON.search(text), text


def test_same_result_always_reads_the_same():
    seed = str(uuid.uuid4())
    assert tone.wording_for(seed, "clear", "low") == tone.wording_for(seed, "clear", "low")


def test_different_results_get_varied_wording():
    seeds = [str(uuid.uuid4()) for _ in range(40)]
    openers = {tone.wording_for(s, "clear", "low").opener for s in seeds}
    titles = {tone.wording_for(s, "clear", "low").callout_title for s in seeds}
    assert len(openers) >= 3 and len(titles) >= 2


def test_serious_results_always_say_see_a_doctor_soon():
    for i in range(30):
        w = tone.wording_for(str(i), "clear", "high")
        assert "doctor soon" in w.callout_title
        assert "doctor" in w.reassure


def test_unclear_and_unfamiliar_wording():
    w = tone.wording_for("x", "unclear")
    assert w.title in tone.UNCLEAR_TITLE and w.reassure in tone.UNCLEAR_BODY
    assert tone.wording_for("x", "unfamiliar").title in tone.UNFAMILIAR_TITLE
