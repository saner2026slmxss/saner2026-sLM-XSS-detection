#!/usr/bin/env bash
set -u

TARGET_DIR="${1:?}"
LABEL="${2:?}"

run() {
  "$@" 2>&1 || return $?
}

process_file() {
  local js="$1"
  local base="${js%.js}"
  local pdg="${base}.json"
  local part="${base}.part.json"
  local slice="${base}.slices.jsonl"
  local success=1
  local run_output=""

  if [ -f "$slice" ]; then
    return 0 
  fi

  # echo "[1/3] build_pdg.js - node 1_build_pdg.js $js > $pdg"
  if run node 1_build_pdg.js "$js" > "$pdg" 2>&1; then
    # 2) Partition 
    # echo "[2/3] partition.py - python3 2_partition.py $pdg -o $part"
    if run python3 2_partition.py "$pdg" -o "$part" 2>&1; then
      # 3) Slices
      # echo "[3/3] gen_repr.py - python3 3_gen_repr.py --code $js --label ${LABEL} --out $slice"
      if run python3 3_gen_repr.py --code "$js" --label "${LABEL}" --out "$slice" 2>&1; then
        success=0
      fi
    fi
  fi

  if [ $success -eq 0 ]; then
    echo "[DONE] $js"
    :
  else
    echo"[FAIL] $js"
    rm -f "$js" "$pdg" "$part" "$slice"
  fi
}

export -f process_file run

echo "[SCAN] $TARGET_DIR"

export LABEL 

find "$TARGET_DIR" -type f -name "*.js" -print0 | xargs -0 -P 16 -n 1 bash -c 'process_file "$@"' _

echo "\n========================================"
echo "[ALL DONE]"