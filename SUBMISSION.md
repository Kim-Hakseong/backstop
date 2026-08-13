# SUBMISSION.md — Backstop

**Title**: Backstop
**Tagline**: Replay your agent's last six weeks before you ship the next one.
**Track**: The Fortified Enterprise Fleet
**Built with**: Google ADK · Gemini 3.5 Flash (Vertex AI) · Cloud Run · Pub/Sub · Firestore · OpenTelemetry

> Every number below is measured output from `make bench` (2026-08-12).

### Submission context

**Track**: The Fortified Enterprise Fleet ($20,000 + $2,000 credits)
**Total prize pool**: $175,000 + Google Cloud credits

Two further categories apply to this entry. Neither needs a separate submission — they follow from what this project is.

| Category | Size | Why it applies |
|---|---|---|
| **Individual / Hobbyist** | 2 × $10,000 | Solo entry |
| **Best Architectural Design** | 2 × $5,000 | The decision path is a pure function (zero network or model imports, enforced by a CI import-graph check), the two gates are separated by when they run (execution time vs. deploy time), and all state converges on a single append-only ledger |

Best Multimodal UX does not apply. There is no chat UI and no multimodal input in this product, and that is deliberate.

---

## Inspiration

**Two incidents happened in our own system while building this. Both appeared only in the deployed service; the unit tests were green through both of them.**

**One — the same email went out twice.** Pub/Sub delivered three ticks concurrently, two workers ran the same workflow step, and the ledger recorded `mail.send#MSG-CA2473` twice. The idempotency check was ordered "look up, execute, record." Both workers looked, both saw no prior record, and both proceeded.

**Two — a step disappeared silently.** During a crash-resume test the workflow reported `cursor 12/12` — complete — **while only 11 side effects had actually occurred**. A redelivery arrived inside the claim lease, so a legitimate retry was misread as a duplicate and skipped, and the cursor advanced anyway. No exception, no warning. The system reported success.

These two failures point in opposite directions. One did the same work twice; the other never did the work at all. **What they share is that no human could have noticed either one.** There is nowhere to ask whether a purchase order went out twice, and when a workflow says "done," nothing contradicts it. We produced both by running a six-week workflow for a single day. It is worth considering how often they occur in an agent that genuinely runs for weeks.

Google put the same question in the title of this hackathon's own workshop — **"why does a resumed agent order two laptops?"** An agent running in the background for weeks will eventually crash, eventually resume, and eventually have its code changed. At that moment, nobody is deciding whether an already-emitted side effect is about to be emitted again.

**This is the friction Backstop removes**: the question "if I ship this version, which of the last six weeks of work will it redo?" gets answered with an exit code instead of a guess. On our seed ledger the answer is **three duplicate purchase orders**, and the gate blocks the deploy.

Most submissions in this competition show what an agent **accomplishes**. We took the opposite side. We record what the agent did over the past six weeks, and before a new version ships we rewind those six weeks and compute what this version would have re-executed. **The climax is not "the agent did it" — it is "the deploy was blocked."**

## What it does

Backstop has three parts.

**1. The ledger.** ADK's `before_tool_callback` and `after_tool_callback` intercept every tool call. Each call is written to Firestore with an idempotency key built from `(tool name, canonicalised argument hash, run scope)`, alongside an OpenTelemetry span ID. This is the first gate, at execution time — a side effect with the same key does not go out twice.

**2. Replay.** The ledger's events are fed back, in order, to the new agent version. The tool executor is swapped for a no-op collector, so calls leaving the process number **zero**. Only the intents are gathered. Loading six weeks of ledger (1,094 events, 42 side effects), replaying it, and reaching a verdict takes **1.7ms**.

**3. The divergence gate.** It takes the set difference between the side effects that actually went out and the intents collected during replay. There are three outcomes — `DUPLICATE` (about to redo something already done), `MISSING` (no longer does something it used to), `MUTATED` (same target, different value). A single `DUPLICATE` returns exit code 1 and the deploy is blocked.

**In Backstop, the LLM blocks nothing.** The gate is set arithmetic, a pure function, with unit tests attached. If `divergence.py` imports a network or model library, CI fails. Gemini 3.5 Flash is called only to write the one explanatory sentence at the bottom of a divergence card. **The replay and decision path make zero model calls**; generating the three explanations costs three calls (capped at five). Remove the model entirely and `DEPLOY BLOCKED` and exit code 1 are unchanged.

## How we built it

The subject-agent is an ADK agent running a six-week vendor onboarding workflow. A Pub/Sub `agent.tick` message advances it one step, and state persists in Firestore. It is only the specimen under audit, so it never exceeds five tools.

