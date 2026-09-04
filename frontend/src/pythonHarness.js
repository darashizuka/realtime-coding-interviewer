// frontend/src/pythonHarness.js
//
// Python source for the in-browser test runner. Kept as a raw string constant
// rather than interpolated per-run: the user's code and the test data are
// handed over with pyodide.globals.set(), so nothing here needs escaping and a
// stray quote or backslash in the editor can no longer break the harness.
//
// Reads these globals, all set from App.jsx before execution:
//   _user_code    str   - contents of the editor
//   _cases_json   str   - JSON list of {input: [...], expected: ...}
//   _types_json   str   - JSON list of parameter type strings
//   _return_type  str   - return type string
//   _func_name    str   - method to call on Solution
//
// Returns a JSON string; see the shapes assembled in _run().

export const HARNESS = String.raw`
import json
import sys
from io import StringIO
from typing import *


class ListNode:
    def __init__(self, val=0, next=None):
        self.val = val
        self.next = next


class TreeNode:
    def __init__(self, val=0, left=None, right=None):
        self.val = val
        self.left = left
        self.right = right


def _build_list(values):
    head = None
    for v in reversed(values or []):
        head = ListNode(v, head)
    return head


def _dump_list(node):
    out = []
    seen = set()
    while node is not None:
        if id(node) in seen:  # cycle guard so a bad solution can't hang the tab
            out.append("...cycle...")
            break
        seen.add(id(node))
        out.append(node.val)
        node = node.next
    return out


def _build_tree(values):
    """Level-order with nulls, LeetCode style: [1,null,2,3]."""
    values = list(values or [])
    if not values or values[0] is None:
        return None
    root = TreeNode(values[0])
    queue = [root]
    i = 1
    while queue and i < len(values):
        node = queue.pop(0)
        if i < len(values):
            v = values[i]; i += 1
            if v is not None:
                node.left = TreeNode(v)
                queue.append(node.left)
        if i < len(values):
            v = values[i]; i += 1
            if v is not None:
                node.right = TreeNode(v)
                queue.append(node.right)
    return root


def _dump_tree(node):
    if node is None:
        return []
    out, queue = [], [node]
    while queue:
        n = queue.pop(0)
        if n is None:
            out.append(None)
            continue
        out.append(n.val)
        queue.append(n.left)
        queue.append(n.right)
    while out and out[-1] is None:
        out.pop()
    return out


def _coerce_in(value, type_str):
    if type_str == "ListNode":
        return _build_list(value)
    if type_str == "TreeNode":
        return _build_tree(value)
    return value


def _coerce_out(value, type_str):
    if type_str == "ListNode":
        return _dump_list(value)
    if type_str == "TreeNode":
        return _dump_tree(value)
    return value


def _matches(actual, expected):
    """Exact match, with a tolerance for float-returning problems."""
    if isinstance(actual, float) or isinstance(expected, float):
        try:
            return abs(float(actual) - float(expected)) < 1e-5
        except (TypeError, ValueError):
            return False
    return actual == expected


def _capture(fn):
    """Run fn(), returning (value, error_string, stdout)."""
    buffer = StringIO()
    original = sys.stdout
    sys.stdout = buffer
    try:
        return fn(), None, buffer.getvalue()
    except Exception as exc:
        return None, "{0}: {1}".format(type(exc).__name__, exc), buffer.getvalue()
    finally:
        sys.stdout = original


def _run():
    cases = json.loads(_cases_json)
    param_types = json.loads(_types_json)

    # The user's solution needs ListNode/TreeNode/typing names in scope.
    namespace = dict(globals())
    _, error, stdout = _capture(lambda: exec(_user_code, namespace))
    if error:
        return json.dumps({
            "status": "error",
            "message": "Your code did not compile or run: " + error,
            "stdout": stdout,
            "results": [],
        })

    solution_cls = namespace.get("Solution")
    if solution_cls is None:
        return json.dumps({
            "status": "error",
            "message": "No class named Solution was found.",
            "stdout": stdout,
            "results": [],
        })
    if not hasattr(solution_cls(), _func_name):
        return json.dumps({
            "status": "error",
            "message": "Solution has no method named '" + _func_name + "'.",
            "stdout": stdout,
            "results": [],
        })

    # No parseable examples for this problem - just execute and show output.
    if not cases:
        return json.dumps({
            "status": "no_tests",
            "message": "This problem has no machine-checkable examples. "
                       "Your code ran without errors.",
            "stdout": stdout,
            "results": [],
        })

    results = []
    for case in cases:
        args = [
            _coerce_in(value, param_types[i] if i < len(param_types) else "")
            for i, value in enumerate(case["input"])
        ]
        # Fresh instance per case so state cannot leak between them.
        method = getattr(solution_cls(), _func_name)
        raw, error, case_stdout = _capture(lambda: method(*args))
        actual = None if error else _coerce_out(raw, _return_type)
        results.append({
            "input": case["input"],
            "expected": case["expected"],
            "actual": actual,
            "error": error,
            "stdout": case_stdout,
            "passed": error is None and _matches(actual, case["expected"]),
        })

    passed = sum(1 for r in results if r["passed"])
    return json.dumps({
        "status": "ok",
        "passed": passed,
        "total": len(results),
        "stdout": stdout,
        "results": results,
    })


_run()
`;
