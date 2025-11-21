#!/bin/bash
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <search directory> <output filename>"
    echo "Example: $0 /path/to/data merged_output.jsonl"
    exit 1
fi

SEARCH_DIR="$1"
OUTPUT_FILE="$2"

if [ ! -d "$SEARCH_DIR" ]; then
    echo "Error: Directory '$SEARCH_DIR' not found or is not a directory."
    exit 1
fi

> "$OUTPUT_FILE"
echo "Recursively searching for all .jsonl files under directory '$SEARCH_DIR'."
echo "Merging results into '$OUTPUT_FILE'."
echo "---"

find "$SEARCH_DIR" -type f -name "*.jsonl" -print0 | while IFS= read -r -d $'\0' JSONL_FILE; do
    echo "Merging: $JSONL_FILE"
    cat "$JSONL_FILE" >> "$OUTPUT_FILE"
done

LINE_COUNT=$(wc -l < "$OUTPUT_FILE")
echo "---"
echo "Merging completed! A total of $LINE_COUNT lines of data have been successfully merged into '$OUTPUT_FILE'."