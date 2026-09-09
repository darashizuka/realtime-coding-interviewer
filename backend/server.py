# backend/server.py
import asyncio
import base64
import io
import json
import logging
import os
import random
import re
import sys
import time

import socketio
import uvicorn
from dotenv import load_dotenv
from groq import Groq
from PIL import Image

# Add root directory to path so we can import 'modules'
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from modules.attention_detector import load_model, predict_is_distracted  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-7s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("interviewer")

load_dotenv()

# --- VISION MODEL ---
# A missing checkpoint is fatal for the distraction feature, so surface it at
# startup rather than letting every frame fail silently.
try:
    model, device = load_model()
    log.info("Vision model loaded on %s", device)
except Exception as exc:
    log.error("Vision model unavailable, distraction nudges disabled: %s", exc)
    model, device = None, None

# --- GROQ ---
# Groq retires models fairly often, so keep this overridable without a code
# change. If you get a 404 saying the model does not exist, list what your key
# can actually reach:
#   curl https://api.groq.com/openai/v1/models -H "Authorization: Bearer $GROQ_API_KEY"
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b")

# gpt-oss are reasoning models, and their reasoning tokens are billed against
# max_tokens. At the default effort a one-sentence nudge would spend its whole
# 150-token budget thinking and come back empty or cut off mid-word
# (finish_reason="length"), so ask for minimal reasoning. Only gpt-oss accepts
# this parameter, hence the guard.
SUPPORTS_REASONING_EFFORT = GROQ_MODEL.startswith("openai/gpt-oss")
GROQ_API_KEY = os.getenv("GROQ_API_KEY")
if not GROQ_API_KEY:
    log.error(
        "GROQ_API_KEY is not set. Copy .env.example to .env and add your key, "
        "or the interviewer will not be able to respond."
    )
    client = None
else:
    client = Groq(api_key=GROQ_API_KEY)
    log.info("Groq client initialised, model=%s", GROQ_MODEL)

# --- TUNING ---
# process_frame runs at roughly 1 fps. Distraction accrues a point per frame and
# decays two per focused frame, so a nudge needs sustained looking-away rather
# than one unlucky classification. The previous logic reset the score to zero on
# any single focused frame, which meant the threshold was effectively never hit.
DISTRACTION_THRESHOLD = 12
DISTRACTION_DECAY = 2
NUDGE_COOLDOWN = 25          # seconds between nudges of any kind
TYPING_GRACE = 5             # recent typing counts as focused regardless of gaze

ALLOWED_ORIGINS = os.getenv(
    "ALLOWED_ORIGINS",
    "http://localhost:5173,https://realtime-coding-interviewer.vercel.app",
).split(",")

sio = socketio.AsyncServer(async_mode="asgi", cors_allowed_origins=ALLOWED_ORIGINS)
app = socketio.ASGIApp(sio)

user_sessions = {}
QUESTION_DB = []

PERSONA_DEFINITIONS = {
    "Friendly": "You are a warm, supportive, and encouraging interviewer. Be patient.",
    "Neutral": "You are a professional, objective, and concise interviewer. Be direct but polite.",
    "Strict": "You are a tough, no-nonsense, high-pressure interviewer. Be critical",
}

UNIVERSAL_RULES = """
CRITICAL INSTRUCTIONS:
1. NEVER write code for the candidate.
2. NEVER give the full answer or solution.
3. If they are stuck, give high-level conceptual hints only.
4. Keep spoken responses short (under 2 sentences).
5. DO NOT generate physical actions (e.g. *taps desk*, (looks at watch)). ONLY generate spoken words.
6. DO NOT ask behavioral questions.
7. Focus EXCLUSIVELY on the current coding problem.
"""

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "questions.json")

try:
    with open(DB_PATH, "r", encoding="utf-8") as f:
        QUESTION_DB = json.load(f)
    log.info("Loaded %d questions", len(QUESTION_DB))
except (OSError, json.JSONDecodeError) as exc:
    log.error("Could not load %s: %s", DB_PATH, exc)
    QUESTION_DB = []


def new_session():
    return {
        "persona": "Friendly",
        "code": "",
        "question": None,
        "distraction_score": 0,
        "last_nudge_time": 0,
        "last_type_time": 0,
        "transcript": [],
    }


