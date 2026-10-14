#!/usr/bin/env python3
"""Generates the buff table of the token shop (fl-lua-scripts TokenShop/TokenShop_Server.lua).

Reads the server's spell data - the file Data/dbc/Spell.dbc overlaid with the world database table
`spell_dbc` (the table wins, as in the core) - and the SpellDuration.dbc, and writes the Lua rows between the
markers `-- BEGIN GENERATED BUFFS` and `-- END GENERATED BUFFS` of the server file. Read-only on the database
(one SELECT); needs the `mysql` client.

Every buff is the ORIGINAL class spell at its top rank (the single-target form where one exists). The shop casts it
on the buyer with each amount x1.5 and sets the aura to one hour, so this script writes, per spell, the amounts the
shop scales: `fx[effect index] = { base = <the amount a normal cast gives, without the per-level part>, die = <random
points, only when > 1> }`, and `lvl = { floor, from, per, cap }` when the amount grows with the caster's level (Battle
Shout). What is scaled: the aura types listed in SCALE_AURAS; an effect with another aura type (a dummy that a
script reads, a custom effect) stays as the spell has it and is listed in a comment.

Usage:  python gen_shop_buffs.py [--insert <TokenShop_Server.lua>] [--out <file>] [--check]
Add a buff: append the spell id to PICKS (class heading, id, shop name) and run the script again.
"""
import argparse
import math
import os
import re
import struct
import subprocess
import sys

