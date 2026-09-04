# backend/smoke_test.py
"""End-to-end wiring check: boots the real server and drives it over a socket.

Exercises the full interview lifecycle the frontend performs - connect,
start_session, code_update, user_typing, process_frame, end_session - and
asserts the expected events come back.

Does not require GROQ_API_KEY. Without a key the LLM replies are placeholder
strings, but every event still round-trips, so this verifies transport,
question selection, vision inference and the evaluation path. With a key set,
it additionally confirms the model is actually reachable.

Usage: python backend/smoke_test.py
"""
import base64
import io
import os
import socket
import subprocess
import sys
import time

import socketio
from dotenv import load_dotenv
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)

# Read the same .env the server does, so the key check below reflects what the
# server will actually use rather than whatever is in the calling shell.
load_dotenv(os.path.join(REPO, ".env"))

# Deliberately not 5000: a dev server is often already running there, and if we
# used it this test would silently drive that server instead of the one it
# started, reporting on stale code.
PORT = int(os.getenv("SMOKE_PORT", "5057"))
URL = f"http://localhost:{PORT}"

received = {}


def synthetic_frame():
    """A plausible webcam frame as base64 JPEG."""
    image = Image.new("RGB", (640, 480), (90, 90, 110))
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG")
    return base64.b64encode(buffer.getvalue()).decode()


def wait_for(key, timeout=45):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if key in received:
            return received[key]
        time.sleep(0.25)
    return None


def port_is_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def main():
    if not port_is_free(PORT):
        print(f"Port {PORT} is already in use. Stop whatever is on it, or set "
              f"SMOKE_PORT to a free port.")
        sys.exit(1)

    print(f"Starting server on port {PORT}...")
    server = subprocess.Popen(
        [sys.executable, os.path.join(HERE, "server.py")],
        cwd=REPO,
        env={**os.environ, "PORT": str(PORT)},
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    failures = []

    def check(label, condition, detail=""):
        print(f"  {'PASS' if condition else 'FAIL'}  {label}"
              + (f"  [{detail}]" if detail else ""))
        if not condition:
            failures.append(label)

    try:
        # Wait for uvicorn to bind (model load takes a few seconds).
        client = socketio.Client()
        for attempt in range(40):
            try:
                client.connect(URL, transports=["polling"], wait_timeout=5)
                break
            except Exception:
                if server.poll() is not None:
                    print("Server died during startup:")
                    print(server.stdout.read())
                    sys.exit(1)
                time.sleep(1)
        else:
            print("Could not connect to server")
            sys.exit(1)

        for event in ("session_data", "ai_text_response", "ai_nudge", "interview_feedback"):
            client.on(event, lambda data, e=event: received.setdefault(e, data))

        print("Connected.\n")

        print("start_session")
        client.emit("start_session", {
            "difficulty": "Easy", "topic": "Array", "persona": "Strict",
        })
        session = wait_for("session_data")
        check("session_data received", session is not None)
        question = (session or {}).get("question") or {}
        check("question has a title", bool(question.get("title")), question.get("title", ""))
        check("question matches requested difficulty",
              question.get("difficulty") == "Easy", question.get("difficulty", ""))
        check("question carries test_cases field", "test_cases" in question,
              f"{len(question.get('test_cases', []))} cases")
        check("question carries starter_code", bool(question.get("starter_code")))

        greeting = wait_for("ai_text_response")
        check("interviewer greeting received", greeting is not None)
        if greeting:
            text = greeting.get("text", "")
            has_key = bool(os.getenv("GROQ_API_KEY"))
            real = "trouble thinking" not in text and "Please continue." != text
            check("greeting is a real LLM response" if has_key
                  else "greeting is the documented no-key placeholder",
                  real if has_key else not real,
                  text[:70])

        print("\ncode_update / user_typing")
        client.emit("code_update", {"code": "class Solution:\n    pass\n"})
        client.emit("user_typing", {"timestamp": time.time()})
        time.sleep(0.5)
        check("accepted without error", server.poll() is None)

        print("\nprocess_frame (vision inference)")
        frame = synthetic_frame()
        for _ in range(3):
            client.emit("process_frame", {"image": frame})
            time.sleep(0.4)
        check("server alive after inference", server.poll() is None)

        print("\nend_session")
        received.pop("interview_feedback", None)
        client.emit("end_session", {"test_results": {"passed": 2, "total": 3}})
        feedback = wait_for("interview_feedback")
        check("interview_feedback received", feedback is not None)
        if feedback:
            check("feedback is non-empty markdown",
                  bool(feedback.get("markdown", "").strip()),
                  feedback.get("markdown", "")[:70].replace("\n", " "))

        client.disconnect()
        time.sleep(0.5)

    finally:
        server.terminate()
        try:
            output = server.communicate(timeout=10)[0]
        except subprocess.TimeoutExpired:
            server.kill()
            output = server.communicate()[0]

    print("\n--- server log ---")
    print((output or "").strip()[:1800])
    print("--- end log ---\n")

    if failures:
        print(f"{len(failures)} check(s) failed: {', '.join(failures)}")
        sys.exit(1)
    print("Smoke test passed.")


if __name__ == "__main__":
    main()
