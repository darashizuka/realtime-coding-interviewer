# backend/generate_test_cases.py
"""Derive runnable test cases from the worked examples in each question's markdown.

LeetCode problem statements embed their examples as literal lines:

    Input: nums = [2,7,11,15], target = 9
    Output: [0,1]

That is the only source of expected outputs we have - the upstream dataset does
not ship them - so we parse those pairs into a structured `test_cases` field
that the Pyodide runner in the frontend can assert against.

Questions whose examples do not parse (prose outputs like "Intersected at '8'",
in-place mutation results like "nums = [1,2,_]", or no examples at all) get an
empty `test_cases` list and fall back to run-without-assertion in the UI.

Idempotent - safe to re-run. Usage: python backend/generate_test_cases.py
"""
import json
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "questions.json")

# Structural types the frontend harness knows how to build and serialize.
STRUCTURAL = ("ListNode", "TreeNode")


def parse_args(raw_input, param_names):
    """"nums = [2,7,11,15], target = 9" -> [[2,7,11,15], 9], ordered by signature."""
    # Split only on commas that begin a new "name =" clause, so commas inside
    # list literals survive.
    parts = re.split(r",\s*(?=[A-Za-z_]\w*\s*=)", raw_input.strip())
    by_name = {}
    for part in parts:
        if "=" not in part:
            return None
        name, _, value = part.partition("=")
        by_name[name.strip()] = json.loads(value.strip())

    # Fall back to positional order when the example uses different names.
    if set(by_name) == set(param_names):
        return [by_name[n] for n in param_names]
    if len(by_name) == len(param_names):
        return list(by_name.values())
    return None


def extract_cases(question):
    md = question["markdown_content"].replace(" ", " ")
    inputs = re.findall(r"^Input:\s*(.+)$", md, re.M)
    outputs = re.findall(r"^Output:\s*(.+)$", md, re.M)
    if not inputs or len(inputs) != len(outputs):
        return []

    meta = json.loads(question["meta_data"])
    param_names = [p["name"] for p in meta.get("params", [])]

    cases = []
    for raw_in, raw_out in zip(inputs, outputs):
        try:
            args = parse_args(raw_in, param_names)
            if args is None:
                continue
            expected = json.loads(raw_out.strip())
        except (json.JSONDecodeError, ValueError):
            # Prose or in-place output - not assertable, skip this case.
            continue
        cases.append({"input": args, "expected": expected})
    return cases


def main():
    with open(DB_PATH, encoding="utf-8") as f:
        db = json.load(f)

    with_cases = 0
    for question in db:
        meta = json.loads(question["meta_data"])
        question["param_types"] = [p["type"] for p in meta.get("params", [])]
        question["return_type"] = meta.get("return", {}).get("type", "")
        question["test_cases"] = extract_cases(question)
        if question["test_cases"]:
            with_cases += 1

    with open(DB_PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)

    total_cases = sum(len(q["test_cases"]) for q in db)
    structural = sum(
        1 for q in db
        if any(t in STRUCTURAL for t in q["param_types"]) or q["return_type"] in STRUCTURAL
    )
    print(f"{with_cases}/{len(db)} questions have assertable test cases "
          f"({total_cases} cases total; {structural} involve ListNode/TreeNode).")
    for q in db:
        if not q["test_cases"]:
            print(f"  run-only (no assertable examples): {q['title']}")


if __name__ == "__main__":
    main()
