"""What the rules say, in English, Hindi and Spanish. The rules decide; this only words their decisions.

Each rule's wording follows its cited sources. Distances are given in feet with metres beside them. Nothing here
calls a placement "safe" ("seguro", "सुरक्षित"): a test checks every phrase in every language. The Hindi lines are
in everyday Hindi with "आप", reviewed by a native speaker (tests/test_reviewed_hindi.py pins them); where an agency
has published the rule in Hindi (Ready.gov's "घर के अंदर कभी भी जनरेटर का इस्तेमाल न करें"), the line follows it.
Spanish keeps to the agencies' own Spanish: a line that states a rule quotes CDC, CPSC or Ready.gov word for word (a
test checks it), and only the measurement, the situation and the downed-line distance, which no agency gives in
Spanish, are this app's words.
"""

import math
import re

from .rules import Advice

FOOT = 0.3048

PLACES = {
    "en": {"indoors": "inside the house", "garage": "in the garage", "basement": "in the basement",
           "crawlspace": "in a crawlspace", "shed": "in a shed", "porch": "on the porch",
           "under_eaves": "under the eaves", "carport": "in the carport", "doorway": "in a doorway",
           "window": "by a window"},
    "es": {"indoors": "dentro de la casa", "garage": "en el garaje", "basement": "en el sótano",
           "crawlspace": "debajo de la casa", "shed": "en un cobertizo", "porch": "en una galería exterior",
           "under_eaves": "bajo el alero", "carport": "en un garaje abierto", "doorway": "en una puerta",
           "window": "junto a una ventana"},
    "hi": {"indoors": "घर के अंदर", "garage": "गैराज में", "basement": "बेसमेंट में", "crawlspace": "घर के नीचे की खाली जगह में",
           "shed": "शेड में", "porch": "बरामदे में", "under_eaves": "छज्जे के नीचे", "carport": "कार शेड में",
           "doorway": "दरवाज़े पर", "window": "खिड़की के पास"},
}