The core is how the replay harness swaps the execution mode. Inject `IntentCollector` into ADK's tool execution path and the agent believes it is calling tools while nothing leaves the process. To enforce that, a test monkey-patches sockets — a single network call during replay turns it red. Blocking sockets alone was not enough, so the test also asserts the stubs' side-effect lists stay empty, because our stubs need no network to cause an effect.

Time is injected everywhere. No `datetime.now()` call exists anywhere in the code; everything goes through `clock.now()`, and an AST-based test enforces it across the repository. That is what let us generate six weeks of ledger with no real waiting, and because that ledger is committed, anyone can run `make replay` with no API key and see the same divergences.

## Challenges we ran into

Six of them. The first two are fixed, and how they were fixed is most of what this product is. The remaining four are unsolved.

**Fixing the two incidents above changed the design twice.** The duplicate leaked because gate ① was ordered "look up, execute, record." The key is now claimed **before** the tool runs, and the Firestore document ID *is* the idempotency key, so uniqueness is enforced by a **storage constraint** rather than by application logic. That introduced the opposite bug — a crash redelivery landing inside the claim lease was misread as a duplicate, and the cursor advanced past work that never happened. So blocking now means two different things: **blocked by a committed effect is work already done, so advance the cursor; blocked by an in-lease claim is work still unfinished, so hold it.** The gate's `DUPLICATE` and `MISSING` categories are not invented taxonomy — they are the names of these two incidents.

**A crash after claiming but before committing is indistinguishable.** Dying just before the tool executes and dying just after it executes but before the record is written look identical in the ledger. The window is milliseconds, but it is real, and reclaiming in the second case sends the side effect twice. Today we only buy time with a 25-second lease. The real fix is a lookup API on the tool side or a two-phase commit, and we left it out because stubs cannot prove it works.

**Changing a prompt shifts the idempotency key.** When argument canonicalisation changes, a semantically identical call produces a different key. The demo's three divergences are exactly this — v3 changed `vendor_id` from `"acme-corp"` to `"ACME Corp"`, purely cosmetically, and the gate calls it duplicate purchase orders. **That is not a gate malfunction: the order really would go out a second time.** The limitation is that the gate cannot separate "a harmless relabelling" from "genuinely a different vendor." We version the canonicalisation rules (`CANON_VERSION`) so a rule change is detectable, but the judgement is not automatic.

**The six-week ledger is generated by simulation.** It is not a real six-week operational log; it is compressed into existence with a FrozenClock. The event distribution and failure rates are values we chose, and it does not carry the messiness of real production traffic.

**We did not integrate Memory Bank or Agent Registry.** They are recommended Fleet-track components, but the learning cost did not fit the sprint. Memory is served by a Firestore implementation behind the same interface.

**The Narrator fabricates.** One of the three divergence explanations written by Gemini asserted the matter "has already been logged in an existing incident" — a fact that does not exist. So on screen this text is the lowest, dimmest line of the card, and `make gate` defaults to deterministic pre-written sentences. The verdict is identical either way. This is the one place in the product that is genuinely an LLM wrapper, which is exactly why it is isolated from the decision path.

## What's next for Backstop

Managing the ledgers of several agents registered in Agent Registry behind one gate; today it handles a single agent's ledger. And joining Model Armor's blocked events into the ledger, so the gate can also compute "this version would have let 2 of the 12 past prompt-injection attempts through."

---

## Submission checklist

| Item | Status | Link |
|---|---|---|
| Demo video (under 3 min, **fully public** YouTube/Vimeo) | ☐ | Unlisted is not acceptable — the Rules say "publicly visible" |
| Code repository (public) | ☐ | |
| **Architecture diagram** (image, required) | ☑ | `docs/architecture.svg` (self-contained, fonts embedded) · `docs/architecture.png` (3200×1800, 2x) |
| Write-up, 5 sections | ☑ | This file |
| Deployed URL (console) | ☑ | https://backstop-api-5nohynuexa-uc.a.run.app/ |
| Track selected: Fortified Enterprise Fleet | ☐ | |
| Built-with tags: ADK / Gemini / Cloud Run / Pub/Sub / Firestore | ☐ | |

---

## Video shot list (3 minutes, 3 cuts maximum)

