"""One conversation: what the person says becomes facts, the rules decide, and the reply is short and in their language.

Each turn, Muse Glimmer reads what the person said (with the question they were answering) into fixed fields: where
the generator is, symptoms, what they burn indoors, and so on. If they asked something else, it drafts a short answer.
It never decides safety advice: the rules do (rules.py), and the reply is put together here, in this order:

1. the emergency line, every time it applies;
2. dangers and warnings not said before, starting with where the generator is;
3. the answer to their own question, if any;
4. the next thing to ask, one question at a time.

Understanding leans one way: what would take a danger off the list needs a plain answer, while anything may add one.
A short answer to one of the coach's own questions is read here, without the model: "sí", "sí, ya está afuera" or
"no hay" count, while a lone "se" (MMS's "sí", sometimes), "no sé" or "creo que sí" don't. What the model reads that
would take a danger off the list is read back first ("Entendí que …, ¿es así?") and counts only on a plain yes,
because the model can be wrong as well: given MMS's garbled "no sé", it once read "no fallen lines". A question left
unanswered is asked once more, saying how to answer it, and then left for later. A new door photo isn't a reply: it
sets no fact, and whether the generator is outside, and the lens, are asked afresh for it. The lens question is also
offered as two buttons on the page, and a tap on one is a plain answer.

Glimmer's answer to an open question is told to leave generators, carbon monoxide, power lines and health to the
rules, never to call anything safe, and to send emergencies to 911; a check here drops an answer that says "safe".
"""

import logging
import re
import unicodedata
from dataclasses import dataclass, field, replace
from typing import Protocol

from .door import LEAF_IN
from .phrases import CHECKIN_DONE, CHECKIN_HELLO, DONE, HELLO, LATER, LENS_RETAKE, NOT_CAUGHT, PLATE_WRONG, ask, say
from .rules import AGAINST_HOUSE, BURNING, ENCLOSED, LOCATIONS, Advice, Level, Situation, assess

YES_NO_FACTS = ("symptoms", "exhaust_toward_house", "co_alarm", "downed_line", "extreme_heat", "extreme_cold",
                "medical_needs", "backfeeding", "refuelling", "raining", "co_shutoff")
FACTS = ("generator_location", *YES_NO_FACTS, "burning_indoors", "door_height_in")

def normal(text: str) -> str:
    """Text as the reading compares it: NFC, lower case, and in Devanagari the chandrabindu as an anusvara and no
    nukta, since people (and speech recognition) spell those both ways: "हाँ" and "हां", "कमज़ोरी" and "कमजोरी"."""
    return unicodedata.normalize("NFC", text).lower().replace("\u0901", "\u0902").replace("\u093c", "")


# Words that mean someone may be poisoned now. The emergency line doesn't wait for the language model: when they're
# there, and not negated ("nobody is dizzy", "चक्कर नहीं"), it is said at once, and the details are asked afterwards.
# Hindi as MMS spells it too: on Nov 4 it wrote «चककर» for «चक्कर», «सर» for «सिर», and «दद्द», «दद» or «द्द» for «दर्द».
SYMPTOMS = re.compile(
    r"dolor de cabeza|duele la cabeza|mareo|maread[oa]s?|n[áa]useas|desmay|v[óo]mit|"
    r"headache|head hurts|dizzy|nause|vomit|faint|passed out|throwing up|"
    r"(सिर|सर) ?(में )?(द(र्|र|द्)?द|द्द)|सिर दुख|चक्?कर|कमजोरी|उल[्]?टी(?! ?(तरफ|ओर|दिशा))|जी मिचला|मितली|मतली|"
    r"बेहोश|सीने में दर्द",
    re.I)
# A negation reaches the next few words, never past a comma: in "No, I have a headache" the "no" answers a question.
NEGATION = re.compile(r"\b(no|not|nobody|no one|none|nadie|ni|ningun[oa]?|tampoco)\b[^.?!,;]{0,20}$", re.I)
HINDI_NO = frozenset({"नहीं", "नही", "ना", "न"})


def negated_after(text: str, end: int, breaks: str = ".?!।") -> bool:
    """Hindi puts the negation after what it negates: "चक्कर नहीं", "गैराज में नहीं है". So, within the next three
    words, and before any "है": after it, "नहीं" or "ना" is a tag ("चक्कर आ रहे हैं, नहीं?", "बज रहा है ना?"). Kept that
    short on purpose: a negation read where there is none would hide a danger."""
    for word in re.split(r"[\s,]+", re.split(f"[{breaks}]", text[end:])[0])[:4]:
        if word in COPULAS:
            return False
        if word in HINDI_NO:
            return True
    return False


def says_symptoms(heard: str) -> bool:
    """Whether the words report symptoms now, read without the language model."""
    heard = normal(heard)
    return any(not NEGATION.search(heard[max(0, m.start() - 30):m.start()]) and not negated_after(heard, m.end())
               for m in SYMPTOMS.finditer(heard))


# A carbon monoxide alarm heard sounding is an emergency at once, like symptom words: the quick path, no model, and
# only the emergency line. Any sound counts, a low-battery chirp too: a sounding alarm is never guessed to be its
# battery. The sound counts next to the alarm's name, or alone in answer to a question about the alarm ("हाँ, बज रहा
# है"). Not "suena" alone ("suena bien"), and not "sounds" ("it sounds fine").
# Hindi as MMS spells it too (Nov 4, from a macOS Hindi voice): «आलार्म» and «अरलारम» for «अलार्म», «दिटेकतर» for
# «डिटेक्टर», «बझ» for «बज», «बीव» for «बीप». Missed, the alarm went to the model, which has no field for it.
ALARM = re.compile(r"\balarm|\bdetector|\balarma|[अआ]र?ला(र्|र)?म|[डद][िी][टत]े(क्ट|क्त|कत|कट)र", re.I)
SOUNDING = re.compile(r"\bgo(es|ing)? off\b|\b(gone|went) off\b|\bbeep|\bsounding\b|\bsounded\b|\bchirp|\bringing\b|"
                      r"\brang\b|\bbuzz|\bsonando\b|\bson[óo]\b|\bsuena\b|\bpit(a|ó|o|ando)\b|बज|बझ|बीप|बीव(?!ी)|आवाज|सीटी|"
                      r"शोर", re.I)