PHRASES = {
    "alarm-sounding": {
        "en": "Your carbon monoxide alarm is warning you of a danger that can kill. Don't look for the cause: "
              "everyone go outside into fresh air now, then call 911. Count that everyone is out, and don't go back "
              "in until emergency responders say so.",
        "es": "Su detector de monóxido de carbono le está avisando de un peligro que puede matar. No busque la "
              "causa. Si sospecha intoxicación, salga inmediatamente a tomar aire fresco y luego llame al 911. "
              "Cuenten que todos hayan salido, y no vuelvan a entrar hasta que los servicios de emergencia lo "
              "permitan.",
        "hi": "आपका कार्बन मोनोऑक्साइड अलार्म ऐसे ख़तरे की चेतावनी दे रहा है जो जान ले सकता है। कारण ढूँढने की कोशिश न "
              "करें: सब लोग अभी बाहर खुली हवा में जाएँ, फिर 911 पर फ़ोन करें। गिन लें कि सब बाहर आ गए हैं, और जब तक "
              "इमरजेंसी टीम इजाज़त न दे, अंदर वापस न जाएँ।",
    },
    "fresh-air-now": {
        "en": "Get everyone into fresh air right now and call 911. A headache, dizziness, weakness or nausea near "
              "a generator can be carbon monoxide poisoning, and it can kill quickly.",
        "es": "Si comienza a sentirse enfermo, mareado o débil mientras usa un generador, salga a tomar aire fresco "
              "INMEDIATAMENTE. NO ESPERE. Que salgan todos al aire libre y llamen al 911.",
        "hi": "सब लोग अभी तुरंत खुली हवा में जाएँ, देर न करें, और 911 पर फ़ोन करें। जनरेटर के पास सिरदर्द, चक्कर, "
              "कमज़ोरी या जी मिचलाना कार्बन मोनोऑक्साइड पॉइज़निंग की निशानी हो सकती है, और यह जल्दी जान ले सकता है।",
    },
    "move-outside-now": {
        "en": "A generator must never run {place}, even with the doors and windows open: carbon monoxide builds up "
              "fast and stays for hours after it stops. If it's running there now, everyone should get out into "
              "fresh air. Run it only outdoors, more than {twenty} from doors, windows and vents.",
        "es": "NUNCA utilice un generador dentro de hogares, garajes, espacios entre plantas, cobertizos, o áreas "
              "similares, aún cuando utilice abanicos o abra las puertas y ventanas para ventilación. Si está "
              "funcionando ahí ahora, que todos salgan al aire libre. Use su generador afuera, a más de 20 pies de "
              "las ventanas, puertas o rejillas de ventilación para evitar la intoxicación por monóxido de carbono.",
        "hi": "{place} कभी भी जनरेटर का इस्तेमाल न करें, दरवाज़े और खिड़कियाँ खुली हों तब भी: कार्बन मोनोऑक्साइड "
              "जल्दी भर जाती है और जनरेटर बंद होने के बाद भी घंटों बनी रहती है। अगर वह अभी वहाँ चल रहा है, तो सब लोग "
              "खुली हवा में निकल जाएँ। हमेशा जनरेटर को बाहर रखें, दरवाज़ों, खिड़कियों और रोशनदानों से {twenty} से "
              "ज़्यादा दूर।",
    },
    "away-from-openings": {
        "en": "Running {place}, the generator is too close to the house: carbon monoxide can drift in through "
              "doors, windows and vents. Move it out into the open, more than {twenty} from any door, window or "
              "vent, with the exhaust pointing away.",
        "es": "Funcionando {place}, el generador está demasiado cerca de la casa. No utilice un generador en una "
              "galería exterior o en un garaje abierto porque estos lugares están demasiado cerca de la vivienda. "
              "Utilice los generadores portátiles únicamente en el exterior, a una distancia mínima de 20 pies de la "
              "casa, y dirija el escape del generador en sentido contrario a la casa y a cualquier otro edificio en "
              "el que alguien pudiera entrar.",
        "hi": "{place} चल रहा जनरेटर घर के बहुत पास है: कार्बन मोनोऑक्साइड दरवाज़ों, खिड़कियों और रोशनदानों से अंदर आ "
              "सकती है। उसे खुली जगह में ले जाएँ, किसी भी दरवाज़े, खिड़की या रोशनदान से {twenty} से ज़्यादा दूर, और "
              "उसका धुआँ घर से दूर की तरफ़ रखें।",
    },
    "too-close": {
        "en": "The generator is about {feet} from the door, and at least {lowest} allowing for measuring error. "
              "That's too close: move it to more than {twenty} from any door, window or vent. Farther is better: "
              "NIST found that {fifteen} from open windows wasn't far enough, and that as much as {twentyfive} may "
              "be needed.",
        "es": "El generador está a unos {feet} de la puerta, y a por lo menos {lowest} contando el error de medición. "
              "Está demasiado cerca. Use su generador afuera, a más de 20 pies de las ventanas, puertas o rejillas de "
              "ventilación para evitar la intoxicación por monóxido de carbono.",
        "hi": "जनरेटर दरवाज़े से लगभग {feet} दूर है, और नापने में होने वाली गलती गिनकर कम से कम {lowest}। यह बहुत पास "
              "है: उसे किसी भी दरवाज़े, खिड़की या रोशनदान से {twenty} से ज़्यादा दूर ले जाएँ। जितना दूर, उतना अच्छा: "
              "निस्ट ने पाया कि खुली खिड़कियों से {fifteen} की दूरी काफ़ी नहीं थी, और {twentyfive} तक की ज़रूरत पड़ "
              "सकती है।",
    },
    "borderline": {
        "en": "The generator is about {feet} from the door, and at least {lowest} allowing for measuring error. "
              "That's borderline: move it farther, past {twentyfive} if you can. In NIST's studies, little carbon "
              "monoxide got indoors with the generator {thirty} away.",
        "es": "El generador está a unos {feet} de la puerta, y a por lo menos {lowest} contando el error de medición. "
              "Está en el límite: muévalo más lejos. Use su generador afuera, a más de 20 pies de las ventanas, "
              "puertas o rejillas de ventilación para evitar la intoxicación por monóxido de carbono.",
        "hi": "जनरेटर दरवाज़े से लगभग {feet} दूर है, और नापने में होने वाली गलती गिनकर कम से कम {lowest}। यह सीमा पर "
              "है: हो सके तो उसे और दूर ले जाएँ, {twentyfive} से भी आगे। निस्ट के अध्ययनों में, जनरेटर {thirty} दूर "
              "होने पर घर के अंदर बहुत कम कार्बन मोनोऑक्साइड पहुँची।",
    },
    "meets-guidance": {
        "en": "The generator is about {feet} from the door, and at least {lowest} allowing for measuring error. "
              "That meets the CDC's guidance of more than {twenty}. Farther is still better, and check the windows "
              "and vents too, not only this door.",
        "es": "El generador está a unos {feet} de la puerta, y a por lo menos {lowest} contando el error de medición. "
              "Eso cumple la recomendación de los CDC. Use su generador afuera, a más de 20 pies de las ventanas, "
              "puertas o rejillas de ventilación para evitar la intoxicación por monóxido de carbono. Aun así, más "
              "lejos es mejor; revise también las ventanas y rejillas de ventilación, no solo esta puerta.",
        "hi": "जनरेटर दरवाज़े से लगभग {feet} दूर है, और नापने में होने वाली गलती गिनकर कम से कम {lowest}। यह सीडीसी "
              "की सलाह के मुताबिक है, जो {twenty} से ज़्यादा दूरी कहती है। फिर भी जितना दूर, उतना अच्छा; और सिर्फ़ इस "
              "दरवाज़े से नहीं, खिड़कियों और रोशनदानों से भी दूरी देखें।",
    },
    "if-outside": {
        "en": "From where you took the photo, the door is about {feet} away, and at least {lowest} allowing for "
              "measuring error. {if_outside}",
        "es": "Desde donde tomó la foto, la puerta está a unos {feet}, y a por lo menos {lowest} contando el error "
              "de medición. {if_outside}",
        "hi": "जहाँ से आपने फ़ोटो ली, वहाँ से दरवाज़ा लगभग {feet} दूर है, और नापने में होने वाली गलती गिनकर कम से कम "
              "{lowest}। {if_outside}",
    },
    "confirm-outside": {
        "en": "Is the generator outside, out in the open, where you took the photo?",
        "es": "¿El generador está afuera, al aire libre, donde tomó la foto?",
        "hi": "क्या जनरेटर बाहर, खुली जगह में है, वहीं जहाँ से आपने फ़ोटो ली?",
    },
    "if-1x": {  # a door photo that didn't record its lens, measured as if at 1×
        "en": "This photo doesn't say which lens took it. If the camera was at 1×, the door is about {feet} away, "
              "and at least {lowest} allowing for measuring error.",
        "es": "Esta foto no dice con qué lente se tomó. Si la cámara estaba en 1×, la puerta está a unos {feet}, y "
              "a por lo menos {lowest} contando el error de medición.",
        "hi": "इस फ़ोटो में यह जानकारी नहीं है कि वह किस लेंस से ली गई। अगर कैमरा 1× पर था, तो दरवाज़ा लगभग "
              "{feet} दूर है, और नापने में होने वाली गलती गिनकर कम से कम {lowest}।",
    },
    "confirm-1x": {
        "en": "Was the camera at 1×, its normal zoom, when you took the photo?",
        "es": "¿La cámara estaba en 1×, su zoom normal, cuando tomó la foto?",
        "hi": "क्या फ़ोटो लेते समय कैमरा 1× पर था, यानी आम ज़ूम पर?",
    },
    "measure-distance": {
        "en": "Is the generator outside? If it is, let's check how far it is from the nearest door: stand by the "
              "generator and take a photo of the door.",
        "es": "¿El generador está afuera? Si es así, veamos qué tan lejos está de la puerta más cercana: párese "
              "junto al generador y tómele una foto a la puerta.",
        "hi": "क्या जनरेटर बाहर है? अगर हाँ, तो देखते हैं कि वह सबसे पास वाले दरवाज़े से कितनी दूर है: जनरेटर के पास "
              "खड़े होकर दरवाज़े की फ़ोटो लीजिए।",
    },
    "no-charcoal-grill": {
        "en": "Never burn charcoal indoors, even with the windows open. A grill brought inside is a common cause "
              "of carbon monoxide poisoning after storms.",
        "es": "Nunca queme carbón adentro. No cocine en una parrilla a carbón en un garaje, incluso con la puerta del "
              "garaje abierta.",
        "hi": "घर के अंदर कभी कोयला न जलाएँ, खिड़कियाँ खुली हों तब भी। तूफ़ान के बाद अंदर लाई गई अंगीठी या ग्रिल "
              "कार्बन मोनोऑक्साइड के ज़हर की एक आम वजह है।",
    },
    "no-gas-oven": {
        "en": "Never heat your home with a gas oven.",
        "es": "Nunca use un horno de gas para calentar su casa.",
        "hi": "घर को गर्म करने के लिए कभी गैस का ओवन न चलाएँ।",
    },
    "no-camp-stove": {
        "en": "Never use a portable gas camp stove indoors.",
        "es": "Nunca use adentro una estufa o cocina de gas portátil como las que se usan para acampar.",
        "hi": "घर के अंदर कभी पोर्टेबल गैस वाला कैंप स्टोव न जलाएँ।",
    },
    "no-car-in-garage": {
        "en": "Never run a car or truck in a garage attached to the house, even with the garage door open.",
        "es": "Nunca deje encendido el motor de su auto o camioneta dentro de un garaje que esté pegado a la casa, ni "
              "siquiera con la puerta del garaje abierta.",
        "hi": "घर से जुड़े गैराज में कभी गाड़ी या ट्रक चालू न छोड़ें, गैराज का दरवाज़ा खुला हो तब भी।",
    },
    "no-backfeeding": {
        "en": "Don't plug the generator into a wall outlet to power the house: that \"backfeeding\" can "
              "electrocute utility workers and neighbors. Plug appliances into the generator with heavy-duty "
              "outdoor extension cords instead.",
        "es": "NUNCA trate de traer energía a su hogar conectando un generador directamente a un tomacorriente. "
              "Conecte los aparatos eléctricos al generador usando alargadores de alta resistencia diseñados para uso "
              "en exteriores.",
        "hi": "घर में बिजली देने के लिए जनरेटर को दीवार के सॉकेट में न लगाएँ: इससे बिजली कंपनी के कर्मचारियों और "
              "पड़ोसियों को करंट लग सकता है। इसके बजाय, बाहर के लिए बनी मोटी एक्सटेंशन तारों से सामान को सीधे जनरेटर "
              "में लगाएँ।",
    },
    "stay-away-from-lines": {
        "en": "Stay at least {feet} from any fallen power line and keep others away. Treat every wire as live, and "
              "call 911 or the power company.",
        "es": "Manténgase por lo menos a {feet} de cualquier cable de luz caído y no deje que otros se acerquen. "
              "Trate todo cable como si tuviera corriente, y llame al 911 o a la compañía de luz.",
        "hi": "गिरे हुए किसी भी बिजली के तार से कम से कम {feet} दूर रहें, और दूसरों को भी पास न जाने दें। हर तार में "
              "करंट मानकर चलें, और 911 या बिजली कंपनी को फ़ोन करें।",
    },
    "turn-exhaust": {
        "en": "Point the generator's exhaust away from the house. In NIST's studies, pointing it away greatly cut "
              "the carbon monoxide reaching the house.",
        "es": "Utilice los generadores portátiles únicamente en el exterior, a una distancia mínima de 20 pies de la "
              "casa, y dirija el escape del generador en sentido contrario a la casa y a cualquier otro edificio en "
              "el que alguien pudiera entrar.",
        "hi": "जनरेटर का धुआँ घर से दूर की तरफ़ करें। निस्ट के अध्ययनों में, धुआँ घर से दूर करने पर घर तक पहुँचने "
              "वाली कार्बन मोनोऑक्साइड बहुत कम हो गई।",
    },
    "get-co-alarm": {
        "en": "Get a carbon monoxide alarm that runs on batteries (or has a battery backup) and put it near where "
              "people sleep. Carbon monoxide has no smell: the alarm is how you'd know.",
        "es": "Instale detectores de monóxido de carbono que funcionen con pilas o tengan pilas de reserva cerca de "
              "todas las áreas para dormir en su casa. El monóxido de carbono no tiene olor: el detector es la forma "
              "de saberlo.",
        "hi": "बैटरी से चलने वाला (या बैटरी बैकअप वाला) कार्बन मोनोऑक्साइड अलार्म लीजिए, और उसे वहाँ लगाइए जहाँ लोग "
              "सोते हैं। कार्बन मोनोऑक्साइड की कोई गंध नहीं होती: अलार्म से ही पता चलता है।",
    },
    "go-where-there-is-power": {
        "en": "If it's {weather}, go to a community location with power, such as a {center}. Ask local officials "
              "which ones are open.",
        "es": "Vaya a un lugar de la comunidad que tenga electricidad si el calor o el frío es extremo. Pregunte a "
              "las autoridades locales cuáles están abiertos.",
        "hi": "अगर {weather}, तो किसी ऐसी सार्वजनिक जगह जाएँ जहाँ बिजली हो, जैसे {center}। स्थानीय अधिकारियों से "
              "पूछें कि कौन-सी जगहें खुली हैं।",
    },
    "medical-plan": {
        "en": "Make a plan for medicines that need the fridge and for any medical device that needs power: ask "
              "your pharmacy, your doctor or your local emergency office.",
        "es": "Haga un plan para las medicinas que necesitan refrigerador y para cualquier aparato médico que "
              "necesite luz: pregunte en su farmacia, a su médico o a la oficina local de emergencias.",
        "hi": "फ्रिज में रखी जाने वाली दवाओं और बिजली से चलने वाले किसी भी मेडिकल उपकरण के लिए पहले से इंतज़ाम सोचें: "
              "अपनी दवा की दुकान, अपने डॉक्टर या स्थानीय आपातकालीन दफ़्तर से पूछें।",
    },
    "cool-before-refuel": {
        "en": "Before refuelling, turn the generator off and let it cool down: fuel spilled on a hot engine can "
              "catch fire.",
        "es": "Apague el generador y deje que se enfríe antes de volver a llenar el tanque de combustible.",
        "hi": "पेट्रोल डालने से पहले जनरेटर बंद करें और उसे ठंडा होने दें: गर्म इंजन पर गिरा पेट्रोल आग पकड़ सकता है।",
    },
    "ask-moved-outside": {
        "en": "Is the generator outside now, out in the open, away from the house?{note}",
        "es": "¿El generador ya está afuera, al aire libre y lejos de la casa?{note}",
        "hi": "क्या जनरेटर अब बाहर है, खुली जगह में, घर से दूर?{note}",
    },
    "ask-exhaust": {
        "en": "Which way does the generator's exhaust point: toward the house, or away from it?",
        "es": "¿Hacia dónde apunta el escape del generador: hacia la casa o lejos de ella?",
        "hi": "जनरेटर का धुआँ किस तरफ़ निकलता है: घर की तरफ़, या घर से दूर?",
    },
    "ask-co-alarm": {
        "en": "Do you have a working carbon monoxide alarm with a battery?",
        "es": "¿Tiene un detector de monóxido de carbono que funcione con pilas?",
        "hi": "क्या आपके पास बैटरी वाला कार्बन मोनोऑक्साइड अलार्म है जो काम करता हो?",
    },
    "ask-heat-and-cooking": {
        "en": "What are you using to cook or to keep warm? Grills, camp stoves, gas ovens and cars make carbon "
              "monoxide too.",
        "es": "¿Qué está usando para cocinar o para calentarse? Las parrillas de carbón, las estufas de acampar, los "
              "hornos de gas y los carros también producen monóxido de carbono.",
        "hi": "खाना पकाने या गर्मी के लिए आप क्या इस्तेमाल कर रहे हैं? अंगीठी, सिगड़ी, कोयले की ग्रिल, कैंप स्टोव, "
              "गैस ओवन और गाड़ियाँ भी कार्बन मोनोऑक्साइड बनाती हैं।",
    },
    "ask-downed-lines": {
        "en": "Are there any fallen power lines near your home?",
        "es": "¿Hay cables de luz caídos cerca de su casa?",
        "hi": "क्या आपके घर के पास बिजली के तार गिरे हुए हैं?",
    },
    "test-co-alarm": {
        "en": "Test the carbon monoxide alarm's battery every month.",
        "es": "Pruebe las pilas del detector de monóxido de carbono cada mes.",
        "hi": "कार्बन मोनोऑक्साइड अलार्म की बैटरी हर महीने जाँचें।",
    },
    "dry-and-outdoors": {
        "en": "In the rain, keep the generator outdoors under an open canopy on a dry surface, never inside or in "
              "the garage.",
        "es": "Opere el generador en una superficie seca y bajo una estructura tipo toldo que no esté encerrada donde "
              "el agua no pueda alcanzarlo o correr debajo de éste.",
        "hi": "बारिश में जनरेटर को बाहर ही रखें, किसी खुले छप्पर के नीचे, सूखी जगह पर; कभी अंदर या गैराज में नहीं।",
    },
    "shutoff-is-not-distance": {
        "en": "A carbon monoxide shutoff helps, but it doesn't replace distance. In 2021 a generator with a shutoff, "
              "running outdoors under the eaves with its exhaust toward a door, didn't shut off, and three people "
              "died. Keep it more than {twenty} away all the same.",
        "es": "El apagado automático por monóxido de carbono ayuda, pero no reemplaza la distancia. En 2021, un "
              "generador con ese apagado, funcionando afuera bajo el alero con el escape hacia una puerta, no se "
              "apagó, y murieron tres personas. Aun así, manténgalo a más de {twenty}.",
        "hi": "कार्बन मोनोऑक्साइड होने पर अपने आप बंद होने वाला सिस्टम मदद करता है, लेकिन दूरी की जगह नहीं ले सकता। "
              "2021 में ऐसा एक जनरेटर बाहर छज्जे के नीचे चल रहा था, उसका धुआँ एक दरवाज़े की तरफ़ था; वह बंद नहीं हुआ, "
              "और तीन लोगों की मौत हो गई। फिर भी उसे {twenty} से ज़्यादा दूर रखें।",
    },
    "symptoms-line": {
        "en": "If anyone gets a headache or feels dizzy, weak or sick to their stomach, get everyone into fresh "
              "air and call 911. You can also call Poison Control at 1-800-222-1222. People who are asleep can be "
              "poisoned before they feel anything.",
        "es": "Los síntomas más comunes del monóxido de carbono son dolor de cabeza, mareos, debilidad, malestar "
              "estomacal, vómitos, dolor de pecho y confusión. Si comienza a sentirse enfermo, mareado o débil "
              "mientras usa un generador, salga a tomar aire fresco INMEDIATAMENTE. NO ESPERE. Si alguien tiene "
              "signos de intoxicación por monóxido de carbono, llame al 911 o al centro de control de intoxicaciones "
              "y envenenamientos local al 1-800-222-1222, o consulte a un profesional de atención médica "
              "inmediatamente. Las personas que estén durmiendo, que estén borrachas o bajo los efectos de otras "
              "sustancias pueden morir por la intoxicación por monóxido de carbono antes de presentar síntomas.",
        "hi": "अगर किसी को सिरदर्द हो, या चक्कर, कमज़ोरी या जी मिचलाना लगे, तो सबको खुली हवा में ले जाएँ और 911 पर "
              "फ़ोन करें। आप पॉइज़न कंट्रोल को भी 1-800-222-1222 पर फ़ोन कर सकते हैं। सोते हुए लोगों पर ज़हर का असर "
              "कुछ महसूस होने से पहले ही हो सकता है।",
    },
}

