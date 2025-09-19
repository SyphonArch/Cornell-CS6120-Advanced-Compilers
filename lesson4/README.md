# Bril Data-Flow Analyses

This repo provides a generic DFA solver (`DFA.py`) plus three example analyses:

* `reaching_defs.py`: forward, may (union)
* `available_exprs.py`: forward, must (intersection)
* `live_vars.py`: backward, may (union)

---

## Running

Each pass takes Bril JSON from stdin:

```bash
bril2json < prog.bril | python reaching_defs.py
bril2json < prog.bril | python available_exprs.py
bril2json < prog.bril | python live_vars.py
```

Output shows per-function, per-block `IN` and `OUT` sets.

---

## How it works

* `DFA.py` implements a worklist solver with:

  * `Direction.{FORWARD,BACKWARD}`
  * `Seed.{KEEP,TOP,BOTTOM}` for entry/exit initialization
* Each fact type subclasses `DataFlowFact` and defines:

  * `merge` (lattice meet)
  * `transfer` (local step)
  * `top` (meet identity)
  * `bottom` (meet absorbing)

---

## Making your own pass

1. Define a `DataFlowFact` subclass with `merge`, `transfer`, `top`, and `bottom`.
2. Pick direction (forward/backward) and seed (entry/exit).
3. Call:

```python
dfa = DFA(cfg, Direction.FORWARD, MyFact, entry=Seed.BOTTOM)
dfa.analyze()
```

4. Inspect results in `dfa.in_lattice`, `dfa.out_lattice`, or per-instruction in `dfa.inst_in_lattice` / `dfa.inst_out_lattice`.

---

## Disclaimer

The `README.md` was written using ChatGPT, and information on what each of the DFA analyses does was queried with ChatGPT.
