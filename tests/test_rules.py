import re

import pytest

from aftermath.guidance import SOURCES
from aftermath.phrases import (ACTION, AGAIN, DONE, DOOR_NOTES, LATER, NOT_CAUGHT, PHRASES, PLATE_CHECK,
                                PLATE_NOTES, PLATE_WRONG, TAKE_PHOTO, UNDERSTOOD, action, distance, say)
from aftermath.rules import AGAINST_HOUSE, BURNING, ENCLOSED, Level, Situation, assess, band


def rules_of(situation):
    return [a.rule for a in assess(situation).advice]


def test_bands_lean_toward_too_close():
    assert [band(f) for f in (16.9, 17.0, 23.0, 23.1)] == ["too close", "borderline", "borderline",
                                                           "meets the guidance"]


@pytest.mark.parametrize("place", sorted(ENCLOSED))
def test_inside_is_never_acceptable_whatever_the_distance(place):
    result = assess(Situation(location=place, measured_ft=40, lowest_ft=38))
    assert result.placement == "never indoors"
    assert result.advice[0].rule == "move-outside-now" and result.advice[0].level == Level.DANGER
    assert "meets-guidance" not in rules_of(Situation(location=place, measured_ft=40, lowest_ft=38))


@pytest.mark.parametrize("place", sorted(AGAINST_HOUSE))
def test_against_the_house_is_too_close_whatever_the_distance(place):
    result = assess(Situation(location=place, measured_ft=30, lowest_ft=28))
    assert result.placement == "against the house" and result.advice[0].rule == "away-from-openings"


def test_symptoms_come_first_and_replace_the_standing_line():
    rules = rules_of(Situation(symptoms=True, location="outdoors", measured_ft=30, lowest_ft=28))
    assert rules[0] == "fresh-air-now" and "symptoms-line" not in rules


def test_the_low_end_of_the_measurement_decides():
    assert assess(Situation(location="outdoors", measured_ft=24.0, lowest_ft=22.6)).placement == "borderline"
    assert assess(Situation(location="outdoors", measured_ft=26.0, lowest_ft=24.5)).placement == "meets the guidance"
    assert assess(Situation(location="outdoors", measured_ft=17.5, lowest_ft=16.5)).advice[0].rule == "too-close"


def test_a_door_photo_counts_only_once_the_generator_is_known_to_be_outside():
    for lowest in (18.9, 24.5, 40.0):
        result = assess(Situation(measured_ft=lowest * 1.06, lowest_ft=lowest))
        assert result.placement == "if outside" and result.headline.rule == "if-outside"
        assert result.headline.level == Level.WARNING and "meets-guidance" not in rules_of(Situation(lowest_ft=lowest))
        assert "confirm-outside" in [a.rule for a in result.advice]
        assert "outside" in say(result.headline, "en") and "meets" not in say(result.headline, "en")
    too_close = assess(Situation(measured_ft=12, lowest_ft=11.3))  # too close whether it's outside or not
    assert too_close.placement == "too close" and "confirm-outside" in [a.rule for a in too_close.advice]
    assert assess(Situation(location="outdoors", measured_ft=26, lowest_ft=24.5)).placement == "meets the guidance"


def test_a_photo_that_didnt_record_its_lens_counts_only_once_the_person_says_it_was_1x():
    for lowest in (18.9, 24.5, 40.0):
        for location in ("outdoors", None):
            result = assess(Situation(location=location, measured_ft=lowest * 1.06, lowest_ft=lowest,
                                      lens_assumed=True))
            assert result.placement == "if at 1x" and result.headline.rule == "if-1x"
            assert result.headline.level == Level.WARNING
            rules = [a.rule for a in result.advice]
            assert not {"meets-guidance", "borderline"} & set(rules) and "confirm-1x" in rules
            assert rules.index("confirm-1x") < rules.index("confirm-outside") if location is None else True
            assert "If the camera was at 1×" in say(result.headline, "en") and "meets" not in say(result.headline, "en")
    too_close = assess(Situation(location="outdoors", measured_ft=12, lowest_ft=11.3, lens_assumed=True))
    assert too_close.placement == "too close" and "confirm-1x" not in [a.rule for a in too_close.advice]
    inside = assess(Situation(location="garage", measured_ft=30, lowest_ft=28.3, lens_assumed=True))
    assert inside.placement == "never indoors" and "confirm-1x" not in [a.rule for a in inside.advice]


def test_what_isnt_known_becomes_a_question():
    rules = rules_of(Situation())
    for question in ("measure-distance", "ask-exhaust", "ask-co-alarm", "ask-heat-and-cooking", "ask-downed-lines"):
        assert question in rules
    assert rules[-1] == "symptoms-line"  # standing guidance comes last