# A door photo before anyone said where the generator is: the band, only if it's outside (never "meets the guidance").
IF_OUTSIDE = {
    "borderline": {"en": "If the generator is there and outside, that's borderline: move it farther, past "
                         "{twentyfive} if you can.",
                   "es": "Si el generador está ahí y afuera, eso está en el límite: muévalo más lejos, a más de "
                         "{twentyfive} si puede.",
                   "hi": "अगर जनरेटर वहीं है और बाहर है, तो यह सीमा पर है: हो सके तो उसे और दूर ले जाएँ, {twentyfive} "
                         "से भी आगे।"},
    "meets the guidance": {"en": "If the generator is there and outside, that's more than {twenty}, but the distance "
                                 "only counts outside.",
                           "es": "Si el generador está ahí y afuera, eso es más de {twenty}, pero la distancia solo "
                                 "cuenta afuera.",
                           "hi": "अगर जनरेटर वहीं है और बाहर है, तो यह {twenty} से ज़्यादा है, लेकिन यह दूरी तभी "
                                 "गिनी जाती है जब जनरेटर बाहर हो।"},
}

# After "never indoors", when a door was measured: that photo was taken from inside, so it's taken again.
MEASURED_NOTE = {"en": " If it is, take a new photo of the door from where it stands.",
                 "es": " Si es así, tome otra foto de la puerta desde donde quedó.",
                 "hi": " अगर हाँ, तो जहाँ वह अब है, वहाँ से दरवाज़े की नई फ़ोटो लीजिए।"}

