import re
from dataclasses import replace
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from test_conversation import UNCLEAR_HI, Glimmer, reading

from aftermath.checkin import Record, calendar, summary
from aftermath.conversation import Conversation
from aftermath.phrases import AGAIN, CHECKIN_ASK, CHECKIN_DONE, CHECKIN_HELLO, NOT_CAUGHT, PHRASES
from aftermath.rules import Advice, Level, Situation

OUT = Situation(location="outdoors", measured_ft=25.8, lowest_ft=24.3, exhaust_toward_house=False, co_alarm=True,
                symptoms=False, burning_indoors=frozenset(), downed_line=False)
ZONE = ZoneInfo("America/New_York")
NIGHT = datetime(2026, 10, 30, 2, 10, tzinfo=ZONE)


def checking(*readings, situation=OUT, language="hi"):
    """A check-in that has just asked whether anyone feels sick; the model, if asked, answers with ``readings``."""
    talk = Conversation(Glimmer(*readings), language=language, situation=situation, door_checked=True).check_in()
    opening = talk.opening()
    assert opening == f"{CHECKIN_HELLO[language]} {CHECKIN_ASK['checkin-symptoms'][language]}"
    return talk


def test_a_check_in_asks_its_three_questions_again_in_order_then_ends():
    talk = checking()
    assert (talk.situation.symptoms, talk.situation.location, talk.situation.co_alarm) == (None, None, None)
    assert talk.situation.measured_ft == 25.8 and talk.situation.downed_line is False  # the rest carries on
    first = talk.reply("नहीं, किसी को नहीं")
    assert first.text == CHECKIN_ASK["checkin-outside"]["measured"]["hi"] and talk.situation.symptoms is False
    second = talk.reply("हाँ, अभी भी बाहर है।")
    assert second.text == CHECKIN_ASK["checkin-co-alarm"]["hi"] and talk.situation.location == "outdoors"
    last = talk.reply("हाँ, काम कर रहा है।")
    assert last.text == CHECKIN_DONE["hi"] and talk.situation.co_alarm is True
    assert talk.reader.prompts == []  # plain answers: no model


def test_a_photo_taken_while_the_generator_was_inside_doesnt_count_at_the_check_in():
    talk = checking(situation=Situation(location="garage", measured_ft=22, lowest_ft=20.7))
    assert talk.situation.measured_ft is None
    talk.reply("नहीं")
    assert talk.asking.values == {"measured": False}
    assert talk.reply("नहीं").said == ["move-outside-now"]  # not outside: the danger


# What the model reads, at its worst, for each check-in question: the reassuring answer.
REASSURING = {"checkin-symptoms": reading(symptoms="no"), "checkin-outside": reading(generator_location="outdoors"),
              "checkin-co-alarm": reading(co_alarm="yes")}
FACT = {"checkin-symptoms": ("symptoms", False), "checkin-outside": ("location", "outdoors"),
        "checkin-co-alarm": ("co_alarm", True)}


def at(rule, *readings):
    """A check-in at ``rule``'s question, the ones before answered plainly."""
    talk = checking(*readings)
    for answer, asked in (("नहीं", "checkin-symptoms"), ("हाँ, बाहर है", "checkin-outside")):
        if talk.asked == rule:
            break
        assert talk.asked == asked
        talk.reply(answer)
    assert talk.asked == rule
    return talk


@pytest.mark.parametrize("heard", [*UNCLEAR_HI, "sab theek", "मुझे लगता है सब ठीक हैं"])
@pytest.mark.parametrize("rule", sorted(REASSURING))
def test_an_unclear_check_in_answer_never_reassures_even_if_the_model_reads_it_so(rule, heard):
    talk = at(rule, REASSURING[rule], REASSURING[rule])
    reply = talk.reply(heard)
    fact, reassuring = FACT[rule]
    assert getattr(talk.situation, fact) != reassuring, reply.text  # "लगता है हाँ" to symptoms: the emergency
    if getattr(talk.situation, fact) is None:
        assert re.search(r"(no clear answer|no answer)\.", summary(Record(talk=talk, checked_at=NIGHT), NIGHT))


def test_a_reassuring_reading_of_a_longer_answer_is_read_back_and_counts_only_on_a_plain_yes():
    talk = at("checkin-symptoms", reading(symptoms="no"))
    back = talk.reply("सब लोग सो रहे हैं, किसी को कोई परेशानी नहीं है")  # "everyone's asleep, nobody has any trouble"
    assert talk.situation.symptoms is None and back.question == "confirm"
    talk.reply("हाँ, सही है")
    assert talk.situation.symptoms is False and talk.asked == "checkin-outside"


