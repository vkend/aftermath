# The demo video: what's in it, and under what terms

The scripts in `scripts/video/` build the demo video from the parts below: the narrated cut (v2, Nov 4:
`narrate.py` and `edit2.py`) and its fallback with captions beside the phone instead of narration (v1:
`make_video.py`). Their inputs and the videos themselves stay in `data/video/`, outside this repository.

## Made for the video

- **Screen recordings** of the real app, through its own phone page at iPhone size (headless Chromium driven by
  `scripts/video/record.js`), and the cards, diagram and chart (HTML rendered by `scripts/video/render.js`): made by
  the scripts here, under the code's MIT licence.
- **The scenes are staged.** No generator was run. The narrated cut's door photos are the builder's own garage, taken
  at taped distances on Nov 4 and sent to the app as a phone sends them, with the house number painted out and only the
  lens data kept (no location); it also shows 1.2 s of that garage door, closed and only starting to lift, so nothing
  inside the garage is seen. The first cut's are the builder's hallway shots of Oct 29, with people and rooms blurred
  before the app saw them; the narrated cut's mumbled answer comes from that take, with its card blurred so that only
  the app's reply reads. None of them is in this repository. The narrated cut is in Spanish: the app's own Spanish,
  beyond the agencies' quoted lines, isn't yet reviewed by a native speaker (README, "Limits"), and its credits say so.
- **The app's voice** is Meta MMS-TTS (`facebook/mms-tts-spa` in the narrated cut; `-hin` and `-eng` too, CC BY-NC
  4.0), the app's own voice model, named on screen whenever it speaks. **The person** is a synthetic stand-in: in the
  narrated cut macOS's Paulina (es_MX, the user's choice), in the first cut MMS-TTS pitched lower. Each of the
  stand-in's lines was kept only if the app heard it as meant: from Paulina, every line the first time but the mumble,
  which MMS heard as nothing in «Mmm…» and as «e» in «Mmm, eh…»; in the first cut, for «हाँ, बाहर है», 2 of 16 takes.
- **Narration (v2):** macOS text-to-speech in the system's Siri voice, reading the script in
  `scripts/video/narrate.py` (the user asked for the Mac's own voice, and chose Siri's over Samantha), in the third
  person and without naming the builder: the voice isn't theirs. Each line is voiced in one breath, and the words'
  times come from OpenAI's Whisper (large-v3-turbo, MIT licence) through mlx-audio, on the laptop. Credited as "The
  narrator: macOS Siri voice", beside the app's voice and the person's.
- **Music and sound effects (v2):** procedural, made for the video by the builder's own seeded score generator, from
  no samples or recordings.
- **v2's frames** are drawn by `scripts/video/stage.html` in headless Chromium (`scripts/video/render2.js`), from the
  recordings, the door photos with SAM 3.1's outline, and the footage below.

## Footage (public domain, sound muted)

| Clip | Source | Credit | Terms |
|---|---|---|---|
| Pine Island after Hurricane Ian, drone | [DVIDS 859865](https://www.dvidshub.net/video/859865), "Coast Guard Drone B-Roll post Hurricane Ian" | U.S. Coast Guard video by Petty Officer 3rd Class Ian Gray, via DVIDS | Public domain |
| Florida's lights at night before and after Ian | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Florida_Nighttime_Lights_Before_and_After_Hurricane_Ian_(SVS5058_-_black_marble_fade).webm), from NASA SVS 5058 | NASA's Scientific Visualization Studio / NASA Black Marble (SSAI/Michala Garrison) | Public domain (a NASA work); no NASA insignia shown |
| Fort Myers Beach after Ian, from a vehicle (v2) | [DVIDS 859276](https://www.dvidshub.net/video/859276), "Coast Guard conducts damage assessments in wake of Hurricane Ian" | U.S. Coast Guard video by Maritime Safety and Security Team Miami, via DVIDS | Public domain |
| Portable generators being readied (v2) | [DVIDS 160340](https://www.dvidshub.net/video/160340), "NY National Guard Prepares Generators for Polling Locations" | National Guard Bureau video by Sgt. Michael Dann, via DVIDS | Public domain |
| A lineman after Dorian (v2) | [DVIDS 707468](https://www.dvidshub.net/video/707468), "Hurricane Dorian: Power Line Replacement" | U.S. Marine Corps video by Sgt. Justin X. Toledo, via DVIDS | Public domain |
| "Prevent Carbon Monoxide Poisoning", its 20 ft card (3.6 s from 0:42; not the logo end card) | [Wikimedia Commons](https://commons.wikimedia.org/wiki/File:Prevent_Carbon_Monoxide_Poisoning.webm) | Centers for Disease Control and Prevention (CDC) | Public domain (a U.S. federal work) |

"The appearance of U.S. Department of War (DoW) visual information does not imply or constitute DoW endorsement."
No agency endorses Aftermath.

## Figures and quotes on the cards

- 1,332 people killed by carbon monoxide from portable generators in the US, 2004–2021:
  [CPSC, 88 FR 24346 (2023)](https://www.govinfo.gov/content/pkg/FR-2023-04-20/html/2023-07870.htm).
- 89% of disaster carbon monoxide deaths within three days:
  [Iqbal et al., American Journal of Public Health, 2012](https://doi.org/10.2105/AJPH.2012.300674).
- 59% of one Houston children's hospital's carbon monoxide cases in the 2021 Texas freeze preferred a language other
  than English: [Portillo et al. 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11258496/).
- The CDC's "more than 20 feet" and NIST's findings: quoted, with their links, in `src/aftermath/guidance.py`.
- The results card (v1) and the proof chapter (v2): this repository's own evals (README, "How the distance is
  measured", "Listening" and "Reading"), on Google FLEURS (CC BY 4.0), DIODE (MIT) and Hypersim (CC BY-SA 3.0, numbers
  only): the six tape photos (+0.2% to +3.1%), DIODE's 7 doors of known height (median −0.2%, worst −2.0%), and 0 of
  31 door views under 20 ft rated far enough (DIODE 11, Hypersim 20).
- v2's other figures: the ±6% error range in the diagram (`src/aftermath/door.py`); short Spanish answers heard
  right, 17 of 30 by MMS on the laptop and 26 of 30 by Voice Transcribe, the lone "Sí." Voice Transcribe returned
  empty without silence around it, and the 0.5 s of silence that fixed it, and not one of 240 transcripts, in Spanish,
  English and Hindi, taking a danger off the list (all README, "Listening", Oct 29); the 0.1 s reply to symptom words
  (README's Conversation row; the take's own reply came in 0.08 s); and Spanish as the most spoken language at home in
  the US after English ([US Census Bureau, American Community Survey](https://www.census.gov/programs-surveys/acs)).

## Type

Noto Sans and Noto Sans Devanagari (v1), Inter and JetBrains Mono (v2), all under the SIL Open Font License 1.1.
