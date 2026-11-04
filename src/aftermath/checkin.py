"""The overnight check-in's reminder, and the summary a family can be sent.

The coach can't stay up with the person, so it offers a calendar reminder: an event at the time they choose, whose
link reopens the page for the check-in (conversation.CHECKIN asks its three questions again). The summary is plain
English, for a relative who may not share the person's language: what was measured, what the check-in found or that
nobody answered it, any danger, and what's still unknown. It never says "safe", and it carries no name, address or
location; the reminder carries only the page's own address. Anything personal is the person's to type into the
note the page adds to the summary.
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .conversation import Conversation, key
from .phrases import PLACES
from .rules import Level, Situation, assess, band, capped

TITLE = {"en": "Generator check-in", "es": "Revisión del generador", "hi": "जनरेटर की जाँच"}
NOTE = {"en": "Open the coach and answer three quick questions: {url}",
        "es": "Abra el asistente y conteste tres preguntas rápidas: {url}",
        "hi": "सहायक खोलें और तीन छोटे सवालों के जवाब दें: {url}"}


def calendar(url: str, at: datetime, language: str, uid: str, now: datetime) -> str:
    """An iCalendar event at ``at`` with an alert, whose link reopens the page for the check-in."""
    title = TITLE[language]
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//Aftermath//Generator check-in//EN", "CALSCALE:GREGORIAN",
             "METHOD:PUBLISH", "BEGIN:VEVENT", f"UID:{uid}", f"DTSTAMP:{utc(now)}", f"DTSTART:{utc(at)}",
             "DURATION:PT10M", f"SUMMARY:{escaped(title)}", f"DESCRIPTION:{escaped(NOTE[language].format(url=url))}",
             f"URL:{url}", "BEGIN:VALARM", "ACTION:DISPLAY", f"DESCRIPTION:{escaped(title)}", "TRIGGER:PT0M",
             "END:VALARM", "END:VEVENT", "END:VCALENDAR"]
    return "".join(folded(line) + "\r\n" for line in lines)


def utc(t: datetime) -> str:
    return t.astimezone(UTC).strftime("%Y%m%dT%H%M%SZ")


def escaped(text: str) -> str:
    """Text as an iCalendar value: backslashes, commas, semicolons and line breaks escaped."""
    return text.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def folded(line: str) -> str:
    """A content line cut into pieces of at most 75 bytes, never inside a character, each further piece starting
    with a space, as iCalendar requires."""
    pieces, piece, size, limit = [], "", 0, 75
    for char in line:
        width = len(char.encode())
        if size + width > limit:
            pieces.append(piece)
            piece, size, limit = "", 0, 74  # the space a continuation starts with counts
        piece += char
        size += width
    return "\r\n ".join(pieces + [piece])


@dataclass
class Record:
    """What a summary is written from. Times are in the phone's time zone."""

    talk: Conversation  # the conversation now: the check-in's, once one has begun
    before: Situation | None = None  # the situation when the check-in began
    measured_at: datetime | None = None  # when the door was photographed
    due: datetime | None = None  # when the check-in was planned for
    checked_at: datetime | None = None  # when it began
    lost: bool = False  # the check-in began from nothing: the conversation before it was gone (a restart)


BANDS = {
    "meets the guidance": "That meets CDC's guidance of more than 20 ft from doors, windows and vents. Farther is "
                          "better.",
    "borderline": "That's borderline: CDC says more than 20 ft from doors, windows and vents, so it should be moved "
                  "farther.",
    "too close": "That's too close: CDC says more than 20 ft from doors, windows and vents.",
}
DANGERS = {
    "move-outside-now": "The generator is {place}. It must never run there, even with the doors open.",
    "away-from-openings": "The generator is {place}, against the house. It must be moved away from doors, windows "
                          "and vents.",
    "too-close": "The generator is too close to the house.",
    "no-charcoal-grill": "A charcoal grill or coal stove is being used indoors.",
    "no-gas-oven": "A gas oven is being used for heat.",
    "no-camp-stove": "A camp stove is being used indoors.",
    "no-car-in-garage": "A car is running in the garage.",
    "no-backfeeding": "The generator is plugged into a wall outlet (backfeeding).",
    "stay-away-from-lines": "A fallen power line was reported nearby.",
}
WARNINGS = {
    "turn-exhaust": "The exhaust points toward the house.",
    "get-co-alarm": "There's no working carbon monoxide alarm.",
    "go-where-there-is-power": "It's {weather}; the coach suggested going somewhere with power.",
    "medical-plan": "Someone needs power for medicine or a medical device.",
    "cool-before-refuel": "They were adding fuel: the generator should be off and cool first.",
}
UNKNOWN = {
    "measure-distance": "How far the generator is from the house.",
    "confirm-outside": "Whether the generator is outside.",
    "confirm-1x": "Whether the camera was at 1× for the door photo.",
    "ask-moved-outside": "Whether the generator has been moved outside.",
    "ask-exhaust": "Which way the exhaust points.",
    "ask-co-alarm": "Whether there's a working carbon monoxide alarm.",
    "ask-heat-and-cooking": "What they use for heat and cooking.",
    "ask-downed-lines": "Whether there are fallen power lines nearby.",
}
CHECKIN_LINES = {"checkin-symptoms": "Anyone with a headache, dizziness, weakness or nausea",
                 "checkin-co-alarm": "A working carbon monoxide alarm"}