def test_symptoms_at_the_check_in_get_the_emergency_line_alone():
    talk = checking()
    reply = talk.reply("हाँ, मुझे चक्कर आ रहे हैं")
    assert reply.said == ["fresh-air-now"] and reply.text == PHRASES["fresh-air-now"]["hi"]
    assert summary(Record(talk=talk, checked_at=NIGHT), NIGHT).splitlines()[2].startswith("URGENT: someone reported")


def test_a_generator_found_in_the_garage_at_the_check_in_gets_the_danger_then_the_rest():
    talk = checking()
    talk.reply("नहीं")
    reply = talk.reply("नहीं, गैराज में है")
    assert talk.situation.location == "garage" and reply.said == ["move-outside-now"]
    assert reply.text.endswith(CHECKIN_ASK["checkin-co-alarm"]["hi"])
    after = talk.reply("हाँ, काम कर रहा है")
    assert after.question == "ask-moved-outside"  # whether it's been moved out yet, before the check-in ends
    text = summary(Record(talk=talk, before=OUT, checked_at=NIGHT), NIGHT)
    assert "- Generator still outside, where it was measured: no." in text
    assert "The generator is in the garage. It must never run there" in text


def test_a_question_unanswered_twice_is_left_and_shown_as_no_clear_answer():
    talk = at("checkin-co-alarm", reading(), reading())
    again = talk.reply("पता नहीं")  # unsure: left for later at once
    assert again.text.startswith("कोई बात नहीं।") and again.text.endswith(CHECKIN_DONE["hi"])
    talk = at("checkin-co-alarm")
    assert talk.reply("हम्म").text == f"{NOT_CAUGHT['hi']} {AGAIN['checkin-co-alarm']['hi']}"
    assert talk.reply("हम्म").text.endswith(CHECKIN_DONE["hi"])
    assert "- A working carbon monoxide alarm: no clear answer." in summary(Record(talk=talk, checked_at=NIGHT), NIGHT)


# "Safe" and its cousins, which the summary must never use.
REASSURANCE = re.compile(r"\bsafe(ly)?\b|all good|all clear|nothing to worry|no problem|\bfine\b", re.I)


def test_the_summary_says_what_was_measured_found_and_unknown_and_never_that_all_is_well():
    talk = checking()
    for answer in ("नहीं, किसी को नहीं", "हाँ, अभी भी बाहर है", "हाँ, काम कर रहा है"):
        talk.reply(answer)
    text = summary(Record(talk=talk, before=OUT, measured_at=NIGHT - timedelta(hours=4), due=NIGHT,
                          checked_at=NIGHT + timedelta(minutes=2)), NIGHT + timedelta(minutes=5))
    assert text.startswith("Generator check-in summary, 2:15 AM, Fri Oct 30.")
    assert ("Distance from the generator to the nearest door: about 26 ft, at least 24 ft allowing for measuring "
            "error, measured at 10:10 PM.") in text
    assert "That meets CDC's guidance of more than 20 ft" in text and "Where the generator is: outside." in text
    assert "At the 2:12 AM check-in:" in text and "- Anyone with a headache, dizziness, weakness or nausea: no." in text
    assert "No answer" not in text and "Dangers:" not in text and not REASSURANCE.search(text)


def test_a_missed_check_in_is_said_first_and_a_planned_one_is_said_as_planned():
    talk = Conversation(Glimmer(), situation=Situation(location="outdoors", measured_ft=14, lowest_ft=13.2))
    missed = summary(Record(talk=talk, due=NIGHT - timedelta(minutes=10)), NIGHT).splitlines()
    assert missed[2] == "No answer at the 2:00 AM check-in."
    planned = summary(Record(talk=talk, due=NIGHT + timedelta(hours=1)), NIGHT)
    assert "Check-in planned for 3:10 AM." in planned and "No answer" not in planned
    assert "That's too close" in planned and "- The generator is too close to the house." in planned
    assert "(That assumes a standard door, 6 ft 8 in tall.)" in planned and not REASSURANCE.search(planned)


def test_the_summary_is_written_from_the_facts_never_from_what_was_said():
    talk = Conversation(Glimmer(reading("en", generator_location="garage", burning_indoors=["charcoal_grill"])),
                        language="en")
    talk.reply("It's in the garage at 12 Oak Street, Tampa, and we cook on the charcoal grill. I'm Maria.")
    text = summary(Record(talk=talk), NIGHT)
    assert "The generator is in the garage. It must never run there" in text
    assert "A charcoal grill or coal stove is being used indoors." in text
    assert not re.search(r"Oak|Tampa|Maria|\b12\b", text)