| Time | Screen | Narration | Preparation |
|---|---|---|---|
| 0:00–0:10 | Timeline full screen (6 weeks, 1,094 dots, 3 red markers at week 4) | "This agent has been running in the background for six weeks" | Console preloaded, browser fullscreen, bookmarks bar hidden |
| 0:10–0:30 | Same screen held | "We changed the code last week. Who decides whether it can ship?" | Minimal mouse movement |
| 0:30–0:50 | Terminal, run `make gate` | "We feed six weeks of events back into the new version" | Font 18pt or larger, shortened prompt |
| 0:50–0:55 | v3 gate result — instant. Four numbers on screen (1,094 events / 1.7ms / 0 external calls / 3 blocked) | "Six weeks finished in 1.7 milliseconds. Zero external calls" | **No progress bar.** Replay really is 1.7ms, so it ends instantly. Do not stage it slower |
| 0:55–1:05 | **Same command against v1** → `DUPLICATE 0` / `DEPLOY ALLOWED` / exit 0 | "Replay the version that wrote the ledger and you get zero. This gate is not always red" | `--version v1`. The control run is the point of this segment |
| 1:05–1:10 | Both results side by side (left v3 BLOCKED / right v1 ALLOWED) | "One version is the only difference" | Split terminal, or one composed still |
| 1:10–1:30 | Click a red marker → divergence card | "Three of them were duplicate purchase orders" → `DEPLOY BLOCKED` | Verify card contents beforehand |
| 1:30–1:50 | Split screen: 12 lines of `divergence.py` + `pytest -q` passing | "The block is set arithmetic. It is not the LLM" | Code highlighted, test output prepared |
| 1:50–1:55 | **Cloud Run console → live `.run.app` call** (5 seconds) | "This is not local. It runs on Cloud Run" | From the console service list (backstop-api, us-central1), click the URL through to a `/health` 200 in the browser, in one shot. Sign in and prepare tabs in advance |
| 1:55–2:15 | Architecture diagram, one cut (20 seconds) | Point out the three required technologies | Same image file as the submission |
| 2:15–2:30 | Zoom on `LLM calls during replay: 0` | "Zero model calls in the decision path" | Confirm the measured number |
| 2:30–2:50 | `POST /admin/kill` → crash in the logs → resume | "Even after a crash and resume, the side effect does not go out twice" | Rehearse three times. If it fails, reuse the recorded take |
| 2:50–3:00 | Four hero numbers + Cloud Run URL, held still | Silence, or one line | Subtitle font IBM Plex Mono |

**Why 0:50–1:10 is a control run**: replay takes 1.7ms, so there is no honest way to spend 20 seconds on a "timeline filling up" shot — you would have to fake the animation, which violates the motion rules in Design.md. Instead we **run the same command again against v1**. The first thing a judge suspects of any deploy-gate demo is "isn't that just always red?", and ten seconds of control run answers exactly that. It is a stronger 20 seconds than a progress bar.

**Filming principles**: three cuts maximum. Heavy editing invites doubt about whether it really runs. Screen capture at 1920×1080, microphone recorded separately afterwards.

**Why the 1:50 cut exists**: the Overview requires "approximately 4-minute demo video **proving backend runs on Google Cloud**." We keep the 3-minute structure (which is under 4 minutes, so compliant), but the proof that the backend runs on Google Cloud has to be shown once on screen rather than asserted. The five seconds came out of the architecture diagram segment (25→20 seconds). **The 2:30–3:00 blocking climax is untouched.**
If the live call fails on the day: substitute the Cloud Run console request-log screen, which still proves the deployment. Do not reshoot.

---

## Final 2-hour pre-submit checklist (08-31 19:00–21:00 KST)

1. Open all four links in a private window — video / repository / console URL / diagram
2. Clone the repository → `make setup && make replay` in an environment with no API key
3. Run `make bench` → reconcile its numbers against the README, the write-up, and the video subtitles
4. Re-check from a stranger's perspective that the top three README lines are enough to reproduce
5. Confirm the "this ledger is generated by simulation" notice appears in both the README and the write-up
6. Confirm the architecture diagram carries the Gemini 3.5 Flash / Google ADK / Cloud Run · Pub/Sub · Firestore labels
7. Devpost form: track = Fortified Enterprise Fleet
8. Devpost form: enter the built-with tags
9. Confirm video length is under 4 minutes (ours is 3) and the visibility is **fully public**. The Rules say "uploaded to and made publicly visible on YouTube or Vimeo" — do not use unlisted
10. ~~Check the Rules tab for IP and open-source terms~~ — done 2026-08-12. Entrants retain IP; Google receives a non-exclusive evaluation and promotion licence. Open source is permitted subject to its own licences → font OFL notice in place
11. Submit → **confirm the "Submitted" status with your own eyes**
12. After submitting, open the submission page on another device and confirm all four attachments render
