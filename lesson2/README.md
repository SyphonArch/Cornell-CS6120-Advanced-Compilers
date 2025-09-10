# Lesson 2 – Bril Transformations and Control-Flow Analysis

## Transformation: Constant Addition Folding

- **`complex_add.bril`**  
  Example Bril program with several constant additions.
- **`complex_add.json`**  
  JSON form of the above program.
- **`const_add_fold.py`**  
  Python script that:
  - Recursively folds chains of `add` instructions into equivalent `const` instructions.
  - Eliminates dead code
- **`complex_add_folded.json`**  
  Result of running `const_add_fold.py` on `complex_add.json`.

## Control-Flow Graph Construction

- **`build_cfg.py`**  
  Python script to:
  - Split Bril functions into basic blocks.
  - Build control-flow graphs (CFGs) with edges for jumps, branches, and fallthroughs.
- **`complex_add_cfg.json`**  
  CFG for `complex_add.json`.
- **`graycode.bril`**  
  Bril benchmark that generates Gray codes from `0` to `n-1`.
- **`graycode.json`**  
  JSON form of the Gray code program.
- **`graycode_cfg.json`**  
  CFG for `graycode.json`.

## Testing with Turnt

- **`turnt.toml`**  
  Minimal configuration for testing.
- **`chain.json`, `effects.json`, `noop.json`, `partial.json`**  
  Input Bril JSON test programs.
- **`*.folded.json`**  
  Expected outputs for constant folding.

Run all tests with:

```bash
turnt *.json
