import re
from dataclasses import asdict

import pytest

from aftermath.conversation import (CONFIRM, QUESTIONS, REASSURING, Conversation, facts_of, merge, quick_place,
                                    read_answer, says_alarm, says_symptoms, words_of)
from aftermath.phrases import AGAIN, LENS_RETAKE, NOT_CAUGHT, PHRASES, TAKE_PHOTO, understood
from aftermath.rules import Advice, Level, Situation, assess


def reading(language="", question="", answer="", **facts):
    """What Glimmer returns for a turn: only the facts the person stated, plus the three fields always present."""
    return {"language": language, "question": question, "answer": answer, **facts}


class Glimmer:
    """Answers each turn with the next prepared reading, and keeps what it was asked."""

    def __init__(self, *readings):
        self.readings, self.prompts = list(readings), []

    def ask_json(self, prompt, schema, images=()):
        self.prompts.append(prompt)
        return self.readings.pop(0)


def test_stated_facts_are_merged_and_unstated_ones_kept():
    facts = facts_of(reading(generator_location="garage", symptoms="No", co_alarm="maybe", door_height_in=""))
    situation = merge(Situation(co_alarm=True), facts)
    assert (situation.location, situation.symptoms, situation.co_alarm) == ("garage", False, True)
    assert merge(situation, facts_of(reading(burning_indoors=["none"]))).burning_indoors == frozenset()
    grill = merge(situation, facts_of(reading(burning_indoors=["charcoal_grill", "candles"])))
    assert grill.burning_indoors == frozenset({"charcoal_grill"})


def test_a_garage_generator_gets_the_danger_first_and_then_one_question():
    glimmer = Glimmer(reading("es", generator_location="garage"))
    talk = Conversation(glimmer)
    assert talk.opening().startswith("Hola. Soy un asistente")
    reply = talk.reply("Lo tengo en el garaje con la puerta abierta.")
    assert reply.said == ["move-outside-now"]
    assert reply.text.startswith("NUNCA utilice un generador dentro de hogares, garajes")
    assert reply.question == "ask-moved-outside" and reply.text.endswith("¿El generador ya está afuera, al aire "
                                                                        "libre y lejos de la casa?")
    assert "Hola" not in glimmer.prompts[0] and "¿El generador está afuera?" in glimmer.prompts[0]


def test_in_an_emergency_only_the_emergency_is_said():
    talk = Conversation(Glimmer(reading("en", symptoms="yes", co_alarm="no", burning_indoors=["charcoal_grill"]),
                                reading(symptoms="no")))
    first = talk.reply("no alarm, we cook on the grill inside, and my wife doesn't feel right")
    assert first.said == ["fresh-air-now"] and first.text.startswith("Get everyone into fresh air right now")
    later = talk.reply("we're outside now and feel fine")  # read back before the emergency is over
    assert later.said == ["fresh-air-now"]
    assert later.text.endswith("I understood that nobody feels sick. Is that right?")
    clear = talk.reply("Yes.")
    assert {"no-charcoal-grill", "get-co-alarm"} <= set(clear.said)  # what waited is said once it's clear


def test_a_door_photo_counts_only_once_the_generator_is_plainly_outside():
    talk = Conversation(Glimmer(reading("en", generator_location="outdoors")), language="en")
    photo = talk.reply("", door=(24.0, 22.6))  # before anyone said where the generator is
    assert photo.said == ["if-outside"] and photo.question == "confirm-outside"
    assert photo.text.endswith("Is the generator outside, out in the open, where you took the photo?")
    assert talk.situation.location is None and assess(talk.situation).placement == "if outside"
    assert talk.reply("se").question == "confirm-outside"  # unclear: still only if it's outside
    assert talk.reply("It's out in the yard.").question == "confirm"  # Glimmer's reading, read back
    assert assess(talk.situation).placement == "if outside"
    verdict = talk.reply("Yes.")
    assert verdict.said == ["borderline"] and verdict.question == "ask-door-height"
    assert "borderline" not in talk.reply("ok").said  # said once


def test_a_far_door_before_anyone_said_where_the_generator_is_never_reads_meets_the_guidance():
    talk = Conversation(Glimmer())
    photo = talk.reply("", door=(26.0, 24.5))
    assert "Cumple" not in photo.text and "Si el generador está ahí y afuera" in photo.text
    assert assess(talk.situation).placement == "if outside"
    talk.reply("No.")  # not outside: somewhere inside, the stricter reading
    assert assess(talk.situation).placement == "never indoors"


def test_a_standing_line_waits_for_a_turn_with_nothing_more_pressing():
    talk = Conversation(Glimmer(reading(generator_location="garage"), reading(co_alarm="yes")), language="en")
    assert talk.reply("it's in the garage").said == ["move-outside-now"]  # no standing line beside a danger
    assert talk.reply("we have a carbon monoxide alarm").question == "confirm"  # the model's reading, read back
    quiet = talk.reply("Yes.")
    assert len([r for r in quiet.said if r in ("symptoms-line", "test-co-alarm")]) == 1


def test_an_open_question_gets_glimmers_answer_unless_it_says_safe():
    helpful = reading("en", question="how long will the outage last?",
                      answer="I don't know; your utility's outage map would.")
    risky = reading("en", question="how long?", answer="It is safe to wait.")
    talk = Conversation(Glimmer(helpful, risky), language="en")
    assert "your utility's outage map would" in talk.reply("how long will it last?").text
    assert "safe" not in talk.reply("how long?").text.lower()


def test_silence_just_repeats_the_question():
    glimmer = Glimmer()
    reply = Conversation(glimmer, language="en").reply("   ")
    assert glimmer.prompts == [] and reply.question == "measure-distance"


def test_symptom_words_get_the_emergency_line_without_waiting_for_the_model():
    glimmer = Glimmer(reading("en"))
    talk = Conversation(glimmer, language="en")
    reply = talk.reply("my head hurts and I feel dizzy")
    assert reply.said == ["fresh-air-now"] and glimmer.prompts == []
    talk.reply("nobody is dizzy now, we're outside")  # negated: the model reads it
    assert len(glimmer.prompts) == 1


