# Run the run_lvn_tdce.sh on all .bril files in the input directory, and saving the output as .bril.lvn.dce files.
# Usage: ./run_all_dce.sh <input_directory>
# Disclaimer: This script was written by ChatGPT

#!/bin/bash
set -e

if [ "$#" -ne 1 ]; then
    echo "Usage: $0 <input_directory>"
    exit 1
fi

INPUT_DIR=$1

if [ ! -d "$INPUT_DIR" ]; then
    echo "Error: $INPUT_DIR is not a directory."
    exit 1
fi

for file in "$INPUT_DIR"/*.bril; do
    if [ -f "$file" ]; then
        echo "Processing $file..."
        ./run_lvn_tdce.sh "$file" > "$file.lvn.dce"
    else
        echo "No .bril files found in $INPUT_DIR."
    fi
done
echo "All files processed."