WEATHER = {"en": {"heat": ("extremely hot", "cooling center"), "cold": ("extremely cold", "warming center"),
                  "both": ("extremely hot or cold", "cooling or warming center")},
           "es": {"heat": ("mucho calor", "centro de enfriamiento"), "cold": ("mucho frío", "centro de calentamiento"),
                  "both": ("mucho calor o mucho frío", "centro de enfriamiento o de calentamiento")},
           "hi": {"heat": ("बहुत गर्मी है", "कूलिंग सेंटर"), "cold": ("बहुत ठंड है", "वार्मिंग सेंटर"),
                  "both": ("बहुत गर्मी या बहुत ठंड है", "कूलिंग या वार्मिंग सेंटर")}}


def distance(feet: float, language: str, down: bool = False) -> str:
    """A distance in feet with metres beside it: "20 feet (6.1 m)", "20 pies (6.1 m)". ``down`` rounds both down, for
    an "at least" figure that must never be overstated."""
    metres = feet * FOOT
    word = {"en": "feet", "es": "pies", "hi": "फीट"}[language]
    if down:
        feet, metres = math.floor(feet), (math.floor(metres * 10) / 10 if metres < 10 else math.floor(metres))
    return f"{feet:.0f} {word} ({metres:.1f} m)" if metres < 10 else f"{feet:.0f} {word} ({metres:.0f} m)"


TAKE_PHOTO = {  # measure-distance once the generator is known to be outside
    "en": "Let's check how far it is from the nearest door: stand by the generator and take a photo of the door.",
    "es": "Veamos qué tan lejos está de la puerta más cercana: párese junto al generador y tómele una foto a la "
          "puerta.",
    "hi": "देखते हैं कि वह सबसे पास वाले दरवाज़े से कितनी दूर है: जनरेटर के पास खड़े होकर दरवाज़े की फ़ोटो लीजिए।",
}

# A question asked a second time, because the reply didn't answer it, saying how to answer. The suggested answers are
# ones the conversation reads as plain answers without the model (a test checks them).
AGAIN = {
    "checkin-symptoms": {
        "en": "Does anyone have a headache, or feel dizzy, weak or sick? Say “yes” or “no, nobody”.",
        "es": "¿Alguien tiene dolor de cabeza, mareos, debilidad o malestar? Diga «sí» o «no, nadie».",
        "hi": "क्या किसी को सिरदर्द, चक्कर, कमज़ोरी या जी मिचलाना है? कहिए «हाँ» या «नहीं, किसी को नहीं»।",
    },
    "checkin-outside": {
        "en": "Is the generator still outside? Say “yes, it's outside” or “no”.",
        "es": "¿El generador sigue afuera? Diga «sí, está afuera» o «no».",
        "hi": "क्या जनरेटर अभी भी बाहर है? कहिए «हाँ, बाहर है» या «नहीं»।",
    },
    "checkin-co-alarm": {
        "en": "Is your carbon monoxide alarm working? Say “yes, it's working” or “no”.",
        "es": "¿Su detector de monóxido de carbono funciona? Diga «sí, funciona» o «no».",
        "hi": "क्या आपका कार्बन मोनोऑक्साइड अलार्म काम कर रहा है? कहिए «हाँ, काम कर रहा है» या «नहीं»।",
    },
    "measure-distance": {
        "en": "Is the generator outside, out in the open? Say “yes, it's outside” or “no”.",
        "es": "¿El generador está afuera, al aire libre? Diga «sí, está afuera» o «no».",
        "hi": "क्या जनरेटर बाहर, खुली जगह में है? कहिए «हाँ, बाहर है» या «नहीं»।",
    },
    "take-photo": {
        "en": "When you can, stand by the generator and take a photo of the nearest door with the “Photo of the "
              "door” button.",
        "es": "Cuando pueda, párese junto al generador y tómele una foto a la puerta más cercana con el botón «Foto "
              "de la puerta».",
        "hi": "जब हो सके, जनरेटर के पास खड़े होकर «दरवाज़े की फ़ोटो» बटन से सबसे पास वाले दरवाज़े की फ़ोटो लीजिए।",
    },
    "confirm-outside": {
        "en": "Is the generator outside, out in the open, where you took the photo? Say “yes, it's outside” or “no”.",
        "es": "¿El generador está afuera, al aire libre, donde tomó la foto? Diga «sí, está afuera» o «no».",
        "hi": "क्या जनरेटर बाहर, खुली जगह में है, वहीं जहाँ से आपने फ़ोटो ली? कहिए «हाँ, बाहर है» या «नहीं»।",
    },
    "confirm-1x": {
        "en": "Was the camera at 1× when you took the photo? Say “yes, at 1×” or “no”.",
        "es": "¿La cámara estaba en 1× cuando tomó la foto? Diga «sí, en 1×» o «no».",
        "hi": "क्या फ़ोटो लेते समय कैमरा 1× पर था? कहिए «हाँ, 1× पर था» या «नहीं»।",
    },
    "ask-moved-outside": {
        "en": "Is the generator outside now, out in the open, away from the house? Say “yes, it's outside” or “no”.",
        "es": "¿El generador ya está afuera, al aire libre y lejos de la casa? Diga «sí, está afuera» o «no».",
        "hi": "क्या जनरेटर अब बाहर है, खुली जगह में, घर से दूर? कहिए «हाँ, बाहर है» या «नहीं»।",
    },
    "ask-exhaust": {
        "en": "Does the exhaust point toward the house or away from it? Say “toward the house” or “away from the "
              "house”.",
        "es": "¿El escape apunta hacia la casa o lejos de ella? Diga «hacia la casa» o «lejos de la casa».",
        "hi": "धुआँ घर की तरफ़ निकलता है या घर से दूर? कहिए «घर की तरफ़» या «घर से दूर»।",
    },
    "ask-co-alarm": {
        "en": "Do you have a working carbon monoxide alarm? Say “yes, I have one” or “no, I don't”.",
        "es": "¿Tiene un detector de monóxido de carbono que funcione? Diga «sí, tengo» o «no tengo».",
        "hi": "क्या आपके पास काम करने वाला कार्बन मोनोऑक्साइड अलार्म है? कहिए «हाँ, है» या «नहीं है»।",
    },
    "ask-heat-and-cooking": {
        "en": "Indoors, do you use a grill, a camp stove or a gas oven, or run a car in the garage? Say which, or "
              "“none of those”.",
        "es": "Adentro, ¿usa una parrilla de carbón, una estufa de acampar o el horno de gas, o deja un carro "
              "prendido en el garaje? Diga cuál, o «nada de eso».",
        "hi": "क्या आप घर के अंदर अंगीठी, सिगड़ी, कोयला, कैंप स्टोव या गैस ओवन जलाते हैं, या गैराज में गाड़ी चालू "
              "रखते हैं? बताइए कौन-सा, या कहिए «इनमें से कुछ नहीं»।",
    },
    "ask-downed-lines": {
        "en": "Are there fallen power lines near your home? Say “yes, there are” or “no, there aren't”.",
        "es": "¿Hay cables de luz caídos cerca de su casa? Diga «sí, hay» o «no hay».",
        "hi": "क्या आपके घर के पास बिजली के तार गिरे हुए हैं? कहिए «हाँ, हैं» या «नहीं हैं»।",
    },
    "ask-door-height": {
        "en": "How tall is the door? If it's a regular one, about 6 feet 8 inches, say “it's regular”; if not, tell "
              "me its height, for example “six and a half feet”.",
        "es": "¿Cuánto mide de alto la puerta? Si es normal, de unos 6 pies 8 pulgadas, diga «es normal»; si no, "
              "dígame la medida, por ejemplo «seis pies y medio».",
        "hi": "दरवाज़ा कितना ऊँचा है? अगर आम दरवाज़ा है, लगभग 6 फीट 8 इंच, तो कहिए «नॉर्मल है»; नहीं तो उसकी ऊँचाई "
              "बताइए, जैसे «साढ़े छह फीट»।",
    },
    "confirm-plate": {
        "en": "Did I read the generator's plate right? Say “yes, that's right” or “no”.",
        "es": "¿Leí bien la placa del generador? Diga «sí, está bien» o «no».",
        "hi": "क्या मैंने जनरेटर की प्लेट सही पढ़ी? कहिए «हाँ, सही है» या «नहीं»।",
    },
}
# The overnight check-in: its greeting, its three questions (asked again with how to answer, in AGAIN), and its end.
HELLO = {"es": "Hola. Soy un asistente para después de la tormenta. No soy el 911: si alguien se siente mal, llame "
               "al 911.",
         "en": "Hi. I'm a coach for after the storm. I'm not 911: if anyone feels sick, call 911.",
         "hi": "नमस्ते। मैं तूफ़ान के बाद के लिए एक सहायक हूँ। मैं 911 नहीं हूँ: अगर किसी की तबीयत ख़राब लगे, तो 911 पर "
               "फ़ोन करें।"}  # the coach's first words, before its first question
