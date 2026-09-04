# backend/test_harness.py
"""Run the frontend's Python harness under CPython to check its plumbing.

The harness in frontend/src/pythonHarness.js is plain Python with no Pyodide
dependencies, so we can extract the string and exercise it here instead of
clicking through a browser. Verifies that correct solutions pass, wrong ones
fail, and ListNode/TreeNode marshalling round-trips.

Usage: python backend/test_harness.py
"""
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
HARNESS_JS = os.path.join(REPO, "frontend", "src", "pythonHarness.js")
DB_PATH = os.path.join(HERE, "questions.json")


def load_harness_source():
    with open(HARNESS_JS, encoding="utf-8") as f:
        js = f.read()
    match = re.search(r"String\.raw`(.*?)`;", js, re.S)
    if not match:
        raise SystemExit("Could not find the String.raw`...` block in pythonHarness.js")
    return match.group(1)


HARNESS = load_harness_source()


def run(question, user_code):
    """Execute the harness the way App.jsx does and return the parsed report."""
    meta = json.loads(question["meta_data"])
    globals_dict = {
        "_user_code": user_code,
        "_cases_json": json.dumps(question["test_cases"]),
        "_types_json": json.dumps(question["param_types"]),
        "_return_type": question["return_type"],
        "_func_name": meta.get("name", "solution"),
        "__name__": "__harness__",
    }
    # The harness ends with a bare `_run()` expression; capture it by compiling
    # the body and evaluating the final call separately.
    exec(compile(HARNESS, "<harness>", "exec"), globals_dict)
    return json.loads(globals_dict["_run"]())


def find(db, title):
    q = next((x for x in db if x["title"] == title), None)
    if q is None:
        raise SystemExit(f"Question not in DB: {title}")
    return q


CORRECT_TWO_SUM = """
class Solution:
    def twoSum(self, nums, target):
        seen = {}
        for i, n in enumerate(nums):
            if target - n in seen:
                return [seen[target - n], i]
            seen[n] = i
"""

WRONG_TWO_SUM = """
class Solution:
    def twoSum(self, nums, target):
        return [0, 0]
"""

CRASHING = """
class Solution:
    def twoSum(self, nums, target):
        raise ValueError("boom")
"""

SYNTAX_ERROR = "class Solution:\n    def twoSum(self, nums, target)\n        return []"

NO_SOLUTION_CLASS = "def twoSum(nums, target):\n    return []"

# Quotes and backslashes that would have broken the old string-interpolated runner.
TRICKY_LITERALS = r'''
class Solution:
    def twoSum(self, nums, target):
        marker = "he said \"hi\" \\ done"  # noqa
        seen = {}
        for i, n in enumerate(nums):
            if target - n in seen:
                return [seen[target - n], i]
            seen[n] = i
'''

CORRECT_ADD_TWO = """
class Solution:
    def addTwoNumbers(self, l1, l2):
        head = tail = ListNode(0)
        carry = 0
        while l1 or l2 or carry:
            total = carry
            if l1: total += l1.val; l1 = l1.next
            if l2: total += l2.val; l2 = l2.next
            carry, digit = divmod(total, 10)
            tail.next = ListNode(digit)
            tail = tail.next
        return head.next
"""


def main():
    with open(DB_PATH, encoding="utf-8") as f:
        db = json.load(f)

    two_sum = find(db, "Two Sum")
    add_two = find(db, "Add Two Numbers")

    failures = []

    def check(label, condition, detail=""):
        print(f"  {'PASS' if condition else 'FAIL'}  {label}")
        if not condition:
            failures.append(f"{label} {detail}")

    print("Two Sum - correct solution")
    r = run(two_sum, CORRECT_TWO_SUM)
    check("status ok", r["status"] == "ok", r.get("message", ""))
    check(f"all {r.get('total')} cases pass", r.get("passed") == r.get("total"), json.dumps(r)[:200])

    print("Two Sum - wrong solution")
    r = run(two_sum, WRONG_TWO_SUM)
    check("reports failures", r["status"] == "ok" and r["passed"] < r["total"])
    check("failing case carries expected+actual",
          any(c["expected"] is not None and c["actual"] is not None
              for c in r["results"] if not c["passed"]))

    print("Two Sum - solution that raises")
    r = run(two_sum, CRASHING)
    check("cases marked failed, not crashed", r["status"] == "ok" and r["passed"] == 0)
    check("error text surfaced", all("ValueError" in (c["error"] or "") for c in r["results"]))

    print("Two Sum - syntax error")
    r = run(two_sum, SYNTAX_ERROR)
    check("reported as error", r["status"] == "error")

    print("Two Sum - no Solution class")
    r = run(two_sum, NO_SOLUTION_CLASS)
    check("reported as error", r["status"] == "error")

    print("Two Sum - quotes and backslashes in user code")
    r = run(two_sum, TRICKY_LITERALS)
    check("still passes", r["status"] == "ok" and r["passed"] == r["total"], json.dumps(r)[:200])

    print("Add Two Numbers - ListNode in and out")
    r = run(add_two, CORRECT_ADD_TWO)
    check("status ok", r["status"] == "ok", r.get("message", ""))
    check(f"all {r.get('total')} cases pass", r.get("passed") == r.get("total"), json.dumps(r)[:300])

    print("Question with no assertable examples")
    run_only = next(q for q in db if not q["test_cases"])
    meta = json.loads(run_only["meta_data"])
    stub = f"class Solution:\n    def {meta['name']}(self, *a, **k):\n        return None\n"
    r = run(run_only, stub)
    check("status no_tests", r["status"] == "no_tests", r.get("message", ""))

    print()
    if failures:
        print(f"{len(failures)} check(s) failed:")
        for f in failures:
            print("  -", f)
        sys.exit(1)
    print("All harness checks passed.")


if __name__ == "__main__":
    main()
