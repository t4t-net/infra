"""QuestieDB's forever data (GPLv3, github.com/Questie/QuestieDB): quest levels, givers, chains.

th files r lua: `QuestieDB.<kind>Data = [[return { [id] = {positional fields...}, ... }]]`. this reads
just th literal subset they use (tables, strings, numbers, nil, booleans) into python.
"""
import re
import urllib.request

BASE = "https://raw.githubusercontent.com/Questie/QuestieDB/master/data/Forever/forever{kind}DB.lua"

# 1-based field positions from each file's <kind>Keys table
QUEST = {"name": 1, "startedBy": 2, "finishedBy": 3, "requiredLevel": 4, "questLevel": 5, "requiredRaces": 6,
         "requiredClasses": 7, "objectivesText": 8, "preQuestGroup": 12, "preQuestSingle": 13, "zoneOrSort": 17,
         "nextQuestInChain": 22, "specialFlags": 24, "breadcrumbForQuestId": 27}
NPC = {"name": 1, "minLevel": 4, "maxLevel": 5, "spawns": 7, "zoneID": 9, "subName": 14}
OBJECT = {"name": 1, "spawns": 4, "zoneID": 5}

_TOKEN = re.compile(r"""\s*(?:(?P<str>"(?:[^"\\]|\\.)*"|'(?:[^'\\]|\\.)*')|(?P<num>-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?)"""
                    r"""|(?P<word>nil|true|false)|(?P<punct>[{}\[\]=,;]))""", re.S)
_ESC = {"n": "\n", "t": "\t", "r": "\r", "\\": "\\", '"': '"', "'": "'"}


def _tokens(text):
    pos = 0
    while True:
        m = _TOKEN.match(text, pos)
        if not m:
            if text[pos:].strip():
                raise ValueError(f"lua parse error near {text[pos:pos + 40]!r}")
            return
        pos = m.end()
        if m.group("str") is not None:
            s = m.group("str")[1:-1]
            yield "v", re.sub(r"\\(.)", lambda e: _ESC.get(e.group(1), e.group(1)), s)
        elif m.group("num") is not None:
            n = m.group("num")
            yield "v", float(n) if any(c in n for c in ".eE") else int(n)
        elif m.group("word") is not None:
            yield "v", {"nil": None, "true": True, "false": False}[m.group("word")]
        else:
            yield m.group("punct"), None


def parse(text):
    """one lua table literal -> list (positional only) or dict (any [key] = value)"""
    toks = _tokens(text)

    def value(tok, val):
        if tok == "v":
            return val
        if tok != "{":
            raise ValueError(f"unexpected {tok!r}")
        pos, keyed = [], {}
        for tok, val in toks:
            if tok == "}":
                break
            if tok in (",", ";"):
                continue
            if tok == "[":
                k = value(*next(toks))
                assert next(toks)[0] == "]" and next(toks)[0] == "="
                keyed[k] = value(*next(toks))
            else:
                pos.append(value(tok, val))
        if not keyed:
            return pos
        keyed.update({i + 1: v for i, v in enumerate(pos)})
        return keyed

    return value(*next(toks))


def load(kind):
    """kind is Quest, Npc or Object; returns {id: [fields...]} w 1-based fields at index-1"""
    with urllib.request.urlopen(urllib.request.Request(BASE.format(kind=kind), headers={"User-Agent": "forever-ah/0.1"}),
                                timeout=120) as r:
        text = r.read().decode()
    body = text[text.index(f"QuestieDB.{kind.lower()}Data = [[") + len(f"QuestieDB.{kind.lower()}Data = [["):]
    body = body[:body.rindex("]]")].strip()
    assert body.startswith("return"), body[:40]
    return parse(body[len("return"):])


def field(row, keys, name):
    i = keys[name] - 1
    return row[i] if i < len(row) else None