def test_answers_replace_questions_with_advice():
    rules = rules_of(Situation(location="outdoors", measured_ft=30, lowest_ft=28, exhaust_toward_house=True,
                               co_alarm=False, burning_indoors=frozenset({"charcoal_grill", "car_in_garage"}),
                               downed_line=True))
    assert rules[:4] == ["no-car-in-garage", "no-charcoal-grill", "stay-away-from-lines", "turn-exhaust"]
    assert "get-co-alarm" in rules and "meets-guidance" in rules
    assert not {"ask-exhaust", "ask-co-alarm", "ask-heat-and-cooking", "ask-downed-lines"} & set(rules)
    assert "ask-heat-and-cooking" not in rules_of(Situation(burning_indoors=frozenset()))  # asked, nothing burning


def test_unknown_facts_are_refused():
    with pytest.raises(ValueError, match="location"):
        Situation(location="roof")
    with pytest.raises(ValueError, match="CO sources"):
        Situation(burning_indoors=frozenset({"candles"}))


EVERYTHING = [
    Situation(),
    Situation(symptoms=True, alarm_sounding=True, location="garage", backfeeding=True, refuelling=True, raining=True,
              extreme_heat=True, extreme_cold=True, medical_needs=True, burning_indoors=BURNING, downed_line=True,
              co_alarm=True),
    Situation(location="porch", exhaust_toward_house=True, co_alarm=False, extreme_cold=True, measured_ft=22,
              lowest_ft=20.7),
    Situation(location="outdoors", measured_ft=12, lowest_ft=11.3, extreme_heat=True),
    Situation(location="outdoors", measured_ft=20, lowest_ft=18.9),
    Situation(location="outdoors", measured_ft=31, lowest_ft=29.2, raining=True, co_shutoff=True),
    Situation(location="outdoors"),
    Situation(measured_ft=26, lowest_ft=24.5),  # a door photo before anyone said where the generator is
    Situation(measured_ft=20, lowest_ft=18.9),
    Situation(location="outdoors", measured_ft=26, lowest_ft=24.5, lens_assumed=True),  # a photo with no lens data
]
ALL_ADVICE = [a for s in EVERYTHING for a in assess(s).advice]


def test_every_rule_is_reached_and_every_rule_cites_known_sources():
    assert {a.rule for a in ALL_ADVICE} == set(PHRASES)
    for advice in ALL_ADVICE:
        assert advice.sources and all(source in SOURCES for source in advice.sources), advice.rule


# "Safe", in each language (Hindi as written, with and without the nukta).
FORBIDDEN = {"en": re.compile(r"\bsafe(ly)?\b", re.I), "es": re.compile(r"\bsegur[oa]s?\b|\ba salvo\b", re.I),
             "hi": re.compile(r"सुरक्षित|सेफ|महफ़ूज़|महफूज")}


@pytest.mark.parametrize("language", ["en", "es", "hi"])
def test_every_rule_has_wording_and_none_of_it_calls_anything_safe(language):
    forbidden = FORBIDDEN[language]
    for advice in ALL_ADVICE:
        text = say(advice, language)
        assert text and "{" not in text and not forbidden.search(text), (advice.rule, text)


@pytest.mark.parametrize("language", ["en", "es", "hi"])
def test_nothing_else_the_coach_says_calls_anything_safe_either(language):
    forbidden = FORBIDDEN[language]
    texts = [*(AGAIN[k][language] for k in AGAIN), *(DOOR_NOTES[k][language] for k in DOOR_NOTES),
             *(UNDERSTOOD[k][language] for k in UNDERSTOOD), *(PLATE_NOTES[k][language] for k in PLATE_NOTES),
             NOT_CAUGHT[language], LATER[language], TAKE_PHOTO[language], DONE[language], PLATE_CHECK[language],
             PLATE_WRONG[language]]
    assert not [text for text in texts if forbidden.search(text)]


def test_distances_carry_metres_and_lower_bounds_round_down():
    assert distance(20, "en") == "20 feet (6.1 m)"
    assert distance(35, "es") == "35 pies (11 m)"
    assert distance(13.6, "en") == "14 feet (4.1 m)" and distance(13.6, "en", down=True) == "13 feet (4.1 m)"
    assert distance(19.99, "es", down=True) == "19 pies (6.0 m)"
    advice = assess(Situation(location="outdoors", measured_ft=14.2, lowest_ft=13.4)).advice[0]
    assert say(advice, "es").startswith("El generador está a unos 14 pies (4.3 m) de la puerta, y a por lo menos 13 "
                                        "pies (4.0 m) contando el error de medición. Está demasiado cerca")


def test_the_headline_is_the_verdict_on_placement_whatever_else_comes_first():
    result = assess(Situation(location="outdoors", measured_ft=30, lowest_ft=28))  # questions sort before it
    assert result.advice[0].rule != "meets-guidance" and result.headline.rule == "meets-guidance"
    assert assess(Situation(location="garage")).headline.rule == "move-outside-now"
    assert assess(Situation()).headline.rule == "measure-distance"


# Every headline the verdict card can show, as assess gives it.
HEADLINES = [Situation(location="garage"), Situation(location="porch"), Situation(measured_ft=10, lowest_ft=9.4),
             Situation(location="outdoors", measured_ft=19, lowest_ft=17.9),
             Situation(location="outdoors", measured_ft=30.2, lowest_ft=28.5),
             Situation(location="outdoors", measured_ft=10, lowest_ft=9.4), Situation(measured_ft=30.2, lowest_ft=28.5),
             Situation(measured_ft=28.9, lowest_ft=27.3, lens_assumed=True), Situation()]


