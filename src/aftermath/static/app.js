// The phone page: start a conversation, talk, photograph the door and the generator's label, and show what the
// rules say and the sources behind it. Everything is sent to this laptop (which, in API mode, asks the Meta Model API).

// The page's words in each language, from /api/text (phrases.PAGE, reviewed with the coach's lines).
let TEXT = null;

// Opened from the check-in reminder: /?checkin=<conversation>&language=<its language>.
const params = new URLSearchParams(location.search);
let checkinFor = params.get("checkin");
let language = ["hi", "en", "es"].includes(params.get("language")) ? params.get("language") : "hi";
let session = null;
let summaryText = "";
let recorder = null;
const moments = {};
const $ = (id) => document.getElementById(id);
const player = $("player");
const SILENCE = "data:audio/wav;base64,UklGRiQAAABXQVZFZm10IBAAAAABAAEAQB8AAIA+AAACABAAZGF0YQAAAAA=";

function labels() {
  const t = TEXT[language];
  document.documentElement.lang = language;
  $("subtitle").textContent = t.subtitle;
  $("welcome-text").textContent = checkinFor ? t.checkinWelcome : t.welcome;
  $("begin").textContent = checkinFor ? t.startCheckin : t.begin;
  $("talk-label").textContent = recorder ? t.stop : t.talk;
  $("door-label").textContent = t.door;
  $("plate-label").textContent = t.plate;
  $("advice-title").textContent = t.adviceTitle;
  $("not-911").textContent = t.notNine11;
  $("checkin-banner").textContent = t.checkinBanner;
  $("tonight-title").textContent = t.tonight;
  $("tonight-text").textContent = t.tonightText;
  $("time-label").textContent = t.checkinTime;
  $("add-calendar").textContent = t.addCalendar;
  $("check-now").textContent = t.checkNow;
  $("note-label").textContent = t.note;
  $("share").textContent = t.share;
  $("preview-label").textContent = t.preview;
  $("listen-label").textContent = t.listen;
  $("tap-yes").textContent = t.lensYes;
  $("tap-no").textContent = t.lensNo;
  document.querySelectorAll(".language").forEach((b) => b.classList.toggle("chosen", b.dataset.language === language));
}

// The line under the buttons: what the page is waiting for (with a spinner), or what went wrong.
function status(message, waiting = false) {
  $("status").textContent = message || "";
  $("status").classList.toggle("waiting", Boolean(message) && waiting);
}

// The conversation so far. The latest turn is in the reply box above, so the list shows the turns before it.
function say(who, text) {
  if (!text) return;
  const item = document.createElement("li");
  item.className = `${who} current`;
  item.textContent = text;
  $("log").appendChild(item);
}
function turnOver() {
  $("log").querySelectorAll(".current").forEach((item) => item.classList.remove("current"));
}

// A text's sentences (each ends in . ? ! or । before a space or the end).
function sentenceList(text) {
  const out = [];
  let start = 0;
  for (let i = 0; i < text.length; i += 1) {
    if (".?!।".includes(text[i]) && (i + 1 === text.length || /\s/.test(text[i + 1]))) {
      out.push(text.slice(start, i + 1).trim());
      start = i + 1;
    }
  }
  if (text.slice(start).trim()) out.push(text.slice(start).trim());
  return out;
}

// A text's first sentence and the rest ("" if it has one sentence).
function sentences(text) {
  const list = sentenceList(text || "");
  return [list[0] || "", list.slice(1).join(" ")];
}

// What a long reply shows before "…" opens the rest (the voice says it all): its open question, from the last
// question on, unless the card above already asks it; otherwise its first sentence. "" to show it whole.
function brief(text, asked) {
  const list = sentenceList(text);
  if (text.length <= 110 || list.length < 2) return "";
  let last = -1;
  list.forEach((sentence, i) => { if (sentence.endsWith("?")) last = i; });
  const question = last >= 0 ? list.slice(last).join(" ") : "";
  const shown = question && !(asked && question.includes(asked)) ? question : list[0];
  return shown.length < text.length ? shown : "";
}

