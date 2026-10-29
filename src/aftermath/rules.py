"""The safety rules: deterministic, outside any language model, every piece of advice citing its source.

The language model only works out what the person said (where the generator is, whether they feel sick, what they
heat with) and answers open questions; these rules decide what to tell them. A fact the person hasn't given is None,
and becomes a question rather than an assumption.

Distance bands lean toward "too close": under 17 ft is too close, 17–23 ft is borderline (move it farther), and over
23 ft meets the guidance. The band is taken from the low end of the measurement's error range, so measuring error
can't turn "too close" into "far enough". A distance only counts once the generator is known to be outside: a door
photo taken before then gives the distance "if it's outside" and asks (a distance too close is too close either way).
Likewise a photo that didn't record its lens is measured as if taken at 1×, and its distance counts only once the
person says the camera was at 1× (0.5× would make the door look nearly twice as far as it is); too close stands.
The rules never call anything "safe": the most they say is that a placement meets the guidance, and that farther is
better.
"""

from dataclasses import dataclass, field
from enum import IntEnum

TOO_CLOSE_FT, BORDERLINE_FT = 17.0, 23.0
ENCLOSED = frozenset({"indoors", "garage", "basement", "crawlspace", "shed"})  # never, even with doors open
AGAINST_HOUSE = frozenset({"porch", "under_eaves", "carport", "doorway", "window"})  # outdoors but at an opening
LOCATIONS = ENCLOSED | AGAINST_HOUSE | {"outdoors"}
BURNING = frozenset({"charcoal_grill", "gas_oven", "camp_stove", "car_in_garage"})  # CO sources besides the generator


class Level(IntEnum):
    """How urgent a piece of advice is; lower comes first."""

    EMERGENCY = 0  # act now
    DANGER = 1  # stop or move it now
    WARNING = 2  # change something
    CHECK = 3  # something to check, or a question to answer
    INFO = 4  # standing guidance


@dataclass(frozen=True)
class Situation:
    """What is known about the household; None means not known yet."""

    location: str | None = None  # where the generator runs: "outdoors", or one of ENCLOSED or AGAINST_HOUSE
    measured_ft: float | None = None  # measured distance from the generator to the nearest door
    lowest_ft: float | None = None  # the low end of that measurement's error range
    lens_assumed: bool = False  # the door photo had no lens data: measured as if at 1×, not yet confirmed
    exhaust_toward_house: bool | None = None
    co_alarm: bool | None = None  # a working battery or battery-backup CO alarm in the home
    symptoms: bool | None = None  # headache, dizziness, weakness, nausea, confusion, now
    alarm_sounding: bool | None = None  # the CO alarm was heard going off (beeping, sounding)
    burning_indoors: frozenset[str] | None = None  # BURNING sources used indoors; empty once asked and none
    downed_line: bool | None = None  # a fallen power line nearby
    extreme_heat: bool | None = None
    extreme_cold: bool | None = None
    medical_needs: bool | None = None  # refrigerated medicine or a power-dependent medical device
    backfeeding: bool | None = None  # generator plugged into a wall outlet
    refuelling: bool | None = None
    raining: bool | None = None
    co_shutoff: bool | None = None  # the generator has a CO shutoff (from its label or the person)

    def __post_init__(self) -> None:
        if self.location is not None and self.location not in LOCATIONS:
            raise ValueError(f"unknown generator location {self.location!r}")
        if self.burning_indoors is not None and not self.burning_indoors <= BURNING:
            raise ValueError(f"unknown CO sources {sorted(self.burning_indoors - BURNING)}")


@dataclass(frozen=True)
class Advice:
    rule: str  # also the key of its wording in phrases.py
    level: Level
    sources: tuple[str, ...]  # ids in guidance.SOURCES
    values: dict = field(default_factory=dict)  # numbers the wording needs


