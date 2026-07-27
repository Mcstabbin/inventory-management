#!/bin/bash

# PreToolUse hook: block console.log from being written into .vue files.
#
# Why: the Reports page shipped with console.log spam that fired on every
# render and flooded the browser console. This hook enforces the rule from
# CLAUDE.md ("no debug logging in committed components") at the moment code is
# written, so the same class of bug can't slip back in. It targets console.log
# specifically and intentionally allows console.error / console.warn, which the
# app legitimately uses inside catch blocks.
#
# Exit codes (Claude Code hook contract):
#   0 - allow the tool call to proceed
#   2 - block the tool call and surface the stderr message to Claude

INPUT=$(cat)

# Extract the target path and the text being written. Edit/Write/MultiEdit put
# the new content in different fields, so gather all of them.
if command -v jq &> /dev/null; then
    TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
    FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""')
    NEW_CONTENT=$(echo "$INPUT" | jq -r '
        [ .tool_input.content // empty,
          .tool_input.new_string // empty,
          ( .tool_input.edits[]?.new_string // empty ) ] | join("\n")
    ')
else
    # Fallback without jq: scan the whole raw payload.
    TOOL_NAME=""
    FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[^,]*' | head -1)
    NEW_CONTENT="$INPUT"
fi

# Only guard .vue files.
case "$FILE_PATH" in
    *.vue) ;;
    *) exit 0 ;;
esac

# Block if the incoming content introduces console.log(.
if echo "$NEW_CONTENT" | grep -qE 'console\.log\s*\('; then
    echo "Blocked: console.log detected in ${FILE_PATH}." >&2
    echo "Debug logging must not be committed in .vue components (see CLAUDE.md)." >&2
    echo "Remove the console.log, or use console.error/console.warn for genuine error paths." >&2
    exit 2
fi

exit 0
