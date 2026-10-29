"""Text as an MMS-TTS voice can say it.

Each MMS-TTS voice knows only the characters it was trained on (its vocab.json). None of them has punctuation; the
Hindi one has no "/" or "।" and only some digits; and numbers read from digits come out mumbled (on Oct 29, the
Hindi "6 मीटर / 20 फीट"). So before a voice speaks:

- numbers become words ("बीस फीट", "veintiún pies"), and an emergency or phone number is read digit by digit
  ("नौ एक एक"), as are model numbers;
- a metre figure in brackets, "(6.1 m)", is left to the screen, and so, in Hindi, is a word in Latin letters (a
  brand on the rating plate), which the Hindi voice can't say;
- symbols become words ("/" is "या", "o" or "or"), and quotation marks go;
- the text is cut at its punctuation into chunks, spoken with a short pause after each.

Any character a voice doesn't know is then dropped. A test runs every line the coach can say through this and checks
that nothing is.
"""

import re
import unicodedata

# The characters of each voice: the keys of its vocab.json (facebook/mms-tts-spa, -eng and -hin, at the revisions
# speech.py pins). A test checks them against the files when the models are on this machine.
VOCAB = {
    "es": frozenset(" 0123456789_abcdefghijklmnopqrstuvxyz\xe1\xe9\xed\xf1\xf3\xfa\xfc—"),
    "en": frozenset(" '-0123456_abcdefghijklmnopqrstuvwxyz–"),
    "hi": frozenset(" '-012348_`ँंःअआइईउऊएऐऑओऔ"
                    "कखगघचछजझञटठडढणतथ"
                    "दधनपफबभमयरलवशषसह"
                    "़ािीुूृॅेैॉोौ्‍"),
}
SENTENCE_PAUSE, CLAUSE_PAUSE = 0.25, 0.15  # seconds of silence after a sentence, and after a comma or the like

ES_UNITS = ("cero uno dos tres cuatro cinco seis siete ocho nueve diez once doce trece catorce quince dieciséis "
            "diecisiete dieciocho diecinueve veinte veintiuno veintidós veintitrés veinticuatro veinticinco "
            "veintiséis veintisiete veintiocho veintinueve").split()
ES_TENS = {3: "treinta", 4: "cuarenta", 5: "cincuenta", 6: "sesenta", 7: "setenta", 8: "ochenta", 9: "noventa"}
ES_HUNDREDS = {1: "ciento", 2: "doscientos", 3: "trescientos", 4: "cuatrocientos", 5: "quinientos",
               6: "seiscientos", 7: "setecientos", 8: "ochocientos", 9: "novecientos"}
ES_MASCULINE = frozenset({"pie", "pies", "metro", "metros", "vatio", "vatios", "voltio", "voltios", "grado", "grados",
                          "amperio", "amperios", "minuto", "minutos", "día", "días", "mil"})
ES_FEMININE = frozenset({"pulgada", "pulgadas", "hora", "horas", "persona", "personas", "vez", "veces"})
EN_UNITS = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
            "seventeen eighteen nineteen").split()
EN_TENS = {2: "twenty", 3: "thirty", 4: "forty", 5: "fifty", 6: "sixty", 7: "seventy", 8: "eighty", 9: "ninety"}
# Hindi has a word of its own for every number up to 100.
HI_NUMBERS = ("शून्य एक दो तीन चार पाँच छह सात आठ नौ दस ग्यारह बारह तेरह चौदह पंद्रह सोलह सत्रह अठारह उन्नीस बीस "
              "इक्कीस बाईस तेईस चौबीस पच्चीस छब्बीस सत्ताईस अट्ठाईस उनतीस तीस इकतीस बत्तीस तैंतीस चौंतीस पैंतीस "
              "छत्तीस सैंतीस अड़तीस उनतालीस चालीस इकतालीस बयालीस तैंतालीस चवालीस पैंतालीस छियालीस सैंतालीस "
              "अड़तालीस उनचास पचास इक्यावन बावन तिरपन चौवन पचपन छप्पन सत्तावन अट्ठावन उनसठ साठ इकसठ बासठ तिरसठ "
              "चौंसठ पैंसठ छियासठ सड़सठ अड़सठ उनहत्तर सत्तर इकहत्तर बहत्तर तिहत्तर चौहत्तर पचहत्तर छिहत्तर "
              "सतहत्तर अठहत्तर उन्यासी अस्सी इक्यासी बयासी तिरासी चौरासी पचासी छियासी सत्तासी अट्ठासी नवासी "
              "नब्बे इक्यानबे बानबे तिरानबे चौरानबे पचानबे छियानबे सत्तानबे अट्ठानबे निन्यानबे सौ").split()
DIGITS = {"es": ES_UNITS[:10], "en": EN_UNITS[:10], "hi": HI_NUMBERS[:10]}
POINT = {"es": "punto", "en": "point", "hi": "दशमलव"}  # US Spanish says "punto" for a decimal point
SYMBOLS = {  # said as words
    "es": {"/": " o ", "%": " por ciento", "°": " grados", "×": " equis", "&": " y "},
    "en": {"/": " or ", "%": " percent", "°": " degrees", "×": " ex", "&": " and "},
    "hi": {"/": " या ", "%": " प्रतिशत", "°": " डिग्री", "×": " एक्स", "&": " और "},
}


def spanish(n: int) -> str:
    if n < 30:
        return ES_UNITS[n]
    if n < 100:
        tens, unit = divmod(n, 10)
        return ES_TENS[tens] + (f" y {ES_UNITS[unit]}" if unit else "")
    if n == 100:
        return "cien"
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return ES_HUNDREDS[hundreds] + (f" {spanish(rest)}" if rest else "")
    thousands, rest = divmod(n, 1000)
    head = "mil" if thousands == 1 else f"{agree(spanish(thousands), 'mil')} mil"
    return head + (f" {spanish(rest)}" if rest else "")