def test_a_short_answer_to_the_coachs_question_needs_no_model():
    glimmer = Glimmer()
    talk = Conversation(glimmer, language="en")
    talk.opening()  # asks whether the generator is outside
    reply = talk.reply("No")  # not outside: somewhere inside, the stricter reading
    assert reply.said[0] == "move-outside-now" and reply.question == "ask-moved-outside" and glimmer.prompts == []
    assert reply.text.endswith("Is the generator outside now, out in the open, away from the house?")
    talk.reply("yes")  # moved out
    assert talk.situation.location == "outdoors" and glimmer.prompts == []  # still without the model


def test_a_dangerous_place_is_said_before_the_model_reads_the_rest():
    talk = Conversation(Glimmer(reading("es", question="¿Cuánto dura la gasolina?", answer="Depende del tanque.")))
    talk.opening()
    first = talk.quick("El generador está en el garaje y quiero saber cuánto dura la gasolina")
    assert first.pending and first.said == ["move-outside-now"] and talk.waiting
    rest = talk.finish()
    assert "move-outside-now" not in rest.said and "Depende del tanque." in rest.text
    assert "symptoms-line" not in rest.said  # the turn already said a danger, so it isn't a quiet one


# A situation in which each of the coach's questions comes next.
OUT = {"location": "outdoors", "measured_ft": 30.0, "lowest_ft": 28.3}
BEFORE = {
    "measure-distance": Situation(),
    "ask-moved-outside": Situation(location="garage"),
    "confirm-outside": Situation(measured_ft=30.0, lowest_ft=28.3),
    "ask-door-height": Situation(**OUT),
    "ask-exhaust": Situation(**OUT),
    "ask-co-alarm": Situation(**OUT, exhaust_toward_house=False),
    "ask-heat-and-cooking": Situation(**OUT, exhaust_toward_house=False, co_alarm=True),
    "ask-downed-lines": Situation(**OUT, exhaust_toward_house=False, co_alarm=True, burning_indoors=frozenset()),
    "confirm-1x": Situation(**OUT, lens_assumed=True),  # a door photo that didn't record its lens
}


def asked(rule, *readings, language="es"):
    """A conversation that has just asked ``rule``; Glimmer, if it's called, answers with ``readings``."""
    talk = Conversation(Glimmer(*readings), language=language, situation=BEFORE[rule],
                        door_checked=rule != "ask-door-height")
    assert talk.reply("").question == rule
    return talk


# Each question whose answer can take a danger off the list: a plain answer that does, Glimmer reading a reply that
# way, and how to tell the danger was taken off.
CLEARING = {
    "measure-distance": ("Sí.", reading(generator_location="outdoors"), lambda t: t.situation.location == "outdoors"),
    "ask-moved-outside": ("Sí.", reading(generator_location="outdoors"), lambda t: t.situation.location == "outdoors"),
    "confirm-outside": ("Sí.", reading(generator_location="outdoors"), lambda t: t.situation.location == "outdoors"),
    "ask-door-height": ("Sí.", reading(door_height_in=80), lambda t: t.door_checked),
    "ask-co-alarm": ("Sí.", reading(co_alarm="yes"), lambda t: t.situation.co_alarm is True),
    "ask-exhaust": ("Lejos de la casa.", reading(exhaust_toward_house="no"),
                    lambda t: t.situation.exhaust_toward_house is False),
    "ask-heat-and-cooking": ("No.", reading(burning_indoors=["none"]),
                             lambda t: t.situation.burning_indoors == frozenset()),
    "ask-downed-lines": ("No.", reading(downed_line="no"), lambda t: t.situation.downed_line is False),
}


@pytest.mark.parametrize("rule", sorted(CLEARING))
def test_a_plain_answer_takes_the_danger_off_the_list(rule):
    plain, read, cleared = CLEARING[rule]
    talk = asked(rule, read)
    talk.reply(plain)
    assert cleared(talk)


UNCLEAR = ["se", "Se.", "¿Qué?", "ok", "no sé", "No lo sé.", "creo que sí", "tal vez", "si lo muevo",
           "se fue la luz hace rato", "sí, pero no sé si funciona", "no estoy seguro, creo que no hay", "Sí, no."]


@pytest.mark.parametrize("heard", UNCLEAR)
@pytest.mark.parametrize("rule", sorted(CLEARING))
def test_an_unclear_answer_never_takes_a_danger_off_the_list_even_if_glimmer_reads_it_so(rule, heard):
    _, read, cleared = CLEARING[rule]
    talk = asked(rule, read, read)
    talk.reply(heard)
    assert not cleared(talk)


def test_a_lone_se_is_asked_again_saying_how_to_answer_and_a_fuller_yes_counts():
    talk = asked("ask-co-alarm")
    again = talk.reply("se")  # how MMS can hear a lone "sí"
    assert again.text == ("Perdón, no le entendí bien. ¿Tiene un detector de monóxido de carbono que funcione? Diga "
                          "«sí, tengo» o «no tengo».")
    talk.reply("se tengo")
    assert talk.situation.co_alarm is True


def test_a_question_asked_again_without_an_answer_is_left_for_later():
    talk = asked("ask-co-alarm")
    assert talk.reply("se").question == "ask-co-alarm"
    later = talk.reply("eh")
    assert later.question == "ask-heat-and-cooking" and talk.situation.co_alarm is None
    assert "ask-co-alarm" in [a.rule for a in assess(talk.situation).advice]  # still open on the page


@pytest.mark.parametrize("rule", ["ask-downed-lines", "ask-heat-and-cooking", "ask-co-alarm"])
def test_i_dont_know_is_not_a_no_and_the_question_waits(rule):
    talk = asked(rule)  # Glimmer has nothing to say: it isn't needed
    reply = talk.reply("No sé.")
    assert reply.text.startswith("Está bien.") and reply.question != rule
    if reply.question is None:  # nothing left to ask
        assert reply.text.endswith("Eso es todo por ahora. Si algo cambia, hábleme, o tome otra foto de la puerta.")
    assert rule in [a.rule for a in assess(talk.situation).advice]


def test_an_unclear_answer_may_still_add_a_danger():
    assert asked("ask-downed-lines").reply("creo que sí").said == ["stay-away-from-lines"]
    assert asked("measure-distance", reading()).reply("No, todavía no.").said[0] == "move-outside-now"
    alarm = asked("ask-co-alarm")
    alarm.reply("creo que no")
    assert alarm.situation.co_alarm is False


