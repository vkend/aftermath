"""The official guidance Aftermath's rules rest on, quoted word for word, with where each quote comes from.

Every piece of advice the rules give cites one or more of these. ``checked`` says how each quote was confirmed. Most
quotes are English; where an agency published the rule in Hindi, that source is cited too, in Hindi, and the Hindi
line follows it. Where none exists (CDC has no Hindi), the Hindi line is this app's own, citing the English.
Where agencies disagree on the generator distance, the rules follow all of them at once: outdoors only, more than
20 feet from doors, windows and vents (CDC), and farther is better (NIST found 15 feet from open windows wasn't far
enough, and said "perhaps as much as 25 feet" may be needed). The downed-line distance comes from utilities, not a
federal agency, and is labelled that way.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    id: str
    publisher: str
    title: str
    url: str
    quote: str  # verbatim; "…" marks a cut
    checked: str  # how and when the quote was confirmed
    language: str = "en"  # the quote's language


CDC_CO = "https://www.cdc.gov/carbon-monoxide/about/index.html"
CPSC_ALERT = "https://www.cpsc.gov/s3fs-public/5123_SafetyAlert_PortableGenerators_102021.pdf"
CPSC_2026 = ("https://www.cpsc.gov/Newsroom/News-Releases/2026/"
             "CPSC-Warns-of-Generator-Carbon-Monoxide-and-Fire-Hazards-Ahead-of-Hurricane-Season")
READY = "https://www.ready.gov/power-outages"
CDC_PAGE = "live page (last reviewed Oct 26 2026), checked Oct 29 2026"
CPSC_PDF = "Publication 5123 (Oct 2021), read Oct 29 2026"
READY_PAGE = "live page (updated Jun 4 2026), checked Oct 29 2026"
RECHECKED = "live source, checked Oct 29 2026 (meta-max)"
READY_HI = "https://www.ready.gov/sites/default/files/2024-08/"
READY_HI_CHECKED = ("text of the graphic in Ready.gov's Hindi collection (updated Aug 23 2024), read Oct 29 2026 "
                    "(aftermath-max)")
CDC_ES = 'https://www.cdc.gov/carbon-monoxide/es/about/informacion-basica-sobre-la-intoxicacion-por-monoxido-de-carbono.html'
CPSC_ES_PDF = "https://cpsc.gov/s3fs-public/5123s.pdf"
CPSC_ES_2024 = ("https://www.cpsc.gov/es/Newsroom/News-Releases/2024/"
                "CPSC-Issues-Life-Saving-Tips-to-Millions-in-the-Path-of-Hurricane-Helene")
READY_ES = "https://www.ready.gov/es/apagones"
ES_CDC = "live page (header \"26 DE OCT. DEL 2026\"), checked Oct 29 2026 (meta-max)"
ES_CPSC_PDF = "Spanish Pub. 5123s (April 2007, older than the English 5123), read Oct 29 2026 (meta-max)"
ES_CPSC_2024 = "live page, checked Oct 29 2026 (meta-max)"
ES_READY = "live page (last updated Mar 5 2026), checked Oct 29 2026 (meta-max)"
NIST_RELEASE = "https://www.nist.gov/news-events/news/2009/10/safer-emergencies-give-your-power-generator-some-space"
CDC_OUTAGE = "https://www.cdc.gov/natural-disasters/response/what-to-do-protect-yourself-during-a-power-outage.html"
CDC_OUTAGE_ES = "https://www.cdc.gov/natural-disasters/es/response/que-hacer-para-protegerse-durante-un-apagon.html"
OUTAGE_PAGE = "live page (last reviewed Aug 26 2026), checked Oct 29 2026 (aftermath-max)"
CPSC_CO_FACTS = "https://www.cpsc.gov/safety-education/safety-guides/carbon-monoxide/carbon-monoxide-fact-sheet"
CPSC_CO_CENTER = "https://www.cpsc.gov/Safety-Education/Safety-Education-Centers/Carbon-Monoxide-Information-Center"
CPSC_CO_CENTER_ES = ("https://www.cpsc.gov/es/Safety-Education/Safety-Education-Centers/"
                     "Carbon-Monoxide-Information-Center")
NO_DATE = "live page (no date shown), checked Oct 29 2026 (meta-max, aftermath-max)"
OUTAGE_ES_PAGE = "live page (last reviewed \"26 DE AGO. DEL 2026\"), checked Oct 29 2026 (aftermath-max)"
UTILITY = "; utility guidance, not a federal agency"

SOURCES = {s.id: s for s in (
    Source("cdc-distance", "CDC", "Carbon Monoxide Poisoning Basics", CDC_CO,
           "Operate your generator outdoors more than 20 feet from windows, doors, and vents to avoid CO poisoning.",
           CDC_PAGE),
    Source("cdc-never-indoors", "CDC", "Carbon Monoxide Poisoning Basics", CDC_CO,
           "Never use a generator inside your home or garage, even if doors and windows are open.", CDC_PAGE),
    Source("cpsc-2026", "CPSC", "News release, May 27 2026", CPSC_2026,
           "Operate generators outdoors only, at least 20 feet from homes and buildings, with exhaust directed away "
           "from windows, doors and vents.", "live page, checked Oct 29 2026"),
    Source("cpsc-indoors", "CPSC", "Portable Generator Hazards, Safety Alert", CPSC_ALERT,
           "NEVER use a generator inside homes, garages, crawlspaces, sheds, or similar areas, even when using fans or "
           "opening doors and windows for ventilation. Deadly levels of carbon monoxide can quickly build up in these "
           "areas and can linger for hours, even after the generator has shut off.", CPSC_PDF),
    Source("cpsc-exhaust", "CPSC", "Portable Generator Hazards, Safety Alert", CPSC_ALERT,
           "Locate the unit outdoors and far from doors, windows, and vents that could allow CO to come indoors and "
           "point the exhaust away from any nearby buildings.", CPSC_PDF),
    Source("cpsc-sick", "CPSC", "Portable Generator Hazards, Safety Alert", CPSC_ALERT,
           "If you start to feel sick, dizzy, or weak while using a generator, get to fresh air RIGHT AWAY. DO NOT "
           "DELAY. The CO from generators can rapidly kill you.", CPSC_PDF),
    Source("cpsc-alarm", "CPSC", "Portable Generator Hazards, Safety Alert", CPSC_ALERT,
           "Install battery-operated CO alarms or plug-in CO alarms with battery back-up in your home, according to "
           "the manufacturer's instructions. … Test batteries monthly.", CPSC_PDF),
    Source("cpsc-refuel", "CPSC", "Portable Generator Hazards, Safety Alert", CPSC_ALERT,
           "Before refueling the generator, turn it off and let it cool down. Gasoline spilled on hot engine parts "
           "could ignite.", CPSC_PDF),
    Source("cpsc-backfeed", "CPSC", "Portable Generator Hazards, Safety Alert", CPSC_ALERT,
           "NEVER try to power the house wiring by plugging the generator into a wall outlet, a practice known as "
           "“backfeeding.” This is extremely dangerous and presents an electrocution risk to utility workers and "
           "neighbors served by the same utility transformer.", CPSC_PDF),
    Source("cpsc-cords", "CPSC", "Portable Generator Hazards, Safety Alert", CPSC_ALERT,
           "Connect appliances to the generator using heavy-duty extension cords that are specifically designed for "
           "outdoor use.", CPSC_PDF),
    Source("cpsc-wet", "CPSC", "Portable Generator Hazards, Safety Alert", CPSC_ALERT,
           "Operate the generator under an open, canopy-like structure on a dry surface where water cannot reach it "
           "or puddle or drain under it.", CPSC_PDF),
    Source("cdc-alarm", "CDC", "Carbon Monoxide Poisoning Basics", CDC_CO,
           "Install battery-operated or battery back-up CO detectors near every sleeping area in your home.",
           CDC_PAGE),
    Source("cdc-symptoms", "CDC", "Carbon Monoxide Poisoning Basics", CDC_CO,
           "The most common symptoms of CO poisoning are headache, dizziness, weakness, upset stomach, vomiting, chest "
           "pain, and confusion.", CDC_PAGE),
    Source("cdc-asleep", "CDC", "Carbon Monoxide Poisoning Basics", CDC_CO,
           "People who are sleeping, drunk, or under the influence of other substances can die from CO poisoning "
           "before they have symptoms.", CDC_PAGE),
    Source("cdc-poison-control", "CDC", "What to Do to Protect Yourself During a Power Outage", CDC_OUTAGE,
           "If someone shows signs of having carbon monoxide poisoning, call 911 or your local Poison Control Center "
           "at 1-800-222-1222 or consult a health care professional right away.", OUTAGE_PAGE),
    Source("cpsc-alarm-sounds", "CPSC", "Carbon Monoxide Fact Sheet", CPSC_CO_FACTS,
           "Never ignore an alarming CO alarm! It is warning you of a potentially deadly hazard. If the alarm signal "
           "sounds do not try to find the source of the CO: Immediately move outside to fresh air. Call your emergency "
           "services, fire department, or 911.", NO_DATE + "; the last two sentences are a list on the page"),
    Source("cpsc-alarm-after", "CPSC", "Carbon Monoxide Fact Sheet", CPSC_CO_FACTS,
           "After calling 911, do a head count to check that all persons are accounted for. DO NOT reenter the "
           "premises until the emergency services responders have given you permission.", NO_DATE),
    Source("cpsc-suspect-co", "CPSC", "Carbon Monoxide (information center)", CPSC_CO_CENTER,
           "If you suspect CO poisoning, get outside to fresh air immediately, and then call 911.", NO_DATE),
    Source("cdc-other-sources", "CDC", "Carbon Monoxide Poisoning Basics", CDC_CO,
           "Never heat your house with a gas oven. Never burn charcoal indoors. Never use a portable gas camp stove "
           "indoors. Never run your car or truck inside a garage that is attached to a house, even with the garage "
           "door open.", CDC_PAGE),
    Source("cpsc-charcoal", "CPSC", "Generators and Engine-Driven Tools",
           "https://www.cpsc.gov/Safety-Education/Safety-Guides/Carbon-Monoxide-Home/"
           "Generators-and-Engine-Driven-Tools",
           "Also, never burn charcoal grills indoors, even with ventilation.", RECHECKED),
    Source("cpsc-2023-shutoff", "CPSC", "Generators and OEDT CO Poisoning Fatalities report (2023)",
           "https://www.cpsc.gov/s3fs-public/Generators-and-OEDT-CO-Poisoning-Fatalities-Report-2023-final.pdf",
           "The exhaust pointed towards one of the closed exterior doors; the generator did not shut off and ran "
           "until the gas tank was empty.",
           RECHECKED + "; printed pp. 6, 26 and 36. September 2021: a generator with a CO shutoff, advertised as "
           "certified to the voluntary standard ANSI/PGMA G300-2018, ran outdoors under eaves with soffit vents into "
           "the attic, the windows and doors closed; a 54-year-old woman and her two children died"),
    Source("nist-15ft", "NIST", "For Safer Emergencies, Give Your Power Generator Some Space (news release, Oct 6 "
           "2009, updated Feb 3 2025)", NIST_RELEASE,
           "a generator position 15 feet away from open windows was not far enough to prevent carbon monoxide entry "
           "into the house.", RECHECKED),
    Source("nist-25ft", "NIST", "For Safer Emergencies, Give Your Power Generator Some Space (news release, Oct 6 "
           "2009, updated Feb 3 2025)", NIST_RELEASE,
           "users may need to keep generators farther from the house than previously believed—perhaps as much as 25 "
           "feet.", RECHECKED),
    Source("nist-tn1637", "NIST", "Technical Note 1637 (2009)", "https://doi.org/10.6028/NIST.TN.1637",
           "For the house modeled in this study, a generator positioned 4.6 m (15 feet) away from open windows may not "
           "be far enough to limit CO entry into the house. … When the distance is increased to 7.6 m (25 ft), CO is "
           "well diluted outside the recirculation zone", RECHECKED + "; PDF pp. 4 and 15"),
    Source("nist-30ft", "NIST", "Technical Note 1666 (2010, for CDC)",
           "https://cdc.gov/carbon-monoxide/media/pdfs/2024/09/NIST_PhaseII_TN1666.pdf",
           "A distance of 9.1 m (30 ft) (the next closest distance modeled) generally resulted in low CO entry indoors, "
           "especially with the exhaust pointing away from the house which caused the maximum CO at the house "
           "envelope to be only 17 % of that when the exhaust is pointing towards the house.",
           RECHECKED + "; PDF p. 4. The 17 % is at the house's outside walls (the envelope), so the spoken line "
           "doesn't give a figure"),
    Source("ready-hi-generator", "Ready.gov (FEMA)", "Generator Safety – Hindi", READY_HI +
           "ready-gov-generator-safety_Hindi-100.jpg",
           "घर के अंदर कभी भी जनरेटर का इस्तेमाल न करें, हमेशा जनरेटर को बाहर और घरों और गराज से दूर रखें।",
           READY_HI_CHECKED + "; it shows 20 फीट between the generator and the house, and opens with \"सुरक्षित "
           "रहें\", left out here because the coach never calls anything safe", language="hi"),
    Source("ready-hi-prepare", "Ready.gov (FEMA)", "Prepare Your Home – Hindi", READY_HI +
           "ready-gov_prepare-your-home_hindi.jpg",
           "कार्बन मोनोक्साइड पॉइज़निंग से बचने के लिए हमेशा बाहर जनरेटर चलाएँ।", READY_HI_CHECKED, language="hi"),
    Source("ready-distance", "Ready.gov (FEMA)", "Power Outages", READY,
           "Generators and fuel should always be used outdoors and at least 20 feet away from windows, doors and "
           "attached garages.", READY_PAGE),
    Source("ready-alarm", "Ready.gov (FEMA)", "Power Outages", READY,
           "Install carbon monoxide detectors with battery backup in central locations on every level of your home.",
           READY_PAGE),
    Source("ready-heat-cold", "Ready.gov (FEMA)", "Power Outages", READY,
           "Go to a community location with power if heat or cold is extreme.", READY_PAGE),
    Source("ready-medical", "Ready.gov (FEMA)", "Power Outages", READY,
           "Have alternate plans for refrigerating medicines or using power-dependent medical devices.", READY_PAGE),
    Source("ready-food", "Ready.gov (FEMA)", "Power Outages", READY,
           "The refrigerator will keep food cold for about four hours. A full freezer will keep the temperature for "
           "about 48 hours.", READY_PAGE),
    Source("utility-lines-35", "CenterPoint Energy", "Electric safety", "https://www.centerpointenergy.com/en-us/"
           "safety/electric", "Stay at least 35 feet away from the wire", RECHECKED + UTILITY),
    Source("utility-lines-40", "Kentucky electric co-ops", "Stay clear of downed power lines (Kentucky Living, Feb 10 "
           "2021)", "https://www.kentuckyliving.com/news/stay-clear-of-downed-power-lines",
           "always stay clear at least 40 feet as the ground around the line may be energized up to 35 feet.",
           RECHECKED + UTILITY),
    Source("utility-lines-teco", "Tampa Electric", "Storm Center, questions and answers",
           "https://www.tampaelectric.com/stormcenter",
           "If you encounter a downed power line, always assume it is energized, move … away (at least 30 feet) and "
           "immediately call 911, then Tampa Electric at 877-588-1010.",
           RECHECKED + UTILITY + "; the cut is the word \"safe\", which the coach never uses; the rules keep the "
           "stricter 35 feet"),
    # The agencies' own Spanish, quoted by the Spanish lines (collected live Oct 29 2026 for meta-max).
    Source("cdc-es-distance", "CDC", "Información básica sobre la intoxicación por monóxido de carbono", CDC_ES,
           'Use su generador afuera, a más de 20 pies de las ventanas, puertas o rejillas de ventilación para evitar la intoxicación por monóxido de carbono.', ES_CDC, language="es"),
    Source("cdc-es-alarm", "CDC", "Información básica sobre la intoxicación por monóxido de carbono", CDC_ES,
           'Instale detectores de monóxido de carbono que funcionen con pilas o tengan pilas de reserva cerca de todas las áreas para dormir en su casa.', ES_CDC, language="es"),
    Source("cdc-es-symptoms", "CDC", "Información básica sobre la intoxicación por monóxido de carbono", CDC_ES,
           'Los síntomas más comunes del monóxido de carbono son dolor de cabeza, mareos, debilidad, malestar estomacal, vómitos, dolor de pecho y confusión.', ES_CDC, language="es"),
    Source("cdc-es-asleep", "CDC", "Información básica sobre la intoxicación por monóxido de carbono", CDC_ES,
           'Las personas que estén durmiendo, que estén borrachas o bajo los efectos de otras sustancias pueden morir por la intoxicación por monóxido de carbono antes de presentar síntomas.', ES_CDC, language="es"),
    Source("cdc-es-poison-control", "CDC", "Qué hacer para protegerse durante un apagón", CDC_OUTAGE_ES,
           "Si alguien tiene signos de intoxicación por monóxido de carbono, llame al 911 o al centro de control de "
           "intoxicaciones y envenenamientos local al 1-800-222-1222, o consulte a un profesional de atención médica "
           "inmediatamente.", OUTAGE_ES_PAGE, language="es"),
    Source("cpsc-es-suspect-co", "CPSC", "Monóxido de carbono (centro de información)", CPSC_CO_CENTER_ES,
           "Si sospecha intoxicación, salga inmediatamente a tomar aire fresco y luego llame al 911.", NO_DATE,
           language="es"),
    Source("cdc-es-oven", "CDC", "Información básica sobre la intoxicación por monóxido de carbono", CDC_ES,
           'Nunca use un horno de gas para calentar su casa.', ES_CDC, language="es"),
    Source("cdc-es-charcoal", "CDC", "Información básica sobre la intoxicación por monóxido de carbono", CDC_ES,
           'Nunca queme carbón adentro.', ES_CDC, language="es"),
    Source("cdc-es-stove", "CDC", "Información básica sobre la intoxicación por monóxido de carbono", CDC_ES,
           'Nunca use adentro una estufa o cocina de gas portátil como las que se usan para acampar.', ES_CDC, language="es"),
    Source("cdc-es-car", "CDC", "Información básica sobre la intoxicación por monóxido de carbono", CDC_ES,
           'Nunca deje encendido el motor de su auto o camioneta dentro de un garaje que esté pegado a la casa, ni siquiera con la puerta del garaje abierta.', ES_CDC, language="es"),
    Source("cpsc-es-indoors", "CPSC", "Los Peligros de los Generadores Portátiles (Pub. 5123s)", CPSC_ES_PDF,
           'NUNCA utilice un generador dentro de hogares, garajes, espacios entre plantas, cobertizos, o áreas similares, aún cuando utilice abanicos o abra las puertas y ventanas para ventilación.', ES_CPSC_PDF, language="es"),
    Source("cpsc-es-sick", "CPSC", "Los Peligros de los Generadores Portátiles (Pub. 5123s)", CPSC_ES_PDF,
           'Si comienza a sentirse enfermo, mareado o débil mientras usa un generador, salga a tomar aire fresco INMEDIATAMENTE. NO ESPERE.', ES_CPSC_PDF, language="es"),
    Source("cpsc-es-refuel", "CPSC", "Los Peligros de los Generadores Portátiles (Pub. 5123s)", CPSC_ES_PDF,
           'Apague el generador y deje que se enfríe antes de volver a llenar el tanque de combustible.', ES_CPSC_PDF, language="es"),
    Source("cpsc-es-backfeed", "CPSC", "Los Peligros de los Generadores Portátiles (Pub. 5123s)", CPSC_ES_PDF,
           'NUNCA trate de traer energía a su hogar conectando un generador directamente a un tomacorriente.', ES_CPSC_PDF, language="es"),
    Source("cpsc-es-cords", "CPSC", "Los Peligros de los Generadores Portátiles (Pub. 5123s)", CPSC_ES_PDF,
           'Conecte los aparatos eléctricos al generador usando alargadores de alta resistencia diseñados para uso en exteriores.', ES_CPSC_PDF, language="es"),
    Source("cpsc-es-wet", "CPSC", "Los Peligros de los Generadores Portátiles (Pub. 5123s)", CPSC_ES_PDF,
           'Opere el generador en una superficie seca y bajo una estructura tipo toldo que no esté encerrada donde el agua no pueda alcanzarlo o correr debajo de éste.', ES_CPSC_PDF, language="es"),
    Source("cpsc-es-exhaust", "CPSC", "Comunicado de prensa, 26 de septiembre de 2024 (huracán Helene)", CPSC_ES_2024,
           'Utilice los generadores portátiles únicamente en el exterior, a una distancia mínima de 20 pies de la casa, y dirija el escape del generador en sentido contrario a la casa y a cualquier otro edificio en el que alguien pudiera entrar.', ES_CPSC_2024, language="es"),
    Source("cpsc-es-porch", "CPSC", "Comunicado de prensa, 26 de septiembre de 2024 (huracán Helene)", CPSC_ES_2024,
           'No utilice un generador en una galería exterior o en un garaje abierto porque estos lugares están demasiado cerca de la vivienda.', ES_CPSC_2024, language="es"),
    Source("cpsc-es-grill", "CPSC", "Comunicado de prensa, 26 de septiembre de 2024 (huracán Helene)", CPSC_ES_2024,
           'No cocine en una parrilla a carbón en un garaje, incluso con la puerta del garaje abierta.', ES_CPSC_2024, language="es"),
    Source("ready-es-distance", "Ready.gov (FEMA)", "Apagones", READY_ES, 'Los generadores y el combustible siempre deben usarse al aire libre y al menos a 20 pies (6 metros) de distancia de ventanas, puertas y garajes adjuntos.', ES_READY, language="es"),
    Source("ready-es-heat-cold", "Ready.gov (FEMA)", "Apagones", READY_ES, 'Vaya a un lugar de la comunidad que tenga electricidad si el calor o el frío es extremo.', ES_READY, language="es"),
)}