EARLY = timedelta(hours=1)  # a check-in this long before the reminder, or any time after it, answers it
FOOTER = ("From Aftermath, a generator coach for after the storm. It isn't a carbon monoxide detector and doesn't "
          "replace 911. If anyone feels sick, get everyone into fresh air and call 911.")


def clock(t: datetime) -> str:
    return f"{t.hour % 12 or 12}:{t:%M} {'AM' if t.hour < 12 else 'PM'}"


def summary(record: Record, now: datetime) -> str:
    """The summary for the family, in plain English."""
    talk, s = record.talk, record.talk.situation
    result = assess(s)
    lines = [f"Generator check-in summary, {clock(now)}, {now:%a %b} {now.day}.", ""]
    urgent, earlier = [], record.before or Situation()
    if s.alarm_sounding:
        urgent.append("URGENT: the carbon monoxide alarm was reported sounding. The coach told them to get everyone "
                      "outside into fresh air, call 911, and not go back in until emergency responders say so.")
    elif earlier.alarm_sounding:
        urgent.append("Earlier, the carbon monoxide alarm was reported sounding.")
    if s.symptoms:
        urgent.append("URGENT: someone reported a headache, dizziness, weakness or nausea. The coach told them to get "
                      "everyone into fresh air and call 911.")
    elif earlier.symptoms:
        urgent.append("Earlier, someone reported a headache, dizziness, weakness or nausea.")
    due, checked = record.due, record.checked_at
    if due is not None and now >= due and (checked is None or checked < due - EARLY):
        urgent.append(f"No answer at the {clock(due)} check-in.")
    if record.lost:
        urgent.append("The conversation before this check-in wasn't on record (the laptop restarted), so only the "
                      "check-in's answers are known.")
    if urgent:
        lines += urgent + [""]

    if s.lowest_ft is not None:
        when = f", measured at {clock(record.measured_at)}" if record.measured_at else ""
        lines.append(f"Distance from the generator to the nearest door: about {s.measured_ft:.0f} ft, at least "
                     f"{int(s.lowest_ft)} ft allowing for measuring error{when}.")
        unconfirmed = s.lens_assumed and band(s.lowest_ft) != "too close"
        if unconfirmed:
            lines.append("The photo didn't record which lens took it, and nobody has said the camera was at 1×, "
                         "so the distance counts only if it was.")
        elif s.lens_assumed:
            lines.append("(The photo didn't record which lens took it: the distance assumes the camera was at 1×.)")
        elif talk.lens_confirmed:
            lines.append("(The photo didn't record which lens took it; they said the camera was at 1×.)")
        if s.location == "outdoors":
            if not unconfirmed:  # no verdict on the distance until the lens is confirmed
                lines.append(BANDS[band(s.lowest_ft, s.reads_far)])
                if capped(s):
                    lines.append("(Something in the photo can make the distance read too far, so it counts as "
                                 "borderline at best.)")
        elif s.location is None:
            lines.append("Whether the generator is outside hasn't been confirmed, and the distance counts only if "
                         "it is.")
        else:
            lines.append("It isn't outside now, so that distance doesn't count.")
        if not talk.door_checked:
            lines.append(f"(That assumes a standard door, {talk.door_in // 12:.0f} ft {talk.door_in % 12:.0f} in "
                         "tall.)")
    else:
        lines.append("Distance from the generator to the house: not measured.")
    where = {"outdoors": "outside", None: "not confirmed"}.get(s.location, PLACES["en"].get(s.location, s.location))
    lines.append(f"Where the generator is: {where}.")

    if record.checked_at is not None:
        lines += ["", f"At the {clock(record.checked_at)} check-in:"]
        for question in talk.checkin:
            value = {"checkin-symptoms": s.symptoms, "checkin-co-alarm": s.co_alarm}.get(question.rule)
            if question.rule == "checkin-outside":
                label = ("Generator still outside, where it was measured" if question.values.get("measured")
                         else "Generator outside")
                value = None if s.location is None else s.location == "outdoors"
            else:
                label = CHECKIN_LINES[question.rule]
            if question.rule == "checkin-co-alarm" and s.alarm_sounding:
                answer = "it was sounding"
            elif value is None:
                answer = "no clear answer" if talk.tries.get(key(question), 0) else "no answer"
            else:
                answer = "yes" if value else "no"
            lines.append(f"- {label}: {answer}.")
    if due is not None and now < due:
        lines += ["", f"{'Next check-in' if checked is not None else 'Check-in'} planned for {clock(due)}."]

    dangers = [DANGERS[a.rule].format(place=PLACES["en"].get(a.values.get("place"), "")) for a in result.advice
               if a.level == Level.DANGER and a.rule in DANGERS]
    warnings = [WARNINGS[a.rule].format(weather=weather(a.values)) for a in result.advice
                if a.level == Level.WARNING and a.rule in WARNINGS]
    reported = {"ask-co-alarm", "confirm-outside"} if record.checked_at is not None else set()  # in its own lines
    unknown = [UNKNOWN[a.rule] for a in result.advice
               if a.level == Level.CHECK and a.rule in UNKNOWN and a.rule not in reported]
    if not talk.door_checked and s.lowest_ft is not None:
        unknown.append("The door's real height (the distance depends on it).")
    for title, items in (("Dangers:", dangers), ("Also:", warnings), ("Still unknown:", unknown)):
        if items:
            lines += ["", title] + [f"- {item}" for item in items]
    return "\n".join(lines + ["", FOOTER])


def weather(values: dict) -> str:
    heat, cold = values.get("heat"), values.get("cold")
    return "very hot or very cold" if heat and cold else "very hot" if heat else "very cold"
