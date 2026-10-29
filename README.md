# Aftermath

After a hurricane cuts the power, a phone coach that measures how far the generator is from the door and checks it
against CDC and NIST guidance, in Hindi and English, with the agencies' own Spanish for the safety lines.

Built for the [Meta Global AI Developer Hackathon](https://cerebralvalley.ai/e/meta-ai-developer-hackathon)
(Oct 26 – Nov 4, 2026), Indie Developer track, "Build for Your World". Work in progress.

## Why

Portable generators were linked to at least 1,332 carbon monoxide deaths in the US from 2004 to 2021
([CPSC, 88 FR 24346](https://www.govinfo.gov/content/pkg/FR-2023-04-20/html/2023-07870.htm)). In disasters the deaths
cluster in the first three days ([Iqbal et al. 2012](https://doi.org/10.2105/AJPH.2012.300674)), and up to half of
nonfatal poisonings in the 2004–05 hurricane seasons involved generators running outdoors but within seven feet of the
home ([NIST](https://www.nist.gov/node/562351)). The burden falls hard on families who don't speak English: during the
2021 Texas freeze, 59% of one Houston children's hospital's CO patients preferred another language
([Portillo et al. 2024](https://pmc.ncbi.nlm.nih.gov/articles/PMC11258496/)). The guidance exists, in about ten
languages, as PDFs that need the internet and the power that just went out. The demo speaks Hindi, the builder's own
language: Ready.gov publishes the generator rule in Hindi only as a picture, and the coach quotes it.

## What it does (and what's built so far)

| Part | State |
|---|---|
| **Door distance:** stand at the generator, photograph the nearest door; SAM 3.1 finds the door and the photo's focal length gives the distance | Built; tested on real photos (below) |
| **Safety rules:** deterministic, outside the language model, every line citing CDC, CPSC, Ready.gov, NIST or utility guidance word for word | Built, tested |
| Hindi and English wording, the Hindi reviewed by a native speaker (below); Spanish only as the agencies' own sentences (CDC, CPSC, Ready.gov), quoted word for word; never calls anything "safe" in any of them | Built, tested |
| **Phone web page** over HTTPS on the laptop: talk, photograph the door and the rating plate, see the verdict and its sources | Built; run end to end on the laptop |
| **Conversation:** speech recognition by Meta MMS on the laptop, or Muse Voice Transcribe through the Meta Model API (`serve --listen muse`); Muse Glimmer on the laptop, or Muse Spark through the API (`serve --think spark`), reads what the person said into fixed facts; the rules decide; Meta MMS-TTS speaks, with numbers and symbols turned into words first | Built; run end to end in Hindi, offline and in API mode. A reply to a short answer or a danger is ready in 1–5 s, most of it the voice; one the model reads takes 2–5 s with Spark, 5–12 s with Glimmer (warm, on a quiet laptop) |
| **Listening compared:** Muse Voice Transcribe against MMS on short answers in Hindi, English and Spanish | Done Oct 29 (below) |
| **Reading compared:** Muse Spark against Muse Glimmer on Hindi turns: unclear answers, plain ones and longer ones | Done Oct 29 (below) |
| If the model fails or the network drops, nothing counts as read: the coach says it didn't catch that and asks again | Built, tested |
| Symptom words, and a carbon monoxide alarm heard sounding, skip the language model and get the emergency line at once | Built, tested |
| Answers that would take a danger off the list must be plain; the model's readings of that kind are read back first | Built, tested; checked live with MMS and macOS voices |
| **Rating plate** read by Muse Glimmer (or Spark) into fixed fields, sanity-checked, read back; the CO advice never depends on it | Built; Spark read a drawn test plate right; real plates on Oct 31 |
| Screening: what they heat and cook with, heat and cold, downed power lines | Built (asked one question at a time) |
| **Overnight check-in:** a calendar reminder reopens the page; symptoms, "still outside?" and the CO alarm are asked again, as strictly; a plain-English summary for family goes out through the phone's share sheet | Built, tested; "Check in now" for a demo |

## Prior work

- **[Flood Father](https://github.com/aabdullakh/Hurricane-and-flood-voice-assistant-for-Houston-)** (2026): a phone
  voice agent for Houston floods in English and Spanish that reports risk as unknown when data are stale and never
  calls an area "safe". Aftermath uses the same "never say safe" framing; it didn't invent it.
- **Briggs & Stratton, US 11,220,964 B2:** a generator with a proximity sensor that alarms when its exhaust is too
  close to an object, for the same reason: exhaust drifting in through a door or window.
- **Kofax, US 9,946,954 B2:** distance from image data and a camera's intrinsics; pinhole ranging with an object of
  known size is textbook.
- **LifePod (US 10,258,295 and family):** voice check-ins that alert a caregiver. Daily check-in apps such as Snug
  Safety text a contact after a missed tap.
- CO-shutoff generators (Champion CO Shield, Honda CO-MINDER) and smart CO alarms act once CO is already present.

None of these is new here. What Aftermath puts together is a phone that measures the hazard rather than describing
it, a deterministic rule that cites its source, coaching in the person's language, and a follow-up that knows the
generator is running at 2 a.m.

## How the distance is measured

SAM 3.1 finds the door in a photo taken where the generator stands. The door's height in pixels, measured down the
middle of its mask, and the focal length in pixels give the distance by the pinhole model. The focal length comes from
the photo's EXIF 35 mm-equivalent focal length over the image diagonal, so it works for any phone and for downscaled
copies. Some photos carry no lens data: on Oct 29 the iPhone's camera inside Safari (Take Photo, from the page's door
button) left it out, while a Camera-app photo picked from Photo Library kept it. Such a photo is measured as if taken
at 1× through a 23 mm-equivalent lens, the widest 1× camera common on phones, so a 1× photo reads no farther than it
is (an iPhone 15 Pro's 24 mm photo about 4% closer). Taken at 0.5× it would read nearly twice as far as it is, so the
coach gives that distance only "if the camera was at 1×" and asks; until a plain yes the verdict is "only if the
camera was at 1×", never "meets the guidance" (too close stays too close). Whether Safari's camera at 1× sees exactly
what the Camera app does is still to be checked against the tape. The door's height is an assumption: 80 in is the standard US door leaf. The distance is proportional to the
height assumed, so a shorter door read as 80 in comes out too far, the unsafe direction (a taller one comes out too
close). The coach asks whether it's a regular door, and a height the person gives rescales the reading. Only doors are
used: windows have no standard size. A distance counts only once the generator is known to be outside: for a photo
taken before that, the coach gives the distance "if the generator is there and outside" and asks, and until a plain
yes the verdict is "only if it's outside", never "meets the guidance".

Six iPhone 15 Pro photos of one double door, tape-measured on Oct 29:

| Tape | 10 ft | 10 ft | 15 ft | 20 ft | 25 ft | 30 ft |
|---|---|---|---|---|---|---|
| Measured (80 in leaf) | 10.0 | 10.0 | 15.1 | 20.4 | 25.8 | 30.2 |
| Error | +0.2% | +0.3% | +0.5% | +1.9% | +3.1% | +0.6% |

That's one door and one phone, so the error range used is a conservative ±6%, and the safety bands use its low end:
under 17 ft is too close, 17–23 ft is borderline (move it farther), and over 23 ft meets the guidance. A photo is
refused, with the reason, when it can't be measured honestly: no door found, or the door cut off. It warns about zoom, a tilted phone (seen in the door's taper), a garage-door
shape, a door off to the side, and a second door at a different distance.

## The rules and their sources

Generator distance guidance doesn't agree on a number. CDC says "Operate your generator outdoors more than 20 feet
from windows, doors, and vents"; CPSC's 2026 release says "at least 20 feet from homes and buildings"; NIST found
that 15 feet from open windows wasn't far enough and that "perhaps as much as 25 feet" may be needed. The rules follow
all of them at once: outdoors only, more than 20 feet from any door, window or vent, farther is better, exhaust pointed
away, never in a garage, shed or porch even with the door open, a battery CO alarm, and the symptoms-and-fresh-air
line, which gives 911 and Poison Control (1-800-222-1222), as CDC's power-outage page does. Downed-line distance (35 ft; Tampa Electric says 30, some utilities 40) comes from utilities, not a federal agency,
and is labelled so. Every quote, its page and when it was checked are in `src/aftermath/guidance.py`.

## How it understands answers

Speech recognition makes mistakes, and so does the language model, so understanding leans one way. Anything that adds
a danger counts at once. Anything that would take one off the list has to be plain. A short answer is read without the
model: "हाँ, बाहर है", "नहीं है", "इनमें से कुछ नहीं", "sí, ya está afuera" or "no hay" count, while a lone "जी" (also
"pardon?"), "पता नहीं", "शायद", a lone "se" (which MMS can make of "sí"), "no sé" or "creo que sí" don't. Hindi puts
the "no" late ("अलार्म नहीं है"), and that counts, but a "नहीं" that's only a tag at the end ("तार गिरे हैं, नहीं?")
doesn't. What the model reads that way is read back first ("मैंने समझा कि जनरेटर बाहर, खुली जगह में है। क्या यह सही
है?") and counts only on a plain yes. A question left unanswered is asked once more, with the words to answer in,
then left for later.

Two things skip the model and get the emergency line at once, and nothing else: symptom words ("मुझे चक्कर आ रहे हैं",
"I have a headache") and the carbon monoxide alarm heard sounding ("अलार्म बज रहा है", "the alarm is going off", "la
alarma está sonando", or "हाँ, बज रहा है" in answer to the alarm question). A beep that may only be a low battery
counts as the alarm too, as CPSC says: "Never ignore an alarming CO alarm!" A negation stops either ("अलार्म नहीं बज
रहा", "nobody has a headache"), but a "no" that answers the question before doesn't ("No, the alarm is beeping"), and
neither does a tag ("…बज रहा है ना?").

This comes from testing it. On Oct 29, with macOS voices saying short answers, MMS turned "Sí, tengo." into "sceg" and
"No sé." into "esmose". Asked what they meant, Glimmer read "esmose" as "no fallen lines", and "sceg" (said to the CO
alarm question) as a generator in a shed, filling in every other field too, after the person had plainly said the
generator was outside. So a word or two that answer nothing are asked again rather than guessed at, and a reading with
more facts than the reply has words, or more than half of all the facts at once, is dropped and the question asked
again. Muse Spark did the same to a ten-word answer (the gas oven and the cold it mentioned, and "no" for nearly
everything else) until its schema was sent strict, with "not stated" as a choice for every fact.

## Listening: Voice Transcribe and MMS

On Oct 29, 60 short answers ("हाँ", "नहीं", "पता नहीं", "Sí.", "No sé.", "Yes.", "I don't know." and others), each said
by macOS voices and the app's own MMS voices, went to both listeners as the same 16 kHz WAV, raw and with half a
second of silence on each side as a push-to-talk recording has (`scripts/compare_listeners.py`). Each transcript was
scored by what the conversation does with it, next to what it does with the answer itself.

| With the silence | Hindi | English | Spanish | Latency (p50 / p90) |
|---|---|---|---|---|
| MMS-1B, on the laptop | 5 of 10 | 16 of 20 | 17 of 30 | 23 / 25 ms (40 / 83 ms on a busy laptop) |
| Muse Voice Transcribe, Meta Model API | 6 of 10 | 19 of 20 | 26 of 30 | 0.81 / 0.99 s |

- Not one of the 240 transcripts made the coach take a danger off the list. Every miss was safe: the person was
  asked again, or the model read it and the reading was read back.
- Voice Transcribe returns an empty transcript for a lone "Sí." 0.4 s long with no silence around it, and hears it
  with 0.5 s of silence on each side, so the app adds that (about one billed second a turn).
- A lone "हाँ" is the hard case: MMS heard none of four ("fhcc", "खत"), Voice Transcribe one.
- These are synthetic voices on clean audio. Phone recordings with a running generator nearby come next.

API mode uses Voice Transcribe; MMS stays for when there's no internet after a storm.

## Reading: Spark and Glimmer

On Oct 29, Muse Glimmer on the laptop and Muse Spark through the Meta Model API each read the same 156 turns with the
app's own prompt (`scripts/compare_readers.py`): the test suite's 15 unclear Hindi answers ("जी", "पता नहीं", "शायद",
"fhcc", "तार गिरे हैं, नहीं?" and the rest) to each of the 8 questions whose answer can take a danger off the list, its
8 plain Hindi answers, and 28 longer turns, 22 in Hindi and 6 in English, each with the facts it states.

| | Muse Glimmer 30B, on the laptop | Muse Spark, as the app asks it | Spark before its schema was strict |
|---|---|---|---|
| Plain Hindi answers read right | 8 of 8 | 8 of 8 | 8 of 8 |
| Longer Hindi turns read right | 21 of 22 | 22 of 22 | 21 of 22 |
| Longer English turns read right (or with a harmless extra fact) | 5 of 6 | 6 of 6 | 6 of 6 |
| Unclear Hindi answers the model read as taking a danger off the list | 16 of 120 | 15 of 120 | 16 of 120 |
| ... that the conversation then took off the list | 0 of 120 | 0 of 120 | 0 of 120 |
| Turns where the model filled in nearly every field | 3 of 156 | 0 of 156 | 8 of 156 |
| Time to read a longer Hindi turn, median / max | 13.1 / 18.6 s | 1.4 / 1.8 s | 1.0 / 1.5 s |
| Cost of the 156 turns | none (local) | $0.37 | $0.29 |

- No model's mistake reached the person: for none of the unclear answers did the conversation take a danger off the
  list. Most of what the models read that way was a lone "जी", "है" or "हा" taken as yes (fair: "जी" often means
  yes), which the conversation counts as unclear and asks again.
- Sent the schema loose, Spark with little reasoning sometimes wrote nearly every field, mostly "no" (8 of
  156; with more reasoning, 3 of 156, at twice the time). Sent strict, with "not stated" as a choice for
  every fact, it didn't. Glimmer did it 3 times, each to an unclear answer. The conversation drops
  such a reading, and asks again.
- Asked "पेट्रोल का एक टैंक कितनी देर चलता है?", Spark said «यह जनरेटर के मॉडल, टैंक के आकार और लोड पर निर्भर करता है; सटीक जानकारी के लिए अपने जनरेटर की मैनुअल देखें या निर्माता से पूछें।» and Glimmer «मुझे नहीं पता। यह जानकारी जनरेटर के मैनुअल या निर्माता को पता होगी।» Asked
  "How long will a tank of gas last?", Glimmer said only «The coach will cover it.»
- Glimmer's times were measured while other work shared the laptop's GPU. Earlier that day, on a quiet laptop, a
  reply that needed Glimmer took 5–12 s.

API mode reads with Spark; Glimmer stays for when there's no internet.

## The overnight check-in

Carbon monoxide can poison people in their sleep, so the coach offers one check-in during the night.

- **Add to calendar** gives the phone an event at the chosen time (2:00 AM unless changed), with an alert. Its link
  reopens the page for the check-in. The event holds the page's address and nothing about the person.
- The check-in asks three things again, whatever was said before: whether anyone has a headache, dizziness, weakness
  or nausea (a yes gets the emergency line and nothing else), whether the generator is still outside where it was
  measured, and whether the carbon monoxide alarm works. An answer that reassures counts only when it's plain, or
  once it's read back and confirmed, as in the rest of the conversation.
- **Send the summary to your family** opens the phone's share sheet, or copies the summary where there is none. It's
  in plain English: what was measured (the band and the low end of the distance) and when, what the check-in found,
  any danger, and what's still unknown. A missed check-in comes first: "No answer at the 2:00 AM check-in." It never
  says "safe" or "all good", and it's written from the facts, not from what was said, so it holds no name, address or
  location; only the optional note the person types is theirs.
- **Check in now** runs the check-in at once, for a demo.

The laptop has to stay awake and on the same Wi-Fi through the night (`caffeinate -dis uv run aftermath serve`).
Conversations are kept in memory: if the server restarts, the check-in starts from nothing, and the summary says so.

## What it isn't

It isn't a CO detector, it doesn't replace 911 or local officials, and it never says a placement is "safe": the most
it says is that a placement meets the guidance and that farther is better. Its measurements come with their error
ranges, shown on screen.

The builder, a native Hindi speaker, reviewed all of the Hindi on Oct 29: the 144 lines first put to them, approved
with one change of wording (the emergency line now says «कार्बन मोनोऑक्साइड पॉइज़निंग», Ready.gov's term); three lines
that list missed; and the lines written since, for a door photo that didn't record its lens, the page's Listen button
and the plate read-back's shorter forms. A test pins each reviewed line by a hash of its text
(`tests/reviewed_hindi.json`), so a line that changes, or a new one, fails until it's reviewed.

Not natively reviewed yet: the Spanish sentences that are the app's own rather than an agency's. Those are the
measurement and situation sentences ("El generador está a unos … de la puerta…", "Está demasiado cerca.",
"Funcionando en una galería exterior…", "Esta foto no dice con qué lente se tomó…"), the downed-line, medical-plan and
CO-shutoff lines, the first and last sentences of the alarm line ("Su detector … le está avisando de un peligro que
puede matar. No busque la causa.", "Cuenten que todos hayan salido…"), the questions and the check-in's lines, the
read-backs, the photo and plate notes, and the page's labels. The demo doesn't use Spanish.

## Run it

Needs [uv](https://docs.astral.sh/uv/) and an Apple silicon Mac for the local models (SAM 3.1 through mlx-vlm; Muse
Glimmer 30B through [Ollama](https://ollama.com), `ollama pull muse-glimmer:30b-mlx`; the MMS speech models download
on first use).

```bash
uv sync
uv run pytest
uv run aftermath door ~/Photos/door.HEIC                 # distance, band and advice for one photo
uv run aftermath door IMG_*.HEIC --truth-ft 10,15,20,25,30 --language hi
uv run aftermath serve                                   # the phone page (set up HTTPS first, below)
caffeinate -dis uv run aftermath serve                   # the same, keeping the Mac awake for the night's check-in
uv run aftermath serve --keep data/filming               # also saves each recording and photo sent, for testing
uv run aftermath serve --listen muse                     # hears speech with Muse Voice Transcribe (MODEL_API_KEY)
uv run aftermath serve --listen muse --think spark       # API mode: also reads with Muse Spark
uv run python scripts/compare_listeners.py               # the comparisons above (MODEL_API_KEY for the API models)
uv run python scripts/compare_readers.py
```

Photos, recordings, certificates and model caches stay in `data/`, which is never committed.

### The phone page over HTTPS

A phone's browser only allows the microphone on a secure page, so the laptop serves the page with its own
certificate. `scripts/make_certs.sh` makes a local certificate authority (once) and a server certificate for the
laptop's network address and `.local` name, with macOS's own `openssl`. The authority can only vouch for local
addresses and `.local` names, so its key couldn't be used to impersonate a public website to the phone.

1. On the Mac, once: `scripts/make_certs.sh`. It writes `data/certs/aftermath-ca.crt`.
2. AirDrop `data/certs/aftermath-ca.crt` to the iPhone and accept it. The iPhone says the profile was downloaded.
3. On the iPhone: **Settings › General › VPN & Device Management**, tap **Aftermath local CA (this laptop only)**,
   then **Install** (enter the passcode), **Install** again, and **Done**.
4. **Settings › General › About › Certificate Trust Settings**: turn on **Aftermath local CA (this laptop only)**
   and tap **Continue**.
5. On the Mac: `uv run aftermath serve`. It prints the page's address, such as `https://<laptop-ip>:8443/`.
6. On the iPhone, on the same Wi-Fi, open that address in Safari, tap **शुरू करें** (or **Start**), and allow the
   microphone and the camera when asked.

If the Mac's network address changes, run `scripts/make_certs.sh` again: only the server certificate is remade, and
the phone needs nothing new. When you're done, remove it on the iPhone under **Settings › General › VPN & Device
Management**, **Remove Profile**.

## Meta models

- **SAM 3.1** (open weights, SAM License), locally through mlx-vlm (`mlx-community/sam3.1-bf16`): finds the door.
- **Muse Glimmer 30B** (open weights, Apache 2.0), locally through Ollama: reads what the person says into fixed
  facts, answers their other questions, and reads the rating plate. It never decides the safety advice.
- **Meta MMS** (CC BY-NC 4.0): speech recognition (`mms-1b-all` with the Hindi, English or Spanish adapter) and
  speech (`mms-tts-hin`, `mms-tts-eng`, `mms-tts-spa`), locally. Each voice knows only its own characters (none has
  punctuation; the Hindi one lacks most digits), so numbers become words and the text is cut at its punctuation
  before it's spoken (`speakable.py`).
- **Muse Voice Transcribe** through the Meta Model API: the listener in API mode, and compared against MMS above.
- **Muse Spark** (`muse-spark-1.3`) through the Meta Model API: the reader in API mode, compared against Glimmer
  above. Each request asks Meta not to store the response (`store: false`), sets the reasoning effort (minimal, then
  low if the answer is unusable) and sends the schema strict. Photos go without their metadata, location included.

In API mode, the recording goes to Voice Transcribe, and the words heard and any rating-plate photo go to Spark. Door
photos never leave the laptop.

## Built during the hackathon

Everything in this repository was written during the hackathon, after the kickoff on October 26, 2026. Nothing
pre-existing is included apart from the public libraries declared in `pyproject.toml`. The response cache and the
SAM 3.1 and Glimmer clients were written on Oct 26 for the builder's earlier hackathon ideas and carried over; the door
measurement started as a decision spike that evening.

| Component | Built |
|---|---|
| Response cache; local SAM 3.1 (MLX) and Muse Glimmer (Ollama) clients | Oct 26 |
| Door-distance spike and Spanish voice-turn spike | Oct 26 |
| Project skeleton; cited guidance; deterministic safety rules; English and Spanish wording | Oct 29 |
| Door distance module with refusals, warnings and error range; `aftermath door` | Oct 29 |
| Rating plate reader; speech in and out; the conversation; the phone page over HTTPS with a local CA | Oct 29 |
| Hindi; Spanish from the agencies' own text; Muse Voice Transcribe and its comparison with MMS; speakable text | Oct 29 |
| Muse Spark as the API mode's reader, and its comparison with Glimmer; failed reads asked again | Oct 29 |
| The overnight check-in: the calendar reminder, the check-in questions, and the summary for family | Oct 29 |

## Licence

Not chosen yet.