def test_a_reply_in_its_own_words_is_read_by_the_model_and_read_back_or_read_by_its_words():
    talk = asked("ask-moved-outside", reading("es", generator_location="outdoors"))
    back = talk.reply("Lo saqué al patio, lejos de la casa.")
    assert back.text == "Entendí que el generador está afuera, al aire libre. ¿Es así?"
    assert talk.situation.location == "garage"
    talk.reply("Sí.")
    assert talk.situation.location == "outdoors"
    plain = asked("ask-moved-outside")  # no model needed for the question's own words
    plain.reply("Ya está afuera.")
    assert plain.situation.location == "outdoors"


def test_once_its_outside_the_first_question_asks_only_for_the_photo():
    talk = Conversation(Glimmer())
    talk.opening()
    reply = talk.reply("Sí.")
    assert reply.question == "measure-distance" and "¿El generador está afuera?" not in reply.text
    assert reply.text.endswith("párese junto al generador y tómele una foto a la puerta.")


def test_a_door_photo_from_the_garage_doesnt_count_once_the_generator_is_moved_out():
    talk = Conversation(Glimmer(), situation=Situation(location="garage"))
    talk.reply("", door=(26.0, 24.5))
    assert talk.reply("Sí, ya está afuera.").question == "measure-distance"
    assert assess(talk.situation).placement == "not measured"


def test_after_a_door_photo_a_yes_answers_the_door_question_not_another():
    talk = Conversation(Glimmer(), situation=Situation(location="outdoors"))
    measured = talk.reply("", door=(26.0, 24.5))
    assert measured.said == ["meets-guidance"] and measured.question == "ask-door-height"
    assert measured.text.endswith("Si es más baja o más alta, dígame cuánto mide.")
    talk.reply("Sí.")
    assert talk.door_checked and talk.situation.co_alarm is None and talk.asked == "ask-exhaust"


def test_a_shorter_door_brings_the_generator_closer_and_the_verdict_is_said_again():
    talk = Conversation(Glimmer(reading("es", door_height_in=72)), situation=Situation(location="outdoors"))
    talk.reply("", door=(26.0, 24.5))
    corrected = talk.reply("Es más bajita, de seis pies.")
    assert talk.situation.measured_ft == pytest.approx(26 * 72 / 80)
    assert talk.situation.lowest_ft == pytest.approx(24.5 * 72 / 80) and corrected.said == ["borderline"]
    assert talk.door_checked and corrected.question == "ask-exhaust"


def test_a_taller_door_needs_a_plain_statement():
    talk = Conversation(Glimmer(reading(door_height_in=96), reading(door_height_in=96)),
                        situation=Situation(location="outdoors"))
    talk.reply("", door=(20.0, 18.9))
    talk.reply("creo que mide ocho pies")
    assert talk.situation.measured_ft == 20.0 and not talk.door_checked
    assert talk.reply("Mide ocho pies.").text == "Entendí que la puerta mide unas 96 pulgadas de alto. ¿Es así?"
    talk.reply("Sí.")
    assert talk.situation.measured_ft == pytest.approx(24.0) and talk.door_checked


@pytest.mark.parametrize("language", ["es", "en", "hi"])
@pytest.mark.parametrize("rule", sorted(QUESTIONS))
def test_the_answers_the_coach_suggests_are_read_as_plain_answers(rule, language):
    question = QUESTIONS[rule]
    suggested = [a or b for a, b in re.findall(r"«([^»]+)»|“([^”]+)”", AGAIN[rule][language])]
    readings = [read_answer(s, question) for s in suggested]
    assert readings and all(r is None or r.plain and r.of(question) is not None for r in readings), readings
    assert readings[0] is not None  # (a later one may be a door height, for the model)


@pytest.mark.parametrize("language", ["es", "en", "hi"])
def test_everything_the_model_could_clear_can_be_read_back(language):
    for name, value in REASSURING.items():
        assert understood({name: [value] if name == "burning_indoors" else value}, language).endswith("?")
    assert "80 pulgadas" in understood({"door_height_in": 80.0}, "es")


@pytest.mark.parametrize("heard", ["creo que sí", "sí, pero no sé", "Sí, lo saqué.", "se"])
def test_a_read_back_counts_only_on_a_plain_yes(heard):
    outdoors = reading("es", generator_location="outdoors")
    talk = asked("ask-moved-outside", outdoors, outdoors)
    assert talk.reply("Lo puse en el patio.").question == "confirm"
    talk.reply(heard)
    assert talk.situation.location == "garage"


def test_mms_splitting_a_word_in_two_still_gives_a_plain_answer():
    talk = asked("ask-exhaust")  # Glimmer has nothing to say: it isn't needed
    talk.reply("lejos de la ca sa")  # how MMS heard "Lejos de la casa."
    assert talk.situation.exhaust_toward_house is False


def test_unsure_about_a_read_back_leaves_its_question_for_later_too():
    talk = asked("ask-exhaust", reading("es", exhaust_toward_house="no"))
    assert talk.reply("Pues apunta para allá, lejitos.").question == "confirm"
    later = talk.reply("No sé.")
    assert later.text.startswith("Está bien. ¿Tiene un detector") and later.question == "ask-co-alarm"
    assert talk.situation.exhaust_toward_house is None


def test_an_unsure_reply_is_not_read_back_either():
    talk = asked("ask-downed-lines", reading("es", downed_line="no"))
    reply = talk.reply("No estoy seguro, creo que no hay.")
    assert not talk.unconfirmed and reply.question != "confirm" and talk.situation.downed_line is None


def test_a_read_back_says_how_to_answer_when_asked_again():
    assert understood({"downed_line": "no", "co_alarm": "yes"}, "es", again=True) == (
        "Entendí que no hay cables de luz caídos cerca y que tiene un detector de monóxido de carbono que funciona. "
        "¿Es así? Diga «sí, es así» o «no».")
    assert read_answer("sí, es así", CONFIRM).plain and read_answer("Así es.", CONFIRM).of(CONFIRM) is True


