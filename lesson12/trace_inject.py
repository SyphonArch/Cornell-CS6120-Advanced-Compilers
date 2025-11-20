"""Inject a trace function into the main function of a Bril program.

Usage: python3 trace_inject.py < input.json > output.json
"""
import json
import sys


TRACE_FUNC_NAME = "__trace_main"
TRACE_META_FUNC_NAME = "__trace_meta_main"
ABORT_LABEL = "__trace_abort"
DONE_LABEL = "__trace_done"


def find_func(funcs, name):
    matches = [f for f in funcs if f.get("name") == name]
    if not matches:
        raise SystemExit(f"no function named {name} found")
    if len(matches) > 1:
        raise SystemExit(f"multiple functions named {name} found")
    return matches[0]


def make_label(name):
    return {"label": name}


def get_stop_index_from_meta(prog):
    funcs = prog.get("functions", [])
    try:
        meta = find_func(funcs, TRACE_META_FUNC_NAME)
    except SystemExit:
        return None

    for instr in meta.get("instrs", []):
        if instr.get("op") == "const" and instr.get("dest") == "__trace_stop_index":
            return instr.get("value")
    return None


def inject_trace(prog):
    funcs = prog.get("functions", [])
    main = find_func(funcs, "main")
    trace = find_func(funcs, TRACE_FUNC_NAME)
    trace_body = trace.get("instrs", [])

    stop_index = get_stop_index_from_meta(prog)
    if stop_index is None:
        raise SystemExit("trace metadata missing stop index; refusing to inject")

    main_instrs = main.get("instrs", [])
    if not (0 <= stop_index <= len(main_instrs)):
        raise SystemExit(f"invalid stop index {stop_index} for main of length {len(main_instrs)}")

    # If there is already a label at stop_index, reuse it; otherwise, insert
    # a fresh continuation label there.
    cont_label = None
    if stop_index < len(main_instrs) and "label" in main_instrs[stop_index]:
        cont_label = main_instrs[stop_index]["label"]
    else:
        cont_label = "__trace_continuation"
        main_instrs.insert(stop_index, {"label": cont_label})

    # Build the new instruction list for main.
    new_instrs = []

    # Fast path entry.
    new_instrs.append({"op": "speculate"})

    # Copy the trace body into main.
    new_instrs.extend(trace_body)

    # End speculation and jump to continuation.
    new_instrs.append({"op": "commit"})
    new_instrs.append({"op": "jmp", "labels": [cont_label]})

    # Abort label: slow path entry.
    new_instrs.append(make_label(ABORT_LABEL))

    # Original main body as slow path.
    orig_instrs = main.get("instrs", [])
    new_instrs.extend(orig_instrs)

    main["instrs"] = new_instrs

    # Drop trace and metadata functions from the optimized program.
    prog["functions"] = [
        f
        for f in prog.get("functions", [])
        if f.get("name") not in {TRACE_FUNC_NAME, TRACE_META_FUNC_NAME}
    ]

    return prog


def cli_main():
    prog = json.load(sys.stdin)
    prog = inject_trace(prog)
    json.dump(prog, sys.stdout)

if __name__ == "__main__":
    cli_main()
