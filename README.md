# Realtime Coding Interviewer

A mock technical-interview app. You get a LeetCode-style problem, an editor, and an
AI interviewer that listens to you think out loud, answers follow-up questions
without giving away the solution, notices when you stop paying attention, and
writes you a hiring-style evaluation at the end.

Everything runs in real time over a single Socket.IO connection: speech in,
speech out, webcam frames for attention tracking, and code execution in the
browser.

---

## What it does

| Feature | How it works |
| --- | --- |
| **Spoken conversation** | Browser Web Speech API for both directions. Your speech is transcribed and sent to the interviewer; its reply is spoken back and mirrored on screen as a caption. |
| **Attention tracking** | A ResNet18 classifier scores a webcam frame once per second as focused/distracted. Sustained distraction triggers a spoken nudge in your interviewer's persona. |
| **Personas** | `Friendly`, `Neutral`, and `Strict` change the interviewer's tone and how hard it pushes back. |
| **Hints, not answers** | The prompt forbids writing code or revealing solutions. Asking "just tell me the answer" gets you a conceptual nudge instead. |
| **Real code execution** | Python runs in the browser via Pyodide and is checked against real test cases — no server round-trip, no sandbox to secure. |
| **Final evaluation** | "End Interview" produces a markdown report: verdict, problem solving, communication, code quality, and what to work on. |

**Chrome only.** The Web Speech API is not implemented in Firefox and is
unreliable in Safari.

---

## Is this full stack?

Yes — and then some. It is a React SPA, a Python realtime backend, a computer
vision model, and an external LLM integration:

```
┌──────────────────────────────┐         ┌───────────────────────────────┐
│  Browser (React + Vite)      │         │  Backend (Python, uvicorn)    │
│                              │         │                               │
│  Monaco editor               │         │  Socket.IO event handlers     │
│  Pyodide (runs your Python)  │◄───────►│  ResNet18 attention model     │
│  Web Speech API (STT + TTS)  │ Socket  │  Prompt construction          │
│  Webcam capture @ 1 fps      │   .IO   │  Session state                │
└──────────────────────────────┘         └───────────────┬───────────────┘
                                                         │ HTTPS
                                                   ┌─────▼─────┐
                                                   │  Groq API │
                                                   └───────────┘
```

What it does **not** have: a database (questions are a JSON file, sessions live
in memory and die on disconnect), user accounts, or auth. If you are describing
this project, "full-stack realtime app with a CV model in the loop" is accurate;
"full-stack CRUD app" is not.

---

## Setup