// The coach's latest reply, just under the verdict and above the buttons: a refusal said only in the conversation
// further down was missed (Oct 29). A long one is folded (see brief). In an emergency it's shown whole, its first
// sentence (get to fresh air, call 911) leading in bold, with a button that calls 911.
let replyFull = "";
function showReply(text, refused, emergency, more, asked) {
  if (!text) return;
  const box = $("reply"), shown = $("reply-text");
  replyFull = more && !box.hidden ? `${replyFull} ${text}` : text;
  if (emergency) {
    const [first, rest] = sentences(replyFull);
    shown.replaceChildren(Object.assign(document.createElement("strong"), { className: "lead", textContent: first }),
      rest ? ` ${rest}` : "");
  } else {
    const short = refused ? "" : brief(replyFull, asked);
    shown.replaceChildren(short || replyFull);
    if (short) {
      const open = Object.assign(document.createElement("button"), { className: "more", textContent: "…" });
      open.setAttribute("aria-expanded", "false");
      open.addEventListener("click", () => shown.replaceChildren(replyFull));
      shown.append(" ", open);
    }
  }
  box.classList.toggle("refused", Boolean(refused));
  box.classList.toggle("emergency", Boolean(emergency));
  $("call").hidden = !emergency;
  box.hidden = false;
}

// After a reply, the verdict's headline goes to the top of the screen, with the reply under it. A refused photo leaves
// the verdict as it was, and an emergency is said in the reply, so then the reply goes to the top instead.
function reveal(urgent) {
  const banner = $("checkin-banner");
  const target = urgent ? $("reply") : banner.hidden ? $("verdict") : banner;
  if (target.hidden) return;
  requestAnimationFrame(() => target.scrollIntoView({ behavior: "smooth", block: "start" }));
}

// Under the photo, the verdict's explanation: its first sentence, and the rest and the measurement's limits a tap
// away. When the reply just below says it already, only the limits are left here. (The explanation is also in the
// advice list further down, with its sources.)
function explain(verdict, limits, said) {
  const [first, rest] = sentences(said ? limits : verdict);
  const more = said ? "" : limits;
  const folded = Boolean(rest || more);
  $("verdict-text").hidden = folded || !first;
  $("verdict-text").textContent = folded ? "" : first;
  $("verdict-more").hidden = !folded;
  $("verdict-more").open = false;
  $("verdict-more").classList.toggle("limits", said);
  $("verdict-first").textContent = first;
  $("verdict-rest").textContent = rest;
  $("limits").textContent = more;
  $("limits").hidden = !more;
}

// Replies queue up, so a second part waits for the first to finish instead of cutting it off. If the phone won't
// play one by itself (an iPhone back from its camera may not), a tap on "Listen" plays it.
const queue = [];
function next() {
  const audio = queue.shift();
  if (!audio) return;
  player.src = audio;
  player.play().then(() => { $("listen").hidden = true; }).catch((error) => {
    if (error.name !== "NotAllowedError") return next();
    queue.unshift(audio);
    $("listen").hidden = false;
  });
}
$("listen").addEventListener("click", () => {
  $("listen").hidden = true;
  next();
});
function play(audio) {
  if (!audio) return;
  queue.push(audio);
  if (player.paused || player.ended) next();
}
player.addEventListener("ended", next);

// A question that's easy to mishear ("was the camera at 1×?") also gets two buttons, shown only with the reply that
// asks it. A tap is a plain answer to that reply's question; the laptop ignores a tap on an older reply's buttons.
let tapping = null;
function choices(data) {
  tapping = data.tap ? { question: data.tap, turn: data.turn } : null;
  $("choices").hidden = !tapping;
}
function tap(answer) {
  if (!tapping) return;
  const { question, turn } = tapping;
  post(`/api/tap?session_id=${session}&question=${question}&answer=${answer}&turn=${turn}`, null,
    TEXT[language].thinking);
}
$("tap-yes").addEventListener("click", () => tap("yes"));
$("tap-no").addEventListener("click", () => tap("no"));

