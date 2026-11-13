"""Stop hook: catch robot voice in luna's last message and ask for a rewrite.

Reads the Stop hook payload on stdin, lints `last_assistant_message`, and prints
`{"decision": "block", "reason": ...}` when it finds robot-voice tells. Lets the
stop through when `stop_hook_active` is set, so a message gets at most one rewrite.
`--lint FILE` lints a plain-text file instead, for tuning.
"""

import json
import re
import sys

CODE_FENCE = re.compile(r"```.*?```", re.S)
INLINE_CODE = re.compile(r"`[^`\n]*`")
URL = re.compile(r"https?://\S+")
BOLD = re.compile(r"\*\*[^*\n]+\*\*")
# Quoting someone else's bold ("i put **this** in bold") isn't using it.
QUOTED = re.compile(r"\"[^\"\n]*\"|\u201c[^\u201d\n]*\u201d")
HEADER = re.compile(r"^\s{0,3}#{1,6}\s+\S", re.M)
TABLE_SEPARATOR = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)+\|?\s*$", re.M)
# A sentence starts at a line start (after any list or quote marker) or after .!? and a space.
SENTENCE_START = re.compile(r"(?:^|(?<=[.!?])\s+)(?:[-*>]\s+|\d+\.\s+)?([A-Z][a-z]+)\b", re.M)
VOICE_MARKER = re.compile(
    r">[/,w.~_]+<|>\.<|:3+|T_+T|\^\^|owo|uwu|aw+a|bweh+|wrff|"
    r"\b[a-z]*(?:sdf|jkl|dfg|lkj|ghj|skd|fjs)[a-z]*\b|_[a-z][^_\n]{2,}_"
)
NUMBER_WORD = re.compile(r"\b(?:nd|th|tht|wat|cuz|b4|lol|u|r|ur|2|4)\b")
# Only long-enough messages have room for voice; short tool narration is judged on formatting alone.
VOICE_MIN_CHARS = 280
MIN_CAPITAL_STARTS = 2


def prose(text: str) -> str:
    return URL.sub(" ", INLINE_CODE.sub(" ", CODE_FENCE.sub(" ", text)))


def problems(text: str) -> list[str]:
    body = prose(text)
    found = []
    capital_starts = SENTENCE_START.findall(body)
    if len(capital_starts) >= MIN_CAPITAL_STARTS:
        examples = ", ".join(f'"{w}"' for w in capital_starts[:4])
        found.append(f"{len(capital_starts)} sentences start w a capital letter ({examples})")
    bold_spans = BOLD.findall(QUOTED.sub(" ", body))
    if bold_spans:
        found.append(f"{len(bold_spans)} **bold** spans")
    if HEADER.search(body):
        found.append("markdown ### headers")
    if TABLE_SEPARATOR.search(body):
        found.append("a markdown table")
    if len(body) >= VOICE_MIN_CHARS:
        if not VOICE_MARKER.search(body):
            found.append("no kaomoji, keysmash or /me at all")
        if not NUMBER_WORD.search(body):
            found.append("no number-words or typos (2, 4, u, r, nd, th)")
    return found


def reason(found: list[str]) -> str:
    issues = "; ".join(found)
    return (
        f"luna voice lint (Stop hook): ur last message drifted into robot voice: {issues}. "
        "rewrite it as luna: lowercase starts, no bold/headers (a table only if ellie asked 4 one), "
        "paragraphs over bullets, typos nd number-words nd kaomoji. keep every fact exact, "
        "and just send the rewrite, no long apology."
    )


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "--lint":
        with open(sys.argv[2]) as f:
            print("\n".join(problems(f.read())) or "ok")
        return
    payload = json.load(sys.stdin)
    if payload.get("stop_hook_active"):
        return
    found = problems(payload.get("last_assistant_message") or "")
    if found:
        print(json.dumps({"decision": "block", "reason": reason(found)}))


if __name__ == "__main__":
    main()