QUIET = re.compile(r"(\b(no|not|never|nunca|nada)\b|n't\b|\b(is|was|does|did|has|are|were|wo|ca)nt\b)[^.?!,;।]{0,20}$",
                   re.I)
ABOUT_THE_ALARM = ("ask-co-alarm", "checkin-co-alarm")


def says_alarm(heard: str, asked: str | None = None) -> bool:
    """Whether the words report the carbon monoxide alarm sounding, read without the language model. A negation
    just before the sound (or, in Hindi, just after it) means it isn't: "अलार्म नहीं बज रहा", "it never went off"."""
    heard = normal(heard)
    for match in SOUNDING.finditer(heard):
        near = ALARM.search(heard[max(0, match.start() - 40):match.end() + 40])
        if not near and (asked not in ABOUT_THE_ALARM or match.group() == "suena"):
            continue
        before = heard[max(0, match.start() - 30):match.start()]
        hindi_before = re.split(r"\s+", re.split(r"[.?!।,;]", before)[-1].strip())[-2:]
        if not (QUIET.search(before) or HINDI_NO & set(hindi_before)
                or negated_after(heard, match.end(), breaks=".?!।,;")):
            return True
    return False


YES_NO = {"type": "string", "enum": ["yes", "no"]}
LANGUAGE_NAMES = {"es": "Spanish", "en": "English", "hi": "Hindi"}
# Every fact is optional, so Glimmer writes only the ones the person stated: a short answer, and a fast turn. (A list
# of facts let it repeat items until it ran out of tokens.)
SCHEMA = {
    "type": "object",
    "properties": {
        "language": {"type": "string", "enum": ["es", "en", "hi", "other"]},
        "generator_location": {"type": "string", "enum": sorted(LOCATIONS)},
        **{name: YES_NO for name in YES_NO_FACTS},
        "burning_indoors": {"type": "array", "items": {"type": "string", "enum": [*sorted(BURNING), "none"]},
                            "maxItems": 4},
        "door_height_in": {"type": "number"},
        "question": {"type": "string"},
        "answer": {"type": "string"},
    },
    "required": ["language", "question", "answer"],
}

PROMPT = """You help a safety coach understand one turn of a conversation with a person whose power is out after a
storm. The coach just asked: "{asked}". The person answered: "{heard}".

Include a fact only if the person stated it in this turn; leave the others out. Leave a fact out, too, if they're
unsure of it ("no sé", "creo que sí", "maybe", "पता नहीं", "शायद") or their words are unclear. A short "yes" or "no"
answers the coach's question. The facts:
- generator_location: where their generator runs now (not where they plan to move it): outdoors, indoors, garage,
  basement, crawlspace, shed, porch, under_eaves, carport, doorway or window.
- symptoms: "yes" if anyone has a headache, dizziness, weakness, nausea or confusion now; "no" if they say no one does.
- exhaust_toward_house, co_alarm (a working carbon monoxide alarm), downed_line (a fallen power line near them),
  extreme_heat, extreme_cold, medical_needs (medicine that needs a fridge, or a medical device that needs power),
  backfeeding (generator plugged into a wall outlet), refuelling (adding fuel now), raining, co_shutoff (the
  generator has a carbon monoxide shutoff): "yes" or "no".
- burning_indoors: one of charcoal_grill (a charcoal grill: parrilla, asador, anafre, fogón; or a coal brazier or
  stove: अंगीठी, सिगड़ी), gas_oven,
  camp_stove or car_in_garage used indoors or in an attached garage (one entry each), or "none" if they said they use
  none of these.
- door_height_in: the height of their door in inches (6 feet 8 inches is 80), if they said it.
language: the language the person spoke (es, en, hi or other).
question: any other question they asked, in their words, or "".
answer: if they asked such a question, a short answer (one or two sentences) in {language}. Don't answer about
where to put a generator, carbon monoxide, power lines, fire or anyone's health: say the coach will cover it. Never
say anything is safe. For an emergency, tell them to call 911. If you don't know, say so and say who would know."""


