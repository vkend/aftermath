import json

import numpy as np
import pytest
from test_rules import EVERYTHING

from aftermath.conversation import Conversation
from aftermath.phrases import (AGAIN, DONE, DOOR_NOTES, LATER, LENS_RETAKE, MEASURED_NOTE, NOT_CAUGHT, PLATE_CHECK,
                               PLATE_NOTES, PLATE_WRONG, TAKE_PHOTO, UNDERSTOOD, ask, door_note, read_back, say,
                               understood)
from aftermath.plate import Plate
from aftermath.rules import Level, assess
from aftermath.speakable import HI_NUMBERS, VOCAB, chunks, lost, number_words, spoken
from aftermath.speech import VOICES, Voice
from aftermath.web import MOMENT


@pytest.mark.parametrize("n, es, en, hi", [
    (6, "seis", "six", "छह"), (20, "veinte", "twenty", "बीस"), (25, "veinticinco", "twenty five", "पच्चीस"),
    (35, "treinta y cinco", "thirty five", "पैंतीस"), (40, "cuarenta", "forty", "चालीस"), (100, "cien", "one hundred",
                                                                                                "सौ"),
    (120, "ciento veinte", "one hundred twenty", "एक सौ बीस"),
    (3500, "tres mil quinientos", "three thousand five hundred", "तीन हज़ार पाँच सौ"),
    (4375, "cuatro mil trescientos setenta y cinco", "four thousand three hundred seventy five",
     "चार हज़ार तीन सौ पचहत्तर"),
    (21000, "veintiún mil", "twenty one thousand", "इक्कीस हज़ार"),
])
def test_numbers_become_words(n, es, en, hi):
    assert (number_words(n, "es"), number_words(n, "en"), number_words(n, "hi")) == (es, en, hi)


def test_a_spanish_one_agrees_with_its_noun():
    assert spoken("a unos 21 pies, 1 pulgada, 81 pulgadas, 31 metros, 1 hora", "es") == (
        "a unos veintiún pies, una pulgada, ochenta y una pulgadas, treinta y un metros, una hora")


def test_emergency_phone_and_model_numbers_are_read_digit_by_digit():
    assert spoken("llame al 911", "es") == "llame al nueve uno uno"
    assert spoken("911 पर फ़ोन करें", "hi").startswith("नौ एक एक पर")
    assert spoken("1-800-222-1222", "en") == "one, eight zero zero, two two two, one two two two"
    assert spoken("Champion 201183", "en") == "Champion two zero one one eight three"
    assert spoken("WGen3600v", "en") == "WGen three six zero zero v"


def test_the_mumbled_hindi_distance_is_said_in_words_and_metres_in_brackets_are_left_to_the_screen():
    said = " ".join(c for c, _ in chunks("कम से कम 6 मीटर / 20 फीट दूर, खुली जगह पर रखें।", "hi"))
    assert said == "कम से कम छह मीटर या बीस फीट दूर खुली जगह पर रखें"
    assert spoken("más de 20 pies (6.1 m) de puertas", "es") == "más de veinte pies de puertas"
    assert spoken("120/240 volts, 6% and 12°, at 1×", "en") == (
        "one hundred twenty or two hundred forty volts, six percent and twelve degrees, at one ex")
    assert spoken("2.5 मीटर", "hi") == "दो दशमलव पाँच मीटर" and spoken("6.1", "es") == "seis punto uno"


def test_in_hindi_a_word_in_latin_letters_is_left_to_the_screen():
    said = " ".join(c for c, _ in chunks("मैंने पढ़ा: Champion 201183, 3,500 रनिंग वॉट।", "hi"))
    assert said == "मैंने पढ़ा दो शून्य एक एक आठ तीन तीन हज़ार पाँच सौ रनिंग वॉट"
    assert lost("मैंने पढ़ा: Champion 201183।", "hi") == set()