CHECKIN_HELLO = {"en": "Checking in on the generator. A few quick questions.",
                 "es": "Revisemos el generador. Unas preguntas rápidas.",
                 "hi": "जनरेटर की जाँच के लिए कुछ छोटे सवाल।"}
CHECKIN_ASK = {
    "checkin-symptoms": {
        "en": "Does anyone in the house have a headache, or feel dizzy, weak or sick to their stomach?",
        "es": "¿Alguien en la casa tiene dolor de cabeza, o se siente mareado, débil o con malestar estomacal?",
        "hi": "क्या घर में किसी को सिरदर्द है, या चक्कर, कमज़ोरी या जी मिचलाना लग रहा है?",
    },
    "checkin-outside": {  # by whether the door was measured from where the generator stood
        "measured": {"en": "Is the generator still outside, where you measured it?",
                     "es": "¿El generador sigue afuera, donde lo midió?",
                     "hi": "क्या जनरेटर अभी भी बाहर है, वहीं जहाँ आपने उसे नापा था?"},
        "now": {"en": "Is the generator outside now, out in the open, away from the house?",
                "es": "¿El generador está afuera ahora, al aire libre y lejos de la casa?",
                "hi": "क्या जनरेटर अभी बाहर है, खुली जगह में, घर से दूर?"},
    },
    "checkin-co-alarm": {
        "en": "Is your carbon monoxide alarm working?",
        "es": "¿Su detector de monóxido de carbono está funcionando?",
        "hi": "क्या आपका कार्बन मोनोऑक्साइड अलार्म काम कर रहा है?",
    },
}
CHECKIN_DONE = {"en": "Thank you. That's the check-in. You can send the summary to your family from the page.",
                "es": "Gracias. Eso es todo. Puede enviar el resumen a su familia desde la página.",
                "hi": "धन्यवाद। जाँच पूरी हुई। आप इस पेज से अपने परिवार को सारांश भेज सकते हैं।"}

NOT_CAUGHT = {"en": "Sorry, I didn't catch that.", "es": "Perdón, no le entendí bien.",
              "hi": "माफ़ कीजिए, आपकी बात ठीक से समझ नहीं आई।"}
LENS_RETAKE = {"en": "Then that distance doesn't count: take the next photo with the camera at 1×.",
               "es": "Entonces esa distancia no cuenta: tome la próxima foto con la cámara en 1×.",
               "hi": "तो यह दूरी नहीं गिनी जाएगी: अगली फ़ोटो कैमरा 1× पर रखकर लीजिए।"}  # a "no" to confirm-1x
LATER = {"en": "That's all right.", "es": "Está bien.", "hi": "कोई बात नहीं।"}  # after "no sé": left for later
DONE = {"en": "That's all for now. If anything changes, talk to me, or take a new photo of the door.",
        "es": "Eso es todo por ahora. Si algo cambia, hábleme, o tome otra foto de la puerta.",
        "hi": "अभी के लिए बस इतना ही। अगर कुछ बदले, तो मुझसे बात करें, या दरवाज़े की नई फ़ोटो लें।"}


# What the model read that would take a danger off the list, read back before it counts: "Entendí que …".
UNDERSTOOD = {
    ("generator_location", "outdoors"): {"en": "the generator is outside, out in the open",
                                         "es": "el generador está afuera, al aire libre",
                                         "hi": "जनरेटर बाहर, खुली जगह में है"},
    ("symptoms", "no"): {"en": "nobody feels sick", "es": "nadie se siente mal",
                         "hi": "किसी की तबीयत ख़राब नहीं है"},
    ("exhaust_toward_house", "no"): {"en": "the exhaust points away from the house",
                                     "es": "el escape apunta lejos de la casa",
                                     "hi": "धुआँ घर से दूर की तरफ़ निकलता है"},
    ("co_alarm", "yes"): {"en": "you have a working carbon monoxide alarm",
                          "es": "tiene un detector de monóxido de carbono que funciona",
                          "hi": "आपके पास काम करने वाला कार्बन मोनोऑक्साइड अलार्म है"},
    ("downed_line", "no"): {"en": "there are no fallen power lines nearby", "es": "no hay cables de luz caídos cerca",
                            "hi": "पास में बिजली के तार गिरे हुए नहीं हैं"},
    ("extreme_heat", "no"): {"en": "it isn't extremely hot", "es": "no hace mucho calor",
                             "hi": "बहुत ज़्यादा गर्मी नहीं है"},
    ("extreme_cold", "no"): {"en": "it isn't extremely cold", "es": "no hace mucho frío",
                             "hi": "बहुत ज़्यादा ठंड नहीं है"},
    ("medical_needs", "no"): {"en": "nobody needs power for medicine or a medical device",
                              "es": "nadie necesita luz para medicinas o aparatos médicos",
                              "hi": "किसी को दवाओं या मेडिकल उपकरणों के लिए बिजली की ज़रूरत नहीं है"},
    ("backfeeding", "no"): {"en": "the generator isn't plugged into a wall outlet",
                            "es": "el generador no está conectado a un enchufe de la pared",
                            "hi": "जनरेटर दीवार के सॉकेट में नहीं लगा है"},
    ("refuelling", "no"): {"en": "you aren't adding fuel now", "es": "no le está echando gasolina ahora",
                           "hi": "आप अभी पेट्रोल नहीं डाल रहे हैं"},
    ("burning_indoors", "none"): {"en": "you don't use a grill, a camp stove, a gas oven or a running car indoors",
                                  "es": "no usa adentro parrillas de carbón, estufas de acampar, hornos de gas ni carros "
                                        "prendidos",
                                  "hi": "आप घर के अंदर अंगीठी, कैंप स्टोव, गैस ओवन या चालू गाड़ी का इस्तेमाल नहीं "
                                        "करते"},
    ("door_height_in", None): {"en": "the door is about {inches:.0f} inches tall",
                               "es": "la puerta mide unas {inches:.0f} pulgadas de alto",
                               "hi": "दरवाज़ा लगभग {inches:.0f} इंच ऊँचा है"},
}