@pytest.mark.parametrize("language", ["hi", "en", "es"])
def test_the_cards_action_line_is_part_of_what_the_coach_says(language):
    """The line under the verdict's headline is a part of the headline's own line (first letter capitalised, and the
    clause given its sentence's end mark), or the question it leaves open: no new wording."""
    seen = set()
    for situation in HEADLINES:
        headline = assess(situation).headline
        line = action(headline, language)
        seen.add(headline.rule)
        if headline.rule not in ACTION:
            assert line == ""
        elif isinstance(ACTION[headline.rule], str):
            assert line == PHRASES[ACTION[headline.rule]][language]
        else:
            assert line and line[1:-1] in say(headline, language) and line[0].lower() in say(headline, language).lower()
    assert set(ACTION) <= seen


def test_the_hindi_action_lines_are_the_approved_ones():
    """As approved on Nov 4 (through the coordinating session): parts of the reviewed lines."""
    lines = {headline.rule: action(headline, "hi") for headline in (assess(s).headline for s in HEADLINES)}
    assert lines["too-close"] == "उसे किसी भी दरवाज़े, खिड़की या रोशनदान से 20 फीट (6.1 m) से ज़्यादा दूर ले जाएँ।"
    assert lines["borderline"] == "हो सके तो उसे और दूर ले जाएँ, 25 फीट (7.6 m) से भी आगे।"
    assert lines["meets-guidance"] == "फिर भी जितना दूर, उतना अच्छा।"
    assert lines["if-outside"] == PHRASES["confirm-outside"]["hi"] and lines["if-1x"] == PHRASES["confirm-1x"]["hi"]


def test_a_measurement_while_the_generator_is_inside_asks_whether_it_was_moved():
    rules = rules_of(Situation(location="garage", measured_ft=22, lowest_ft=20.7))
    assert rules[0] == "move-outside-now" and rules[1] == "ask-moved-outside"
    assert "ask-moved-outside" not in rules_of(Situation(location="outdoors", measured_ft=22, lowest_ft=20.7))
    note = [say(a, "en") for a in assess(Situation(location="garage", measured_ft=22, lowest_ft=20.7)).advice
            if a.rule == "ask-moved-outside"][0]
    assert note.endswith("If it is, take a new photo of the door from where it stands.")
    assert rules_of(Situation(location="shed"))[1] == "ask-moved-outside"  # asked without a measurement too



def test_a_spanish_line_quotes_the_official_spanish_it_cites_word_for_word():
    """Spanish keeps to the agencies' own Spanish: every Spanish source a rule cites is quoted in its Spanish line,
    exactly (a question only cites the rule it asks about)."""
    quoted = set()
    for advice in ALL_ADVICE:
        line = say(advice, "es")
        for source in advice.sources:
            if SOURCES[source].language == "es" and advice.level != Level.CHECK:
                assert SOURCES[source].quote in line, (advice.rule, source)
                quoted.add(advice.rule)
    assert quoted >= {"fresh-air-now", "move-outside-now", "away-from-openings", "too-close", "borderline",
                      "meets-guidance", "no-charcoal-grill", "no-gas-oven", "no-camp-stove", "no-car-in-garage",
                      "no-backfeeding", "turn-exhaust", "get-co-alarm", "go-where-there-is-power",
                      "cool-before-refuel", "dry-and-outdoors", "symptoms-line"}


def test_every_source_says_which_language_it_quotes_and_every_one_is_cited():
    assert {s.language for s in SOURCES.values()} == {"en", "es", "hi"}
    assert all(re.search(r"[\u0900-\u097f]", s.quote) for s in SOURCES.values() if s.language == "hi")
    official = {i for i, s in SOURCES.items() if s.language != "en"}
    assert official <= {i for a in ALL_ADVICE for i in a.sources}


@pytest.mark.parametrize("language", ["en", "hi", "es"])
def test_the_symptoms_line_gives_poison_control_as_well_as_911_from_the_cdc(language):
    line = next(a for a in assess(Situation()).advice if a.rule == "symptoms-line")
    assert "cdc-poison-control" in line.sources and "1-800-222-1222" in SOURCES["cdc-poison-control"].quote
    text = say(line, language)
    assert "911" in text and "1-800-222-1222" in text
    emergency = assess(Situation(symptoms=True)).advice[0]
    assert emergency.rule == "fresh-air-now" and "1-800" not in say(emergency, language)  # in an emergency, 911 only



@pytest.mark.parametrize("language", ["en", "es", "hi"])
def test_nothing_on_the_page_calls_anything_safe(language):
    from aftermath.phrases import PAGE

    texts = [v for v in PAGE[language].values() if isinstance(v, str)] + list(PAGE[language]["placement"].values())
    assert not [text for text in texts if FORBIDDEN[language].search(text)]