# Stage directions the model sometimes emits despite UNIVERSAL_RULES #5, e.g.
# *taps desk* or (looks at watch). Both patterns are deliberately narrow:
#   - the asterisk form requires a non-space just inside each delimiter, so
#     arithmetic like "2 * 3 and 4 * 5" is not swallowed as one action.
#   - the parenthesis form only fires when "(" does not follow a word
#     character, which keeps complexity notation like O(n log n) intact. A
#     blanket \(.*?\) turned every "O(n)" into a bare "O".
_ACTION_ASTERISK = re.compile(r"\*(?!\s)[^*\n]{1,80}(?<!\s)\*")
_ACTION_PAREN = re.compile(r"(?<!\w)\([^)\n]{1,80}\)")


def strip_stage_directions(text):
    cleaned = _ACTION_PAREN.sub("", _ACTION_ASTERISK.sub("", text))
    cleaned = re.sub(r"[ \t]{2,}", " ", cleaned).strip()
    # If the model wrapped its whole reply in parentheses the cleanup can
    # consume everything. An empty reply means silent TTS and a blank caption,
    # so fall back to the original rather than saying nothing.
    return cleaned if cleaned else text.strip()


def ask_llama(system_prompt, user_text, max_tokens=150, spoken=True):
    """Ask the model.

    `spoken` strips stage directions like *leans forward* and parentheticals so
    they are not read aloud by the browser's TTS. Leave it off for anything
    rendered as markdown, or the cleanup eats the formatting.
    """
    if not client:
        return "I am having trouble thinking. Check that GROQ_API_KEY is set."
    try:
        completion = client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_text},
            ],
            temperature=0.7,
            max_tokens=max_tokens,
            **({"reasoning_effort": "low"} if SUPPORTS_REASONING_EFFORT else {}),
        )
        choice = completion.choices[0]
        if choice.finish_reason == "length":
            log.warning(
                "Reply hit the %d token cap and was cut off. If this is common, "
                "raise max_tokens or pick a non-reasoning model.", max_tokens
            )
        text = choice.message.content or ""
        if spoken:
            text = strip_stage_directions(text)
        text = text.strip()
        if not text:
            log.warning("Model returned an empty reply")
            return "Please continue."
        return text
    except Exception as exc:
        log.error("LLM call failed: %s", exc)
        return "Please continue."


async def ask_llama_async(system_prompt, user_text, max_tokens=150, spoken=True):
    """Groq's client is synchronous; keep it off the event loop."""
    return await asyncio.get_running_loop().run_in_executor(
        None, ask_llama, system_prompt, user_text, max_tokens, spoken
    )


def persona_for(session):
    return PERSONA_DEFINITIONS.get(session["persona"], PERSONA_DEFINITIONS["Friendly"])


async def send_nudge(sid, session, situation):
    """Emit a spoken nudge if we are outside the cooldown window."""
    now = time.time()
    if (now - session["last_nudge_time"]) < NUDGE_COOLDOWN:
        return False
    session["last_nudge_time"] = now

    prompt = f"{persona_for(session)}\n{UNIVERSAL_RULES}\n{situation}"
    reply = await ask_llama_async(prompt, situation)
    session["transcript"].append(("interviewer", reply))
    await sio.emit("ai_nudge", {"message": reply}, to=sid)
    return True


# --- SOCKET EVENTS ---

@sio.event
async def connect(sid, environ):
    log.info("Client connected: %s", sid)
    user_sessions[sid] = new_session()


@sio.event
async def disconnect(sid):
    log.info("Client disconnected: %s", sid)
    user_sessions.pop(sid, None)


@sio.event
async def start_session(sid, data):
    session = user_sessions.setdefault(sid, new_session())
    log.info("Session started: %s", data)

    session.update(
        persona=data.get("persona", "Friendly"),
        distraction_score=0,
        last_nudge_time=0,
        last_type_time=time.time(),
        transcript=[],
    )

    topic = data.get("topic", "").lower()
    difficulty = data.get("difficulty", "Medium")
    matches = [
        q for q in QUESTION_DB
        if q.get("difficulty") == difficulty and topic in q.get("topic", "").lower()
    ]
    question = random.choice(matches) if matches else (
        random.choice(QUESTION_DB) if QUESTION_DB else None
    )
    session["question"] = question
    session["code"] = (question or {}).get("starter_code", "")

    await sio.emit(
        "session_data",
        {"question": question, "persona": session["persona"]},
        to=sid,
    )

    title = question["title"] if question else "the problem"
    intro_prompt = f"""
    {persona_for(session)}
    {UNIVERSAL_RULES}
    The interview has just started. The candidate is solving the problem: "{title}".
    Introduce yourself in 1 short sentence, then tell them to explain their approach to "{title}".
    DO NOT ask how they are doing.
    """
    greeting = await ask_llama_async(intro_prompt, "Start the interview.")
    session["transcript"].append(("interviewer", greeting))
    log.info("Greeting: %s", greeting)
    await sio.emit("ai_text_response", {"text": greeting}, to=sid)