def agree(words: str, noun: str) -> str:
    """A Spanish number before its noun: "uno" is "un" before a masculine one, "una" before a feminine one."""
    if not words.endswith("uno"):
        return words
    if noun in ES_FEMININE:
        return words[:-3] + "una"
    if noun in ES_MASCULINE:
        return words[:-3] + ("ún" if words.endswith("veintiuno") else "un")
    return words


def english(n: int) -> str:
    if n < 20:
        return EN_UNITS[n]
    if n < 100:
        tens, unit = divmod(n, 10)
        return EN_TENS[tens] + (f" {EN_UNITS[unit]}" if unit else "")
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return f"{EN_UNITS[hundreds]} hundred" + (f" {english(rest)}" if rest else "")
    thousands, rest = divmod(n, 1000)
    return f"{english(thousands)} thousand" + (f" {english(rest)}" if rest else "")


def hindi(n: int) -> str:
    if n <= 100:
        return HI_NUMBERS[n]
    if n < 1000:
        hundreds, rest = divmod(n, 100)
        return f"{HI_NUMBERS[hundreds]} सौ" + (f" {HI_NUMBERS[rest]}" if rest else "")
    if n < 100_000:
        thousands, rest = divmod(n, 1000)
        return f"{hindi(thousands)} हज़ार" + (f" {hindi(rest)}" if rest else "")
    lakhs, rest = divmod(n, 100_000)
    return f"{hindi(lakhs)} लाख" + (f" {hindi(rest)}" if rest else "")


WORDS = {"es": spanish, "en": english, "hi": hindi}


def number_words(n: int, language: str) -> str:
    """A whole number in words, up to a million (beyond that, digit by digit)."""
    return WORDS[language](n) if 0 <= n < 1_000_000 else digit_words(str(n), language)


def digit_words(digits: str, language: str) -> str:
    return " ".join(DIGITS[language][int(d)] for d in digits)


METRES = re.compile(r"\s*\(\s*\d+(?:[.,]\d+)?\s*m\s*\)")
MIXED = re.compile(r"\b(?=[^\W_]*\d)(?=[^\W_]*[^\W\d_])[^\W_]+\b")  # letters and digits in one word: a model number
NUMBER = re.compile(r"\d+(?:-\d+)+|\d{1,3}(?:,\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?")


def spoken(text: str, language: str) -> str:
    """The text with its numbers and symbols in words, and its metre figures in brackets left out."""
    text = METRES.sub("", unicodedata.normalize("NFC", text))
    text = MIXED.sub(lambda m: " ".join(digit_words(part, language) if part.isdigit() else part
                                        for part in re.findall(r"\d+|\D+", m.group())), text)

    def number(match: re.Match) -> str:
        token = match.group()
        if "-" in token:  # a phone number, group by group
            return ", ".join(digit_words(group, language) for group in token.split("-"))
        if token == "911" or ("," not in token and "." not in token and len(token) >= 5):
            return digit_words(token, language)
        whole, _, fraction = token.replace(",", "").partition(".")
        words = number_words(int(whole), language)
        if fraction:
            return f"{words} {POINT[language]} {digit_words(fraction, language)}"
        if language == "es":
            following = re.match(r"\s*([^\W\d_]+)", text[match.end():])
            words = agree(words, following.group(1).lower() if following else "")
        return words

    text = NUMBER.sub(number, text)
    for symbol, words in SYMBOLS[language].items():
        text = text.replace(symbol, words)
    if language == "hi":
        text = re.sub(r"\b[A-Za-z]+\b", "", text)
    return text


BREAK = re.compile(r"([.?!।]+|[,;:—–…()\[\]]+)")
QUOTES = frozenset("¿¡«»“”\"")


def prepared(chunk: str, language: str) -> str:
    """A chunk in lower case, with hyphens as spaces and the letters the voice lacks replaced."""
    chunk = chunk.lower().replace("’", "'").replace("-", " ")
    if language == "es":
        chunk = chunk.replace("w", "u")  # the Spanish voice has no "w" ("Westinghouse")
    if language != "en":
        chunk = chunk.replace("'", " ")
    return chunk


def clean(chunk: str, language: str) -> str:
    """A chunk as the voice gets it: only characters it knows."""
    return " ".join("".join(c for c in prepared(chunk, language) if c in VOCAB[language] or c.isspace()).split())


def chunks(text: str, language: str) -> list[tuple[str, float]]:
    """What the voice says, in chunks cut at the punctuation, each with the seconds of silence after it."""
    out: list[list] = []
    parts = BREAK.split(spoken(text, language))
    for piece, mark in zip(parts[::2], [*parts[1::2], ""]):
        pause = SENTENCE_PAUSE if re.search(r"[.?!।]", mark) else CLAUSE_PAUSE if mark else 0.0
        said = clean(piece, language)
        if said:
            out.append([said, pause])
        elif out:
            out[-1][1] = max(out[-1][1], pause)
    return [(said, pause) for said, pause in out]


def lost(text: str, language: str) -> set[str]:
    """What the voice would miss of this text: characters it doesn't know, other than punctuation and quotation
    marks, and any digit left (a digit should have become a word). Nothing, for anything the coach says."""
    said = prepared(BREAK.sub(" ", spoken(text, language)), language)
    return ({c for c in said if c not in VOCAB[language] and not c.isspace() and c not in QUOTES}
            | {c for c in said if c.isdigit()})
