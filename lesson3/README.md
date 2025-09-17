# LVN + DCE Workflow

This repo contains scripts for applying **Local Value Numbering (LVN)** and **Dead Code Elimination (DCE)** to Bril programs, plus utilities to benchmark and visualize their effects.

## Usage

### Run Optimizations

* **LVN + DCE**:

  ```sh
  ./run_lvn_tdce.sh file.bril > file.bril.lvn.dce
  ```
* **DCE only**:

  ```sh
  ./run_tdce.sh file.bril > file.bril.dce
  ```
* Batch process a directory:

  ```sh
  ./run_all_lvn_tdce.sh core-benchmarks
  ./run_all_tdce.sh core-benchmarks
  ```

### Testing with Turnt

Run benchmarks against expected outputs:

```sh
turnt core-benchmarks.lvn.dce/*.bril
```

To assist with preparing the necessary `.out` files and the `# ARGS` lines, you may use the `create_lvn_dce_test_suite_dir.py` script.

To profile execution counts (`.prof` files):

```sh
command = "bril2json < {filename} | brili -p {args}"  # in turnt.toml
```

### Visualization

Compare performance before/after LVN+DCE:

```sh
python visualize_gains.py core-benchmarks core-benchmarks.lvn.dce
```

This prints a table, statistics, and produces `performance_gains.pdf`.

## Notes

* Scripts insert `# ARGS` lines automatically if missing.
* Visualization uses **matplotlib** and **pandas**.
* Shell scripts and visualization code were written with assistance from ChatGPT.

## Generative AI Acknowledgment

Shell scripts and visualization code, and this README were written with assistance from ChatGPT.
