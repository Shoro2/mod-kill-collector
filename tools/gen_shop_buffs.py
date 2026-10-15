#!/usr/bin/env python3
"""Generator of the token shop's class buffs (v2, 2026-10-15): one OWN spell per buff.

Every shop buff is a COPY of a class buff's top-rank spell with every amount x1.5 (round half up) and a one hour
duration (SpellDuration.dbc index 42): a spell of its own id in the module's band 2032000-2032099. The shop casts it
on the buyer (fl-lua-scripts TokenShop/TokenShop_Server.lua), the client shows its tooltip from the copy's row, and the
core's spell groups (EXCLUSIVE_HIGHEST) make a normal cast of the original fail with "A more powerful spell is already
active" while the copy holds. One generator writes everything that has to agree:

  * the Lua rows between `-- BEGIN GENERATED BUFFS` and `-- END GENERATED BUFFS` of TokenShop_Server.lua (--insert),
  * the server rows `data/sql/db-world/base/mod_kill_collector_shop_buffs.sql` (--sql): `spell_dbc` for every copy,
    `spell_group` / `spell_group_stack_rules` for the stacking,
  * the client rows' recipe `tools/shop_buff_spells.json` (--spec), which fl-pipeline script 214 applies to the client's
    Spell.dbc (hot_dbc and the CoA pack overlay),
  * the sticky id table `tools/shop_buff_ids.json` (a copy id once assigned never moves; a new pick takes the next free id).

Reads (read-only): the server's Data/dbc/Spell.dbc overlaid with the world database table `spell_dbc` (the table wins,
as in the core), SpellDuration.dbc, the tables `spell_ranks`, `spell_group`, `spell_group_stack_rules`, and the client's
effective Spell.dbc (the CoA pack overlay; its texts are the clean 3.3.5a ones, the server's CoA rows keep Ascension
variables). The generator ignores its own rows (spell ids and group ids of its bands) when they are already in the
database, so it can run again after the SQL is applied: `--verify` regenerates everything in memory and compares it with
the files on disk - run it against the live database to prove the committed files match what the live tables say.

What a copy is (the rules; a scenario or a reviewer finds them here):
  * the row of the ORIGINAL class spell (the single-target form, its top rank). Blessing of Sanctuary's real stat aura
    is the spell its script casts (67480), so that row is the source; the script's other parts (the damage reduction,
    the mana proc) are not part of the copy.
  * effects: every effect whose aura type is an amount the shop scales (SCALE_AURAS) is kept at the SAME effect index
    (the tooltip's $s1..$s3 follow) with the boosted amount baked in (no random points, no per-level part; level 80
    values), as a plain APPLY_AURA on the caster (implicit target 1): a self buff, never an area aura. Every other
    effect (a dummy a script reads, a no-op amount 0, a custom effect) is dropped.
  * the cast data is cleared (no cost, reagents, cooldown, category, range, stance or aura-state needs, no proc mask,
    no family): `SpellClassSet` and `SpellClassMask_*` are 0, so no talent, glyph or class script keyed to the family
    or the spell id touches the copy, and it belongs to no per-caster blessing rule.
  * the text: the client's name, icon and visuals, the rank text "Empowered"; the description and aura description are
    the client's own (they compute from the copy's boosted values) with the statements that no longer hold removed
    (party reach, the per-caster "only one" sentences) - see TEXT_RULES / TEXT_FIXES.

Stacking (spell groups): the copy joins every EXCLUSIVE_HIGHEST group its original sits in; for the original's rank
chains and group ("Greater ...") versions that no such group covers, a group of its own id (2300000-2300199) holds that
spell's first rank + the copy, with stack rule EXCLUSIVE_HIGHEST. A separate group per spell is used wherever one shared
group would change how two ORIGINALS stack (checked by a port of SpellMgr::CheckSpellGroupStackRules, which also proves
that every excluded spell and the copy end at rule EXCLUSIVE_HIGHEST); so no existing pair of spells changes its rule.

Usage:
  python gen_shop_buffs.py [--insert <TokenShop_Server.lua>] [--sql <file>] [--spec <file>] [--out <lua rows file>]
                           [--check] [--verify] [--tooltips] [--list]
  (no flag: the Lua rows to stdout.)  Environment: FL_DBC_DIR, FL_WORLDSERVER_CONF, FL_MYSQL, FL_SPELL_DBC_DDL,
  FL_WORLD_DB="host;port;user;password;database" (overrides the conf), FL_CLIENT_SPELL_DBC.
Add a buff: append the original's id to PICKS (class heading, id, shop name[, options]) and run again; the copy id is
assigned and written to shop_buff_ids.json (commit it).
"""
import argparse
import json
import math
import os
import re
import struct
import subprocess
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
FACTOR = 1.5
COPY_BAND = (2032000, 2032099)      # Spell ids of the copies (vault 06-custom-ids.md)
GROUP_BAND = (2300000, 2300399)     # spell_group ids of the pair groups (vault 06-custom-ids.md): 4 per copy id
GROUPS_PER_COPY = 4
DURATION_INDEX = 42                 # SpellDuration.dbc: 3,600,000 ms
DURATION_MS = 3600000
RANK_TEXT = "Empowered"
LEVEL = 80                          # the level the baked amounts are computed for (Battle Shout's per-level part)
STACK_HIGHEST = 4                   # SPELL_GROUP_STACK_RULE_EXCLUSIVE_HIGHEST

DBC_DIR = os.environ.get("FL_DBC_DIR", r"C:\wowstuff\dcore\Data\dbc")
DDL = os.environ.get("FL_SPELL_DBC_DDL", r"C:\Users\Anwender\Documents\GitHub\azerothcore-wotlk\data\sql\base\db_world\spell_dbc.sql")
CONF = os.environ.get("FL_WORLDSERVER_CONF", r"C:\wowstuff\dcore\configs\worldserver.conf")
MYSQL = os.environ.get("FL_MYSQL", r"C:\Program Files\MySQL\MySQL Server 8.4\bin\mysql.exe")
CLIENT_SPELL_DBC = os.environ.get("FL_CLIENT_SPELL_DBC", r"F:\wowstuff\coa-program\pack\overlay\DBFilesClient\Spell.dbc")
IDS_JSON = os.path.join(HERE, "shop_buff_ids.json")