@dataclass(frozen=True)
class Assessment:
    placement: str  # "never indoors", "against the house", "too close", "borderline", "meets the guidance",
    #                 "if outside", "if at 1x" or "not measured"
    headline: Advice  # the advice about where the generator is: the one to say first about it
    advice: list[Advice]  # everything, most urgent first


def band(feet: float) -> str:
    """The distance band of a (conservative) distance in feet."""
    if feet < TOO_CLOSE_FT:
        return "too close"
    if feet <= BORDERLINE_FT:
        return "borderline"
    return "meets the guidance"


def placement(situation: Situation) -> str:
    if situation.location in ENCLOSED:
        return "never indoors"
    if situation.location in AGAINST_HOUSE:
        return "against the house"
    if situation.lowest_ft is None:
        return "not measured"
    measured = band(situation.lowest_ft)
    if measured == "too close":
        return measured  # either way: a photo not taken at 1× was zoomed in (it reads closer) or at 0.5× (closer yet)
    if situation.lens_assumed:
        return "if at 1x"  # a door photo that didn't record its lens, until the person says it was at 1×
    if situation.location is None:
        return "if outside"  # a door photo before anyone said where the generator is
    return measured


def assess(situation: Situation) -> Assessment:
    """The advice for a situation, most urgent first."""
    s, advice = situation, []
    where = placement(s)
    distance = {"feet": s.measured_ft, "lowest": s.lowest_ft}
    measured = band(s.lowest_ft) if s.lowest_ft is not None else None

    if s.alarm_sounding:
        advice.append(Advice("alarm-sounding", Level.EMERGENCY, ("cpsc-alarm-sounds", "cpsc-alarm-after",
                                                                 "cpsc-suspect-co", "cpsc-es-suspect-co")))
    if s.symptoms:
        advice.append(Advice("fresh-air-now", Level.EMERGENCY, ("cpsc-sick", "cdc-symptoms", "cpsc-es-sick")))
    headline = {
        "never indoors": Advice("move-outside-now", Level.DANGER, ("cdc-never-indoors", "cpsc-indoors", "cpsc-2026",
                                                                   "ready-hi-generator", "ready-hi-prepare",
                                                                   "cpsc-es-indoors", "cdc-es-distance"),
                                {"place": s.location}),
        "against the house": Advice("away-from-openings", Level.DANGER, ("cpsc-exhaust", "cdc-distance", "cpsc-2026",
                                                                        "ready-hi-generator", "cpsc-es-porch",
                                                                        "cpsc-es-exhaust"),
                                    {"place": s.location}),
        "too close": Advice("too-close", Level.DANGER, ("cdc-distance", "nist-15ft", "nist-25ft", "nist-tn1637",
                                                        "cdc-es-distance"), distance),
        "borderline": Advice("borderline", Level.WARNING, ("cdc-distance", "nist-25ft", "nist-30ft", "cdc-es-distance"),
                             distance),
        "meets the guidance": Advice("meets-guidance", Level.INFO, ("cdc-distance", "nist-25ft", "cdc-es-distance"),
                                     distance),
        "if outside": Advice("if-outside", Level.WARNING, ("cdc-never-indoors", "cdc-distance"),
                             {**distance, "band": measured}),
        "if at 1x": Advice("if-1x", Level.WARNING, ("cdc-distance",), {**distance, "band": measured}),
        "not measured": Advice("measure-distance", Level.CHECK, ("cdc-distance", "cdc-never-indoors",
                                                                "ready-distance", "ready-hi-generator",
                                                                "ready-es-distance"),
                               {"outdoors": s.location == "outdoors"}),
    }[where]
    advice.append(headline)
    if where == "if at 1x":  # the distance counts only if the camera was at 1×: asked first
        advice.append(Advice("confirm-1x", Level.CHECK, ("cdc-distance",)))
    if s.location is None and s.lowest_ft is not None:  # the distance counts only if the generator is outside
        advice.append(Advice("confirm-outside", Level.CHECK, ("cdc-never-indoors", "cdc-distance")))
    if where in ("never indoors", "against the house"):
        # The next thing to know is whether it's been moved (a door measurement only counts once it has).
        advice.append(Advice("ask-moved-outside", Level.CHECK, ("cdc-never-indoors", "cdc-distance"),
                             {"measured": s.measured_ft is not None}))

    official_es = {"charcoal_grill": ("cdc-es-charcoal", "cpsc-es-grill"), "gas_oven": ("cdc-es-oven",),
                   "camp_stove": ("cdc-es-stove",), "car_in_garage": ("cdc-es-car",)}
    for source in sorted(s.burning_indoors or ()):
        english = ("cdc-other-sources", "cpsc-charcoal") if source == "charcoal_grill" else ("cdc-other-sources",)
        advice.append(Advice(f"no-{source.replace('_', '-')}", Level.DANGER, english + official_es[source]))
    if s.backfeeding:
        advice.append(Advice("no-backfeeding", Level.DANGER, ("cpsc-backfeed", "cpsc-cords", "cpsc-es-backfeed",
                                                              "cpsc-es-cords")))
    if s.downed_line:
        advice.append(Advice("stay-away-from-lines", Level.DANGER, ("utility-lines-35", "utility-lines-40",
                                                                    "utility-lines-teco"),
                             {"feet": 35}))

    if s.exhaust_toward_house:
        advice.append(Advice("turn-exhaust", Level.WARNING, ("cpsc-exhaust", "cpsc-2026", "nist-30ft",
                                                             "cpsc-es-exhaust")))
    if s.co_alarm is False:
        advice.append(Advice("get-co-alarm", Level.WARNING, ("cdc-alarm", "cpsc-alarm", "ready-alarm",
                                                             "cdc-es-alarm")))
    if s.extreme_heat or s.extreme_cold:
        advice.append(Advice("go-where-there-is-power", Level.WARNING, ("ready-heat-cold", "ready-es-heat-cold"),
                             {"heat": bool(s.extreme_heat), "cold": bool(s.extreme_cold)}))
    if s.medical_needs:
        advice.append(Advice("medical-plan", Level.WARNING, ("ready-medical",)))
    if s.refuelling:
        advice.append(Advice("cool-before-refuel", Level.WARNING, ("cpsc-refuel", "cpsc-es-refuel")))

    if s.exhaust_toward_house is None and where != "never indoors":
        advice.append(Advice("ask-exhaust", Level.CHECK, ("cpsc-exhaust",)))
    if s.co_alarm is None:
        advice.append(Advice("ask-co-alarm", Level.CHECK, ("cdc-alarm", "cpsc-alarm")))
    if s.burning_indoors is None:
        advice.append(Advice("ask-heat-and-cooking", Level.CHECK, ("cdc-other-sources",)))
    if s.downed_line is None:
        advice.append(Advice("ask-downed-lines", Level.CHECK, ("utility-lines-35",)))

    if s.co_alarm:
        advice.append(Advice("test-co-alarm", Level.INFO, ("cpsc-alarm",)))
    if s.raining:
        advice.append(Advice("dry-and-outdoors", Level.INFO, ("cpsc-wet", "cdc-never-indoors", "cpsc-es-wet")))
    if s.co_shutoff:
        advice.append(Advice("shutoff-is-not-distance", Level.INFO, ("cpsc-2023-shutoff", "cdc-distance")))
    if not s.symptoms:
        advice.append(Advice("symptoms-line", Level.INFO, ("cdc-symptoms", "cpsc-sick", "cdc-poison-control", "cdc-asleep",
                                                           "cdc-es-symptoms", "cpsc-es-sick", "cdc-es-poison-control",
                                                           "cdc-es-asleep")))
    return Assessment(placement=where, headline=headline, advice=sorted(advice, key=lambda a: a.level))