function render(data, more = false, scroll = true) {
  const t = TEXT[language];
  const emergency = data.advice.some((a) => a.level === "emergency");
  const urgent = Boolean(data.refused) || emergency;
  if (!more) turnOver();
  if (data.heard !== undefined) say("person", data.heard || "…");
  say("coach", data.text);
  $("conversation").hidden = !$("log").querySelector("li:not(.current)");
  if (!more) { // what the coach heard, above its answer
    $("heard-text").textContent = data.heard ? `«${data.heard}»` : "";
    $("reply-heard").hidden = !data.heard;
  }
  showReply(data.text, data.refused, emergency, more, data.action);
  choices(data);
  play(data.audio);

  const card = $("verdict");
  card.hidden = false;
  card.className = `card ${data.level}`;
  $("verdict-title").textContent = t.placement[data.placement] || data.placement;
  $("action").textContent = data.action || "";
  $("action").hidden = !data.action;
  const door = data.door;
  for (const id of ["feet", "range", "outline"]) $(id).hidden = !door;
  $("warnings").hidden = !door || !door.warnings.length;
  if (door) {
    $("feet").textContent = `${t.about} ${door.feet} ft (${door.metres} m)`;
    $("range").textContent = t.between.replace("{lowest}", door.lowest).replace("{highest}", door.highest);
    $("warnings").replaceChildren(...door.warnings.map((w) => Object.assign(document.createElement("li"), { textContent: w })));
  }
  explain(data.verdict, door ? door.limits : "", replyFull.includes(data.verdict));
  if (data.outline && !data.refused) { // a refused photo leaves the card on the last one measured
    $("outline").onload = () => { if (scroll && urgent) reveal(urgent); }; // above the reply, it pushes it down
    $("outline").src = data.outline;
  }

  const list = $("advice");
  list.replaceChildren(...data.advice.map((a) => {
    const item = document.createElement("li");
    item.className = a.level;
    item.append(a.text);
    const details = document.createElement("details");
    const summary = document.createElement("summary");
    summary.textContent = `${t.sources}: ${[...new Set(a.sources.map((s) => s.publisher))].join(", ")}`;
    details.append(summary);
    for (const s of a.sources) {
      const quote = document.createElement("blockquote");
      const link = Object.assign(document.createElement("a"), { href: s.url, textContent: s.publisher, target: "_blank" });
      quote.append(`“${s.quote}” `, link);
      details.append(quote);
    }
    item.append(details);
    return item;
  }));
  $("advice-section").hidden = data.advice.length === 0;
  $("checkin-banner").hidden = !data.checkin;
  refreshSummary().catch(() => {});
  if (scroll) reveal(urgent);
}

async function post(path, body, waiting) {
  status(waiting, true);
  $("choices").hidden = true; // whatever this brings, the buttons belong to the reply before it
  document.querySelectorAll("#actions button, #actions .button").forEach((b) => b.classList.add("busy"));
  try {
    let response = await fetch(path, { method: "POST", body });
    if (!response.ok) throw new Error(await response.text());
    let data = await response.json();
    render(data);
    if (data.more) {
      // The urgent part is playing (or, if there was none, "one moment"); the model reads the rest meanwhile.
      if (!data.audio) moment().catch(() => {});
      response = await fetch(`/api/talk/more?session_id=${session}`, { method: "POST" });
      if (!response.ok) throw new Error(await response.text());
      data = await response.json();
      render(data, true);
    }
    status("");
  } catch (error) {
    status(TEXT[language].failed);
    $("status").scrollIntoView({ behavior: "smooth", block: "nearest" });
    $("choices").hidden = !tapping; // nothing new came back: the last reply's buttons still answer it
    console.error(error);
  } finally {
    document.querySelectorAll("#actions button, #actions .button").forEach((b) => b.classList.remove("busy"));
  }
}

async function moment() {
  // "One moment", fetched once per language and played as soon as the person stops talking.
  if (!moments[language]) moments[language] = (await (await fetch(`/api/moment?language=${language}`)).json()).audio;
  play(moments[language]);
}