# (class heading in the shop, [(spell id, shop name, {options})])
# options: source = the spell whose row is copied when the buff's real aura is another spell (Sanctuary),
#          greater = the stock group version(s) (Prayer of Fortitude, Gift of the Wild, Arcane Brilliance, the Greater
#          Blessings; any rank id) the copy must exclude too: they sit in the same exclusive-highest groups as the single-target
#          spell, so no group of its own is needed, but the generator proves the rule against them. (The CoA "Greater <name>"
#          versions are found by name and family.)
PICKS = [
    ("Priest", [(48161, "Power Word: Fortitude", {"greater": [48162]}), (48073, "Divine Spirit", {"greater": [48074]}),
                (48169, "Shadow Protection", {"greater": [48170]})]),
    ("Druid", [(48469, "Mark of the Wild", {"greater": [48470]}), (53307, "Thorns")]),
    ("Mage", [(42995, "Arcane Intellect", {"greater": [43002]})]),
    ("Paladin", [(20217, "Blessing of Kings", {"greater": [25898]}), (48932, "Blessing of Might", {"greater": [48934]}), (48936, "Blessing of Wisdom", {"greater": [48938]}),
                 (20911, "Blessing of Sanctuary", {"source": 67480})]),
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

# ---- the cast data every copy clears (numeric columns -> value) ------------------------------------------------
CLEAR_COLUMNS = {
    "Category": 0, "RecoveryTime": 0, "CategoryRecoveryTime": 0, "StartRecoveryCategory": 0, "StartRecoveryTime": 0,
    "InterruptFlags": 0, "PowerType": 0, "ManaCost": 0, "ManaCostPerLevel": 0, "ManaPerSecond": 0,
    "ManaPerSecondPerLevel": 0, "ManaCostPct": 0, "RuneCostID": 0, "RangeIndex": 1, "Speed": 0.0, "SpellMissileID": 0,
    "Targets": 0, "TargetCreatureType": 0, "RequiresSpellFocus": 0, "FacingCasterFlags": 0, "CasterAuraState": 0,
    "TargetAuraState": 0, "ExcludeCasterAuraState": 0, "ExcludeTargetAuraState": 0, "CasterAuraSpell": 0,
    "TargetAuraSpell": 0, "ExcludeCasterAuraSpell": 0, "ExcludeTargetAuraSpell": 0, "ShapeshiftMask": 0,
    "ShapeshiftExclude": 0, "StanceBarOrder": 0, "ProcTypeMask": 0, "ProcCharges": 0, "MaxTargets": 0,
    "MaxTargetLevel": 0, "SpellClassSet": 0, "SpellClassMask_1": 0, "SpellClassMask_2": 0, "SpellClassMask_3": 0,
    "CastingTimeIndex": 1, "DurationIndex": DURATION_INDEX,
}
for _i in range(1, 9):
    CLEAR_COLUMNS["Reagent_%d" % _i] = 0
    CLEAR_COLUMNS["ReagentCount_%d" % _i] = 0
for _i in (1, 2):
    CLEAR_COLUMNS["Totem_%d" % _i] = 0
    CLEAR_COLUMNS["RequiredTotemCategoryID_%d" % _i] = 0
# Attributes bits the copy clears: DO_NOT_DISPLAY (hidden in the aura bar: Sanctuary's stat aura 67480 has it) and
# COOLDOWN_ON_EVENT (no second cast while active: a re-buy must refresh)
CLEAR_ATTR0 = 0x80 | 0x02000000
# every column of one effect slot (a dropped effect zeroes all of them; ChainAmplitude / BonusMultiplier stay)
EFFECT_BASES = ["Effect", "EffectDieSides", "EffectRealPointsPerLevel", "EffectBasePoints", "EffectMechanic",
                "ImplicitTargetA", "ImplicitTargetB", "EffectRadiusIndex", "EffectAura", "EffectAuraPeriod",
                "EffectMultipleValue", "EffectChainTargets", "EffectItemType", "EffectMiscValue", "EffectMiscValueB",
                "EffectTriggerSpell", "EffectPointsPerCombo", "EffectSpellClassMaskA", "EffectSpellClassMaskB",
                "EffectSpellClassMaskC"]
FLOAT_EFFECT_BASES = {"EffectRealPointsPerLevel", "EffectMultipleValue", "EffectPointsPerCombo"}
TEXT_COLS = ("Name_Lang_enUS", "NameSubtext_Lang_enUS", "Description_Lang_enUS", "AuraDescription_Lang_enUS")

# ---- texts -----------------------------------------------------------------------------------------------------
# Sentences that describe a rule of the ORIGINAL which the copy is exempt from (removed from the description).
TEXT_RULES = [
    re.compile(r"(?:\r\n)+Players may only have one .*? at any one time\."),
    re.compile(r"\s+Players may only have one .*? at any one time\."),
    re.compile(r"(?:\r\n)+Can only have 1 \|cff[0-9a-fA-F]{6}Wuju\|r active on a target at a time\."),
    re.compile(r"(?:\r\n)+Does not stack with \|cff[0-9a-fA-F]{6}Call of the (?:Storm|Wind)\|r\."),
    re.compile(r"(?:\r\n)+Only one \|cff[0-9a-fA-F]{6}(?:Module|Wisdom)\|r per \w+ can be active\."),
]
# Explicit replacements per source spell (old, new): the area shouts become self buffs, Sanctuary names its one aura,
# Zeliek's aura text states 5 % as a literal. (None, new) replaces the whole text.
TEXT_FIXES = {
    47436: {"Description_Lang_enUS": [("The warrior shouts, increasing attack power of all raid and party members within $a1 yards by $s1.  Lasts $d.",
                                       "The warrior shouts, increasing attack power by $s1.  Lasts $d.")]},
    47440: {"Description_Lang_enUS": [("Increases maximum health of all party and raid members within $a1 yards by $s1.  Lasts $d.",
                                       "Increases maximum health by $s1.  Lasts $d.")]},
    57623: {"Description_Lang_enUS": [("The Death Knight blows the Horn of Winter, which generates 10 runic power and increases total Strength and Agility of all party or raid members within $a1 yards by $s1.  Lasts $d.",
                                       "The Death Knight blows the Horn of Winter, increasing total Strength and Agility by $s1.  Lasts $d.")]},
    300887: {"Description_Lang_enUS": [("Roar with barbaric fury, increasing the Agilty of nearby party and raid members by $s1 for $d.",
                                        "Roar with barbaric fury, increasing Agility by $s1 for $d.")]},
    681441: {"Description_Lang_enUS": [("Roar with enduring fury, increasing the Stamina of nearby allies by $s1 for $d.",
                                        "Roar with enduring fury, increasing Stamina by $s1 for $d.")]},
    803671: {"AuraDescription_Lang_enUS": [("Resource costs reduced by 5%.", "Resource costs reduced by $s2%.")]},
    67480: {"Description_Lang_enUS": [(None, "Places a Blessing on the friendly target, increasing strength and stamina by $s1% for $d.")],
            "AuraDescription_Lang_enUS": [(None, "Strength and stamina increased by $s1%.")]},
}


# ---- DBC / DDL -------------------------------------------------------------------------------------------------
COLS, TYPES, UNSIGNED = [], [], {}
for _m in re.finditer(r"^\s*`(\w+)`\s+(\w+(?: unsigned)?)", open(DDL, encoding="utf-8").read(), re.M):
    if _m.group(1) != "spell_dbc":
        COLS.append(_m.group(1))
        TYPES.append(_m.group(2).split()[0])
        UNSIGNED[_m.group(1)] = "unsigned" in _m.group(2)
assert len(COLS) == 234, len(COLS)
IDX = {c: i for i, c in enumerate(COLS)}


def _typed(k, v):
    t = TYPES[k]
    if t == "float":
        return struct.unpack("<f", struct.pack("<I", v))[0]
    if t == "bigint":
        return v
    return struct.unpack("<i", struct.pack("<I", v))[0]


class Dbc:
    """A Spell.dbc: records as python values by column (strings resolved) - read-only."""

    def __init__(self, path):
        self.path = path
        self.data = open(path, "rb").read()
        magic, self.n, nf, self.rs, self.ss = struct.unpack_from("<4s4I", self.data, 0)
        assert magic == b"WDBC" and nf == 234 and self.rs == 936, (path, magic, nf, self.rs)
        self.sb = 20 + self.n * self.rs
        self.index = {}
        for i in range(self.n):
            self.index.setdefault(struct.unpack_from("<I", self.data, 20 + i * self.rs)[0], i)

    def text(self, off):
        if off == 0 or off >= self.ss:
            return ""
        return self.data[self.sb + off:self.data.index(b"\0", self.sb + off)].decode("utf-8", "replace")

    def rec(self, rid):
        raw = struct.unpack_from("<234I", self.data, 20 + self.index[rid] * self.rs)
        out = []
        for k, v in enumerate(raw):
            t = TYPES[k]
            out.append(self.text(v) if t in ("varchar", "text") else _typed(k, v))
        return out


def split_rows(stdout):
    """mysql --batch output of `SELECT *` on spell_dbc: text columns may hold raw newlines, so count 234 fields."""
    nl, tab = chr(10), chr(9)
    toks = stdout.replace(chr(13) + nl, nl).split(tab)
    rows, cur = [], []
    for t in toks:
        if len(cur) == 233:
            last, nxt = t.rsplit(nl, 1) if nl in t else (t, None)
            cur.append(last)
            rows.append(cur)
            cur = [nxt] if nxt else []
        else:
            cur.append(t)
    return rows


def db_connection():
    spec = os.environ.get("FL_WORLD_DB")
    if spec:
        return spec.split(";")[:5]
    conf = open(CONF, encoding="utf-8", errors="replace").read()
    m = re.search(r'^WorldDatabaseInfo\s*=\s*"([^"]+)"', conf, re.M)
    return m.group(1).split(";")


def mysql(sql, raw_rows=False):
    host, port, user, pwd, _db = db_connection()
    out = subprocess.run([MYSQL, "-h" + host, "-P" + port, "-u" + user, "--batch", "--skip-column-names",
                          "--default-character-set=utf8mb4", "-e", sql],
                         env=dict(os.environ, MYSQL_PWD=pwd), capture_output=True, text=True, encoding="utf-8",
                         errors="replace")
    if out.returncode:
        raise SystemExit(out.stderr)
    if raw_rows:
        return out.stdout
    return [line.split("\t") for line in out.stdout.replace("\r\n", "\n").split("\n") if line]


def load_spells():
    """Server spell data: Data/dbc/Spell.dbc overlaid by acore_world.spell_dbc (the table wins) -> ({id: record},
    ids in the table, {id: name} of what the copy band already holds - taken out of the data)."""
    dbc = Dbc(os.path.join(DBC_DIR, "Spell.dbc"))
    spells = {rid: dbc.rec(rid) for rid in dbc.index}
    in_table = set()
    for f in split_rows(mysql("SELECT * FROM acore_world.spell_dbc", raw_rows=True)):
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
        in_table.add(rec[0])
    band = {}
    for sid in [s for s in spells if COPY_BAND[0] <= s <= COPY_BAND[1]]:
        band[sid] = (spells[sid][IDX["Name_Lang_enUS"]], sid in in_table and sid not in dbc.index)
        del spells[sid]
    return spells, in_table, band


def load_durations():
    data = open(os.path.join(DBC_DIR, "SpellDuration.dbc"), "rb").read()
    magic, n, nf, rs, ss = struct.unpack_from("<4s4I", data, 0)
    out = {}
    for i in range(n):
        a, b, _c, _d = struct.unpack_from("<I3i", data, 20 + i * rs)
        out[a] = b
    return out


def load_groups():
    """spell_ranks, spell_group, spell_group_stack_rules from the world database, without this generator's own rows."""
    first = {}
    for f, s, _r in mysql("SELECT first_spell_id, spell_id, `rank` FROM acore_world.spell_ranks"):
        first[int(s)] = int(f)
    members = defaultdict(list)
    for gid, sid in mysql("SELECT id, spell_id FROM acore_world.spell_group ORDER BY id, spell_id"):
        gid, sid = int(gid), int(sid)
        if GROUP_BAND[0] <= gid <= GROUP_BAND[1] or COPY_BAND[0] <= sid <= COPY_BAND[1]:
            continue
        members[gid].append(sid)
    rules = {}
    for row in mysql("SELECT group_id, stack_rule FROM acore_world.spell_group_stack_rules"):
        gid = int(row[0])
        if not GROUP_BAND[0] <= gid <= GROUP_BAND[1]:
            rules[gid] = int(row[1])
    return GroupModel(first, members, rules)


# ---- a port of the core's spell group logic (SpellMgr::LoadSpellGroups / CheckSpellGroupStackRules) --------------
class GroupModel:
    def __init__(self, first, members, rules):
        self.first = dict(first)
        # LoadSpellGroups erases a member whose rank is above 1 (the chain's first rank is the member)
        self.members = {g: [s for s in v if s < 0 or self.first.get(s, s) == s] for g, v in members.items()}
        self.rules = dict(rules)
        self.expanded = {g: self._expand(g, set()) for g in self.members}
        self.groups_of = defaultdict(set)
        for g_, spells in self.expanded.items():
            for s in spells:
                self.groups_of[s].add(g_)

    def _expand(self, gid, seen):
        if gid in seen:
            return set()
        seen.add(gid)
        out = set()
        for m in self.members.get(gid, []):
            if m < 0:
                out |= self._expand(-m, seen)
            else:
                out.add(m)
        return out

    def first_of(self, sid):
        return self.first.get(sid, sid)

    def rule_between(self, a, b):
        """SpellMgr::CheckSpellGroupStackRules for two spells (any rank ids)."""
        f1, f2 = self.first_of(a), self.first_of(b)
        common = []
        for grp in self.groups_of.get(f1, ()):
            if f2 in self.expanded[grp]:
                add = True
                for m in self.members[grp]:
                    if m < 0 and f1 in self.expanded.get(-m, ()) and f2 in self.expanded.get(-m, ()):
                        add = False
                        break
                if add:
                    common.append(grp)
        rule = 0
        for grp in sorted(common):
            if grp in self.rules:
                rule = self.rules[grp]
            if rule:
                break
        return rule

    def with_rows(self, extra_members, extra_rules):
        m = {g_: list(v) for g_, v in self.members.items()}
        for g_, spells in extra_members.items():
            lst = m.setdefault(g_, [])
            for s in spells:
                if s not in lst:
                    lst.append(s)
        r = dict(self.rules)
        r.update(extra_rules)
        return GroupModel(self.first, m, r)


# ---- effects ---------------------------------------------------------------------------------------------------
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
            137: "Stats" if misc == -1 else STATS.get(misc, "stat"), 230: "Max health", 345: "Spell power"}.get(aura, "aura %d" % aura)


