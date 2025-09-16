#!/bin/sh
# Given a .bril file on stdin, perform local value numbering (LVN)
# followed by trivial dead code elimination (TDCE), then print a .bril file.
# Disclaimer: This script was written with the assistance of ChatGPT.

if [ $# -ne 1 ]; then
  echo "Usage: $0 <file.bril>" >&2
  exit 1
fi

input="$1"

bril2json < "$input" \
  | python3 lvn.py \
  | python3 tdce.py \
  | bril2txt