def understood(facts: dict, language: str = "es", again: bool = False) -> str:
    """Facts read back to be confirmed: "Entendí que A, que B y que C. ¿Es así?"; ``again`` says how to answer."""
    parts = []
    for name, value in facts.items():
        if name == "door_height_in":
            parts.append(UNDERSTOOD[(name, None)][language].format(inches=value))
        else:
            parts.append(UNDERSTOOD[(name, "none" if isinstance(value, (list, tuple)) else value)][language])
    that, also, last = {"es": ("que ", " y ", "Entendí que"), "en": ("that ", " and ", "I understood that"),
                        "hi": ("", " और ", "मैंने समझा कि")}[language]
    clauses = [parts[0], *(f"{that}{part}" for part in parts[1:])]
    listed = clauses[0] if len(clauses) == 1 else ", ".join(clauses[:-1]) + also + clauses[-1]
    if language == "es":
        return f"{last} {listed}. ¿Es así?" + (" Diga «sí, es así» o «no»." if again else "")
    if language == "hi":
        return f"{last} {listed}। क्या यह सही है?" + (" कहिए «हाँ, सही है» या «नहीं»।" if again else "")
    return f"{last} {listed}. Is that right?" + (" Say “yes, that's right” or “no”." if again else "")


def ask(advice: Advice, language: str = "es", again: bool = False) -> str:
    """A question in the person's language; ``again`` asks it a second time, saying how to answer."""
    if advice.rule == "confirm":
        return understood(dict(advice.values["facts"]), language, again)
    rule = "take-photo" if advice.rule == "measure-distance" and advice.values.get("outdoors") else advice.rule
    if again and rule in AGAIN:
        return AGAIN[rule][language]
    if rule == "ask-door-height":
        return DOOR_NOTES[rule][language]
    if rule == "confirm-plate":
        return PLATE_CHECK[language]
    if rule == "checkin-outside":
        return CHECKIN_ASK[rule]["measured" if advice.values.get("measured") else "now"][language]
    if rule in CHECKIN_ASK:
        return CHECKIN_ASK[rule][language]
    return say(advice, language)


# The verdict card's one line under its headline, what to do, in the coach's own words: a part of the headline's
# line (which sentence, then the clause after the first "after" or before the first "before"), or the open question
# itself. So the card says nothing the coach doesn't, and nothing here is new wording.
ACTION = {
    "move-outside-now": {"en": (1,), "es": (1,), "hi": (1,)},
    "away-from-openings": {"en": (1,), "es": (2,), "hi": (1,)},
    "too-close": {"en": (1, ": "), "es": (2,), "hi": (1, ": ")},
    "borderline": {"en": (1, ": "), "es": (1, ": "), "hi": (1, ": ")},
    "meets-guidance": {"en": (2, None, ", and"), "es": (3, None, ";"), "hi": (2, None, ";")},
    "if-outside": "confirm-outside",
    "if-1x": "confirm-1x",
}
# Where a sentence ends. The danda is written by its code point, so every Hindi string in this file is a reviewed line.
SENTENCE_BREAK = re.compile(rf"(?<=[.?!{chr(0x964)}])\s+")


def action(advice: Advice, language: str = "es") -> str:
    """The verdict card's action line for this headline (see ACTION), or "" if it has none."""
    spec = ACTION.get(advice.rule)
    if spec is None:
        return ""
    if isinstance(spec, str):
        return PHRASES[spec][language]
    index, after, before = (*spec[language], None, None)[:3]
    sentence = SENTENCE_BREAK.split(say(advice, language))[index]
    if after:
        sentence = sentence.split(after, 1)[1]
    if before:
        sentence = sentence.split(before, 1)[0] + sentence[-1]
    return sentence[:1].upper() + sentence[1:]


def say(advice: Advice, language: str = "es") -> str:
    """The advice in the person's language."""
    if advice.rule == "measure-distance" and advice.values.get("outdoors"):
        return TAKE_PHOTO[language]
    values = {"fifteen": distance(15, language), "twenty": distance(20, language),
              "twentyfive": distance(25, language), "thirty": distance(30, language)}
    if advice.values.get("feet") is not None:
        values["feet"] = distance(advice.values["feet"], language)
    if advice.values.get("lowest") is not None:
        values["lowest"] = distance(advice.values["lowest"], language, down=True)
    if "place" in advice.values:
        values["place"] = PLACES[language][advice.values["place"]]
    if advice.rule == "ask-moved-outside":
        values["note"] = MEASURED_NOTE[language] if advice.values.get("measured") else ""
    if advice.rule == "if-outside":
        values["if_outside"] = IF_OUTSIDE[advice.values["band"]][language].format(**values)
    if advice.rule == "go-where-there-is-power":
        heat, cold = advice.values["heat"], advice.values["cold"]
        values["weather"], values["center"] = WEATHER[language]["both" if heat and cold else "heat" if heat else "cold"]
    return PHRASES[advice.rule][language].format(**values)


DOOR_NOTES = {
    "no-focal-length": {
        "en": "This photo doesn't say which lens took it (photos sent by text lose that). Take it again with the "
              "phone's own camera, at 1×.",
        "es": "Esta foto no dice con qué lente se tomó (las fotos enviadas por mensaje lo pierden). Tómela otra vez "
              "con la cámara del teléfono, en 1×.",
        "hi": "इस फ़ोटो में यह जानकारी नहीं है कि वह किस लेंस से ली गई (मैसेज से भेजी गई फ़ोटो में यह मिट जाती है)। "
              "फ़ोन के अपने कैमरे से, 1× पर, फिर से लीजिए।",
    },
    "no-door": {
        "en": "I can't find a door in this photo. Point the camera at a door, not a window: windows come in too "
              "many sizes to measure by.",
        "es": "No encuentro una puerta en esta foto. Apunte la cámara a una puerta, no a una ventana: las ventanas "
              "tienen demasiados tamaños para medir con ellas.",
        "hi": "मुझे इस फ़ोटो में दरवाज़ा नहीं दिख रहा। कैमरा किसी दरवाज़े की तरफ़ करें, खिड़की की तरफ़ नहीं: "
              "खिड़कियाँ बहुत अलग-अलग नाप की होती हैं।",
    },
    "door-cut-off": {
        "en": "The door is cut off at the top or bottom of the photo. Hold the phone upright, or step back, so the "
              "whole door fits.",
        "es": "La puerta sale cortada arriba o abajo en la foto. Ponga el teléfono vertical, o aléjese un poco, para "
              "que quepa toda la puerta.",
        "hi": "फ़ोटो में दरवाज़ा ऊपर या नीचे से कट गया है। फ़ोन सीधा खड़ा पकड़ें, या थोड़ा पीछे हटें, ताकि पूरा "
              "दरवाज़ा आ जाए।",
    },
    "lens-assumed": {
        "en": "This photo doesn't say which lens took it, so the distance assumes the camera was at 1×.",
        "es": "Esta foto no dice con qué lente se tomó, así que la distancia supone que la cámara estaba en 1×.",
        "hi": "इस फ़ोटो में यह जानकारी नहीं है कि वह किस लेंस से ली गई, इसलिए दूरी यह मानकर निकाली गई है कि कैमरा "
              "1× पर था।",
    },
    "zoom": {
        "en": "The photo was zoomed in, which can throw the measurement off. Take it again at 1×.",
        "es": "La foto tiene zoom, y eso puede falsear la medida. Tómela otra vez en 1×.",
        "hi": "फ़ोटो ज़ूम करके ली गई है, इससे नाप गलत हो सकता है। 1× पर फिर से लीजिए।",
    },
    "tilt": {
        "en": "The phone looks tilted by about {tilt:.0f}°. Hold it level, pointing straight at the door, and try "
              "again.",
        "es": "El teléfono parece inclinado unos {tilt:.0f}°. Sosténgalo derecho, apuntando de frente a la puerta, e "
              "intente de nuevo.",
        "hi": "फ़ोन लगभग {tilt:.0f}° झुका हुआ लगता है। उसे सीधा, दरवाज़े के ठीक सामने पकड़ें और फिर से कोशिश करें।",
    },
    "garage-door": {
        "en": "This looks like a garage door or a double door. Tell me how tall it is: garage doors are often 7 or 8 "
              "feet.",
        "es": "Esto parece una puerta de garaje o una puerta doble. Dígame qué tan alta es: las de garaje suelen "
              "medir 7 u 8 pies.",
        "hi": "यह गैराज का दरवाज़ा या दोहरा दरवाज़ा लगता है। बताइए यह कितना ऊँचा है: गैराज के दरवाज़े अक्सर 7 या 8 "
              "फीट के होते हैं।",
    },
    "off-centre": {
        "en": "The door is near the edge of the photo, where the lens bends lines. Put it in the middle and try "
              "again.",
        "es": "La puerta está cerca de la orilla de la foto, donde la lente deforma las líneas. Póngala en el centro "
              "e intente de nuevo.",
        "hi": "दरवाज़ा फ़ोटो के किनारे के पास है, जहाँ लेंस सीधी लाइनों को टेढ़ा कर देता है। उसे बीच में रखकर फिर से "
              "कोशिश करें।",
    },
    "small": {
        "en": "The door is very small in this photo. Use the full-size photo, not a shrunken copy.",
        "es": "La puerta se ve muy pequeña en esta foto. Use la foto en tamaño completo, no una copia reducida.",
        "hi": "इस फ़ोटो में दरवाज़ा बहुत छोटा दिख रहा है। पूरे साइज़ वाली फ़ोटो भेजें, छोटी की हुई कॉपी नहीं।",
    },
    "several-doors": {
        "en": "I see more than one door and measured the clearest. Make sure it's the one nearest the generator.",
        "es": "Veo más de una puerta y medí la más clara. Asegúrese de que sea la más cercana al generador.",
        "hi": "मुझे एक से ज़्यादा दरवाज़े दिख रहे हैं, और सबसे साफ़ वाले को नापा गया। देख लें कि यही जनरेटर के सबसे "
              "पास वाला दरवाज़ा हो।",
    },
    "ask-door-height": {
        "en": "Is it a regular door, about 6 feet 8 inches (2 m) tall? If it's shorter or taller, tell me how tall.",
        "es": "¿Es una puerta normal, de unos 6 pies 8 pulgadas (2 m) de alto? Si es más baja o más alta, dígame "
              "cuánto mide.",
        "hi": "क्या यह आम दरवाज़ा है, लगभग 6 फीट 8 इंच (2 m) ऊँचा? अगर छोटा या बड़ा है, तो बताइए कितना ऊँचा है।",
    },
    "error-limits": {  # a door shorter than the height assumed reads too far away: the generator is nearer
        "en": "On test doors this reads within {error:.0%} when the door's height is right. A door shorter than "
              "6 feet 8 inches means the generator is closer than it looks.",
        "es": "En puertas de prueba, esta medida acierta dentro de un {error:.0%} cuando la altura de la puerta es "
              "correcta. Una puerta de menos de 6 pies 8 pulgadas significa que el generador está más cerca de lo "
              "que parece.",
        "hi": "जाँच वाले दरवाज़ों पर, दरवाज़े की ऊँचाई सही हो तो यह नाप {error:.0%} के अंदर सही आता है। 6 फीट 8 इंच "
              "से छोटा दरवाज़ा हो, तो जनरेटर दिखने से ज़्यादा पास है।",
    },
    "door-height-assumed": {
        "en": "Door height: {inches:.0f} inches, assumed (a regular door).",
        "es": "Altura de la puerta: {inches:.0f} pulgadas, supuesta (una puerta normal).",
        "hi": "दरवाज़े की ऊँचाई: {inches:.0f} इंच, मान ली गई (आम दरवाज़ा)।",
    },
    "door-height-given": {
        "en": "Door height: {inches:.0f} inches, as you told me.",
        "es": "Altura de la puerta: {inches:.0f} pulgadas, como me dijo.",
        "hi": "दरवाज़े की ऊँचाई: {inches:.0f} इंच, जैसा आपने बताया।",
    },
}