def analyse(rec, sid, level=LEVEL):
    """-> dict(effects = [per slot: None | dict(kind scaled|dropped, ...)], what = [...], area)"""
    out, what, area = [], [], False
    for i in range(3):
        e = effect(rec, i)
        if not e["effect"]:
            out.append(None)
            continue
        if e["tgtA"] in (56, 57) or e["tgtB"] in (56, 57) or e["effect"] in (35, 65, 128):
            area = True
        die = e["die"]
        mean = e["bp"] + (1 + die) / 2.0 if die >= 1 else e["bp"]
        if e["effect"] not in APPLY_EFFECTS or not e["aura"] or e["aura"] not in SCALE_AURAS or mean == 0:
            why = ("effect %d" % e["effect"]) if e["effect"] not in APPLY_EFFECTS else "aura %d (amount %g)" % (e["aura"], mean)
            out.append(dict(kind="dropped", why="e%d %s" % (i, why)))
            continue
        assert float(mean).is_integer(), (sid, i, mean)
        add = 0
        if e["ppl"]:
            frm = max(g(rec, "BaseLevel"), g(rec, "SpellLevel"))
            cap = g(rec, "MaxLevel")
            lv = min(level, cap) if cap > 0 else level
            lv = max(lv, g(rec, "BaseLevel"))
            add = int((lv - frm) * e["ppl"]) if lv > frm else 0
        nat = int(mean) + add
        amount = boosted(nat)
        out.append(dict(kind="scaled", nat=nat, amount=amount, aura=e["aura"], misc=e["misc"]))
        what.append((label(e["aura"], e["misc"]), e["aura"], nat, amount, "%" if e["aura"] in PERCENT_AURAS else ""))
    return dict(effects=out, what=what, area=area)


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
    text = ", ".join(out)
    return text[:1].upper() + text[1:]


