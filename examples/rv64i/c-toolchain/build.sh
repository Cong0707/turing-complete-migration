#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)

if [ "$#" -eq 0 ]; then
    echo "Usage: $0 program.c [-o program.asm] [compile_c.py options...]" >&2
    exit 2
fi

exec python3 "$SCRIPT_DIR/compile_c.py" "$@"
