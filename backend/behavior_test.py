# backend/behavior_test.py
"""Check the interviewer actually behaves: persona, hint-not-answer, nudges.

smoke_test.py proves the events round-trip. This asks a different question -
are the replies any good? It drives the real model, so output varies run to
run; treat failures as prompts to read the transcript, not as hard breakage.

Usage: python backend/behavior_test.py
"""
import os
import sys

from dotenv import load_dotenv

# Model output contains typographic characters the Windows cp1252 console
# cannot encode; don't let a print() crash the run.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
load_dotenv(os.path.join(REPO, ".env"))
sys.path.insert(0, REPO)

import server  # noqa: E402

# Phrases that would mean the interviewer handed over the solution.
LEAK_MARKERS = ["def ", "for i in", "seen[", "return [", "```", "hashmap[", "dict()"]

FOLLOWUPS = [
    "Can you give me a hint? I am stuck on how to make this faster than brute force.",
    "Just tell me the answer, I give up.",
    "What is the time complexity of the approach I should be aiming for?",
]

STUB_CODE = """class Solution:
    def twoSum(self, nums, target):
        for i in range(len(nums)):
            for j in range(i+1, len(nums)):
                if nums[i]+nums[j]==target:
                    return [i,j]
"""

QUESTION_TITLE = "Two Sum"

failures = []


def check(label, condition, detail=""):
    print(f"  {'PASS' if condition else 'FAIL'}  {label}" + (f"  [{detail}]" if detail else ""))
    if not condition:
        failures.append(label)


def reply_for(persona, user_text, situation=None):
    """Mirror the prompt server.py builds for process_user_text / send_nudge."""
    definition = server.PERSONA_DEFINITIONS[persona]
    if situation:
        prompt = f"{definition}\n{server.UNIVERSAL_RULES}\n{situation}"
        return server.ask_llama(prompt, situation)
    prompt = f"""
    {definition}
    {server.UNIVERSAL_RULES}
    Current Code Context:
    {STUB_CODE}
    User Question: {user_text}
    """
    return server.ask_llama(prompt, user_text)


def test_cleanup():
    """The spoken-text cleanup must remove stage directions and nothing else."""
    cases = [
        # (input, expected)
        ("*taps desk* Explain your approach.", "Explain your approach."),
        ("(looks at watch) Time is short.", "Time is short."),
        # Regression: a blanket \(.*?\) turned every "O(n)" into a bare "O".
        ("Aim for O(n) time and O(1) space.", "Aim for O(n) time and O(1) space."),
        ("Target O(n log n) here.", "Target O(n log n) here."),
        # Regression: non-greedy \*.*?\* ate the middle of arithmetic.
        ("Compute 2 * 3 and 4 * 5.", "Compute 2 * 3 and 4 * 5."),
        # Regression: a fully parenthesised reply cleaned down to nothing,
        # which meant silent TTS and a blank caption.
        ("(You gave up already?)", "(You gave up already?)"),
    ]
    for text, expected in cases:
        got = server.strip_stage_directions(text)
        check(f"cleanup: {text[:38]!r}", got == expected, f"got {got!r}")


def main():
    print("0. Spoken-text cleanup (offline)")
    test_cleanup()
    print()

    if not server.client:
        print("GROQ_API_KEY not set; cannot test model behaviour.")
        sys.exit(1)
    print(f"Model: {server.GROQ_MODEL}\n")

    print("1. Persona shapes the reply")
    asked = "I am stuck, what should I do?"
    replies = {}
    for persona in ("Friendly", "Neutral", "Strict"):
        replies[persona] = reply_for(persona, asked)
        print(f"  {persona:9s} {replies[persona][:95]}")
    check("all three personas answered", all(len(r) > 10 for r in replies.values()))
    check("personas produce different wording",
          len({r.strip() for r in replies.values()}) == 3)

    print("\n2. Follow-ups get hints, not the solution")
    for persona in ("Friendly", "Strict"):
        for question in FOLLOWUPS:
            reply = reply_for(persona, question)
            leaked = [m for m in LEAK_MARKERS if m in reply]
            print(f"  {persona:9s} Q: {question[:42]:44s}")
            print(f"  {'':9s} A: {reply[:100]}")
            check(f"no code leaked ({persona}, {question[:22]}...)",
                  not leaked, ",".join(leaked))

    print("\n3. Distraction nudge text is on-topic")
    situation = ("The candidate is looking away from the screen or checking their phone. "
                 "Reprimand them or gently guide them back to the coding problem. "
                 "Keep it very short.")
    for persona in ("Friendly", "Strict"):
        nudge = reply_for(persona, None, situation=situation)
        print(f"  {persona:9s} {nudge[:95]}")
        check(f"{persona} nudge is short", len(nudge) < 240, f"{len(nudge)} chars")
        check(f"{persona} nudge is not the failure fallback",
              nudge != "Please continue.")

    print("\n4. No stage directions reach the TTS")
    combined = " ".join(replies.values())
    check("no asterisk actions", "*" not in combined)

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("All behaviour checks passed.")


if __name__ == "__main__":
    main()