def slug(name):
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")


def lua_str(s):
    return '"' + s.replace("\\", "\\\\").replace('"', '\\"') + '"'


# ---- the plan --------------------------------------------------------------------------------------------------
def load_ids():
    if os.path.exists(IDS_JSON):
        return {int(k): int(v) for k, v in json.load(open(IDS_JSON, encoding="utf-8"))["ids"].items()}
    return {}


def assign_ids(picks, ids):
    """Sticky ids: a pick keeps its copy id; a new one takes the lowest free id of the band."""
    used = set(ids.values())
    new = {}
    for sid in picks:
        if sid not in ids:
            nxt = next(i for i in range(COPY_BAND[0], COPY_BAND[1] + 1) if i not in used)
            ids[sid] = nxt
            used.add(nxt)
            new[sid] = nxt
    return new


def apply_text_fixes(source_id, col, text):
    changed = False
    for old, new in TEXT_FIXES.get(source_id, {}).get(col, []):
        if old is None:
            text, changed = new, True
        elif old in text:
            text, changed = text.replace(old, new), True
        else:
            raise SystemExit("TEXT_FIXES %d %s: %r is not in %r" % (source_id, col, old, text))
    if col == "Description_Lang_enUS":
        for rx in TEXT_RULES:
            text2 = rx.sub("", text)
            if text2 != text:
                text, changed = text2.rstrip(), True
    return text, changed