def test_text_is_cut_at_its_punctuation_with_a_longer_pause_after_a_sentence():
    assert chunks("Hola. ¿Tiene una alarma, con batería? Diga «sí, tengo».", "es") == [
        ("hola", 0.25), ("tiene una alarma", 0.15), ("con batería", 0.25), ("diga sí", 0.15), ("tengo", 0.25)]
    assert chunks("नहीं, गैराज में कभी नहीं। बाहर रखें", "hi") == [
        ("नहीं", 0.15), ("गैराज में कभी नहीं", 0.25), ("बाहर रखें", 0.0)]
    assert chunks("...", "en") == [] and chunks("", "es") == []


def coach_lines(language):
    """Everything the coach can say in this language: every rule's advice and question, asked once and again, every
    note, read-back and fixed line."""
    lines = [Conversation(None, language=language).opening(), MOMENT[language], NOT_CAUGHT[language],
             LATER[language], DONE[language], TAKE_PHOTO[language], PLATE_CHECK[language], PLATE_WRONG[language],
             LENS_RETAKE[language],
             MEASURED_NOTE[language], *(AGAIN[k][language] for k in AGAIN), *(PLATE_NOTES[k][language]
                                                                              for k in PLATE_NOTES)]
    for situation in EVERYTHING:
        for advice in assess(situation).advice:
            lines.append(say(advice, language))
            if advice.level == Level.CHECK:
                lines += [ask(advice, language), ask(advice, language, again=True)]
    lines += [door_note(key, language, tilt=12.4, error=0.06, inches=80.0) for key in DOOR_NOTES]
    for name, value in UNDERSTOOD:
        facts = {name: 80.0 if value is None else [value] if name == "burning_indoors" else value}
        lines += [understood(facts, language), understood(facts, language, again=True)]
    good = Plate(True, "Champion", "201183", 3500, 4375, "120/240", 60, 14.6, "gasoline")
    odd = Plate(True, "", "", 35000, 3000, "12", 55, 41, "", problems=list(PLATE_NOTES)[1:])
    lines += [read_back(good, language), read_back(odd, language), read_back(Plate(False, problems=["no-plate"]),
                                                                             language)]
    return lines


@pytest.mark.parametrize("language", ["es", "en", "hi"])
def test_the_voice_can_say_every_line_the_coach_has_without_losing_a_character_or_reading_a_digit(language):
    lines = coach_lines(language)
    assert len(lines) > 150
    assert {line: lost(line, language) for line in lines if lost(line, language)} == {}
    assert all(chunks(line, language) for line in lines)


def test_every_hindi_number_word_is_in_the_hindi_voice():
    assert len(HI_NUMBERS) == 101 and not {c for word in HI_NUMBERS for c in word} - VOCAB["hi"]


@pytest.mark.parametrize("language", ["es", "en", "hi"])
def test_the_characters_listed_are_the_voices_own(language):
    from huggingface_hub import try_to_load_from_cache

    repo, revision = VOICES[language]
    path = try_to_load_from_cache(repo, "vocab.json", revision=revision)
    if not isinstance(path, str):
        pytest.skip(f"{repo} isn't downloaded")
    with open(path) as f:
        assert frozenset(json.load(f)) == VOCAB[language]


class FakeTokenizer:
    def __call__(self, text, return_tensors):
        self.said = [*getattr(self, "said", []), text]
        return {"text": text}


class FakeVits:
    class config:
        sampling_rate = 1000

    def __call__(self, text):
        import torch

        class Out:
            waveform = torch.ones((1, 10 * len(text)))
        return Out()


def test_the_voice_says_each_chunk_with_a_pause_after_it():
    voice, tokenizer = Voice(), FakeTokenizer()
    voice._voices["es"] = (FakeVits(), tokenizer)
    audio = voice.speak("Sí. No, 20.", "es")
    assert tokenizer.said == ["sí", "no", "veinte"]
    assert len(audio) == 10 * len("sí") + 250 + 10 * len("no") + 150 + 10 * len("veinte") + 250
    assert len(voice.speak("", "es")) == 1