FACTOR = 1.5
DBC_DIR = os.environ.get("FL_DBC_DIR", r"C:\wowstuff\dcore\Data\dbc")
DDL = os.environ.get("FL_SPELL_DBC_DDL", r"C:\Users\Anwender\Documents\GitHub\azerothcore-wotlk\data\sql\base\db_world\spell_dbc.sql")
CONF = os.environ.get("FL_WORLDSERVER_CONF", r"C:\wowstuff\dcore\configs\worldserver.conf")
MYSQL = os.environ.get("FL_MYSQL", r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe")

# (class heading in the shop, [(spell id, shop name, {options})])  - options: riders = spells the shop casts after
# the main one with their own scaled amounts (Blessing of Sanctuary's real effect is the spell its script casts).
PICKS = [
    ("Priest", [(48161, "Power Word: Fortitude"), (48073, "Divine Spirit"), (48169, "Shadow Protection")]),
    ("Druid", [(48469, "Mark of the Wild"), (53307, "Thorns")]),
    ("Mage", [(42995, "Arcane Intellect")]),
    ("Paladin", [(20217, "Blessing of Kings", {"oneOf": "Kings and Sanctuary"}), (48932, "Blessing of Might"), (48936, "Blessing of Wisdom"),
                 (20911, "Blessing of Sanctuary", {"riders": [67480], "oneOf": "Kings and Sanctuary"})]),
    ("Warrior", [(47436, "Battle Shout"), (47440, "Commanding Shout")]),
    ("Death Knight", [(57623, "Horn of Winter")]),
    ("Barbarian", [(300887, "Brutal Shout"), (681441, "Enduring Shout")]),
    ("Witch Doctor", [(561142, "Spirit Wuju"), (707677, "Power Wuju")]),
    ("Felsworn", [(523483, "Man'ari Intuition"), (501329, "Illidari Intuition")]),
    ("Witch Hunter", [(707687, "Witching Edict"), (707355, "Inquisitor's Edict"), (523488, "Knight's Edict")]),
    ("Stormbringer", [(578315, "Call of the Storm"), (503323, "Call of the Wind"), (575845, "Call of the Lightning")]),
    ("Knight of Xoroth", [(707696, "Mark of Blaumeux"), (803671, "Mark of Zeliek"), (707345, "Mark of Korth'azz"),
                          (803670, "Mark of Rivendare")]),
    ("Guardian", [(301232, "Honor"), (582535, "Fire Protection")]),
    ("Templar", [(572629, "Gift of Fervor"), (300923, "Gift of Zeal")]),
    ("Bloodmage", [(572403, "Bloodsoaked Offering"), (707340, "Sanguinary Offering"), (501670, "Bloodthorns")]),
    ("Ranger", [(803666, "Woodsman's Adaptation"), (523493, "Footpad's Adaptation")]),
    ("Chronomancer", [(572395, "Nozdormu's Wisdom"), (802829, "Chromie's Wisdom")]),
    ("Necromancer", [(572176, "Chill of the Tomb"), (572789, "Grim Mandate"), (573298, "Foul Mandate")]),
    ("Pyromancer", [(802822, "Seal of Alysrazor"), (808012, "Seal of Al'ar")]),
    ("Cultist", [(561386, "Whispers of N'Zoth"), (561391, "Whispers of Y'shaarj"), (572905, "Whispers of C'thun")]),
    ("Starcaller", [(301225, "Celestial Mind"), (573345, "Arcane Protection")]),
    ("Sun Cleric", [(572552, "Devotion of Emperors"), (572389, "Devotion of Dawn"), (300866, "Devotion of Grace"),
                    (575044, "Devotion of Radiance")]),
    ("Tinker", [(707688, "Power Module"), (803664, "Mana Module")]),
    ("Venomancer", [(707692, "Toxic Pheromones"), (803650, "Spider Pheromones"), (803655, "Beetle Pheromones")]),
    ("Reaper", [(803314, "Rite of Resolve"), (578129, "Rite of Power"), (575841, "Rite of Perseverance")]),
    ("Primalist", [(572815, "Grove Instinct"), (573349, "Primal Instinct"), (570755, "Earthen Endurance"),
                   (581315, "Essence of Nature")]),
    ("Runemaster", [(561236, "Etching of the Leylines"), (561240, "Etching of the Dextrous")]),
]

# Aura types whose amount the shop scales (flat or percent amounts that a buyer reads on the buff).
SCALE_AURAS = {
    15: "damage shield", 22: "resistance", 29: "stat", 72: "resource costs %", 85: "mana per 5 s", 99: "attack power",
    124: "ranged attack power", 137: "total stat %", 143: "resistance (exclusive)", 230: "max health",
    345: "spell power (Ascension)",
}
PERCENT_AURAS = {72, 137}
APPLY_EFFECTS = {6, 35, 65, 128}   # APPLY_AURA, area aura party / raid / friend
STATS = {-1: "all stats", 0: "Strength", 1: "Agility", 2: "Stamina", 3: "Intellect", 4: "Spirit"}
SCHOOLS = {2: "Holy", 4: "Fire", 8: "Nature", 16: "Frost", 32: "Shadow", 64: "Arcane"}

COLS, TYPES = [], []
for _m in re.finditer(r"^\s*`(\w+)`\s+(\w+)", open(DDL, encoding="utf-8").read(), re.M):
    if _m.group(1) != "spell_dbc":
        COLS.append(_m.group(1))
        TYPES.append(_m.group(2))
assert len(COLS) == 234, len(COLS)
IDX = {c: i for i, c in enumerate(COLS)}


def load_spells():
    path = os.path.join(DBC_DIR, "Spell.dbc")
    data = open(path, "rb").read()
    magic, n, nf, rs, ss = struct.unpack_from("<4s4I", data, 0)
    assert magic == b"WDBC" and nf == 234, (magic, nf)
    sb = 20 + n * rs

    def s(off):
        return "" if off >= ss else data[sb + off:data.index(b"\0", sb + off)].decode("utf-8", "replace")

    spells = {}
    for i in range(n):
        raw = struct.unpack_from("<234I", data, 20 + i * rs)
        rec = []
        for k, v in enumerate(raw):
            t = TYPES[k]
            if t == "float":
                rec.append(struct.unpack("<f", struct.pack("<I", v))[0])
            elif t in ("varchar", "text"):
                rec.append(s(v))
            elif t == "bigint":
                rec.append(v)
            else:
                rec.append(struct.unpack("<i", struct.pack("<I", v))[0])
        spells[raw[0]] = rec
    # the table overrides the file
    conf = open(CONF, encoding="utf-8", errors="replace").read()
    m = re.search(r'^WorldDatabaseInfo\s*=\s*"([^"]+)"', conf, re.M)
    host, port, user, pwd, _db = m.group(1).split(";")
    out = subprocess.run([MYSQL, "-h" + host, "-P" + port, "-u" + user, "--batch", "--skip-column-names", "-e",
                          "SELECT * FROM acore_world.spell_dbc"],
                         env=dict(os.environ, MYSQL_PWD=pwd), capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    if out.returncode:
        raise SystemExit(out.stderr)
    nl, tab = chr(10), chr(9)
    toks = out.stdout.replace(chr(13) + nl, nl).split(tab)
    rows, cur = [], []
    for t in toks:      # text columns hold raw newlines: count 234 fields per row instead of splitting on lines
        if len(cur) == 233:
            last, nxt = t.rsplit(nl, 1) if nl in t else (t, None)
            cur.append(last)
            rows.append(cur)
            cur = [nxt] if nxt else []
        else:
            cur.append(t)
    for f in rows:
        assert len(f) == 234
        rec = []
        for k, v in enumerate(f):
            t = TYPES[k]
            if t == "float":
                rec.append(float(v))
            elif t in ("varchar", "text"):
                rec.append("" if v == "NULL" else v)
            else:
                rec.append(int(v))
        spells[rec[0]] = rec
    return spells


def g(rec, name):
    return rec[IDX[name]]


def effect(rec, i):
    k = lambda base: rec[IDX["%s_%d" % (base, i + 1)]]
    return dict(effect=k("Effect"), die=k("EffectDieSides"), ppl=k("EffectRealPointsPerLevel"), bp=k("EffectBasePoints"),
                tgtA=k("ImplicitTargetA"), tgtB=k("ImplicitTargetB"), aura=k("EffectAura"), misc=k("EffectMiscValue"))


def boosted(natural):
    return int(math.floor(natural * FACTOR + 0.5))


def label(aura, misc):
    if aura == 29:
        return STATS.get(misc, "stat %d" % misc)
    if aura in (22, 143):
        if misc == 1:
            return "Armor"
        if misc == 126:
            return "all resistances"
        return "/".join(SCHOOLS[b] for b in SCHOOLS if misc & b) + " resistance"
    return {15: "Damage shield", 72: "Resource costs", 85: "Mana per 5 s", 99: "Attack power", 124: "Ranged attack power",
            137: "Stats" if misc == -1 else STATS.get(misc, "stat") , 230: "Max health", 345: "Spell power"}.get(aura, "aura %d" % aura)


def analyse(sp, sid, level=80):
    """-> dict(name, fx, lvl, party, what, unscaled, dur, cast)"""
    r = sp[sid]
    fx, what, unscaled, party = {}, [], [], False
    lvl = None
    for i in range(3):
        e = effect(r, i)
        if e["effect"] not in APPLY_EFFECTS or not e["aura"]:
            if e["effect"]:
                unscaled.append("e%d effect %d" % (i, e["effect"]))
            continue
        if e["tgtA"] == 56 or e["tgtB"] == 56:
            party = True
        die = e["die"]
        mean = e["bp"] + (1 + die) / 2.0 if die >= 1 else e["bp"]
        if e["aura"] not in SCALE_AURAS:
            unscaled.append("e%d aura %d (amount %g)" % (i, e["aura"], mean))
            continue
        if mean == 0:
            continue
        assert float(mean).is_integer(), (sid, i, mean)
        entry = {"base": int(mean)}
        if die > 1:
            assert die % 2 == 1, (sid, die)   # the mean of 1..die must be an integer
            entry["die"] = die
        add = 0
        if e["ppl"]:
            frm = max(g(r, "BaseLevel"), g(r, "SpellLevel"))
            cap = g(r, "MaxLevel")
            here = {"floor": g(r, "BaseLevel"), "from": frm, "per": e["ppl"], "cap": cap}
            assert lvl in (None, here), (sid, lvl, here)
            lvl = here
            lv = min(level, cap) if cap > 0 else level
            lv = max(lv, g(r, "BaseLevel"))
            add = int((lv - frm) * e["ppl"]) if lv > frm else 0
        nat = int(mean) + add
        fx[i] = entry
        sign = "-" if nat < 0 else "+"
        pct = "%" if e["aura"] in PERCENT_AURAS else ""
        what.append((label(e["aura"], e["misc"]), e["aura"], nat, boosted(nat), pct))
    return dict(name=g(r, "Name_Lang_enUS"), sub=g(r, "NameSubtext_Lang_enUS"), fx=fx, lvl=lvl, party=party,
                what=what, unscaled=unscaled, dur=g(r, "DurationIndex"), cast=g(r, "CastingTimeIndex"))


def what_text(parts):
    """Merge attack power + ranged attack power with the same amounts; join the rest."""
    out, skip = [], set()
    for k, (lab, aura, nat, bst, pct) in enumerate(parts):
        if k in skip:
            continue
        if aura == 99:
            for j, p in enumerate(parts):
                if p[1] == 124 and p[2] == nat and j not in skip:
                    skip.add(j)
                    lab = "Attack power (melee and ranged)"
        out.append("%s %+d%s > %+d%s" % (lab, nat, pct, bst, pct))
    return ", ".join(out)


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


def fx_lua(fx):
    parts = []
    for i in sorted(fx):
        e = fx[i]
        parts.append("[%d] = { base = %d%s }" % (i, e["base"], (", die = %d" % e["die"]) if "die" in e else ""))
    return "{ " + ", ".join(parts) + " }"


def build(sp, check=False):
    lines, seen, problems, notes = [], set(), [], []
    ranks = re.compile(r"Rank (\d+)")
    total = 0
    for cls, lst in PICKS:
        lines.append("\t-- %s" % cls)
        for item in lst:
            sid, shop = item[0], item[1]
            opts = item[2] if len(item) > 2 else {}
            if sid not in sp:
                problems.append("spell %d (%s) is not in the spell data" % (sid, shop))
                continue
            a = analyse(sp, sid)
            if a["cast"] not in (0, 1):
                problems.append("%s (%d) has a cast time (index %d)" % (shop, sid, a["cast"]))
            if not a["fx"] and not opts.get("riders"):
                problems.append("%s (%d) has nothing to scale" % (shop, sid))
            key = "buff_" + slug(shop)
            if key in seen:
                problems.append("duplicate key %s" % key)
            seen.add(key)
            what = what_text(a["what"])
            riders = []
            for rid in opts.get("riders", []):
                ra = analyse(sp, rid)
                riders.append("{ spell = %d, fx = %s }" % (rid, fx_lua(ra["fx"])))
                what = (what + ", " if what else "") + what_text(ra["what"])
            row = "\t{ key = %s, class = %s, spell = %d, name = %s, fx = %s" % (
                lua_str(key), lua_str(cls), sid, lua_str(shop), fx_lua(a["fx"]))
            if a["lvl"]:
                row += ", lvl = { floor = %d, from = %d, per = %g, cap = %d }" % (
                    a["lvl"]["floor"], a["lvl"]["from"], a["lvl"]["per"], a["lvl"]["cap"])
            if a["party"]:
                row += ", party = true"
            if riders:
                row += ", riders = { " + ", ".join(riders) + " }"
            if opts.get("oneOf"):
                row += ", oneOf = %s" % lua_str(opts["oneOf"])
            row += ", what = %s }," % lua_str(what[:1].upper() + what[1:])
            lines.append(row)
            total += 1
            tag = []
            if a["unscaled"]:
                tag.append("unscaled: " + "; ".join(a["unscaled"]))
            if a["party"]:
                tag.append("party area spell")
            if tag:
                lines.append("\t\t-- %s (%d): %s" % (shop, sid, " | ".join(tag)))
            # a higher rank with the same name and a rank label?
            mm = ranks.search(a["sub"])
            if mm:
                hi = [(oid, int(ranks.search(g(o, "NameSubtext_Lang_enUS")).group(1))) for oid, o in sp.items()
                      if oid != sid and g(o, "Name_Lang_enUS") == a["name"] and ranks.search(g(o, "NameSubtext_Lang_enUS"))
                      and int(ranks.search(g(o, "NameSubtext_Lang_enUS")).group(1)) > int(mm.group(1))
                      and g(o, "SpellLevel") > 0]
                if hi:
                    notes.append("%s %d (%s): higher ranks exist in the data but are not the class's top taught rank: %s" % (
                        shop, sid, a["sub"], hi))
    return lines, total, problems, notes


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--insert", help="TokenShop_Server.lua: replace the rows between the markers")
    ap.add_argument("--out", help="write the rows to a file as well")
    ap.add_argument("--check", action="store_true", help="only report problems")
    args = ap.parse_args()
    sp = load_spells()
    lines, total, problems, notes = build(sp)
    for n in notes:
        print("NOTE:", n, file=sys.stderr)
    for p in problems:
        print("PROBLEM:", p, file=sys.stderr)
    if problems:
        return 1
    text = "\n".join(lines) + "\n"
    print("%d buffs" % total, file=sys.stderr)
    if args.out:
        open(args.out, "w", encoding="utf-8", newline="\n").write(text)
    if args.insert:
        src = open(args.insert, encoding="utf-8", newline="").read()
        crlf = "\r\n" in src
        src = src.replace("\r\n", "\n")
        b, e = "-- BEGIN GENERATED BUFFS\n", "\t-- END GENERATED BUFFS"
        i, j = src.index(b) + len(b), src.index(e)
        src = src[:i] + text + src[j:]
        open(args.insert, "w", encoding="utf-8", newline="\r\n" if crlf else "\n").write(src)
    elif not args.out and not args.check:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