def numbers_of(source_rec, an):
    """The effect edits one copy makes (column -> value; the common cast data is CLEAR_COLUMNS) and what the source
    must hold (column -> value)."""
    set_ = {}
    expect = {}
    for i, e in enumerate(an["effects"]):
        n = i + 1
        if e is None:
            continue
        if e["kind"] == "scaled":
            for col in ("EffectBasePoints", "EffectDieSides", "EffectMiscValue", "Effect"):
                expect["%s_%d" % (col, n)] = g(source_rec, "%s_%d" % (col, n))
            set_.update({"Effect_%d" % n: 6, "EffectDieSides_%d" % n: 1, "EffectBasePoints_%d" % n: e["amount"] - 1,
                         "EffectRealPointsPerLevel_%d" % n: 0.0, "ImplicitTargetA_%d" % n: 1, "ImplicitTargetB_%d" % n: 0,
                         "EffectRadiusIndex_%d" % n: 0, "EffectChainTargets_%d" % n: 0})
        else:
            for b in EFFECT_BASES:
                set_["%s_%d" % (b, n)] = 0.0 if b in FLOAT_EFFECT_BASES else 0
    return set_, expect


def find_scope(sp, gm, source_id, opts, is_coa):
    """First-rank ids of the spells a copy of `source_id` must exclude: the original's rank chain(s) - every spell of
    its name and family that carries a rank text, plus the spell itself - and its group ("Greater") versions."""
    src = sp[source_id]
    name, fam = g(src, "Name_Lang_enUS"), g(src, "SpellClassSet")
    rank_rx = re.compile(r"^Rank (\d+)$")
    m = rank_rx.match(g(src, "NameSubtext_Lang_enUS") or "")
    top = int(m.group(1)) if m else None     # ranks above the pick are not taught: not part of the scope
    in_chain = source_id in gm.first         # spell_ranks lists it: its chain is the scope
    own = {source_id}
    greater = set(opts.get("greater", []))
    for sid, r in sp.items():
        n = g(r, "Name_Lang_enUS")
        if n == name and g(r, "SpellClassSet") == fam:
            if in_chain:
                if gm.first_of(sid) == gm.first_of(source_id):
                    own.add(sid)
            else:       # a top rank outside its chain (CoA's Brutal Shout 7): the ranks of the same name and family
                mm = rank_rx.match(g(r, "NameSubtext_Lang_enUS") or "")
                if mm and top is not None and int(mm.group(1)) <= top:
                    own.add(sid)
        elif is_coa and n == "Greater " + name and g(r, "SpellClassSet") == fam:
            greater.add(sid)
    return sorted({gm.first_of(s) for s in own}), sorted({gm.first_of(s) for s in greater})


def plan_groups(gm, copies):
    """-> (members to add to existing groups {group: [copy ids]}, new groups {group: [spell ids]}, new rules,
    descriptions, notes, problems)."""
    add_members = defaultdict(list)
    new_members, new_rules, descr, notes = {}, {}, {}, []
    for c in copies:
        own_firsts, greater_firsts = c["scope"]
        everything = list(own_firsts) + [x for x in greater_firsts if x not in own_firsts]
        highest = sorted({gid for x in everything for gid in gm.groups_of.get(x, ()) if gm.rules.get(gid) == STACK_HIGHEST})
        covered = set()
        for gid in highest:
            covered |= gm.expanded[gid]
            add_members[gid].append(c["id"])
        need = [x for x in everything if x not in covered]
        c["groups_existing"], c["groups_new"] = highest, []
        if not need:
            continue
        # The new group's id is above every existing one, so sharing it turns the rule of two members that have none
        # (a pair whose common groups all carry rule 0, or none) into EXCLUSIVE_HIGHEST: such spells get groups apart.
        subgroups = []
        for x in need:
            for sg in subgroups:
                if all(gm.rule_between(x, y) != 0 for y in sg):
                    sg.append(x)
                    break
            else:
                subgroups.append([x])
        if len(subgroups) > 1:
            notes.append("copy %d (%s): %d groups, since the spells %s have no rule between them today" % (
                c["id"], c["name"], len(subgroups), need))
        base = GROUP_BAND[0] + (c["id"] - COPY_BAND[0]) * GROUPS_PER_COPY
        if len(subgroups) > GROUPS_PER_COPY:
            raise SystemExit("copy %d needs %d groups (at most %d)" % (c["id"], len(subgroups), GROUPS_PER_COPY))
        for gid, specs in [(base + k, sg) for k, sg in enumerate(subgroups)]:
            if not GROUP_BAND[0] <= gid <= GROUP_BAND[1]:
                raise SystemExit("group id %d outside the band %s" % (gid, GROUP_BAND))
            new_members[gid] = list(specs) + [c["id"]]
            new_rules[gid] = STACK_HIGHEST
            descr[gid] = "Token shop: %s (%s) with %s" % (c["name"], RANK_TEXT, ", ".join(str(x) for x in specs))
            c["groups_new"].append(gid)
    # proof on the model: every spell a copy excludes ends at rule EXCLUSIVE_HIGHEST with it, no pair of the
    # originals changed its rule, and no spell outside the scopes did either
    final = gm.with_rows({**new_members, **add_members}, new_rules)
    problems = []
    for c in copies:
        for x in list(c["scope"][0]) + list(c["scope"][1]):
            r = final.rule_between(c["id"], x)
            if r != STACK_HIGHEST:
                problems.append("copy %d vs %d: rule %d (not EXCLUSIVE_HIGHEST)" % (c["id"], x, r))
    olds = sorted({x for c in copies for x in list(c["scope"][0]) + list(c["scope"][1])})
    for i, a in enumerate(olds):
        for b in olds[i + 1:]:
            if gm.rule_between(a, b) != final.rule_between(a, b):
                problems.append("pair %d / %d changed its rule from %d to %d" % (a, b, gm.rule_between(a, b), final.rule_between(a, b)))
    return add_members, new_members, new_rules, descr, notes, problems