@sio.event
async def code_update(sid, data):
    session = user_sessions.get(sid)
    if session:
        session["code"] = data.get("code", "")


@sio.event
async def user_typing(sid, data):
    """Recent keystrokes count as engagement even if the candidate is looking away."""
    session = user_sessions.get(sid)
    if session:
        session["last_type_time"] = time.time()
        session["distraction_score"] = 0


@sio.event
async def process_user_text(sid, data):
    session = user_sessions.get(sid)
    if not session:
        return

    user_text = data.get("text", "").strip()
    if not user_text:
        return
    log.info("Candidate: %s", user_text)
    session["transcript"].append(("candidate", user_text))

    prompt = f"""
    {persona_for(session)}
    {UNIVERSAL_RULES}
    Current Code Context:
    {session['code']}
    User Question: {user_text}
    """
    reply = await ask_llama_async(prompt, user_text)
    session["transcript"].append(("interviewer", reply))
    log.info("Interviewer: %s", reply)
    await sio.emit("ai_text_response", {"text": reply}, to=sid)


@sio.event
async def process_frame(sid, data):
    session = user_sessions.get(sid)
    if model is None or session is None:
        return

    try:
        image_bytes = base64.b64decode(data["image"])
        pil_image = Image.open(io.BytesIO(image_bytes)).convert("RGB")

        # Torch inference is blocking; keep it off the event loop so the socket
        # stays responsive between frames.
        is_distracted = await asyncio.get_running_loop().run_in_executor(
            None, predict_is_distracted, pil_image, model, device
        )
    except Exception as exc:
        log.warning("Frame processing failed: %s", exc)
        return

    if (time.time() - session["last_type_time"]) < TYPING_GRACE:
        session["distraction_score"] = 0
        return

    if is_distracted:
        session["distraction_score"] += 1
    else:
        session["distraction_score"] = max(
            0, session["distraction_score"] - DISTRACTION_DECAY
        )

    if session["distraction_score"] >= DISTRACTION_THRESHOLD:
        session["distraction_score"] = 0
        sent = await send_nudge(
            sid,
            session,
            "The candidate is looking away from the screen or checking their phone. "
            "Reprimand them or gently guide them back to the coding problem. Keep it very short.",
        )
        if sent:
            log.info("Nudged %s for distraction", sid)


@sio.event
async def user_silent(sid, data):
    session = user_sessions.get(sid)
    if not session:
        return
    await send_nudge(
        sid,
        session,
        "The candidate has been silent and not typing for a while. "
        "Prompt them to explain their thought process.",
    )


@sio.event
async def end_session(sid, data):
    """Produce a written evaluation of the interview."""
    session = user_sessions.get(sid)
    if not session:
        return

    question = session.get("question") or {}
    title = question.get("title", "the problem")
    results = (data or {}).get("test_results")
    if results:
        test_summary = f"{results.get('passed', 0)} of {results.get('total', 0)} example test cases passing"
    else:
        test_summary = "the candidate never ran the tests"

    conversation = "\n".join(
        f"{speaker}: {text}" for speaker, text in session["transcript"]
    ) or "(the candidate did not speak)"

    prompt = f"""
    You are an experienced technical interviewer writing up your notes after a
    mock coding interview. Be specific and honest; cite what the candidate
    actually did. Do not invent details.

    Problem: {title}
    Final submitted code:
    ```python
    {session['code']}
    ```
    Test outcome: {test_summary}

    Transcript:
    {conversation}

    Write the evaluation in markdown with exactly these sections:
    ## Verdict
    One line: Strong Hire / Hire / Lean No / No Hire, with a one-sentence reason.
    ## Problem Solving
    ## Communication
    ## Code Quality
    ## What To Work On
    Two or three concrete, actionable items.
    """
    feedback = await ask_llama_async(
        prompt, "Write the evaluation.", max_tokens=900, spoken=False
    )
    log.info("Generated feedback for %s", sid)
    await sio.emit("interview_feedback", {"markdown": feedback}, to=sid)


if __name__ == "__main__":
    # PORT is overridable so tests can run against a live dev server on 5000.
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", "5000")))