def door_note(key: str, language: str = "es", **values) -> str:
    """A note about a door photo in the person's language."""
    return DOOR_NOTES[key][language].format(**values)


PLATE_NOTES = {
    "no-plate": {
        "en": "I can't read a rating plate in this photo. It's usually a sticker or metal plate on the generator's "
              "side or near the outlets. Get close, and avoid glare.",
        "es": "No puedo leer la placa en esta foto. Suele ser una etiqueta o una placa de metal a un lado del "
              "generador o cerca de los enchufes. Acérquese y evite los reflejos.",
        "hi": "इस फ़ोटो में जनरेटर की प्लेट पढ़ी नहीं जा रही। यह आमतौर पर जनरेटर के एक तरफ़ या सॉकेट के पास एक स्टिकर "
              "या धातु की प्लेट होती है। पास जाकर, चमक से बचाकर फ़ोटो लीजिए।",
    },
    "no-running-watts": {
        "en": "I couldn't read the running watts. Read them to me, or take a closer photo.",
        "es": "No pude leer los vatios de trabajo. Dígamelos, o tome una foto más de cerca.",
        "hi": "रनिंग वॉट पढ़े नहीं जा सके। मुझे बताइए, या और पास से फ़ोटो लीजिए।",
    },
    "watts-out-of-range": {
        "en": "The watts I read don't look like a portable generator's, so I may have misread them. Please check.",
        "es": "Los vatios que leí no parecen de un generador portátil; puede que los haya leído mal. Revíselos, "
              "por favor.",
        "hi": "जो वॉट पढ़े गए, वे किसी पोर्टेबल जनरेटर जैसे नहीं लगते; हो सकता है वे गलत पढ़े गए हों। कृपया जाँच "
              "लीजिए।",
    },
    "swapped-watts": {
        "en": "The starting watts I read are lower than the running watts, so one of them is probably misread. "
              "Please check both.",
        "es": "Los vatios de arranque que leí son menores que los de trabajo; seguramente leí mal uno de los dos. "
              "Revise ambos, por favor.",
        "hi": "स्टार्टिंग वॉट रनिंग वॉट से कम पढ़े गए, तो दोनों में से एक शायद गलत पढ़ा गया। कृपया दोनों जाँच लीजिए।",
    },
    "odd-hertz": {
        "en": "The frequency I read is unusual. Please check it.",
        "es": "La frecuencia que leí es rara. Revísela, por favor.",
        "hi": "जो फ़्रीक्वेंसी पढ़ी गई, वह अजीब है। कृपया जाँच लीजिए।",
    },
    "odd-volts": {
        "en": "The voltage I read is unusual. Please check it.",
        "es": "El voltaje que leí es raro. Revíselo, por favor.",
        "hi": "जो वोल्टेज पढ़ा गया, वह अजीब है। कृपया जाँच लीजिए।",
    },
    "amps-dont-match": {
        "en": "The amps and volts I read don't match the watts, so a number may be misread. Please check them.",
        "es": "Los amperios y voltios que leí no cuadran con los vatios; puede que haya leído mal un número. "
              "Revíselos, por favor.",
        "hi": "जो एम्पियर और वोल्ट पढ़े गए, वे वॉट से मेल नहीं खाते, तो कोई नंबर शायद गलत पढ़ा गया। कृपया जाँच लीजिए।",
    },
}

FUELS = {"es": {"gasoline": "gasolina", "propane": "propano", "dual fuel": "doble combustible", "diesel": "diésel"},
         "hi": {"gasoline": "पेट्रोल", "propane": "प्रोपेन", "dual fuel": "डुअल फ़्यूल", "diesel": "डीज़ल"}}

# The rating plate's read-back as the coach's own question (read_back() ends it with "¿Es correcto?"), and the reply
# to a "no": the reading is wrong, so the photo is taken again.
PLATE_CHECK = {"en": "Did I read the generator's plate right?", "es": "¿Leí bien la placa del generador?",
               "hi": "क्या मैंने जनरेटर की प्लेट सही पढ़ी?"}
PLATE_WRONG = {"en": "All right. Take another photo of the plate, close up and without glare.",
               "es": "Está bien. Tome otra foto de la placa, de cerca y sin reflejos.",
               "hi": "कोई बात नहीं। प्लेट की एक और फ़ोटो लीजिए, पास से और बिना चमक के।"}


def plate_read(plate, language: str = "es") -> str:
    """What was read off the rating plate, in the order the read-back says it: the generator's name, the numbers
    (the first two joined by "and", any more after a comma), then the fuel. Anything not read is left out, and the
    notes after the read-back say what matters ("I couldn't read the running watts"); "" if nothing was read."""
    units = {"hi": ("रनिंग वॉट", "स्टार्टिंग वॉट", "वोल्ट"), "en": ("running watts", "starting watts", "volts"),
             "es": ("vatios de trabajo", "vatios de arranque", "voltios")}[language]
    values = (None if plate.running_watts is None else f"{plate.running_watts:,.0f}",
              None if plate.starting_watts is None else f"{plate.starting_watts:,.0f}", plate.volts or None)
    numbers = [f"{value} {unit}" for value, unit in zip(values, units) if value]
    joined = {"hi": " और ", "en": " and ", "es": " y "}[language].join(numbers[:2])
    name = " ".join(part for part in (plate.brand, plate.model) if part)
    fuel = FUELS.get(language, {}).get(plate.fuel, plate.fuel)
    return ", ".join(part for part in (name, joined, *numbers[2:], fuel) if part)


