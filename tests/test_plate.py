import re
from dataclasses import replace

import pytest

from aftermath.phrases import PLATE_NOTES, read_back
from aftermath.plate import Plate, ac_volts, number, read_plate


class FakeGlimmer:
    def __init__(self, answer):
        self.answer, self.asked = answer, []

    def ask_json(self, prompt, schema, images=()):
        self.asked.append((prompt, list(images)))
        return self.answer


PLATE = {"plate_visible": True, "brand": "Champion", "model": "201183", "running_watts": "3,500 W",
         "starting_watts": "4375", "volts": "120/240", "hertz": "60 Hz", "amps": "14.6", "fuel": "Gasoline",
         "co_shutoff": "yes"}


def test_a_plate_is_read_into_checked_fields():
    plate = read_plate(FakeGlimmer(PLATE), "plate.jpg")
    assert (plate.brand, plate.running_watts, plate.starting_watts, plate.hertz, plate.amps) == (
        "Champion", 3500, 4375, 60, 14.6)
    assert plate.fuel == "gasoline" and plate.co_shutoff and plate.problems == [] and plate.usable_watts == 3500


@pytest.mark.parametrize("change, problem", [
    ({"starting_watts": "3000"}, "swapped-watts"),
    ({"running_watts": "35000"}, "watts-out-of-range"),
    ({"running_watts": ""}, "no-running-watts"),
    ({"hertz": "55"}, "odd-hertz"),
    ({"volts": "12"}, "odd-volts"),
    ({"amps": "41"}, "amps-dont-match"),
])
def test_readings_a_real_plate_cant_have_are_flagged(change, problem):
    plate = read_plate(FakeGlimmer({**PLATE, **change}), "plate.jpg")
    assert problem in plate.problems


def test_a_misread_wattage_is_never_used_for_the_load_plan():
    assert read_plate(FakeGlimmer({**PLATE, "starting_watts": "3000"}), "p.jpg").usable_watts is None


def test_no_plate_and_numbers_in_words():
    plate = read_plate(FakeGlimmer({**PLATE, "plate_visible": False}), "p.jpg")
    assert not plate.visible and plate.problems == ["no-plate"]
    assert number("Rated 3,500 W") == 3500 and number("") is None and number("n/a") is None


def test_the_reading_is_read_back_to_confirm():
    plate = read_plate(FakeGlimmer({**PLATE, "starting_watts": "3000"}), "p.jpg")
    assert read_back(plate, "en").startswith("I read: Champion 201183, 3,500 running watts and 3,000 starting watts, "
                                             "120/240 volts, gasoline. Is that right? The starting watts I read")
    assert read_back(plate, "es").startswith("Leí: Champion 201183, 3,500 vatios de trabajo y 3,000 vatios de "
                                             "arranque, 120/240 voltios, gasolina. ¿Es correcto?")


def test_a_plate_the_model_failed_to_read_counts_as_unread():
    class Unreachable:
        def ask_json(self, prompt, schema, images=()):
            from aftermath.vlm import ReadFailed

            raise ReadFailed("Meta API: ConnectError('no route to host')")

    plate = read_plate(Unreachable(), "plate.jpg")
    assert not plate.visible and plate.problems == ["no-plate"]


def test_what_wasnt_read_is_left_out_of_the_read_back_and_the_rest_joined_as_before():
    full = Plate(True, "Champion", "100891", 3500, 4375, "120/240", 60, 14.6, "gasoline")
    assert read_back(full, "hi") == ("मैंने पढ़ा: Champion 100891, 3,500 रनिंग वॉट और 4,375 स्टार्टिंग वॉट, 120/240 वोल्ट, "
                                     "पेट्रोल। क्या यह सही है?")  # as reviewed
    no_running = replace(full, running_watts=None, problems=["no-running-watts"])
    assert read_back(no_running, "hi") == ("मैंने पढ़ा: Champion 100891, 4,375 स्टार्टिंग वॉट और 120/240 वोल्ट, पेट्रोल। "
                                           "क्या यह सही है? रनिंग वॉट पढ़े नहीं जा सके। मुझे बताइए, या और पास से "
                                           "फ़ोटो लीजिए।")
    assert read_back(no_running, "en").startswith("I read: Champion 100891, 4,375 starting watts and 120/240 volts, "
                                                  "gasoline. Is that right? I couldn't read the running watts.")
    bare = Plate(True, "", "", None, None, "120/240", 60, None, "", problems=["no-running-watts"])
    assert read_back(bare, "es").startswith("Leí: 120/240 voltios. ¿Es correcto?")
    for language in ("hi", "en", "es"):
        text = read_back(replace(bare, volts=""), language)  # nothing read at all: no empty "I read:"
        assert text == PLATE_NOTES["no-plate"][language]
        assert not re.search(r"पढ़ा नहीं गया|unknown|sin leer", read_back(no_running, language))


@pytest.mark.parametrize("printed,volts", [("120/240", "120/240"), ("120/240 V", "120/240"), ("120V/240V", "120/240"),
                                           ("120/240 VAC, 12 VDC", "120/240"), ("120 - 240 Volts", "120/240"),
                                           ("120 V", "120"), ("", "")])
def test_volts_are_kept_as_numbers_so_the_read_back_says_volts_once(printed, volts):
    assert ac_volts(printed) == volts
    plate = read_plate(FakeGlimmer({**PLATE, "volts": printed}), "p.jpg")
    assert " V volts" not in read_back(plate, "en") and "V वोल्ट" not in read_back(plate, "hi")