# What Glimmer read on Oct 29 from MMS's transcripts of short answers spoken by macOS voices.
def test_a_garbled_no_se_is_asked_again_and_glimmer_reading_no_fallen_lines_is_read_back():
    talk = asked("ask-downed-lines", reading("es", downed_line="no"))
    assert talk.reply("esmose").text.startswith("Perdón, no le entendí bien.")  # MMS's "No sé.": not guessed at
    back = talk.reply("es mo se ya")  # a longer garble reaches Glimmer, which read "no fallen lines" into "esmose"
    assert back.text == "Entendí que no hay cables de luz caídos cerca. ¿Es así?" and talk.situation.downed_line is None
    talk.reply("No.")
    assert talk.situation.downed_line is None and not talk.unconfirmed


def test_glimmer_filling_every_field_from_a_garbled_creo_que_si_is_ignored():
    everything = reading("es", generator_location="outdoors", symptoms="no", exhaust_toward_house="no",
                         co_alarm="no", downed_line="no", extreme_heat="no", extreme_cold="no", medical_needs="no",
                         backfeeding="no", refuelling="no", raining="no", co_shutoff="no", door_height_in=0)
    talk = Conversation(Glimmer(everything), situation=Situation(location="garage", symptoms=True))
    talk.asking = Advice("ask-co-alarm", Level.CHECK, ())
    reply = talk.reply("jesecredevos quas si")  # "Creo que sí."
    assert talk.situation == Situation(location="garage", symptoms=True) and not talk.unconfirmed
    assert reply.said == ["fresh-air-now"]


# Glimmer's reading, on Oct 29, of "sceg": MMS's transcript of "Sí, tengo." said to the CO alarm question by a macOS
# voice. It filled every field, with the generator in a shed, after the person had plainly said it was outside.
SCEG = reading("other", generator_location="shed", symptoms="no", exhaust_toward_house="no", co_alarm="no",
               downed_line="no", extreme_heat="no", extreme_cold="no", medical_needs="no", backfeeding="no",
               refuelling="no", raining="no", co_shutoff="no", burning_indoors=[], door_height_in=80)


def test_sceg_for_si_tengo_never_puts_the_generator_in_a_shed():
    talk = asked("ask-co-alarm", SCEG, SCEG)
    again = talk.reply("sceg")  # a word that answers nothing: asked again, without the model
    assert again.text.startswith("Perdón, no le entendí bien. ¿Tiene un detector")
    assert talk.situation == BEFORE["ask-co-alarm"]
    talk.reply("sceg sceg sceg")  # had it reached Glimmer: more facts than words, so all of it is dropped
    assert talk.situation == BEFORE["ask-co-alarm"] and not talk.unconfirmed


# Spark's reading, on Oct 29 with minimal reasoning, of "ठंड की वजह से गैस का ओवन खोलकर रखा है।" ("for the cold, we've
# left the gas oven on"): the oven and the cold, and "no" for nearly everything else.
FILLED = reading("hi", burning_indoors=["gas_oven"], extreme_cold="yes", symptoms="no", exhaust_toward_house="no",
                 co_alarm="no", downed_line="no", extreme_heat="no", medical_needs="no", backfeeding="no",
                 refuelling="no", raining="no", co_shutoff="no")


def test_a_reading_with_most_of_the_facts_at_once_is_dropped_however_long_the_answer():
    long_answer = ("ठंड की वजह से हमने रसोई में गैस का ओवन खोलकर रखा है, बच्चे और दादी उसी कमरे में सो रहे हैं, "
                   "और बाहर अभी भी तेज़ हवा चल रही है।")  # more words than the reading has facts
    talk = asked("ask-heat-and-cooking", FILLED, language="hi")
    reply = talk.reply(long_answer)
    assert talk.situation == BEFORE["ask-heat-and-cooking"] and not talk.unconfirmed
    assert reply.text.startswith(NOT_CAUGHT["hi"]) and reply.question == "ask-heat-and-cooking"  # asked again


def test_a_short_door_height_is_still_read_by_the_model():
    door = Conversation(Glimmer(reading("es", door_height_in=72)), situation=Situation(location="outdoors"))
    door.reply("", door=(26.0, 24.5))
    door.reply("seis pies")  # two words, but a number: worth the model's reading
    assert door.door_in == 72


def test_a_door_height_already_confirmed_isnt_read_back_again():
    talk = Conversation(Glimmer(reading("es", door_height_in=80)), situation=Situation(location="outdoors"),
                        door_checked=True)
    talk.reply("", door=(26.0, 24.5))
    assert talk.reply("La puerta es de seis pies ocho.").question != "confirm"


# After a rating plate photo the coach reads the plate back ("¿Es correcto?"), so the reply is about the plate. Before
# the plate had a question of its own, a "sí" there counted as the answer to the question asked before the photo.
def test_a_yes_to_the_plates_read_back_confirms_the_plate_and_answers_nothing_else():
    talk = asked("ask-co-alarm")  # Glimmer isn't needed
    talk.plate_read_back(readable=True)
    reply = talk.reply("Sí.")
    assert talk.plate_ok is True and talk.situation == BEFORE["ask-co-alarm"]  # not "yes, I have an alarm"
    assert reply.question == "ask-co-alarm"
    assert reply.text.endswith("¿Tiene un detector de monóxido de carbono que funcione con pilas?")  # not "again"


def test_a_no_to_the_plates_read_back_asks_for_another_photo_and_answers_nothing_else():
    talk = asked("ask-co-alarm")
    talk.plate_read_back(readable=True)
    reply = talk.reply("No.")
    assert talk.plate_ok is False and talk.situation == BEFORE["ask-co-alarm"]  # not "no alarm" either
    assert reply.text.startswith("Está bien. Tome otra foto de la placa") and reply.question == "ask-co-alarm"


def test_an_unclear_reply_to_the_plates_read_back_asks_about_the_plate_again():
    talk = asked("ask-co-alarm")
    talk.plate_read_back(readable=True)
    again = talk.reply("se")
    assert again.text == "Perdón, no le entendí bien. ¿Leí bien la placa del generador? Diga «sí, está bien» o «no»."
    talk.reply("sí, está bien")
    assert talk.plate_ok is True and talk.situation == BEFORE["ask-co-alarm"]