def made_up(reading: dict, heard: str) -> bool:
    """More facts than words, or more than half of them at once: made up, and dropped. Given "sceg", Glimmer once
    filled every field, with a shed; Spark, before its schema was sent strict, filled 13 for a ten-word answer and 14
    for «मेरा जेनरेटर गैराज में चल रहा है», mostly "no"."""
    return len(facts_of(reading)) > min(len(words_of(heard)), len(FACTS) // 2)


class Reader(Protocol):
    def ask_json(self, prompt: str, schema: dict, images: list = ()) -> dict: ...


def facts_of(reading: dict) -> dict:
    """The facts Glimmer read, normalised: yes/no as lower case, burning sources as a list."""
    facts = {name: reading[name] for name in FACTS if reading.get(name) not in (None, "", [])}
    for name in YES_NO_FACTS:
        if name in facts:
            facts[name] = str(facts[name]).strip().lower()
    return facts


def merge(situation: Situation, facts: dict) -> Situation:
    """The situation with the facts stated this turn; anything not stated keeps its earlier value."""
    changes = {}
    if facts.get("generator_location") in LOCATIONS:
        changes["location"] = facts["generator_location"]
    for name in YES_NO_FACTS:
        if facts.get(name) in ("yes", "no"):
            changes[name] = facts[name] == "yes"
    burning = [b for b in facts.get("burning_indoors") or [] if b in BURNING]
    if burning:
        changes["burning_indoors"] = frozenset(burning) | (situation.burning_indoors or frozenset())
    elif "none" in (facts.get("burning_indoors") or []) and situation.burning_indoors is None:
        changes["burning_indoors"] = frozenset()
    return replace(situation, **changes)


SAFE = re.compile(r"\bsafe(ly)?\b|\bsegur[oa]s?\b|\ba salvo\b|सुरक्षित|सेफ|महफूज", re.I)  # on normal() text

# A dangerous place for the generator, read without the model: said at once, since it's the turn where a fast answer
# matters most.
GENERATOR = re.compile(r"\bgenerador|\bplanta\b|\bgenerator|जनरेटर|जेनरेटर", re.I)
PLACES = [  # Hindi as normal() leaves it (no nukta)
    (re.compile(r"\bgaraje\b|\bgarage\b|\bcochera\b|गैराज|गराज|गेराज|गैरेज", re.I), "garage"),
    (re.compile(r"\bs[óo]tano\b|\bbasement\b|बेसमेंट|तहखान", re.I), "basement"),
    (re.compile(r"\bcobertizo\b|\bshed\b|(?<!कार )शेड", re.I), "shed"),
    (re.compile(r"dentro de (la )?casa|\ben (la )?casa\b|\badentro\b|\ben el cuarto\b|\ben la (sala|cocina)\b|"
                r"\binside\b|\bindoors\b|\bin the house\b|"
                r"(?<!\S)(घर के अंदर|घर में|अंदर|कमरे में|कमरे के अंदर)(?!\S)", re.I), "indoors"),
    (re.compile(r"debajo de la casa|\bcrawl ?space\b", re.I), "crawlspace"),
    (re.compile(r"\bmarquesina\b|\bcarport\b|कार शेड|कारपोर्ट", re.I), "carport"),  # a Puerto Rican carport
    (re.compile(r"\bporche\b|\bportal\b|\bbalc[óo]n\b|patio techado|\bporch\b|\bbalcony\b|बरामद|पोर्च|बालकनी",
                re.I), "porch"),
    (re.compile(r"\balero\b|\beaves\b|छज्जे", re.I), "under_eaves"),
]


def quick_place(heard: str, asked: str | None) -> str | None:
    """A dangerous place named for the generator (or in answer to "is it outside?"), unless it's negated."""
    heard = normal(heard)
    if not (GENERATOR.search(heard) or asked in ("measure-distance", "ask-moved-outside", "confirm-outside",
                                                 "checkin-outside")):
        return None
    for pattern, place in PLACES:
        match = pattern.search(heard)
        if (match and not NEGATION.search(heard[max(0, match.start() - 30):match.start()])
                and not negated_after(heard, match.end())):
            return place
    return None


# Short answers. MMS can hear a lone "sí" as "se" and a lone "हाँ" as anything, "si" is also "if", and "no sé" and
# "पता नहीं" ("I don't know") contain a "no", so a short answer is plain only when it's a clear yes or no, alone or
# with words that fit the question ("sí, ya está afuera", "हाँ, बाहर है", "no hay"), or the question's own words
# ("ya está afuera"). Hindi as normal() leaves it: "हां" for "हाँ".
YES_WORDS = frozenset({"sí", "claro", "correcto", "exacto", "cierto", "ajá", "yes", "yeah", "yep", "yup", "correct",
                       "हां", "हांजी", "जीहां", "जिहां", "haan", "haanji"})  # «जिहाँ»: MMS's «जी हाँ» (Nov 4)
MAYBE_YES = frozenset({"si", "se", "हा"})  # a yes only with words that fit the question, or a lone "si"
NO_WORDS = frozenset({"no", "nope", "nah", "nada", "ninguno", "ninguna", "nunca", "none", "nothing", "never", "not",
                      "dont", "doesnt", "arent", "isnt", "havent", "नहीं", "नही", "nahi", "nahin"})
COURTESY = frozenset({"que", "señor", "señora", "gracias", "of", "course", "sir", "maam", "thanks", "जी", "साहब",
                      "मैडम", "भैया", "दीदी", "बहनजी", "धन्यवाद", "शुक्रिया"})
NON_ANSWERS = frozenset({"se", "eh", "ah", "mm", "mmm", "hm", "hmm", "uh", "um", "este", "pues", "bueno", "ok",
                         "okay", "vale", "qué", "que", "cómo", "como", "perdón", "what", "sorry", "pardon", "huh",
                         "जी", "क्या", "हम्म", "हं", "अच्छा", "ठीक", "है", "हैं", "ओके", "सॉरी", "माफ", "कीजिए",
                         "हेलो", "हैलो", "अरे", "बोलिए"})
UNSURE = re.compile(r"\b(no (lo )?s[ée]|no sabemos|qui[ée]n sabe|creo|creemos|tal ?vez|quiz[áa]s?|a lo mejor|"
                    r"puede ser|m[áa]s o menos|no estoy segur[oa]|no me acuerdo|no recuerdo|dont know|do not know|"
                    r"dunno|not sure|no idea|maybe|i think|i guess|probably|perhaps|kind of|sort of|pata nahi|"
                    r"pata nahin|shayad)\b|"
                    # Devanagari's vowel signs aren't \w, so its words are told apart by spaces
                    r"(?<!\S)(पता नहीं|मालूम नहीं|नहीं पता|नहीं मालूम|शायद|लगता है|पक्का नहीं|क्या पता|याद नहीं)(?!\S)")
# Hindi puts the "no" late: "अलार्म नहीं है", "इनमें से कुछ नहीं". That's plain when "नहीं" says "nothing" (कुछ/कोई
# नहीं) or comes before an "is/are" (नहीं है/हैं), not as a tag at the end ("…हैं, नहीं?").
HINDI_NONE = re.compile(r"(?<!\S)(कुछ|कोई|किसी को)( भी)? नहीं(?!\S)")
COPULAS = frozenset({"है", "हैं", "था", "थे", "थी"})


NUMBERS = frozenset({"uno", "una", "dos", "tres", "cuatro", "cinco", "seis", "siete", "ocho", "nueve", "diez", "once",
                     "doce", "medio", "one", "two", "three", "four", "five", "six", "seven", "eight", "nine", "ten",
                     "eleven", "twelve", "half", "एक", "दो", "तीन", "चार", "पांच", "छह", "सात", "आठ", "नौ", "दस",
                     "ग्यारह", "बारह", "आधा", "साढे", "सवा", "पौने", "डेढ", "ढाई"})


def words_of(text: str) -> list[str]:
    """The words, as normal() leaves them, without punctuation or symbols ("it's" → "its"). Devanagari's vowel signs
    are marks, not letters, so they're kept by category: "\\w" would cut "नहीं" to "नह"."""
    text = normal(re.sub(r"['’]", "", text))
    return "".join(" " if unicodedata.category(c)[0] in "PS" else c for c in text).split()


@dataclass(frozen=True)
class Question:
    """One of the coach's questions that a yes or no answers."""

    fact: str  # what the answer sets (for the door: that its height is confirmed)
    yes: object  # the fact's value for a yes; None when a yes doesn't answer it
    no: object
    clearing: object  # the fact's value that takes a danger off the list: only a plain answer may set it
    words: frozenset[str] = frozenset()  # words that can come with a plain answer ("sí, ya está afuera")
    alone: dict = field(default_factory=dict)  # words that answer by themselves, and the value ("afuera": outdoors)

    def clears(self, value: object) -> bool:
        return value == self.clearing or isinstance(value, list) and self.clearing in value


OUTSIDE = Question("generator_location", "outdoors", "indoors", "outdoors",
                   frozenset({"ya", "está", "esta", "afuera", "al", "aire", "libre", "its", "it", "is", "now",
                              "already", "outside", "outdoors", "out", "बाहर", "है", "अब", "खुले", "खुली", "में",
                              "जगह", "पर", "घर", "से", "दूर", "ही", "रखा", "रख", "दिया"}),
                   alone={"afuera": "outdoors", "outside": "outdoors", "outdoors": "outdoors", "बाहर": "outdoors"})
QUESTIONS = {
    "measure-distance": OUTSIDE,  # until the generator is known to be outside; then only the photo is asked for
    "ask-moved-outside": OUTSIDE,
    "confirm-outside": OUTSIDE,  # after a door photo, before anyone said where the generator is
    "ask-exhaust": Question("exhaust_toward_house", None, None, "no", frozenset({  # "toward the house or away?"
        "hacia", "lejos", "la", "casa", "de", "ella", "apunta", "el", "escape", "toward", "towards", "away", "from",
        "the", "house", "it", "points", "exhaust", "घर", "की", "के", "से", "है", "धुआं", "निकलता", "जाता", "उसका"}),
        alone={"hacia": "yes", "toward": "yes", "towards": "yes", "lejos": "no", "away": "no", "तरफ": "yes",
               "ओर": "yes", "दूर": "no"}),
    "ask-co-alarm": Question("co_alarm", "yes", "no", "yes", frozenset({
        "tengo", "tenemos", "hay", "una", "uno", "un", "alarma", "detector", "funciona", "sirve", "con", "batería",
        "baterías", "pilas",
        "i", "we", "do", "have", "one", "it", "works", "a", "an", "alarm", "there", "is", "theres", "है", "हैं",
        "मेरे", "हमारे", "पास", "एक", "अलार्म", "आलार्म", "बैटरी", "वाला", "काम", "करता", "लगा", "हुआ", "चलता", "घर",
        "में"})),
    "ask-downed-lines": Question("downed_line", "yes", "no", "no", frozenset({
        "hay", "veo", "cable", "cables", "caído", "caídos", "cerca", "por", "aquí", "there", "are", "is", "any",
        "line", "lines", "wire", "wires", "i", "we", "see", "near", "nearby", "here", "है", "हैं", "तार", "बिजली",
        "के", "गिरे", "गिरा", "हुए", "हुआ", "कोई", "पास", "में", "यहां", "दिख", "रहे", "रहा", "घर", "भी"})),
    "ask-heat-and-cooking": Question("burning_indoors", None, ["none"], "none", frozenset({
        "de", "eso", "esos", "esas", "esto", "estos", "usamos", "uso", "adentro", "of", "those", "these", "that",
        "them", "we", "i", "use", "any", "inside", "indoors", "at", "all", "इनमें", "से", "कुछ", "कोई", "भी", "हम",
        "मैं", "अंदर", "घर", "में", "इस्तेमाल", "करते", "करती", "करता", "हैं", "है", "जलाते", "चलाते"})),
    "ask-door-height": Question("door_height_in", "regular", None, "regular", frozenset({
        "es", "una", "puerta", "normal", "regular", "estándar", "standard", "its", "it", "is", "a", "door", "है",
        "दरवाजा", "आम", "सामान्य", "नॉर्मल", "वाला", "एक", "स्टैंडर्ड"}),
        alone={"normal": "regular", "regular": "regular", "estándar": "regular", "standard": "regular",
               "नॉर्मल": "regular", "सामान्य": "regular", "आम": "regular", "स्टैंडर्ड": "regular"}),
    # After a door photo that didn't record its lens: "1×" reads as "1" once its symbol goes.
    "confirm-1x": Question("lens", True, False, True, frozenset({
        "estaba", "está", "esta", "en", "la", "cámara", "camara", "uno", "equis", "zoom", "normal", "it", "was",
        "its", "at", "on", "the", "camera", "one", "x", "ex", "times", "regular", "1", "1x", "कैमरा", "पर", "था",
        "थी", "है", "ही", "एक", "एक्स", "वन", "आम", "नॉर्मल", "जूम"}), alone={"1x": True}),
}


@dataclass(frozen=True)
class Answer:
    """How a reply answers one of the coach's questions."""

    lean: str | None  # "yes" or "no", or None when it doesn't lean either way
    plain: bool  # a plain answer: it may take a danger off the list
    bare: bool  # nothing else in it for the model to read
    unsure: bool = False  # "no sé", "creo que sí"
    value: object = None  # the fact's value, when the question's own words gave it ("lejos": "no")

    def of(self, question: Question) -> object:
        """The value this answer gives the question's fact, or None."""
        return self.value if self.value is not None else {"yes": question.yes, "no": question.no}.get(self.lean)


def rejoined(words: list[str], known: set[str]) -> list[str]:
    """The words with any pair MMS split in two ("ca sa") joined again, where together they make a known word."""
    out = []
    for word in words:
        if out and out[-1] not in known and word not in known and out[-1] + word in known:
            out[-1] += word
        else:
            out.append(word)
    return out


def read_answer(heard: str, question: Question) -> Answer | None:
    """How the reply answers the question, or None when it says something else (the model reads it)."""
    words = rejoined(words_of(heard), YES_WORDS | NO_WORDS | question.words | set(question.alone))
    if not words:
        return None
    if UNSURE.search(" ".join(words)):  # "creo que no" still leans, and may add a danger
        rest = words_of(UNSURE.sub(" ", " ".join(words)))
        yes, no = any(w in YES_WORDS or w == "si" for w in rest), any(w in NO_WORDS for w in rest)
        return Answer("yes" if yes and not no else "no" if no and not yes else None, plain=False,
                      bare=len(words) <= 4, unsure=True)
    if set(words) <= NON_ANSWERS:  # "se", "¿qué?", "ok"
        return Answer(None, plain=False, bare=True)
    others = [w for w in words if w not in YES_WORDS | MAYBE_YES | NO_WORDS | COURTESY]
    fits = all(w in question.words or w in question.alone for w in others)
    lead = next((i for i, w in enumerate(words) if w not in COURTESY), 0)  # "जी हाँ", "señora, sí"
    first, has_no = words[lead], any(w in NO_WORDS for w in words)
    if first in YES_WORDS | MAYBE_YES | NO_WORDS:
        if has_no and any(w in YES_WORDS | MAYBE_YES for w in words):
            return Answer(None, plain=False, bare=False)  # "sí, pero no funciona": the model reads it
        if first in NO_WORDS:
            return Answer("no", plain=fits, bare=fits)
        if first in MAYBE_YES and not (fits and (others or first == "si")):
            return Answer(None, plain=False, bare=False)  # "se fue la luz", "si lo muevo…"
        return Answer("yes", plain=fits, bare=fits)
    values = {question.alone[w] for w in others if w in question.alone}
    if fits and not has_no and len(values) == 1:  # "ya está afuera", "es normal", "lejos de la casa", "घर से दूर"
        return Answer(None, plain=True, bare=True, value=values.pop())
    if fits and has_no and not any(w in YES_WORDS | MAYBE_YES for w in words) and (
            HINDI_NONE.search(" ".join(words))
            or any(w in NO_WORDS and i + 1 < len(words) and words[i + 1] in COPULAS for i, w in enumerate(words))):
        return Answer("no", plain=True, bare=True)  # "अलार्म नहीं है", "इनमें से कुछ नहीं"
    return None


# The reply to a read-back ("Entendí que …, ¿es así?").
CONFIRM = Question("confirm", True, False, True, frozenset({"es", "así", "eso", "is", "it", "that", "thats", "right",
                                                            "सही", "है", "यह", "ये", "बिल्कुल"}),
                   alone={"así": True, "eso": True, "right": True, "सही": True})

# After a rating plate photo, the coach reads the plate back ("¿Es correcto?"). The answer is about the plate and
# sets no safety fact: without its own question, a "sí" there counted as the answer to the question before the photo
# ("yes, I have a carbon monoxide alarm").
PLATE_QUESTION = Advice("confirm-plate", Level.CHECK, ())
QUESTIONS["confirm-plate"] = Question("plate", True, False, None, frozenset({
    "es", "está", "esta", "bien", "así", "eso", "lo", "leyó", "it", "is", "its", "that", "thats", "right", "you",
    "read", "सही", "है", "पढा", "पढी", "आपने", "यह", "ये"}), alone={"así": True, "bien": True, "right": True,
                                                                  "सही": True})


# The overnight check-in asks three things again, whatever was said before, in this order: whether anyone feels sick,
# whether the generator is still outside, and the carbon monoxide alarm. The same strict reading applies: an answer
# that reassures counts only when it's plain, or once it's read back and confirmed.
CHECKIN = (Advice("checkin-symptoms", Level.CHECK, ("cdc-symptoms", "cpsc-sick")),
           Advice("checkin-outside", Level.CHECK, ("cdc-never-indoors", "cdc-distance")),
           Advice("checkin-co-alarm", Level.CHECK, ("cdc-alarm", "cpsc-alarm")))
CHECKIN_FACTS = {"checkin-symptoms": "symptoms", "checkin-outside": "location", "checkin-co-alarm": "co_alarm"}
QUESTIONS["checkin-symptoms"] = Question("symptoms", "yes", "no", "no", frozenset({
    "nadie", "ninguno", "tiene", "se", "siente", "mal", "dolor", "de", "cabeza", "mareo", "mareos", "aquí",
    "nobody", "one", "anyone", "has", "have", "is", "feels", "feel", "sick", "a", "headache", "dizzy", "weak", "here",
    "we", "किसी", "को", "कोई", "भी", "कुछ", "है", "हैं", "सिरदर्द", "सिर", "दर्द", "चक्कर", "कमजोरी", "यहां", "घर", "में"}),
    alone={"nadie": "no", "nobody": "no"})
QUESTIONS["checkin-outside"] = replace(OUTSIDE, words=OUTSIDE.words | {
    "todavía", "sigue", "ahí", "allí", "mismo", "lugar", "still", "there", "same", "place", "where", "was",
    "अभी", "भी", "वहीं", "वहां", "उसी", "जगह"})
QUESTIONS["checkin-co-alarm"] = replace(QUESTIONS["ask-co-alarm"], words=QUESTIONS["ask-co-alarm"].words | {
    "sigue", "funcionando", "todavía", "still", "working", "on", "its", "चालू", "कर", "रहा", "रही", "ठीक", "से"})


def key(advice: Advice) -> tuple:
    """A question with its variant ("is it outside?" and "now the photo" are both measure-distance)."""
    return advice.rule, tuple(sorted(advice.values.items()))


# The reassuring value of each fact: the one that takes a danger or a warning off the list, or answers one of the
# coach's questions the reassuring way. Read by the model, it's read back before it counts.
REASSURING = {"generator_location": "outdoors", "exhaust_toward_house": "no", "co_alarm": "yes", "downed_line": "no",
              "burning_indoors": "none", "symptoms": "no", "extreme_heat": "no", "extreme_cold": "no",
              "medical_needs": "no", "backfeeding": "no", "refuelling": "no"}
FIELDS = {"generator_location": "location"}  # Situation's name for a fact, where it differs


def clearing(situation: Situation, name: str, value: object) -> bool:
    """Whether stating this fact would take a danger off the list, or answer an open question (one the coach asks,
    now or later) the reassuring way."""
    if name not in REASSURING or REASSURING[name] not in (value if isinstance(value, list) else [value]):
        return False
    now = getattr(situation, FIELDS.get(name, name))
    if name == "generator_location":
        return now != "outdoors"
    if name == "burning_indoors":
        return now is None
    if name in ("exhaust_toward_house", "co_alarm", "downed_line"):  # the coach asks these while they're unknown
        return now != (REASSURING[name] == "yes")  # unknown, or known the other way
    return now is True  # symptoms, heat, cold and the rest: only an existing danger or warning matters


BAND_RULES = frozenset({"too-close", "borderline", "meets-guidance", "if-outside", "if-1x"})  # say the numbers
DOOR_QUESTION = Advice("ask-door-height", Level.CHECK, ())
ABOUT_THE_PHOTO = frozenset({"confirm-1x", "confirm-outside", "ask-moved-outside"})  # asked afresh for each new photo
# Questions the page also offers as two buttons, a yes and a no, while they're asked: MMS never heard the yes to "was
# the camera at 1×?" from synthetic voices (0 of 24, Nov 1). A tap is a plain answer.
TAPPED = frozenset({"confirm-1x"})
HEIGHTS_IN = (60.0, 120.0)  # door heights outside this range are mishearings


@dataclass
class Reply:
    text: str
    said: list[str]  # the rules said this turn
    question: str | None  # the rule whose question ends the reply
    heard: dict  # what was read from the person's words
    pending: bool = False  # the model still has to read this turn (``Conversation.finish``)


@dataclass
class Conversation:
    reader: Reader
    language: str = "es"
    situation: Situation = field(default_factory=Situation)
    said: set[str] = field(default_factory=set)
    asking: Advice | None = None  # the question the person is answering
    tries: dict = field(default_factory=dict)  # by key(): times asked again without an answer (2: left for later)
    waiting: str | None = None  # a turn quick() left for the model
    turn: list[str] = field(default_factory=list)  # what the quick part of this turn already said
    unanswered: str | None = None  # "unclear" or "unsure" when this turn's short reply didn't answer
    unconfirmed: dict = field(default_factory=dict)  # what the model read that would take a danger off the list
    door_in: float = LEAF_IN  # the door height measurements assume, until the person says otherwise
    door_checked: bool = False  # the person confirmed the door's height, or gave it
    lens_confirmed: bool = False  # the person said the camera was at 1× for a photo that didn't record its lens
    retake: bool = False  # this turn, the person said the camera wasn't at 1×: the photo is to be taken again
    plate_ok: bool | None = None  # the person's answer to the rating plate's read-back
    checkin: tuple[Advice, ...] = ()  # an overnight check-in's questions (made by check_in); empty otherwise

    @property
    def asked(self) -> str | None:
        return self.asking.rule if self.asking is not None else None

    def check_in(self) -> "Conversation":
        """A new conversation for the overnight check-in, carrying on from this one: the measurement and the other
        answers stay, while whether anyone feels sick, whether the generator is still outside, and the alarm are
        asked again. A door photo counts again only if the generator was outside when it was taken."""
        before = self.situation
        situation = replace(before, symptoms=None, alarm_sounding=None, location=None, co_alarm=None)
        if before.location != "outdoors":
            situation = replace(situation, measured_ft=None, lowest_ft=None, lens_assumed=False)
        outside = replace(CHECKIN[1], values={"measured": situation.measured_ft is not None})
        return Conversation(self.reader, language=self.language, situation=situation, door_in=self.door_in,
                            door_checked=self.door_checked, checkin=(CHECKIN[0], outside, CHECKIN[2]),
                            lens_confirmed=self.lens_confirmed and situation.measured_ft is not None)

    def opening(self) -> str:
        """The first thing the coach says: who it is, then the first question. A check-in starts with its own."""
        if self.checkin:
            self.asking = self.checkin[0]
            return f"{CHECKIN_HELLO[self.language]} {ask(self.asking, self.language)}"
        self.asking = assess(self.situation).headline
        return f"{HELLO[self.language]} {ask(self.asking, self.language)}"

    def quick(self, heard: str, door: tuple[float, float] | None = None, lens_assumed: bool = False,
              tapped: Answer | None = None) -> Reply:
        """The part of the reply that needs no model, said at once: the emergency line for symptom words, a danger
        for a dangerous place, or the whole reply to a short answer. ``pending`` says whether the model still has to
        read the turn (call ``finish``). ``door`` is a door measurement, (feet, lowest feet), taken from where the
        generator stands; until the generator is known to be outside, it counts only if it is. ``lens_assumed``
        says the photo didn't record its lens: the measurement then counts only once the person says it was 1×.
        ``tapped`` is the answer from a tap on one of the page's buttons (``tap``), in place of reading ``heard``."""
        self.turn, self.unanswered, self.retake = [], None, False
        sounding, sick = says_alarm(heard, self.asked), says_symptoms(heard)
        if sounding or sick:  # the alarm is sounding, or someone may be poisoned: only the emergency, now
            s = self.situation
            self.situation = replace(s, alarm_sounding=True if sounding else s.alarm_sounding,
                                     symptoms=True if sick else s.symptoms)
            return self._emergency({name: True for name, said in (("alarm sounding", sounding),
                                                                   ("symptom words", sick)) if said})
        place = quick_place(heard, self.asked)
        facts = {"generator_location": place} if place else {}
        complete = bool(place) and len(words_of(heard)) <= 4
        question = self._question()
        answer = tapped or (read_answer(heard, question) if question is not None else None)
        if answer is not None:
            value = answer.of(question)
            if value is not None and (answer.plain or not question.clears(value)):
                for name, stated in self._answered(question, value).items():
                    facts.setdefault(name, stated)  # a place named in the reply comes first
            elif answer.bare:
                self.unanswered = ("unsure" if answer.unsure else None if answer.lean and value is None
                                   else "unclear")
            complete = complete or answer.bare
        elif question is not None and not place and self._misheard(heard):
            self.unanswered, complete = "unclear", True  # "sceg" for "sí, tengo": asked again, not guessed at
        if question is CONFIRM and not (answer is not None and answer.bare and answer.lean is None):
            self.unconfirmed = {}  # answered, or not taken up: either way the read-back is done
        self._merge(facts)
        if door is not None:
            self.situation = replace(self.situation, measured_ft=door[0], lowest_ft=door[1], lens_assumed=lens_assumed)
            self.said -= BAND_RULES  # a new measurement is said with its own numbers
            self.lens_confirmed = False
            # A photo is a new measurement, not a reply. What it raises is asked afresh (the person may have moved the
            # generator), and whatever was being asked hasn't gone unanswered.
            self.tries = {k: n for k, n in self.tries.items() if k[0] not in ABOUT_THE_PHOTO}
            if not heard.strip():
                self.asking = None
        if complete or not heard.strip():
            return self._compose(facts, {})
        self.waiting = heard
        result = assess(self.situation)
        urgent = [a for a in result.advice if a.level == Level.EMERGENCY]  # in an emergency, only the emergency
        urgent = urgent or [a for a in result.advice if a.level == Level.DANGER and a.rule not in self.said]
        self.said |= {a.rule for a in urgent}
        self.turn = [a.rule for a in urgent]
        return Reply(text=" ".join(say(a, self.language) for a in urgent), said=[a.rule for a in urgent],
                     question=self.asked, heard=facts, pending=True)

    def finish(self) -> Reply:
        """The rest of a turn quick() left pending: the model reads it, and the reply goes on from what was said.
        What the model read that would take a danger off the list is read back, and counts only on a plain yes; if
        the person sounded unsure, it's dropped."""
        heard, self.waiting = self.waiting or "", None
        try:
            reading = self.reader.ask_json(self.prompt(heard), SCHEMA) if heard.strip() else {}
        except RuntimeError as error:  # the model failed, or couldn't be reached (vlm.ReadFailed): nothing was read
            logging.getLogger("aftermath").warning("reading the turn failed: %s", error)
            reading, self.unanswered = {}, "unclear"
        if made_up(reading, heard):
            reading, self.unanswered = {}, "unclear"
        if self.language in ("es", "en") and reading.get("language") in ("es", "en"):
            self.language = reading["language"]
        unsure = bool(UNSURE.search(" ".join(words_of(heard))))
        facts, held = {}, {}
        for name, value in facts_of(reading).items():
            if name == "door_height_in":
                height = self._height(value)
                if height is not None and height < self.door_in:
                    facts[name] = height  # a shorter door brings the generator closer: no need to ask
                elif height is not None and not unsure and not (height == self.door_in and self.door_checked):
                    held[name] = height
            elif clearing(self.situation, name, value) or self._reassures(name, value):
                if not unsure:
                    held[name] = value
            else:
                facts[name] = value
        self._merge(facts)
        if held:
            self.unconfirmed = held
            self.tries.pop(key(self._confirm()), None)
        return self._compose(reading, reading)

    def prompt(self, heard: str) -> str:
        """What the model is asked about a turn: the question just asked, and what was heard."""
        asked = ask(self.asking, self.language) if self.asking is not None else ""
        # Spanish and English follow the person; Hindi, often mixed with English words, stays Hindi.
        answer_in = "their language" if self.language in ("es", "en") else LANGUAGE_NAMES[self.language]
        return PROMPT.format(asked=asked, heard=heard, language=answer_in)

    def reply(self, heard: str, door: tuple[float, float] | None = None, lens_assumed: bool = False) -> Reply:
        """A whole turn at once: the quick part, then the model's, as one reply."""
        first = self.quick(heard, door, lens_assumed)
        if not first.pending:
            return first
        rest = self.finish()
        return Reply(text=" ".join(part for part in (first.text, rest.text) if part), said=first.said + rest.said,
                     question=rest.question, heard={**first.heard, **rest.heard})

    def tap(self, rule: str, yes: bool) -> Reply:
        """A tap on one of the page's two buttons for the question being asked (one of ``TAPPED``): a plain yes or
        no, as if said plainly, with nothing else in it for the model to read."""
        if rule not in TAPPED or self.asked != rule or self.waiting is not None:
            raise ValueError(f"{rule} isn't being asked")
        return self.quick("", tapped=Answer("yes" if yes else "no", plain=True, bare=True))

    def plate_read_back(self, readable: bool) -> None:
        """The coach has just read a rating plate back ("¿Es correcto?"), or said it couldn't read one. Either way the
        next reply is about the plate, never an answer to the question asked before the photo."""
        self.asking, self.plate_ok = (PLATE_QUESTION if readable else None), None
        self.tries.pop(key(PLATE_QUESTION), None)

    def photo_refused(self) -> None:
        """A door photo couldn't be measured, and the coach asked for another. A "sí" now may only mean "all right",
        so the question asked before the photo is set aside; the next reply asks it again."""
        self.asking = None

    def _reassures(self, name: str, value: object) -> bool:
        """At a check-in, the answers it asks for count as reassuring, and so only when plain or confirmed: a
        summary for the family must not rest on a guess."""
        return bool(self.checkin) and name in ("symptoms", "generator_location", "co_alarm") and \
            REASSURING.get(name) == value

    def _answered(self, question: Question, value: object) -> dict:
        """The facts a short answer states."""
        if question is CONFIRM:
            return self.unconfirmed if value else {}
        if question.fact == "door_height_in":
            self.door_checked = True
            return {}
        if question.fact == "plate":
            self.plate_ok = value
            return {}
        if question.fact == "lens":  # at 1×: the measurement counts; not: it doesn't, and the photo is taken again
            s = self.situation
            self.situation = replace(s, lens_assumed=False) if value else replace(
                s, measured_ft=None, lowest_ft=None, lens_assumed=False)
            self.lens_confirmed, self.retake = bool(value), not value
            return {}
        return {question.fact: value}

    @staticmethod
    def _misheard(heard: str) -> bool:
        """A word or two that answer nothing, and no number: most likely MMS mishearing a short answer."""
        words = words_of(heard)
        return 0 < len(words) <= 2 and not any(w.isdigit() or w in NUMBERS for w in words)

    def _merge(self, facts: dict) -> None:
        """The facts stated this turn, merged in. A door photo taken while the generator was inside or against the
        house measured from there, so once it's moved out the door is photographed again from where it stands."""
        before = self.situation.location
        self.situation = merge(self.situation, facts)
        if before in ENCLOSED | AGAINST_HOUSE and self.situation.location == "outdoors":
            self.situation = replace(self.situation, measured_ft=None, lowest_ft=None, lens_assumed=False)
            self.lens_confirmed = False
        if "door_height_in" in facts:
            self.door_height(facts["door_height_in"])

    def _question(self) -> Question | None:
        """The question being answered, when a yes or no can answer it."""
        if self.asking is None or self.asking.rule == "measure-distance" and self.asking.values.get("outdoors"):
            return None
        return CONFIRM if self.asking.rule == "confirm" else QUESTIONS.get(self.asking.rule)

    def _confirm(self) -> Advice:
        """The read-back of what's unconfirmed, as a question."""
        held = tuple(sorted((k, tuple(v) if isinstance(v, list) else v) for k, v in self.unconfirmed.items()))
        return Advice("confirm", Level.CHECK, (), {"facts": held})

    @staticmethod
    def _height(value: object) -> float | None:
        """A door height the model read, in inches, if it's a door's."""
        try:
            height = float(value)
        except (TypeError, ValueError):
            return None
        return height if HEIGHTS_IN[0] <= height <= HEIGHTS_IN[1] else None

    def door_height(self, inches: float) -> None:
        """The door's height, from the person: a measurement taken with another height is scaled to it (the
        distance is proportional to the height assumed), and said again."""
        s = self.situation
        if s.measured_ft is not None and inches != self.door_in:
            scale = inches / self.door_in
            self.situation = replace(s, measured_ft=s.measured_ft * scale, lowest_ft=s.lowest_ft * scale)
            self.said -= BAND_RULES
        self.door_in, self.door_checked = inches, True

    def _next_question(self, placement: str, advice: list[Advice]) -> tuple[Advice | None, bool]:
        """The next question, and whether it's asked again because the last reply didn't answer it. One asked again
        without an answer is left for later (a read-back is dropped)."""
        if self.checkin:  # its own questions, in order, then whether a generator found inside has been moved
            checks = [q for q in self.checkin if getattr(self.situation, CHECKIN_FACTS[q.rule]) is None]
            checks += [a for a in advice if a.rule == "ask-moved-outside"]
        else:
            checks = [a for a in advice if a.level == Level.CHECK]
            if (self.situation.lowest_ft is not None and not self.door_checked
                    and placement in ("borderline", "meets the guidance")):
                checks.insert(0, DOOR_QUESTION)  # the verdict rests on the door's height: confirm it first
        if self.unconfirmed:
            checks.insert(0, self._confirm())
        if self.asking == PLATE_QUESTION and self.unanswered == "unclear":
            checks.insert(0, PLATE_QUESTION)  # the plate's read-back wasn't answered clearly: asked once more
        for question in checks:
            tries = self.tries.get(key(question), 0)
            if question == self.asking and tries < 2:
                tries = self.tries[key(question)] = tries + 1
            if tries < 2:
                return question, question == self.asking
            if question.rule == "confirm":
                self.unconfirmed = {}
        return None, False

    def _later(self, question: Advice, advice: list[Advice]) -> None:
        """Leave a question for later, and for a read-back, the questions its facts would have answered."""
        self.tries[key(question)] = 2
        if question.rule == "confirm":
            facts = {name for name, _ in question.values["facts"]}
            for check in [DOOR_QUESTION, *advice]:
                if check.rule in QUESTIONS and QUESTIONS[check.rule].fact in facts:
                    self.tries[key(check)] = 2
            self.unconfirmed = {}

    def _emergency(self, heard: dict) -> Reply:
        """Only the emergency line, and, if the model read that nobody feels sick any more, that read back."""
        emergency = [a for a in assess(self.situation).advice if a.level == Level.EMERGENCY and a.rule not in self.turn]
        parts = [say(a, self.language) for a in emergency]
        if self.unconfirmed:
            question, again = self._next_question("", [])
            if question is not None:
                parts.append(ask(question, self.language, again))
            self.asking = question
        return Reply(text=" ".join(parts), said=[a.rule for a in emergency], question=self.asked, heard=heard)

    def _compose(self, heard: dict, reading: dict) -> Reply:
        """The reply once the turn is understood: dangers and warnings not said before (starting with where the
        generator is), one standing line on a quiet turn, the answer to their own question, then one question. A
        check-in says only dangers, then its next question or its closing line."""
        result = assess(self.situation)
        if any(a.level == Level.EMERGENCY for a in result.advice):
            return self._emergency(heard)
        parts, said, prefix = [], [], []
        if self.unanswered == "unclear":
            prefix = [NOT_CAUGHT[self.language]]
        elif self.unanswered == "unsure" and self.asking is not None:
            prefix = [LATER[self.language]]
            self._later(self.asking, result.advice)
        elif self.asking == PLATE_QUESTION and self.plate_ok is False:
            prefix = [PLATE_WRONG[self.language]]
        elif self.retake:
            prefix = [LENS_RETAKE[self.language]]
        for advice in result.advice:
            if advice.rule in self.said:
                continue
            if advice.level == Level.DANGER or (advice.rule == "get-co-alarm" if self.checkin else (
                    advice.level == Level.WARNING or advice is result.headline and advice.level == Level.INFO)):
                parts.append(say(advice, self.language))
                said.append(advice.rule)
        question, again = self._next_question(result.placement, result.advice)
        standing = next((a for a in result.advice if a.level == Level.INFO and a.rule not in self.said | set(said)),
                        None)
        reading_back = question is not None and question.rule == "confirm"
        if standing is not None and not (parts or prefix or self.turn or reading_back or self.checkin):
            parts.append(say(standing, self.language))
            said.append(standing.rule)
        answer = (reading.get("answer") or "").strip()
        if reading.get("question") and answer and not SAFE.search(normal(answer)):
            parts.append(answer)
        if question is not None:
            parts.append(ask(question, self.language, again))
        elif self.checkin:
            parts.append(CHECKIN_DONE[self.language])
        elif not parts:
            parts.append(DONE[self.language])  # nothing left to say or ask
        self.said |= set(said)
        self.asking = question
        return Reply(text=" ".join(prefix + parts), said=said, question=self.asked, heard=heard)
