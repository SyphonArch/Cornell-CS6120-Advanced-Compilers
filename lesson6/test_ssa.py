"""Given test programs, checks conversions into and out-of SSA form"""
import os
import sys
from tqdm import tqdm
import math
import json
from pathlib import Path
import subprocess
import is_ssa
import to_ssa
import from_ssa


def to_ssa_wrapper(before_path, after_path):
    with open(before_path, 'r') as in_f:
        bril_json_str = subprocess.check_output(['bril2json'], stdin=in_f, text=True)
    bril_program = json.loads(bril_json_str)

    ssa_program = to_ssa.main(bril_program)

    ssa_json_str = json.dumps(ssa_program)
    bril_text = subprocess.check_output(['bril2txt'], input=ssa_json_str, text=True)

    with open(after_path, 'w') as out_f:
        out_f.write(bril_text)


def from_ssa_wrapper(before_path, after_path):
    with open(before_path, 'r') as in_f:
        bril_json_str = subprocess.check_output(['bril2json'], stdin=in_f, text=True)
    ssa_program = json.loads(bril_json_str)

    roundtrip_program = from_ssa.main(ssa_program)

    roundtrip_json_str = json.dumps(roundtrip_program)
    bril_text = subprocess.check_output(['bril2txt'], input=roundtrip_json_str, text=True)

    with open(after_path, 'w') as out_f:
        out_f.write(bril_text)


def run_bril(bril_path, args=None):
    if args is None:
        args = []

    with open(bril_path, 'r') as f:
        bril_json_str = subprocess.check_output(['bril2json'], stdin=f, text=True)
    program = json.loads(bril_json_str)

    static_instr_cnt = sum(len(func['instrs']) for func in program.get('functions', []))

    try:
        result = subprocess.run(['brili', '-p', *args], input=bril_json_str, capture_output=True, text=True, check=True, timeout=20)
    except subprocess.CalledProcessError:
        return 'N/A', static_instr_cnt, 'N/A'
    except subprocess.TimeoutExpired:
        return 'T/O', static_instr_cnt, 'T/O'

    assert result.stderr.startswith('total_dyn_inst: '), f"Invalid total_dyn_inst string: {result.stderr}"
    dyn_instr_cnt = int(result.stderr.split()[1])

    return result.stdout, static_instr_cnt, dyn_instr_cnt


def extract_args(bril_file_path):
    with open(bril_file_path, 'r') as f:
        contents = f.readlines()

    for line in contents:
        if line.replace(' ', '').startswith('#ARGS:'):
            return line[line.find(":") + 1:].split()

    return []


def eval_results(results):
    total_testcases = len(results)

    total_passes = 0
    static_increases = []
    dynamic_increases = []

    for result in results:
        if result['verdict'] == 'Good!':
            total_passes += 1

            static_increases.append(result['static_instr_count_roundtrip'] / result['static_instr_count_orig'])
            dynamic_increases.append(result['dyn_instr_count_roundtrip'] / result['dyn_instr_count_orig'])

    def geometric_mean(nums):
        if not nums:
            raise ValueError("Empty list")
        return math.exp(sum(math.log(x) for x in nums) / len(nums))

    print(f"Successful round trips: {total_passes}/{total_testcases}")

    if total_passes:
        print(f"Static Instr Increase (Geometric Mean): {geometric_mean(static_increases):.2f}x")
        print(f"Dynamic Instr Increase (Geometric Mean): {geometric_mean(dynamic_increases):.2f}x")
    else:
        print("No successful passes - no statistics to show.")


def main(input_paths):
    """Run SSA conversions and tests on bril programs within input_path"""

    # Will collect all target .bril files
    target_bril_files = []

    for input_path in input_paths:
        input_path = Path(input_path)

        if input_path.is_file():
            assert input_path.name.endswith('.bril'), f"Only .bril files accepted, was given: {input_path}"
            target_bril_files.append(input_path)
        else:
            assert input_path.is_dir(), f"Error: non-file and non-dir path: {input_path}"
            for children in input_path.iterdir():
                if children.is_file() and children.name.endswith('.bril'):
                    target_bril_files.append(children)
    
    results = [] 

    if len(target_bril_files) == 0:
        print("No bril files found.")
        return results

    print(f"Target programs: {len(target_bril_files)}")

    target_bril_files.sort()

    # Temporary work directory
    os.makedirs('./tmp', exist_ok=True)

    for target_bril_file in tqdm(target_bril_files):
        args = extract_args(target_bril_file)

        output, static_instr_cnt, dyn_instr_cnt = run_bril(target_bril_file, args)

        ssa_filename = os.path.join('./tmp', str(target_bril_file).replace('/', '__') + '.ssa')
        to_ssa_wrapper(target_bril_file, ssa_filename)

        ssa_output, ssa_static_instr_cnt, ssa_dyn_instr_cnt = run_bril(ssa_filename, args)

        with open(ssa_filename, 'r') as f:
            is_ssa_check = is_ssa.is_ssa(json.loads(subprocess.check_output(['bril2json'], stdin=f, text=True)))

        roundtrip_filename = os.path.join('./tmp', str(target_bril_file).replace('/', '__') + '.roundtrip')
        from_ssa_wrapper(ssa_filename, roundtrip_filename)

        roundtrip_output, roundtrip_static_instr_cnt, roundtrip_dyn_instr_cnt = run_bril(roundtrip_filename, args)

        match_1 = output == ssa_output
        match_2 = ssa_output == roundtrip_output

        if is_ssa_check and match_1 and match_2 and output != 'N/A' and output != 'T/O':
            verdict = 'Good!'
        else:
            if not is_ssa_check:
                verdict = "BAD: non-SSA"
            elif not match_1:
                verdict = 'BAD: match_1 fail'
            elif not match_2:
                verdict = 'BAD: match_2 fail'
            elif output == 'N/A':
                verdict = "BAD: original program fails"
            elif output == 'T/O':
                verdict = "BAD: original program times out"
            else:
                verdict = "BAD: unknown reason"

        record = {
            'file': str(target_bril_file),
            'verdict': verdict,
            'is_ssa': is_ssa_check,
            'match_1': match_1,
            'match_2': match_2,
            'output_orig': output,
            'output_ssa': ssa_output,
            'output_roundtrip': roundtrip_output,
            'static_instr_count_orig': static_instr_cnt,
            'static_instr_count_ssa': ssa_static_instr_cnt,
            'static_instr_count_roundtrip': roundtrip_static_instr_cnt,
            'dyn_instr_count_orig': dyn_instr_cnt,
            'dyn_instr_count_ssa': ssa_dyn_instr_cnt,
            'dyn_instr_count_roundtrip': roundtrip_dyn_instr_cnt,
        }

        results.append(record)

    eval_results(results)

    return results


if __name__ == '__main__':
    paths = sys.argv[1:]
    results = main(paths)

    with open('results.json', 'w') as f:
        json.dump(results, f, indent=2)