@pytest.mark.parametrize("set_aside", ["unreadable plate", "refused door photo"])
def test_after_a_photo_note_a_yes_answers_nothing_asked_before(set_aside):
    talk = asked("ask-co-alarm", reading("es", co_alarm="yes"))
    if set_aside == "unreadable plate":
        talk.plate_read_back(readable=False)  # "No puedo leer la placa en esta foto…"
    else:
        talk.photo_refused()  # "La puerta sale cortada…": a "sí" may only mean "all right"
    reply = talk.reply("Sí.")  # read by the model, and what it reads that would clear a danger is read back first
    assert talk.situation.co_alarm is None and reply.question == "confirm"



# Hindi: the same lean. A plain answer takes a danger off the list; an unclear or unsure one never does, even when
# Glimmer reads it that way.
CLEARING_HI = {"measure-distance": "हाँ, बाहर है।", "ask-moved-outside": "हाँ, बाहर है।", "confirm-outside": "जी हाँ, बाहर है।",
               "ask-door-height": "नॉर्मल है।", "ask-co-alarm": "हाँ, है।", "ask-exhaust": "घर से दूर।",
               "ask-heat-and-cooking": "इनमें से कुछ नहीं।", "ask-downed-lines": "नहीं हैं।"}


@pytest.mark.parametrize("rule", sorted(CLEARING_HI))
def test_a_plain_hindi_answer_takes_the_danger_off_the_list_without_the_model(rule):
    talk = asked(rule, language="hi")  # Glimmer has nothing to answer with: it mustn't be needed
    reply = talk.reply(CLEARING_HI[rule])
    assert CLEARING[rule][2](talk) and not reply.pending


# "जी" alone (also "pardon?"), "पता नहीं" and the rest; MMS's "fhcc" and "खत" for a lone "हाँ"; Voice Transcribe's
# "हर बार है" for "हाँ, बाहर है"; and a "नहीं" that's only a tag ("the wires are down, no?").
UNCLEAR_HI = ["जी", "क्या?", "ठीक है", "है", "हा", "पता नहीं", "मुझे नहीं पता", "मालूम नहीं", "शायद", "लगता है हाँ",
              "हाँ, पर पता नहीं", "fhcc", "खत", "हर बार है", "तार गिरे हैं, नहीं?"]


@pytest.mark.parametrize("heard", UNCLEAR_HI)
@pytest.mark.parametrize("rule", sorted(CLEARING))
def test_an_unclear_hindi_answer_never_takes_a_danger_off_the_list_even_if_glimmer_reads_it_so(rule, heard):
    _, read, cleared = CLEARING[rule]
    talk = asked(rule, read, read, language="hi")
    talk.reply(heard)
    assert not cleared(talk)


@pytest.mark.parametrize("rule", ["ask-downed-lines", "ask-heat-and-cooking", "ask-co-alarm"])
def test_pata_nahin_is_not_a_no_and_the_question_waits(rule):
    talk = asked(rule, language="hi")
    reply = talk.reply("पता नहीं।")
    assert reply.text.startswith("कोई बात नहीं।") and reply.question != rule


def test_a_garbled_lone_haan_is_asked_again_in_hindi_saying_how_to_answer():
    talk = asked("ask-co-alarm", language="hi")
    again = talk.reply("fhcc")  # what MMS made of Lekha's "हाँ"
    assert again.text == ("माफ़ कीजिए, आपकी बात ठीक से समझ नहीं आई। क्या आपके पास काम करने वाला कार्बन मोनोऑक्साइड "
                          "अलार्म है? कहिए «हाँ, है» या «नहीं है»।")
    talk.reply("हाँ, है")
    assert talk.situation.co_alarm is True


def test_hindi_symptoms_get_the_emergency_line_at_once_unless_negated():
    talk = Conversation(Glimmer(), language="hi")  # no model: it would fail if called
    talk.opening()
    reply = talk.reply("मेरी पत्नी को चक्कर आ रहे हैं और सिर में दर्द है")
    assert reply.said == ["fresh-air-now"] and reply.text.startswith("सब लोग अभी तुरंत खुली हवा में जाएँ")
    assert not says_symptoms("किसी को चक्कर नहीं आ रहे") and not says_symptoms("सिरदर्द नहीं है")
    assert says_symptoms("सिरदर्द नहीं, पर चक्कर आ रहे हैं") and not says_symptoms("धुआँ उल्टी तरफ़ जाता है")


def test_a_generator_in_the_garage_said_in_hindi_gets_the_danger_at_once():
    talk = Conversation(Glimmer(), language="hi")
    assert talk.opening().startswith("नमस्ते। मैं तूफ़ान के बाद के लिए एक सहायक हूँ।")
    reply = talk.reply("जनरेटर गैराज में है")
    assert reply.said == ["move-outside-now"] and reply.text.startswith("गैराज में कभी भी जनरेटर का इस्तेमाल न करें")
    assert quick_place("जनरेटर गैराज में नहीं है", None) is None and quick_place("अंदर है", "measure-distance") == "indoors"
    assert quick_place("जेनरेटर बरामदे में चल रहा है", None) == "porch"


def test_devanagari_words_keep_their_vowel_signs_and_spellings_meet():
    assert words_of("नहीं") == ["नहीं"] and words_of("हाँ, बाहर है।") == ["हां", "बाहर", "है"]
    assert words_of("पता नहीं") == ["पता", "नहीं"] and words_of("कमज़ोरी") == words_of("कमजोरी")
    assert words_of("si\u0301") == ["sí"]  # a decomposed "sí" is still "sí"


class Unreachable:
    """A reader that can't be reached, like Muse Spark with the network down."""

    def ask_json(self, prompt, schema, images=()):
        from aftermath.vlm import ReadFailed

        raise ReadFailed("Meta API: ConnectError('no route to host')")


@pytest.mark.parametrize("language,heard", [("hi", "मेरे भाई ने कल रात जनरेटर लगाया था।"),
                                            ("en", "My brother set it up last night.")])
@pytest.mark.parametrize("rule", sorted(CLEARING))
def test_when_the_reader_fails_nothing_is_taken_off_the_list_and_the_coach_says_it_didnt_catch_that(rule, language,
                                                                                                    heard):
    talk = Conversation(Unreachable(), language=language, situation=BEFORE[rule],
                        door_checked=rule != "ask-door-height")
    assert talk.reply("").question == rule
    reply = talk.reply(heard)
    assert not CLEARING[rule][2](talk) and reply.text.startswith(NOT_CAUGHT[language])