def build(sp, band, client, gm, ids):
    problems, notes, copies = [], [], []
    ranks = re.compile(r"Rank (\d+)")
    for cls, lst in PICKS:
        for item in lst:
            sid, shop = item[0], item[1]
            opts = item[2] if len(item) > 2 else {}
            source = opts.get("source", sid)
            if source not in sp or sid not in sp:
                problems.append("spell %d / %d (%s) is not in the server spell data" % (sid, source, shop))
                continue
            if source not in client.index:
                problems.append("spell %d (%s) is not in the client Spell.dbc %s" % (source, shop, client.path))
                continue
            rec, crec = sp[source], client.rec(source)
            an = analyse(rec, source)
            if not any(e and e["kind"] == "scaled" for e in an["effects"]):
                problems.append("%s (%d) has nothing to scale" % (shop, source))
            if g(rec, "CastingTimeIndex") not in (0, 1):
                problems.append("%s (%d) has a cast time (index %d)" % (shop, source, g(rec, "CastingTimeIndex")))
            cid = ids[sid]
            nm = g(crec, "Name_Lang_enUS")
            if cid in band and (band[cid][0] != nm or not band[cid][1]):
                problems.append("copy id %d (%s) is taken in the server data by %r" % (cid, shop, band[cid][0]))
            if cid in client.index and client.rec(cid)[IDX["Name_Lang_enUS"]] != nm:
                problems.append("copy id %d (%s) is taken in the client Spell.dbc by %r" % (cid, shop, client.rec(cid)[IDX["Name_Lang_enUS"]]))
            effect_set, expect = numbers_of(rec, an)
            set_ = {**CLEAR_COLUMNS, **effect_set}
            for col, v in expect.items():          # the client's source row must hold the numbers the server's does
                cv = crec[IDX[col]]
                if cv != v:
                    problems.append("%s: the client row of %d holds %s = %r, the server's %r" % (shop, source, col, cv, v))
            texts, src_texts, changed_cols = {}, {}, ["NameSubtext_Lang_enUS"]
            for col in ("Description_Lang_enUS", "AuraDescription_Lang_enUS"):
                old = g(crec, col)
                new, ch = apply_text_fixes(source, col, old)
                texts[col] = new
                if ch:
                    changed_cols.append(col)
                    src_texts[col] = old
            texts["NameSubtext_Lang_enUS"] = RANK_TEXT
            src_texts["NameSubtext_Lang_enUS"] = g(crec, "NameSubtext_Lang_enUS")
            key = "buff_" + slug(shop)
            fam = g(rec, "SpellClassSet")
            c = dict(id=cid, key=key, cls=cls, name=nm, shop=shop, spell=sid, source=source, what=what_text(an["what"]),
                     area=an["area"], analysis=an, set=set_, effect_set=effect_set, expect=expect, clear_bits={"Attributes": CLEAR_ATTR0},
                     texts=texts, src_texts=src_texts, text_changed=changed_cols,
                     scope=find_scope(sp, gm, source, opts, fam >= 12),
                     dropped=[e["why"] for e in an["effects"] if e and e["kind"] == "dropped"],
                     masks={c_: g(crec, c_) for c_ in ("Name_Lang_Mask", "Description_Lang_Mask", "AuraDescription_Lang_Mask")})
            if cid in {x["id"] for x in copies}:
                problems.append("duplicate copy id %d" % cid)
            if key in {x["key"] for x in copies}:
                problems.append("duplicate key %s" % key)
            copies.append(c)
            mm = ranks.search(g(rec, "NameSubtext_Lang_enUS"))
            if mm:
                hi = [oid for oid, o in sp.items() if oid != source and g(o, "Name_Lang_enUS") == g(rec, "Name_Lang_enUS")
                      and g(o, "SpellClassSet") == fam and ranks.search(g(o, "NameSubtext_Lang_enUS"))
                      and int(ranks.search(g(o, "NameSubtext_Lang_enUS")).group(1)) > int(mm.group(1)) and g(o, "SpellLevel") > 0]
                if hi:
                    notes.append("%s %d (%s): higher ranks exist in the data but are not the class's top taught rank: %s" % (
                        shop, source, g(rec, "NameSubtext_Lang_enUS"), hi))
    add_members, new_members, new_rules, descr, gnotes, gproblems = plan_groups(gm, copies)
    return copies, add_members, new_members, new_rules, descr, problems + gproblems, notes + gnotes