**Prerequisites:** Python 3.11, Node 18+, a webcam, a microphone, Chrome, and a
free [Groq API key](https://console.groq.com/keys).

### 1. Backend

```bash
git clone <your-repo-url>
cd Realtime-Coding-Interviewer

python -m venv venv311
source venv311/Scripts/activate      # Windows (Git Bash)
# source venv311/bin/activate        # macOS / Linux

pip install -r requirements.txt

cp .env.example .env                 # then edit .env and add your key
```

Your `.env`:

```ini
GROQ_API_KEY=gsk_your_key_here
GROQ_MODEL=openai/gpt-oss-120b       # optional, see "Choosing a model"
```

### 2. Frontend

```bash
cd frontend
npm install
```

By default the frontend talks to `http://localhost:5000`. To point it elsewhere,
`cp .env.example .env` in `frontend/` and set `VITE_BACKEND_URL`.

### 3. Run

Two terminals:

```bash
python backend/server.py     # http://localhost:5000
```

```bash
cd frontend && npm run dev   # http://localhost:5173
```

Open **http://localhost:5173** in Chrome and allow camera and microphone access.

---

## Choosing a model

Groq retires models regularly, so the model name is configuration, not code. If
you see `model_not_found`, list what your key can actually reach:

```bash
curl https://api.groq.com/openai/v1/models \
  -H "Authorization: Bearer $GROQ_API_KEY"
```

Then set `GROQ_MODEL` in `.env`. Two things worth knowing:

- **Reasoning models bill their thinking against `max_tokens`.** With
  `openai/gpt-oss-*` at default effort, a one-sentence nudge would spend its
  entire 150-token budget reasoning and return an empty or truncated reply. The
  server sends `reasoning_effort="low"` for those models, which fixes it and is
  also faster. If you switch to a different reasoning model, check
  `SUPPORTS_REASONING_EFFORT` in `backend/server.py`.
- **Latency is the whole experience.** `openai/gpt-oss-120b` answers in ~0.8s;
  `qwen/qwen3.8-27b` in ~0.15s with slightly blunter phrasing.

---

## Testing

Three suites, none of which need a browser:

```bash
python backend/test_harness.py    # the Pyodide harness, run under CPython
python backend/smoke_test.py      # boots the server, drives the full lifecycle
python backend/behavior_test.py   # asks the real model whether it behaves
```

- **`test_harness.py`** extracts the Python out of `frontend/src/pythonHarness.js`
  and runs it directly, so you can check correct/wrong/crashing/syntax-error
  submissions and `ListNode` marshalling without clicking through the UI.
- **`smoke_test.py`** starts a real server on port **5057** — deliberately not
  5000, so it can never accidentally test a dev server you left running — and
  exercises connect → start_session → code_update → process_frame →
  end_session. It works without an API key, and tightens its assertions when one
  is present.
- **`behavior_test.py`** is the only one that needs a key. It checks that the
  three personas produce different replies, that the interviewer refuses to hand
  over the solution, and that the spoken-text cleanup does not mangle `O(n)`.

---

## How some of it works

### Attention tracking

`modules/attention_detector.py` loads a ResNet18 fine-tuned for binary
focused/distracted classification. The frontend posts a webcam frame once per
second; the backend scores it and keeps a running distraction score:

```python
DISTRACTION_THRESHOLD = 12   # points before a nudge fires
DISTRACTION_DECAY = 2        # points removed per focused frame
NUDGE_COOLDOWN = 25          # seconds between nudges of any kind
TYPING_GRACE = 5             # recent keystrokes count as focused
```

A distracted frame adds one point; a focused frame removes two. So a nudge needs
roughly 12 seconds of sustained looking-away, and a single misclassification
cannot trigger one. Typing counts as engagement, because looking at your keyboard
is not the same as being distracted.

Tune these in `backend/server.py`. Lower `DISTRACTION_THRESHOLD` if you want it
twitchier; raise `DISTRACTION_DECAY` if it nags you unfairly.

### Test cases

The upstream question dataset ships problem statements but no expected outputs,
so `backend/generate_test_cases.py` parses the worked `Input:` / `Output:`
examples out of each problem's markdown and attaches `test_cases`, `param_types`
and `return_type`. It is idempotent — safe to re-run.

Current coverage: **109 test cases across 43 of 52 questions**, 18 of which
involve linked lists or trees. The remaining 9 have no machine-readable examples
and run your code without asserting on it.

Comparison is exact, so problems with several valid answers (any ordering, any
valid pair) can report a false failure. Both expected and actual values are shown
in the results panel so you can judge for yourself.

### Why the harness lives in a separate file

`frontend/src/pythonHarness.js` holds the Python that wraps your submission. It
is passed to Pyodide through `pyodide.globals.set()` rather than interpolated
into a string, so quotes and backslashes in your code cannot break the runner.
Keeping it in one file also means `test_harness.py` can extract and test the
exact same source the browser executes.

---

## Project layout

```
backend/
  server.py               Socket.IO server: events, prompts, session state
  questions.json          52 questions with starter code and test cases
  generate_test_cases.py  Parses expected outputs out of problem markdown
  test_harness.py         Tests the Pyodide harness under CPython
  smoke_test.py           End-to-end lifecycle check
  behavior_test.py        Checks the interviewer's actual replies
frontend/src/
  App.jsx                 Main UI, socket wiring, speech, Pyodide
  Setup.jsx               Difficulty / topic / persona picker
  pythonHarness.js        The Python that runs and grades submissions
modules/
  attention_detector.py   ResNet18 load + inference
  attention_detection_training.ipynb   How the model was trained
  avatar_gen.py           Unused, see "Not implemented"
detection_models/
  attention_model_pretrained.pth   Loaded at startup (fine-tuned ResNet18)
  attention_model_scratch.pth      Trained from scratch, kept for comparison
```

---

## Not implemented

- **Animated avatar.** The interviewer is an emoji that scales while speaking.
  `modules/avatar_gen.py` is a stub and is not imported. If you pick this up, a
  viseme-driven 2D mouth off `SpeechSynthesisUtterance.onboundary` will hold
  realtime; Wav2Lip and SadTalker will not.
- **Persistence.** Sessions are in-memory and vanish on disconnect. Nothing is
  saved between runs.
- **Conversation memory.** Each spoken exchange is prompted independently. The
  interviewer sees your current code but not the earlier back-and-forth, so it
  will not reference something you said three turns ago.
- **Multi-user.** Sessions are keyed by socket id and it has only been run
  single-user.

---

## Troubleshooting

| Symptom | Cause |
| --- | --- |
| `model_not_found` (404) | Groq retired the model. See "Choosing a model". |
| Interviewer says "I am having trouble thinking" | `GROQ_API_KEY` is missing. It is read from `.env` at the repo root. |
| Interviewer says "Please continue." | The API call failed. Check the server log for the real error. |
| Nothing is spoken | Not Chrome, or the tab is muted. The caption under the avatar shows what it said either way. |
| Never gets nudged | Expected — it needs ~12s of sustained looking away, and typing resets it. |
| `[Errno 10048] bind` on startup | Port 5000 is already in use by another server instance. |
| Pyodide slow on first run | It downloads ~10 MB from the CDN once, then caches. |