# The carbon monoxide alarm sounding: an emergency at once, without the model, whatever was asked.
SOUNDING = ["अलार्म बज रहा है", "अलार्म बज रहा था", "अलार्म बीप कर रहा है", "अलार्म आवाज़ कर रहा है",
            "अलार्म की सीटी बज रही है", "नहीं, अलार्म बज रहा है", "रात को अलार्म बजा", "अलार्म बज रहा है ना?",
            "अलार्म बज रहा है, नहीं?", "The alarm is going off!", "the CO alarm is beeping", "the detector went off",
            "No, the alarm keeps chirping", "our alarm was sounding a minute ago", "la alarma está sonando",
            "el detector suena", "la alarma pita", "No, la alarma está pitando",
            # what MMS heard a macOS Hindi voice say for «अलार्म बज रहा है» and the like (Nov 4)
            "आलार्म बझ रहा है", "कार्बन मुनो ऑपसाइद आलार्म बज रहा है", "मेरा आलार्म बीव कर रहा है", "दिटेकतर बज रहा है"]
QUIET = ["अलार्म नहीं बज रहा", "अलार्म बज नहीं रहा", "अलार्म ठीक है", "रात के दो बज रहे हैं", "आलार्म नहीं बज रहा",
         "मेरी बीवी बाहर है",
         "the alarm isn't going off", "it never went off", "the alarm's not beeping", "the generator is beeping",
         "it sounds fine", "la alarma no suena", "suena bien"]


@pytest.mark.parametrize("heard", SOUNDING)
def test_the_alarm_sounding_gets_the_emergency_line_alone_at_once(heard):
    talk = asked("ask-exhaust", language="hi")  # a question about something else
    reply = talk.reply(heard)
    assert reply.said == ["alarm-sounding"] and not reply.pending and talk.situation.alarm_sounding is True
    assert reply.text == PHRASES["alarm-sounding"]["hi"] and talk.reader.prompts == []
    assert talk.reply("ठीक है").said == ["alarm-sounding"]  # and it stays the only thing said


@pytest.mark.parametrize("heard", QUIET)
def test_an_alarm_that_isnt_sounding_is_no_emergency(heard):
    assert not says_alarm(heard) and not says_alarm(heard, "ask-exhaust")


@pytest.mark.parametrize("rule", ["ask-co-alarm", "checkin-co-alarm"])
@pytest.mark.parametrize("heard", ["हाँ, बज रहा है", "बीप कर रहा है", "yes, it's beeping", "it's going off",
                                   "sí, está sonando", "está pitando"])
def test_a_sound_alone_in_answer_to_the_alarm_question_is_the_alarm_sounding(rule, heard):
    assert says_alarm(heard, rule) and not says_alarm(heard, "ask-exhaust")
    assert not says_alarm("हाँ, काम कर रहा है", rule) and not says_alarm("sí, suena bien", rule)


# What MMS heard a voice say for «मुझे चक्कर आ रहे हैं» and «सिर में दर्द हो रहा है» (Nov 4, macOS and MMS voices).
@pytest.mark.parametrize("heard", ["मुझे चककर आ रहे हैं", "सिर में दद्द हो रहा है", "सर में द्द हो रहा है",
                                   "सिर में दद हो रहा है"])
def test_symptoms_as_mms_spells_them_get_the_emergency_line_at_once(heard):
    talk = asked("ask-exhaust", language="hi")
    assert talk.reply(heard).said == ["fresh-air-now"] and talk.reader.prompts == []


def test_words_that_only_look_like_symptoms_arent_any():
    for heard in ("चक्रवात के बाद बिजली चली गई", "सर्दी बहुत है", "सरदी है", "किसी को चककर नहीं आ रहे"):
        assert not says_symptoms(heard), heard


def test_ji_haan_as_mms_runs_it_together_is_a_plain_yes():
    talk = asked("confirm-outside", language="hi")
    talk.reply("जिहाँ बाहर है")  # «जी हाँ, बाहर है», as MMS heard a macOS voice say it
    assert talk.situation.location == "outdoors" and talk.reader.prompts == []


def test_a_yes_with_the_alarm_as_mms_spells_it_is_plain():
    talk = asked("ask-co-alarm", language="hi")
    talk.reply("हाँ जी आलार्म है")  # «हाँ जी, अलार्म है», as MMS heard it
    assert talk.situation.co_alarm is True and talk.reader.prompts == []


def test_a_no_answering_the_question_before_doesnt_hide_symptoms_and_a_tag_isnt_a_negation():
    assert says_symptoms("No, I have a headache") and says_symptoms("नहीं, मुझे चक्कर आ रहे हैं")
    assert says_symptoms("मुझे चक्कर आ रहे हैं, नहीं?") and says_symptoms("सिर में दर्द है ना")
    assert not says_symptoms("nobody has a headache") and not says_symptoms("किसी को चक्कर नहीं आ रहे")


# A door photo that didn't record its lens (iPhone Safari's own camera leaves it out) is measured as if taken at 1×;
# the distance counts only once the person plainly says it was. (Not in CLEARING: the model reads no lens, and
# scripts/compare_readers.py builds its turns from that table.)
def test_a_photo_without_lens_data_is_given_as_if_at_1x_and_counts_on_a_plain_yes():
    glimmer = Glimmer()
    talk = Conversation(glimmer, language="en", situation=Situation(location="outdoors"), door_checked=True)
    photo = talk.reply("", door=(26.0, 24.5), lens_assumed=True)
    assert photo.said == ["if-1x"] and photo.question == "confirm-1x"
    assert photo.text == ("This photo doesn't say which lens took it. If the camera was at 1×, the door is about 26 "
                          "feet (7.9 m) away, and at least 24 feet (7.4 m) allowing for measuring error. Was the "
                          "camera at 1×, its normal zoom, when you took the photo?")
    assert assess(talk.situation).placement == "if at 1x"
    verdict = talk.reply("Yes, at 1x.")
    assert verdict.said == ["meets-guidance"] and not talk.situation.lens_assumed and talk.lens_confirmed
    assert glimmer.prompts == []  # plain answers: no model