async function begin() {
  player.src = SILENCE; // a first, silent play inside the tap lets later replies play on iPhones
  player.play().catch(() => {});
  $("welcome").hidden = true;
  $("actions").hidden = false;
  $("log").replaceChildren();
  $("reply").hidden = true;
  // From the reminder, the check-in carries on from that conversation (or, if the laptop restarted, from nothing).
  const path = checkinFor ? `/api/checkin/start?session_id=${checkinFor}&language=${language}`
    : `/api/start?language=${language}`;
  checkinFor = null;
  const response = await fetch(path, { method: "POST" });
  const data = await response.json();
  session = data.session;
  render(data, false, false); // the greeting: the page stays at the top, by the language buttons
  $("tonight").hidden = false;
}

// The overnight check-in: a reminder for the phone's calendar, or the check-in now.
function nextCheckin() {
  const [hours, minutes] = ($("checkin-time").value || "02:00").split(":").map(Number);
  const at = new Date();
  at.setHours(hours, minutes, 0, 0);
  if (at <= new Date()) at.setDate(at.getDate() + 1); // the next time the clock shows it
  return at;
}

async function checkNow() {
  const response = await fetch(`/api/checkin/start?session_id=${session}`, { method: "POST" });
  if (!response.ok) {
    status(TEXT[language].failed);
    return;
  }
  const data = await response.json();
  session = data.session;
  $("log").replaceChildren();
  render(data);
}

// The summary for the family (plain English), kept up to date after every turn, so a tap shares it at once.
async function refreshSummary() {
  if (!session) return;
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || "UTC";
  const response = await fetch(`/api/summary?session_id=${session}&tz=${encodeURIComponent(zone)}`);
  if (!response.ok) return;
  summaryText = (await response.json()).text;
  $("summary-text").textContent = summaryText;
}

async function share() {
  const note = $("note").value.trim(); // the only place a name or an address can go: what the person types
  const text = note ? `${summaryText}\n\nNote: ${note}` : summaryText;
  if (navigator.share) {
    try {
      await navigator.share({ title: "Generator check-in", text });
      return;
    } catch (error) {
      if (error.name === "AbortError") return; // they closed the share sheet
    }
  }
  $("summary-details").open = true; // shown, to copy by hand if copying fails too
  try {
    await navigator.clipboard.writeText(text);
    status(TEXT[language].copied);
  } catch {
    status(TEXT[language].failed);
  }
}

async function talk() {
  const t = TEXT[language];
  if (recorder) {
    recorder.stop();
    return;
  }
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch {
    status(t.micDenied);
    return;
  }
  const chunks = [];
  recorder = new MediaRecorder(stream);
  recorder.ondataavailable = (event) => chunks.push(event.data);
  recorder.onstop = () => {
    stream.getTracks().forEach((track) => track.stop());
    const blob = new Blob(chunks, { type: recorder.mimeType });
    recorder = null;
    labels();
    $("talk").classList.remove("recording");
    post(`/api/talk?session_id=${session}`, blob, t.thinking);
  };
  recorder.start();
  $("talk").classList.add("recording");
  labels();
  status(t.listening);
}

function photo(input, path, waiting) {
  input.addEventListener("click", () => {
    // Inside the tap: a silent play keeps the reply after the camera playable, if nothing is playing now.
    if (player.paused && !queue.length) {
      player.src = SILENCE;
      player.play().catch(() => {});
    }
  });
  input.addEventListener("change", () => {
    const file = input.files[0];
    input.value = "";
    if (file) post(`${path}?session_id=${session}`, file, TEXT[language][waiting]);
  });
}

document.querySelectorAll(".language").forEach((button) => button.addEventListener("click", () => {
  language = button.dataset.language;
  labels();
  if (session) begin();
}));
$("begin").addEventListener("click", begin);
$("check-now").addEventListener("click", checkNow);
$("share").addEventListener("click", share);
$("add-calendar").addEventListener("click", () => {
  // Set just before the link opens: the reminder, at the next time the clock shows.
  $("add-calendar").href = `/api/checkin.ics?session_id=${session}&at=${encodeURIComponent(nextCheckin().toISOString())}`;
  setTimeout(() => refreshSummary().catch(() => {}), 1500); // the summary then says when the check-in is
});
$("talk").addEventListener("click", talk);
photo($("door"), "/api/door", "measuring");
photo($("plate"), "/api/plate", "reading");
fetch("/api/text").then((response) => response.json()).then((text) => {
  TEXT = text;
  labels();
  $("begin").disabled = false;
});