# ---- tooltip evaluator (proof that the final texts show the boosted numbers) ---------------------------------------
def render(text, cset, duration_ms=DURATION_MS):
    """The client's substitution for the variables the picks use ($s1-3, $m1-3, $M1-3, $d, ${expr}); $sps = 0."""
    def val(kind, n):
        bp = cset.get("EffectBasePoints_%d" % n, 0)
        die = cset.get("EffectDieSides_%d" % n, 0)
        lo = bp + (1 if die >= 1 else 0)
        hi = bp + die if die >= 1 else bp
        if kind == "s":
            return abs(lo)
        return lo if kind == "m" else hi

    def expr(m):
        e = re.sub(r"\$([smM])(\d)", lambda mm: str(val(mm.group(1), int(mm.group(2)))), m.group(1)).replace("$sps", "0")
        if not re.fullmatch(r"[0-9+\-*/. ()]+", e):
            return "<%s>" % e
        v = eval(e)
        return ("%d" % v) if float(v).is_integer() else ("%g" % v)

    text = re.sub(r"\$\{([^}]*)\}", expr, text)
    text = re.sub(r"\$([smM])(\d)", lambda m: str(val(m.group(1), int(m.group(2)))), text)
    d = ("%d hour" % (duration_ms // 3600000)) if duration_ms % 3600000 == 0 else ("%d min" % (duration_ms // 60000))
    return text.replace("$d", d).replace("\r\n", " / ")


def check_tooltips(copies):
    bad = []
    for c in copies:
        scaled = {i + 1 for i, e in enumerate(c["analysis"]["effects"]) if e and e["kind"] == "scaled"}
        for col in ("Description_Lang_enUS", "AuraDescription_Lang_enUS"):
            raw = c["texts"][col]
            t = render(raw, c["set"])
            if "$" in t or "<" in t:
                bad.append("%s (%d) %s still has a variable: %r" % (c["name"], c["id"], col, t))
            for n in {int(x) for x in re.findall(r"\$[smM](\d)", raw)}:
                if n not in scaled:
                    bad.append("%s (%d) %s names effect %d, which the copy does not carry" % (c["name"], c["id"], col, n))
    return bad


# ---- outputs -------------------------------------------------------------------------------------------------
def lua_rows(copies):
    lines, last = [], None
    for c in copies:
        if c["cls"] != last:
            lines.append("\t-- %s" % c["cls"])
            last = c["cls"]
        lines.append("\t{ key = %s, class = %s, spell = %d, base = %d, name = %s, what = %s }," % (
            lua_str(c["key"]), lua_str(c["cls"]), c["id"], c["spell"], lua_str(c["shop"]), lua_str(c["what"])))
        tag = []
        if c["source"] != c["spell"]:
            tag.append("a copy of %d, the aura the script of %d casts" % (c["source"], c["spell"]))
        if c["area"]:
            tag.append("area spell made a self buff")
        if c["dropped"]:
            tag.append("dropped: " + "; ".join(c["dropped"]))
        if tag:
            lines.append("\t\t-- %s (%d): %s" % (c["shop"], c["id"], " | ".join(tag)))
    return "\n".join(lines) + "\n"


def sql_text(s):
    s = s.replace("\ufffd", "'")
    return "'" + s.replace("\\", "\\\\").replace("'", "''").replace("\r", "\\r").replace("\n", "\\n") + "'"


def server_row(c, sp):
    """The 234 values of the copy's spell_dbc row: the server's row of the source with the copy's edits."""
    rec = list(sp[c["source"]])
    rec[IDX["ID"]] = c["id"]
    for col, v in c["set"].items():
        rec[IDX[col]] = v
    rec[IDX["Attributes"]] = rec[IDX["Attributes"]] & ~CLEAR_ATTR0 & 0xFFFFFFFF
    for k, name in enumerate(COLS):          # other locales empty (the server never reads them)
        if TYPES[k] in ("varchar", "text") and not name.endswith("enUS"):
            rec[k] = ""
    rec[IDX["Name_Lang_enUS"]] = c["name"]
    for col in ("NameSubtext_Lang_enUS", "Description_Lang_enUS", "AuraDescription_Lang_enUS"):
        rec[IDX[col]] = c["texts"][col]
    for mname, v in c["masks"].items():
        rec[IDX[mname]] = v
    rec[IDX["NameSubtext_Lang_Mask"]] = rec[IDX["Name_Lang_Mask"]]
    return rec


def sql_value(k, v):
    t = TYPES[k]
    if t == "float":
        return ("%.9g" % v) if v != int(v) else str(int(v))
    if t in ("varchar", "text"):
        return "NULL" if v == "" else sql_text(v)
    if t == "bigint":
        return str(v & 0xFFFFFFFFFFFFFFFF)
    if UNSIGNED[COLS[k]] and v < 0:
        return str(v & 0xFFFFFFFF)
    return str(v)


def sql_file(copies, sp, add_members, new_members, new_rules, descr):
    ids = sorted(c["id"] for c in copies)
    lines = [
        "-- mod-kill-collector: the token shop's class buffs as spells of their own. GENERATED by tools/gen_shop_buffs.py; do not edit.",
        "--",
        "-- spell_dbc: one row per shop buff, ids %d-%d (vault 06-custom-ids.md, band %d-%d): a copy of the class buff's top-rank" % (ids[0], ids[-1], COPY_BAND[0], COPY_BAND[1]),
        "-- row with every amount x1.5, one hour (SpellDuration index %d), a self buff, no cost or cooldown, no spell family," % DURATION_INDEX,
        "-- rank text '%s'." % RANK_TEXT,
        "-- spell_group / spell_group_stack_rules: the copy joins the EXCLUSIVE_HIGHEST group(s) its original sits in; the groups",
        "-- %d-%d each hold one spell's first rank + the copy where no such group covers it, so a normal cast of the" % GROUP_BAND,
        "-- original on someone holding the copy fails with 'A more powerful spell is already active'. The client rows come",
        "-- from fl-pipeline 214_token_shop_buff_spells.py (patch-9); the shop itself is fl-lua-scripts TokenShop/.",
        "-- Idempotent: the DELETEs name exactly the keys the INSERTs write.",
        "",
        "DELETE FROM `spell_dbc` WHERE `ID` BETWEEN %d AND %d;" % COPY_BAND,
        "INSERT INTO `spell_dbc` (" + ", ".join("`%s`" % c for c in COLS) + ") VALUES",
    ]
    rows = []
    for c in sorted(copies, key=lambda x: x["id"]):
        rec = server_row(c, sp)
        rows.append("(" + ",".join(sql_value(k, v) for k, v in enumerate(rec)) + ")")
    lines.append(",\n".join(rows) + ";")
    lines += ["", "DELETE FROM `spell_group` WHERE `spell_id` BETWEEN %d AND %d OR `id` BETWEEN %d AND %d;" % (COPY_BAND + GROUP_BAND)]
    gm_rows = ["(%d, %d)" % (gid, cid) for gid in sorted(add_members) for cid in sorted(add_members[gid])]
    gm_rows += ["(%d, %d)" % (gid, sid) for gid in sorted(new_members) for sid in new_members[gid]]
    lines.append("INSERT INTO `spell_group` (`id`, `spell_id`) VALUES")
    lines.append(",\n".join(gm_rows) + ";")
    lines += ["", "DELETE FROM `spell_group_stack_rules` WHERE `group_id` BETWEEN %d AND %d;" % GROUP_BAND,
              "INSERT INTO `spell_group_stack_rules` (`group_id`, `stack_rule`, `description`) VALUES"]
    lines.append(",\n".join("(%d, %d, %s)" % (gid, new_rules[gid], sql_text(descr[gid])) for gid in sorted(new_rules)) + ";")
    return "\n".join(lines) + "\n"


def spec_json(copies):
    out = {"about": "Written by mod-kill-collector tools/gen_shop_buffs.py; fl-pipeline 214_token_shop_buff_spells.py applies it to the "
                    "client's Spell.dbc. Do not edit: change PICKS and regenerate.",
           "factor": FACTOR, "duration_index": DURATION_INDEX, "rank_text": RANK_TEXT, "copy_band": list(COPY_BAND),
           "common": {"set": CLEAR_COLUMNS, "clear_bits": {"Attributes": CLEAR_ATTR0}},
           "copies": []}
    for c in sorted(copies, key=lambda x: x["id"]):
        out["copies"].append({
            "id": c["id"], "source": c["source"], "spell": c["spell"], "key": c["key"], "class": c["cls"], "name": c["name"],
            "what": c["what"], "set": c["effect_set"], "expect": c["expect"],
            "texts": {k: c["texts"][k] for k in c["text_changed"]}, "source_texts": c["src_texts"],
            "tooltip": {col: render(c["texts"][col], c["set"]) for col in ("Description_Lang_enUS", "AuraDescription_Lang_enUS")},
        })
    return json.dumps(out, indent=1, ensure_ascii=False) + "\n"


def insert_lua(path, text):
    src = open(path, encoding="utf-8", newline="").read()
    crlf = "\r\n" in src
    src = src.replace("\r\n", "\n")
    b, e = "-- BEGIN GENERATED BUFFS\n", "\t-- END GENERATED BUFFS"
    i, j = src.index(b) + len(b), src.index(e)
    new = src[:i] + text + src[j:]
    return new.replace("\n", "\r\n") if crlf else new


def read_lf(path):
    return open(path, encoding="utf-8", newline="").read().replace("\r\n", "\n") if os.path.exists(path) else ""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--insert", help="TokenShop_Server.lua: replace the rows between the markers")
    ap.add_argument("--sql", help="write the server rows (spell_dbc, spell_group, spell_group_stack_rules) to this file")
    ap.add_argument("--spec", help="write the client rows' recipe (JSON) to this file")
    ap.add_argument("--out", help="write the Lua rows to a file as well")
    ap.add_argument("--check", action="store_true", help="only report problems")
    ap.add_argument("--verify", action="store_true", help="regenerate in memory and compare with the --insert / --sql / --spec files")
    ap.add_argument("--tooltips", action="store_true", help="print every copy's rendered tooltip")
    ap.add_argument("--list", action="store_true", help="print the copy list: id, original, source, amounts, groups")
    args = ap.parse_args()

    sp, in_table, band = load_spells()
    durations = load_durations()
    if durations.get(DURATION_INDEX) != DURATION_MS:
        raise SystemExit("SpellDuration.dbc index %d is %r, not %d" % (DURATION_INDEX, durations.get(DURATION_INDEX), DURATION_MS))
    client = Dbc(CLIENT_SPELL_DBC)
    gm = load_groups()
    ids = load_ids()
    new_ids = assign_ids([it[0] for _c, lst in PICKS for it in lst], ids)
    copies, add_members, new_members, new_rules, descr, problems, notes = build(sp, band, client, gm, ids)
    problems += check_tooltips(copies)
    for n in notes:
        print("NOTE:", n, file=sys.stderr)
    for p in problems:
        print("PROBLEM:", p, file=sys.stderr)
    if problems:
        return 1
    lua = lua_rows(copies)
    sql = sql_file(copies, sp, add_members, new_members, new_rules, descr)
    spec = spec_json(copies)
    ids_text = json.dumps({"about": "Sticky copy ids of tools/gen_shop_buffs.py: original spell id -> copy id (band %d-%d). "
                                    "Never edit by hand; commit changes." % COPY_BAND,
                           "ids": {str(k): v for k, v in sorted(ids.items(), key=lambda kv: kv[1])}}, indent=1) + "\n"
    print("%d buffs (copies %d-%d), %d existing groups extended, %d new groups, %d new ids assigned" % (
        len(copies), min(c["id"] for c in copies), max(c["id"] for c in copies), len(add_members), len(new_members), len(new_ids)),
        file=sys.stderr)
    if args.list:
        for c in sorted(copies, key=lambda x: x["id"]):
            print("%d <- %d%s  %-16s %-26s %s | groups +%s new %s" % (
                c["id"], c["source"], "" if c["source"] == c["spell"] else " (cast %d)" % c["spell"], c["cls"], c["name"], c["what"],
                c["groups_existing"] or "-", c["groups_new"] or "-"))
    if args.tooltips:
        for c in sorted(copies, key=lambda x: x["id"]):
            print("%d %-26s D: %s" % (c["id"], c["name"], render(c["texts"]["Description_Lang_enUS"], c["set"])))
            print("%-33s A: %s" % ("", render(c["texts"]["AuraDescription_Lang_enUS"], c["set"])))
    if args.verify:
        bad = 0
        pairs = []
        if args.insert:
            pairs.append(("lua rows", read_lf(args.insert), insert_lua(args.insert, lua).replace("\r\n", "\n")))
        if args.sql:
            pairs.append(("sql", read_lf(args.sql), sql))
        if args.spec:
            pairs.append(("spec", read_lf(args.spec), spec))
        pairs.append(("ids", read_lf(IDS_JSON), ids_text))
        for what, cur, want in pairs:
            print("%s: %s" % (what, "IDENTICAL" if cur == want else "DIFFERENT"))
            bad += 0 if cur == want else 1
        return 1 if bad else 0
    if args.check:
        return 0
    if args.out:
        open(args.out, "w", encoding="utf-8", newline="\n").write(lua)
    if args.insert:
        new_lua = insert_lua(args.insert, lua)      # read first: open(..., "w") truncates the file
        open(args.insert, "w", encoding="utf-8", newline="").write(new_lua)
    if args.sql:
        open(args.sql, "w", encoding="utf-8", newline="\n").write(sql)
    if args.spec:
        open(args.spec, "w", encoding="utf-8", newline="\n").write(spec)
    if args.insert or args.sql or args.spec or args.out:
        open(IDS_JSON, "w", encoding="utf-8", newline="\n").write(ids_text)
    elif not (args.list or args.tooltips):
        sys.stdout.write(lua)
    return 0


if __name__ == "__main__":
    sys.exit(main())