@pytest.mark.parametrize("heard", ["हाँ, 1× पर था।", "हाँ", "जी हाँ, एक एक्स पर था", "हाँ, वन एक्स पर था"])
def test_a_plain_hindi_yes_to_1x_lets_the_distance_count(heard):
    talk = asked("confirm-1x", language="hi")
    assert talk.reply(heard).said == ["meets-guidance"] and not talk.situation.lens_assumed


@pytest.mark.parametrize("heard", ["नहीं, 0.5 पर था", "नहीं", "No, it was on 0.5."])
def test_no_to_1x_drops_the_distance_and_asks_for_a_photo_at_1x(heard):
    language = "en" if heard.startswith("No") else "hi"
    talk = asked("confirm-1x", reading(), language=language)  # "0.5" isn't the question's word: the model reads it
    reply = talk.reply(heard)
    assert talk.situation.lowest_ft is None and not talk.situation.lens_assumed and not talk.lens_confirmed
    assert reply.text == f"{LENS_RETAKE[language]} {TAKE_PHOTO[language]}"
    assert talk.reply("", door=(26.0, 24.5), lens_assumed=True).question == "confirm-1x"  # the new photo's lens


@pytest.mark.parametrize("language, heard", [*(("es", h) for h in UNCLEAR), *(("hi", h) for h in UNCLEAR_HI)])
def test_an_unclear_answer_never_lets_a_photo_without_lens_data_count(language, heard):
    talk = asked("confirm-1x", reading(), reading(), language=language)
    talk.reply(heard)
    s = talk.situation  # still only "if at 1×", or (an unsure "creo que no") the distance dropped for a new photo
    assert s.lens_assumed and assess(s).placement == "if at 1x" or s.lowest_ft is None


def test_a_question_about_the_lens_asked_twice_is_left_and_the_distance_still_doesnt_count():
    talk = asked("confirm-1x", reading(), language="hi")
    assert talk.reply("हम्म").text == f"{NOT_CAUGHT['hi']} {AGAIN['confirm-1x']['hi']}"
    assert talk.reply("हम्म").question != "confirm-1x" and talk.situation.lens_assumed
    assert "meets-guidance" not in [a.rule for a in assess(talk.situation).advice]


# The page also shows the lens question as two buttons. A tap is a plain answer: it does what saying it plainly does.
PLAINLY = {True: {"hi": "हाँ, 1× पर था", "en": "Yes, at 1×", "es": "Sí, en 1×"},
           False: {"hi": "नहीं", "en": "No", "es": "No"}}


@pytest.mark.parametrize("language", ["hi", "en", "es"])
@pytest.mark.parametrize("yes", [True, False])
def test_a_tap_on_a_lens_button_does_what_saying_it_plainly_does(language, yes):
    tapped, spoken = asked("confirm-1x", language=language), asked("confirm-1x", language=language)
    by_tap, by_voice = tapped.tap("confirm-1x", yes), spoken.reply(PLAINLY[yes][language])
    assert (by_tap.text, by_tap.said, by_tap.question) == (by_voice.text, by_voice.said, by_voice.question)
    assert tapped.situation == spoken.situation and tapped.lens_confirmed is spoken.lens_confirmed is yes
    assert tapped.reader.prompts == spoken.reader.prompts == []  # neither needs the model
    assert by_tap.said == (["meets-guidance"] if yes else []) and (tapped.situation.lowest_ft is None) is not yes


def test_a_tap_before_anyone_said_where_the_generator_is_still_leaves_that_to_ask():
    talk = Conversation(Glimmer(), language="hi")
    talk.opening()
    assert talk.reply("", door=(26.0, 24.5), lens_assumed=True).question == "confirm-1x"
    then = talk.tap("confirm-1x", True)
    assert then.said == ["if-outside"] and then.question == "confirm-outside" and talk.situation.location is None


def test_a_tap_answers_only_the_question_being_asked():
    talk = asked("confirm-outside")
    for rule in ("confirm-1x", "confirm-outside"):  # not being asked; and "is it outside?" has no buttons
        with pytest.raises(ValueError):
            talk.tap(rule, True)
    assert talk.asked == "confirm-outside" and talk.situation == BEFORE["confirm-outside"]
    talk = asked("confirm-1x", language="hi")
    talk.tap("confirm-1x", True)
    with pytest.raises(ValueError):  # answered: the next question is another one
        talk.tap("confirm-1x", False)
    assert talk.lens_confirmed and talk.situation.lowest_ft is not None


def test_a_tap_while_the_model_reads_a_turn_answers_nothing():
    talk = asked("confirm-1x", reading(), language="en")
    assert talk.quick("Which button do I press for the photo?").pending
    with pytest.raises(ValueError):
        talk.tap("confirm-1x", True)
    assert talk.situation.lens_assumed and not talk.lens_confirmed


def test_too_close_on_an_assumed_lens_is_too_close_without_asking():
    talk = Conversation(Glimmer(), language="en", situation=Situation(location="outdoors"), door_checked=True)
    reply = talk.reply("", door=(12.0, 11.3), lens_assumed=True)
    assert reply.said == ["too-close"] and reply.question != "confirm-1x"


def test_before_anyone_said_where_the_generator_is_the_lens_is_asked_first_then_the_place():
    talk = Conversation(Glimmer(), language="en")
    talk.opening()
    assert talk.reply("", door=(26.0, 24.5), lens_assumed=True).question == "confirm-1x"
    then = talk.reply("Yes.")
    assert then.said == ["if-outside"] and then.question == "confirm-outside"
    assert talk.reply("Yes, it's outside.").said == ["meets-guidance"]


@pytest.mark.parametrize("heard", ["हाँ, 0.5 पर था", "हाँ, 2x पर था", "Yes, at 0.5."])
def test_a_yes_with_another_zoom_in_it_doesnt_confirm_1x(heard):
    talk = asked("confirm-1x", reading(), language="en" if heard.startswith("Yes") else "hi")
    assert talk.reply(heard).question == "confirm-1x" and talk.situation.lens_assumed  # asked again


# A new door photo isn't a reply. Someone who moves the generator and measures again, without answering anything, is
# still asked whether it's outside, and nothing they haven't said counts as said.
NEAR, MIDDLE, FAR = (8.2, 7.7), (14.4, 13.6), (30.2, 28.5)  # a door photo's (feet, lowest feet)
SAYS_OUTSIDE, MISHEARD = "हाँ, बाहर है", "वार है"  # what MMS made of the first, in the app's own voice on Nov 1