def test_the_reminder_is_a_calendar_event_with_an_alert_and_the_link_back_and_nothing_else():
    url = "https://192.0.2.10:8443/?checkin=0123abcd&language=hi"
    text = calendar(url, NIGHT, "hi", "0123abcd-1@aftermath", NIGHT - timedelta(hours=5))
    lines = text.split("\r\n")
    assert lines[0] == "BEGIN:VCALENDAR" and lines[-2] == "END:VCALENDAR" and lines[-1] == ""
    assert "DTSTART:20261030T061000Z" in lines and "TRIGGER:PT0M" in lines and "SUMMARY:जनरेटर की जाँच" in lines
    assert all(len(line.encode()) <= 75 for line in lines)
    unfolded = text.replace("\r\n ", "")
    assert f"URL:{url}" in unfolded and f"सवालों के जवाब दें: {url}" in unfolded
    assert set(re.findall(r"^[A-Z-]+(?=:)", unfolded, re.M)) <= {
        "BEGIN", "VERSION", "PRODID", "CALSCALE", "METHOD", "UID", "DTSTAMP", "DTSTART", "DURATION", "SUMMARY",
        "DESCRIPTION", "URL", "ACTION", "TRIGGER", "END"}  # no location, organizer or attendee
    english = calendar(url, NIGHT, "en", "x", NIGHT).replace("\r\n ", "")
    assert f"DESCRIPTION:Open the coach and answer three quick questions: {url}\r\n" in english


def test_a_check_in_well_before_the_reminder_doesnt_answer_it_and_the_next_one_is_said():
    talk = checking()
    early = summary(Record(talk=talk, checked_at=NIGHT - timedelta(hours=4), due=NIGHT - timedelta(minutes=10)), NIGHT)
    assert "No answer at the 2:00 AM check-in." in early and "At the 10:10 PM check-in:" in early
    on_time = summary(Record(talk=talk, checked_at=NIGHT - timedelta(minutes=40), due=NIGHT - timedelta(minutes=10)),
                      NIGHT)
    assert "No answer" not in on_time  # half an hour early still counts
    ahead = summary(Record(talk=talk, checked_at=NIGHT, due=NIGHT + timedelta(hours=2)), NIGHT)
    assert "Next check-in planned for 4:10 AM." in ahead


def test_yes_its_ringing_to_is_your_alarm_working_is_the_emergency_and_heads_the_summary():
    talk = checking()
    talk.reply("नहीं, किसी को नहीं")
    talk.reply("हाँ, बाहर है")
    assert talk.asked == "checkin-co-alarm"
    reply = talk.reply("हाँ, बज रहा है")
    assert reply.said == ["alarm-sounding"] and talk.situation.co_alarm is None
    text = summary(Record(talk=talk, checked_at=NIGHT), NIGHT)
    assert text.splitlines()[2].startswith("URGENT: the carbon monoxide alarm was reported sounding.")
    assert "- A working carbon monoxide alarm: it was sounding." in text
    later = summary(Record(talk=talk.check_in(), before=talk.situation, checked_at=NIGHT), NIGHT)
    assert "Earlier, the carbon monoxide alarm was reported sounding." in later


def test_a_distance_on_an_unconfirmed_lens_gets_no_verdict_in_the_summary():
    talk = Conversation(Glimmer(), language="en", situation=replace(OUT, lens_assumed=True), door_checked=True)
    text = summary(Record(talk=talk), NIGHT)
    assert "nobody has said the camera was at 1×, so the distance counts only if it was." in text
    assert "That meets CDC's guidance" not in text and "- Whether the camera was at 1× for the door photo." in text
    talk.asking = Advice("confirm-1x", Level.CHECK, ("cdc-distance",))
    talk.reply("Yes, it was at 1x.")
    text = summary(Record(talk=talk), NIGHT)
    assert "(The photo didn't record which lens took it; they said the camera was at 1×.)" in text
    assert "That meets CDC's guidance" in text and "Whether the camera was at 1×" not in text
    later = summary(Record(talk=talk.check_in(), before=talk.situation, checked_at=NIGHT), NIGHT)
    assert "they said the camera was at 1×" in later  # carried into the check-in


def test_a_reading_that_may_be_too_far_is_borderline_in_the_summary_and_says_why():
    talk = Conversation(Glimmer(), language="en", situation=replace(OUT, reads_far=True), door_checked=True)
    text = summary(Record(talk=talk), NIGHT)
    assert "That's borderline" in text and "That meets CDC's guidance" not in text
    assert "can make the distance read too far, so it counts as borderline at best" in text