def read_back(plate, language: str = "es") -> str:
    """The rating plate as read, to confirm aloud, then anything that looks misread or wasn't read. With nothing
    read, only that the plate couldn't be read."""
    listed = plate_read(plate, language) if plate.visible else ""
    if not listed:
        return PLATE_NOTES["no-plate"][language]
    notes = [PLATE_NOTES[p][language] for p in plate.problems if p in PLATE_NOTES]
    text = {"hi": f"मैंने पढ़ा: {listed}। क्या यह सही है?", "en": f"I read: {listed}. Is that right?",
            "es": f"Leí: {listed}. ¿Es correcto?"}[language]
    return " ".join([text, *notes])


# The phone page's own words: static/app.js fetches them from /api/text. Here, so they're reviewed with the rest;
# index.html starts with the Hindi ones (a test keeps the two the same). {lowest} and {highest} are feet.
PAGE = {
    "hi": {
        "subtitle": "जनरेटर और कार्बन मोनोऑक्साइड, तूफ़ान के बाद",
        "welcome": "सहायक से बात करें, या जहाँ जनरेटर है वहाँ से दरवाज़े की फ़ोटो लें।",
        "begin": "शुरू करें",
        "talk": "बोलें",
        "stop": "हो गया, भेजें",
        "door": "दरवाज़े की फ़ोटो",
        "plate": "जनरेटर के लेबल की फ़ोटो",
        "adviceTitle": "सलाह क्या कहती है",
        "sources": "स्रोत",
        "listening": "सुन रहे हैं… बोलने के बाद “हो गया” दबाएँ।",
        "thinking": "सोच रहे हैं…",
        "measuring": "दरवाज़ा नाप रहे हैं…",
        "reading": "लेबल पढ़ रहे हैं…",
        "micDenied": "माइक्रोफ़ोन इस्तेमाल करने की अनुमति चाहिए।",
        "failed": "कुछ गड़बड़ हो गई। फिर से कोशिश करें।",
        "notNine11": "मैं 911 नहीं हूँ। अगर किसी की तबीयत ख़राब लगे, तो खुली हवा में जाएँ और 911 पर फ़ोन करें।",
        "about": "लगभग",
        "between": "{lowest} से {highest} फीट के बीच, नापने की गलती गिनकर",
        "tonight": "आज रात",
        "tonightText": "रात में जाँच का एक समय चुनें: फ़ोन याद दिलाएगा, और लिंक आपको यहीं वापस लाएगा।",
        "checkinTime": "जाँच का समय",
        "addCalendar": "कैलेंडर में जोड़ें",
        "checkNow": "अभी जाँच करें",
        "note": "परिवार के लिए नोट (अगर चाहें)",
        "share": "परिवार को सारांश भेजें",
        "preview": "सारांश देखें (अंग्रेज़ी में)",
        "listen": "सुनें",
        "lensYes": "हाँ, 1× पर था",
        "lensNo": "नहीं",
        "copied": "सारांश कॉपी हो गया: इसे किसी मैसेज में चिपकाएँ।",
        "checkinWelcome": "जनरेटर की जाँच का समय: तीन छोटे सवाल।",
        "startCheckin": "जाँच शुरू करें",
        "checkinBanner": "रात की जाँच",
        "placement": {
            "never indoors": "अंदर कभी नहीं",
            "against the house": "घर के बहुत पास",
            "too close": "बहुत पास",
            "borderline": "सीमा पर",
            "meets the guidance": "सीडीसी की सलाह के मुताबिक",
            "if outside": "सिर्फ़ अगर बाहर है",
            "if at 1x": "सिर्फ़ अगर कैमरा 1× पर था",
            "not measured": "अभी नापा नहीं गया",
        },
    },
    "en": {
        "subtitle": "Generators and carbon monoxide, after the storm",
        "welcome": "Talk to the coach, or take a photo of the door from where the generator stands.",
        "begin": "Start",
        "talk": "Talk",
        "stop": "Done, send",
        "door": "Photo of the door",
        "plate": "Photo of the generator's label",
        "adviceTitle": "What the guidance says",
        "sources": "Sources",
        "listening": "Listening… tap “Done” when you finish.",
        "thinking": "Thinking…",
        "measuring": "Measuring the door…",
        "reading": "Reading the label…",
        "micDenied": "I need permission to use the microphone.",
        "failed": "Something went wrong. Please try again.",
        "notNine11": "I'm not 911. If anyone feels sick, get into fresh air and call 911.",
        "about": "about",
        "between": "between {lowest} and {highest} ft, allowing for measuring error",
        "tonight": "Tonight",
        "tonightText": ("Pick a time to check in overnight: your phone will remind "
                        "you, and the link brings you back here."),
        "checkinTime": "Check-in time",
        "addCalendar": "Add to calendar",
        "checkNow": "Check in now",
        "note": "Note for your family (optional)",
        "share": "Send the summary to your family",
        "preview": "See the summary",
        "listen": "Listen",
        "lensYes": "Yes, at 1×",
        "lensNo": "No",
        "copied": "Summary copied: paste it into a message.",
        "checkinWelcome": "Time to check on the generator: three quick questions.",
        "startCheckin": "Start the check-in",
        "checkinBanner": "Overnight check-in",
        "placement": {
            "never indoors": "Never indoors",
            "against the house": "Too close to the house",
            "too close": "Too close",
            "borderline": "Borderline",
            "meets the guidance": "Meets the CDC's guidance",
            "not measured": "Not measured yet",
            "if outside": "Only if it's outside",
            "if at 1x": "Only if the camera was at 1×",
        },
    },
    "es": {
        "subtitle": "Generador y monóxido de carbono, después de la tormenta",
        "welcome": "Hable con el asistente o tome una foto de la puerta desde donde está el generador.",
        "begin": "Empezar",
        "talk": "Hablar",
        "stop": "Listo, enviar",
        "door": "Foto de la puerta",
        "plate": "Foto de la etiqueta del generador",
        "adviceTitle": "Lo que dicen las guías",
        "sources": "Fuentes",
        "listening": "Escuchando… toque “Listo” al terminar.",
        "thinking": "Pensando…",
        "measuring": "Midiendo la puerta…",
        "reading": "Leyendo la etiqueta…",
        "micDenied": "Necesito permiso para usar el micrófono.",
        "failed": "Algo falló. Intente otra vez.",
        "notNine11": "No soy el 911. Si alguien se siente mal, salgan al aire libre y llamen al 911.",
        "about": "unos",
        "between": "entre {lowest} y {highest} pies, contando el error de medición",
        "tonight": "Esta noche",
        "tonightText": ("Elija una hora para revisar durante la noche: el teléfono "
                        "le avisará y el enlace lo traerá aquí."),
        "checkinTime": "Hora de la revisión",
        "addCalendar": "Agregar al calendario",
        "checkNow": "Revisar ahora",
        "note": "Nota para su familia (opcional)",
        "share": "Enviar el resumen a su familia",
        "preview": "Ver el resumen (en inglés)",
        "listen": "Escuchar",
        "lensYes": "Sí, en 1×",
        "lensNo": "No",
        "copied": "Resumen copiado: péguelo en un mensaje.",
        "checkinWelcome": "Es hora de revisar el generador: tres preguntas rápidas.",
        "startCheckin": "Empezar la revisión",
        "checkinBanner": "Revisión de la noche",
        "placement": {
            "never indoors": "Nunca adentro",
            "against the house": "Demasiado cerca de la casa",
            "too close": "Demasiado cerca",
            "borderline": "En el límite",
            "meets the guidance": "Cumple la guía",
            "if outside": "Solo si está afuera",
            "if at 1x": "Solo si la cámara estaba en 1×",
            "not measured": "Todavía sin medir",
        },
    },
}