def measuring(*readings, situation=Situation()):
    talk = Conversation(Glimmer(*readings), language="hi", situation=situation)
    talk.opening()
    return talk


def answers(situation):
    """Everything known about the household, without the measurement."""
    return {k: v for k, v in asdict(situation).items() if k not in ("measured_ft", "lowest_ft", "lens_assumed")}


def test_moving_the_generator_and_measuring_again_never_stops_the_coach_asking_if_its_outside():
    talk = measuring()
    for door, placement in [(NEAR, "too close"), (MIDDLE, "too close"), (FAR, "if outside"), (FAR, "if outside")]:
        reply = talk.reply("", door=door)
        assert reply.question == "confirm-outside" and assess(talk.situation).placement == placement
        assert reply.text.endswith(PHRASES["confirm-outside"]["hi"])  # asked plainly: nothing has gone unanswered
    assert talk.reply(SAYS_OUTSIDE).said == ["meets-guidance"]


@pytest.mark.parametrize("steps", [
    [NEAR, FAR],  # as filmed
    [NEAR, FAR, MISHEARD],  # it mishears, and they say it again
    [NEAR, FAR, MISHEARD, FAR],  # it mishears, and they take the far photo again
    [NEAR, FAR, FAR],  # a far retake
    [NEAR, NEAR, FAR],  # a near retake
    [NEAR, FAR, MISHEARD, MISHEARD, FAR],  # asked twice and left for later: a new photo asks afresh
])
def test_a_retake_or_a_mishearing_still_ends_on_the_verdict_without_the_model(steps):
    talk = measuring()  # Glimmer has nothing to answer with: it mustn't be needed
    for step in steps:
        talk.reply(step) if isinstance(step, str) else talk.reply("", door=step)
    assert talk.asked == "confirm-outside" and assess(talk.situation).placement == "if outside"
    assert talk.reply(SAYS_OUTSIDE).said == ["meets-guidance"]
    assert assess(talk.situation).placement == "meets the guidance" and talk.reader.prompts == []


def test_a_question_goes_on_being_left_for_later_when_replies_dont_answer_it():
    talk = measuring()
    talk.reply("", door=FAR)
    talk.reply(MISHEARD)
    assert talk.asked == "confirm-outside"
    talk.reply(MISHEARD)
    assert talk.asked != "confirm-outside" and talk.situation.location is None


@pytest.mark.parametrize("lens_assumed", [False, True])
@pytest.mark.parametrize("before", [
    Situation(), Situation(location="garage"), Situation(location="outdoors"),
    Situation(symptoms=False, co_alarm=True, exhaust_toward_house=False, downed_line=False),
    Situation(co_alarm=False, downed_line=True, burning_indoors=frozenset({"gas_oven"}), extreme_heat=True),
])
def test_a_new_photo_never_sets_or_clears_a_fact(before, lens_assumed):
    talk = measuring(situation=before)
    for door in (NEAR, FAR, FAR):
        talk.reply("", door=door, lens_assumed=lens_assumed)
        assert answers(talk.situation) == answers(before)
        assert not talk.door_checked and not talk.lens_confirmed and not talk.unconfirmed


def test_the_verdict_stays_if_outside_until_a_plain_yes_however_many_photos_come_in():
    talk = measuring(reading("hi", generator_location="outdoors"))  # Glimmer reads the one long reply as outside
    for said in ("", "शायद", MISHEARD, "मैंने उसे बाहर रख दिया, घर से दूर", ""):
        talk.reply(said)
        talk.reply("", door=FAR)
        assert talk.situation.location is None and assess(talk.situation).placement == "if outside"
        assert talk.asked == "confirm-outside"
    assert talk.reply(SAYS_OUTSIDE).said == ["meets-guidance"] and talk.situation.location == "outdoors"


def test_a_photo_during_a_read_back_confirms_nothing():
    read = reading("hi", generator_location="outdoors")
    talk = measuring(read, read)
    talk.reply("", door=FAR)
    assert talk.reply("मैंने उसे बाहर रख दिया, घर से दूर").question == "confirm"
    assert talk.reply("", door=FAR).question == "confirm-outside"
    assert talk.situation.location is None and not talk.unconfirmed
    assert talk.reply("हाँ, सही है").question == "confirm"  # the read-back is over: it's read back again, not counted
    assert talk.situation.location is None


def test_a_generator_said_to_be_in_the_garage_is_still_asked_about_however_many_photos_come_in():
    talk = measuring(situation=Situation(location="garage"))
    for _ in range(3):
        assert talk.reply("", door=FAR).question == "ask-moved-outside"
        assert assess(talk.situation).placement == "never indoors" and talk.situation.location == "garage"
    talk.reply("fhcc")
    talk.reply("fhcc")
    assert talk.asked != "ask-moved-outside"
    assert talk.reply("", door=FAR).question == "ask-moved-outside"  # left for later, then a new photo asks afresh


def test_a_new_photo_asks_about_its_own_lens_after_an_earlier_one_was_left_for_later():
    talk = measuring()
    talk.reply("", door=FAR, lens_assumed=True)
    talk.reply("fhcc")
    talk.reply("fhcc")
    assert talk.asked == "confirm-outside" and assess(talk.situation).placement == "if at 1x"
    assert talk.reply("", door=FAR, lens_assumed=True).question == "confirm-1x"


@pytest.mark.parametrize("heard", UNCLEAR_HI)
@pytest.mark.parametrize("rule", sorted(CLEARING))
def test_after_a_new_photo_an_unclear_hindi_answer_still_takes_nothing_off_the_list(rule, heard):
    _, read, cleared = CLEARING[rule]  # even if Glimmer reads it so
    talk = asked(rule, read, read, language="hi")
    talk.reply("", door=FAR)  # while it's being asked
    assert not cleared(talk)
    talk.reply(heard)
    assert not cleared(talk)


@pytest.mark.parametrize("rule", sorted(CLEARING_HI))
def test_after_a_new_photo_a_plain_hindi_answer_still_takes_the_danger_off_the_list_without_the_model(rule):
    talk = asked(rule, language="hi")
    talk.reply("", door=FAR)
    reply = talk.reply(CLEARING_HI[rule])
    assert CLEARING[rule][2](talk) and not reply.pending
