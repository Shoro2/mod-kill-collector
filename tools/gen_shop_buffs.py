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
    is the spell its script casts (67480), so that row is the source, and the damage reduction its script casts
    (68066, aura 87) is added as the copy's third effect (`add` option); the script's mana proc (57319) is not part of
    the copy.
  * effects: every effect whose aura type is an amount the shop scales (SCALE_AURAS) is kept at the SAME effect index
    (the tooltip's $s1..$s3 follow) with the boosted amount baked in (no random points, no per-level part; level 80
    values; a negative amount, a reduction, is rounded on its magnitude: 3 % -> 5 %), as a plain APPLY_AURA on the
    caster (implicit target 1): a self buff, never an area aura. Every other effect (a dummy a script reads, a no-op
    amount 0, a custom effect) is dropped.
  * the cast data is cleared (no cost, reagents, cooldown, category, range, stance or aura-state needs, no proc mask,
    no family): `SpellClassSet` and `SpellClassMask_*` are 0, so no talent, glyph or class script keyed to the family
    or the spell id touches the copy.
  * the text: the client's name, icon and visuals, the rank text "Empowered"; the description and aura description are
    the client's own (they compute from the copy's boosted values) with the statements that no longer hold removed
    (party reach, the per-caster "only one" sentences) - see TEXT_RULES / TEXT_FIXES.

Stacking (spell groups): a copy follows every stacking rule its original follows and is exclusive-highest with the
normal versions of itself:
  * it joins every group of rule EXCLUSIVE (1), EXCLUSIVE_FROM_SAME_CASTER (2) and EXCLUSIVE_SAME_EFFECT (3) its original
    sits in (so a shop Kings does not add to what the Kings group forbids, one blessing per caster, ...), except where
    no other spell sits with it, or a same-effect group's aura type is none of the copy's (the core would log an error);
  * it joins every EXCLUSIVE_HIGHEST (4) group the original or its normal versions sit in;
  * for each normal version of the spell (its rank chain's first ranks, the group "Greater ..." versions, the spells
    that carry the same aura) the copy must end at rule 4 with it. The core takes the FIRST non-zero rule of the groups
    two spells share, in group id order, and a group of ours has the highest id: where an older group (EXCLUSIVE, per
    caster, same effect) would be first, the pair gets a group of its own (2300000-2300399, one per pair: the copy and
    that spell) which is also NESTED in the older groups (a `spell_group` row with a negative spell id): the core skips
    a group when a group nested in it holds both spells. A spell the shop's original does nothing with (Blessing of
    Sanctuary's dummy aura) gets such a pair group without a rule (0): a normal cast and the copy do not touch;
  * a port of SpellMgr::CheckSpellGroupStackRules proves the rule of every pair (copy / each normal version, copy /
    every spell the original has a rule with, copy / copy, no other pair changed) before anything is written.

Usage:
  python gen_shop_buffs.py [--insert <TokenShop_Server.lua>] [--sql <file>] [--spec <file>] [--out <lua rows file>]
                           [--check] [--verify] [--installed] [--tooltips] [--list]
  (no flag: the Lua rows to stdout.)  --verify: do the files on disk equal what the live tables make of PICKS?  --installed:
  do the live tables hold exactly the rows this writes (read-only)?  Environment: FL_DBC_DIR, FL_WORLDSERVER_CONF, FL_MYSQL,
  FL_SPELL_DBC_DDL, FL_WORLD_DB="host;port;user;password;database" (overrides the conf), FL_CLIENT_SPELL_DBC.
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
from collections import Counter, defaultdict

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
#          add = [(spell id, effect index from 0)]: that spell's effect becomes the next free effect slot of the copy,
#          scaled like the others (Sanctuary: the damage reduction its script casts, 68066);
#          exclude = further spells (any rank id) that carry the same aura as one of the copy's effects: the copy must be
#          exclusive-highest with them (68066);
#          inert = spells of the original's own family that have NO amount aura (a dummy a script reads: Sanctuary 20911
#          and its Greater version): the copy must have no rule with them (a normal cast must neither bounce nor remove it).
PICKS = [
    ("Priest", [(48161, "Power Word: Fortitude", {"greater": [48162]}), (48073, "Divine Spirit", {"greater": [48074]}),
                (48169, "Shadow Protection", {"greater": [48170]})]),
    ("Druid", [(48469, "Mark of the Wild", {"greater": [48470]}), (53307, "Thorns")]),
    ("Mage", [(42995, "Arcane Intellect", {"greater": [43002]})]),
    ("Paladin", [(20217, "Blessing of Kings", {"greater": [25898]}), (48932, "Blessing of Might", {"greater": [48934]}), (48936, "Blessing of Wisdom", {"greater": [48938]}),
                 (20911, "Blessing of Sanctuary", {"source": 67480, "add": [(68066, 0)], "exclude": [68066],
                                                   "inert": [20911, 25899]})]),
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
    15: "damage shield", 22: "resistance", 29: "stat", 72: "resource costs %", 85: "mana per 5 s", 87: "damage taken %",
    99: "attack power", 124: "ranged attack power", 137: "total stat %", 143: "resistance (exclusive)", 230: "max health",
    345: "spell power (Ascension)",
}
PERCENT_AURAS = {72, 87, 137}
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
    67480: {"Description_Lang_enUS": [(None, "Places a Blessing on the friendly target, increasing strength and stamina by $s1% and reducing damage taken from all sources by $s3% for $d.")],
            "AuraDescription_Lang_enUS": [(None, "Strength and stamina increased by $s1%, damage taken reduced by $s3%.")]},
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


def parse_db_row(f):
    """The 234 text fields of one `SELECT * FROM spell_dbc` row -> python values (NULL text = "")."""
    assert len(f) == 234, len(f)
    rec = []
    for k, v in enumerate(f):
        t = TYPES[k]
        if t == "float":
            rec.append(float(v))
        elif t in ("varchar", "text"):
            rec.append("" if v == "NULL" else v)
        else:
            rec.append(int(v))
    return rec


def load_spells():
    """Server spell data: Data/dbc/Spell.dbc overlaid by acore_world.spell_dbc (the table wins) -> ({id: record},
    ids in the table, {id: name} of what the copy band already holds - taken out of the data)."""
    dbc = Dbc(os.path.join(DBC_DIR, "Spell.dbc"))
    spells = {rid: dbc.rec(rid) for rid in dbc.index}
    in_table = set()
    for f in split_rows(mysql("SELECT * FROM acore_world.spell_dbc", raw_rows=True)):
        rec = parse_db_row(f)
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
        # this generator's own rows: the copies, the groups of its band, and the groups of its band nested in older ones
        if GROUP_BAND[0] <= gid <= GROUP_BAND[1] or COPY_BAND[0] <= sid <= COPY_BAND[1] or GROUP_BAND[0] <= -sid <= GROUP_BAND[1]:
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

    def counted(self, a, b):
        """The groups SpellMgr::CheckSpellGroupStackRules collects for two spells (any rank ids), in id order: the groups
        both are members of, without a group that has a NESTED group holding both of them (the nested one decides)."""
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
        return sorted(common)

    def rule_between(self, a, b):
        """SpellMgr::CheckSpellGroupStackRules for two spells (any rank ids): the first non-zero rule of `counted`."""
        rule = 0
        for grp in self.counted(a, b):
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
    """x1.5 rounded half up on the MAGNITUDE: a reduction of 3 % becomes 5 % (-4.5 rounded up would give 4), -5 % -> -8 %."""
    mag = int(math.floor(abs(natural) * FACTOR + 0.5))
    return -mag if natural < 0 else mag


def label(aura, misc):
    if aura == 29:
        return STATS.get(misc, "stat %d" % misc)
    if aura in (22, 143):
        if misc == 1:
            return "Armor"
        if misc == 126:
            return "all resistances"
        return "/".join(SCHOOLS[b] for b in SCHOOLS if misc & b) + " resistance"
    return {15: "Damage shield", 72: "Resource costs", 85: "Mana per 5 s", 87: "Damage taken", 99: "Attack power",
            124: "Ranged attack power", 137: "Stats" if misc == -1 else STATS.get(misc, "stat"), 230: "Max health",
            345: "Spell power"}.get(aura, "aura %d" % aura)


def analyse_effect(rec, i, sid, level=LEVEL):
    """One effect slot of a spell row -> (None | dict(kind scaled|dropped, ...), the `what` part or None, area flag)."""
    e = effect(rec, i)
    if not e["effect"]:
        return None, None, False
    area = e["tgtA"] in (56, 57) or e["tgtB"] in (56, 57) or e["effect"] in (35, 65, 128)
    die = e["die"]
    mean = e["bp"] + (1 + die) / 2.0 if die >= 1 else e["bp"]
    if e["effect"] not in APPLY_EFFECTS or not e["aura"] or e["aura"] not in SCALE_AURAS or mean == 0:
        why = ("effect %d" % e["effect"]) if e["effect"] not in APPLY_EFFECTS else "aura %d (amount %g)" % (e["aura"], mean)
        return dict(kind="dropped", why="e%d %s" % (i, why)), None, area
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
    part = (label(e["aura"], e["misc"]), e["aura"], nat, amount, "%" if e["aura"] in PERCENT_AURAS else "")
    return dict(kind="scaled", nat=nat, amount=amount, aura=e["aura"], misc=e["misc"]), part, area


def analyse(rec, sid, level=LEVEL):
    """-> dict(effects = [per slot: None | dict(kind scaled|dropped, ...)], what = [...], area)"""
    out, what, area = [], [], False
    for i in range(3):
        ent, part, a = analyse_effect(rec, i, sid, level)
        out.append(ent)
        area = area or a
        if part:
            what.append(part)
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


def numbers_of(source_rec, an, sp):
    """The effect edits one copy makes (column -> value; the common cast data is CLEAR_COLUMNS), what the source must
    hold (column -> value) and what each donor spell's effect must hold ({donor id: {column: value}}: an effect taken
    from another spell fills a slot the source leaves empty)."""
    set_ = {}
    expect = {}
    donors = {}
    for i, e in enumerate(an["effects"]):
        n = i + 1
        if e is None:
            continue
        if e["kind"] == "scaled" and e.get("donor"):
            did, didx = e["donor"]
            drec, dn = sp[did], didx + 1
            for col in ("Effect", "EffectAura"):
                expect["%s_%d" % (col, n)] = g(source_rec, "%s_%d" % (col, n))     # the slot is empty in the source
            donors.setdefault(did, {}).update({"%s_%d" % (col, dn): g(drec, "%s_%d" % (col, dn)) for col in (
                "Effect", "EffectAura", "EffectBasePoints", "EffectDieSides", "EffectMiscValue")})
            for b in EFFECT_BASES:
                set_["%s_%d" % (b, n)] = 0.0 if b in FLOAT_EFFECT_BASES else 0
            set_.update({"EffectAura_%d" % n: g(drec, "EffectAura_%d" % dn), "EffectMiscValue_%d" % n: g(drec, "EffectMiscValue_%d" % dn),
                         "EffectMiscValueB_%d" % n: g(drec, "EffectMiscValueB_%d" % dn)})
        elif e["kind"] == "scaled":
            for col in ("EffectBasePoints", "EffectDieSides", "EffectMiscValue", "Effect"):
                expect["%s_%d" % (col, n)] = g(source_rec, "%s_%d" % (col, n))
        else:
            for b in EFFECT_BASES:
                set_["%s_%d" % (b, n)] = 0.0 if b in FLOAT_EFFECT_BASES else 0
            continue
        set_.update({"Effect_%d" % n: 6, "EffectDieSides_%d" % n: 1, "EffectBasePoints_%d" % n: e["amount"] - 1,
                     "EffectRealPointsPerLevel_%d" % n: 0.0, "ImplicitTargetA_%d" % n: 1, "ImplicitTargetB_%d" % n: 0,
                     "EffectRadiusIndex_%d" % n: 0, "EffectChainTargets_%d" % n: 0})
    return set_, expect, donors


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


# ---- the stacking plan ------------------------------------------------------------------------------------------
AURA_EFFECT_IDS = {6, 27, 35, 65, 119, 128, 129, 143}    # SpellEffectInfo::IsAura(): APPLY_AURA and the area aura effects
HASTE_AURAS = {138, 140, 220}                            # the loader counts melee / ranged / melee+ranged haste as one
REPLACING = (1, 2, 4)                                    # EXCLUSIVE, FROM_SAME_CASTER, HIGHEST: the newer aura replaces the older one


def aura_types_of(rec):
    out = []
    for i in range(3):
        e = effect(rec, i)
        if e["effect"] in AURA_EFFECT_IDS and e["aura"]:
            out.append(e["aura"])
    return out


def type_counts(model, gid, sp, extra_auras):
    """How often each aura type occurs in the spells of a same-effect group: what SpellMgr::LoadSpellGroupStackRules
    counts to guess the group's aura type (`extra_auras`: {spell id: [aura types]} for spells that are not in `sp`)."""
    cnt = Counter()
    for s in model.expanded.get(gid, ()):
        for a in (aura_types_of(sp[s]) if s in sp else extra_auras.get(s, [])):
            cnt[138 if a in HASTE_AURAS else a] += 1
    return cnt


def types_of_counts(cnt):
    """-> (the aura types the core assigns to the group, True when the guess is a tie the core settles by chance)."""
    if not cnt:
        return set(), False
    top = max(cnt.values())
    best = sorted(a for a, n in cnt.items() if n == top)
    types = set(best)
    if 138 in types:
        types |= HASTE_AURAS
    return types, len(best) > 1


def plan_groups(gm, sp, copies):
    """The stacking of every copy, proven on a port of the core's spell group logic.
    -> (plan, notes, problems); plan = dict(joins {older group: [copy ids]}, nests {older group: [pair group ids]},
    pairs {pair group: [spell, copy]}, rules {pair group: 4 | 0}, descr {pair group: text}).

    A copy has the relations its original has: it joins every group of the original that carries a rule (exclusive, per
    caster, same effect, highest) and every rule-less group nested in another one (an exception: Man'ari Intuition and
    Mark of the Wild do not exclude each other). On top of that: rule 4 (EXCLUSIVE_HIGHEST) with the normal versions of
    the same spell (its rank chain, `exclude`) and with a group ("Greater") version whose original relation REPLACES (rule
    1, 2 or 4: the newer cast wins), so a normal cast never overrides the copy; rule 0 with an inert one. A relation the
    original has with a spell that may stack (rule 0 or 3) stays as it is. The core takes the first non-zero rule of the
    groups two spells share, lowest id first: where an older group would be first, the pair gets a group of its own that
    is nested in the older groups (the core skips a group when a group nested in it holds both spells)."""
    copy_auras = {c["id"]: [e["aura"] for e in c["analysis"]["effects"] if e and e["kind"] == "scaled"] for c in copies}
    nested_in = defaultdict(set)           # inner group -> the groups that nest it directly
    for gid, ms in gm.members.items():
        for m in ms:
            if m < 0:
                nested_in[-m].add(gid)

    def reach(gid):
        out, todo = {gid}, [gid]
        while todo:
            for outer in nested_in.get(todo.pop(), ()):
                if outer not in out:
                    out.add(outer)
                    todo.append(outer)
        return out

    joins, nests = defaultdict(list), defaultdict(list)
    pairs, rules, descr, notes, problems = {}, {}, {}, [], []
    for c in copies:
        cid = c["id"]
        own, greater = c["scope"]
        firsts = lambda lst: sorted({gm.first_of(x) for x in lst})
        originals = firsts(c["originals"])
        inert = firsts(c["inert"])
        want = {x: STACK_HIGHEST for x in list(own) + firsts(c["exclude"])}
        for x in greater:
            if x not in want and {gm.rule_between(o, x) for o in originals} & set(REPLACING):
                want[x] = STACK_HIGHEST
        for x in inert:
            want[x] = 0
        if set(inert) & (set(own) | set(greater) | set(firsts(c["exclude"]))):
            problems.append("copy %d: %s are both a normal version and inert" % (cid, sorted(set(inert) & (set(own) | set(greater)))))
        c["want"], c["originals_firsts"] = want, originals
        # 1. the groups of the original: those with a rule, and the rule-less ones nested in another group (exceptions)
        candidates = sorted({gid for o in originals for gid in gm.groups_of.get(o, ())
                             if gm.rules.get(gid, 0) or nested_in.get(gid)})
        joined = []
        for gid in candidates:
            if gm.rules.get(gid) != STACK_HIGHEST and not gm.expanded[gid] - set(want) - set(originals):
                notes.append("copy %d (%s): group %d not joined, nothing else sits in it" % (cid, c["name"], gid))
                continue
            if gm.rules.get(gid) == 3:
                types, _tie = types_of_counts(type_counts(gm, gid, sp, {}))
                if not types & set(copy_auras[cid]):
                    notes.append("copy %d (%s): same-effect group %d not joined, its aura type %s is none of the copy's %s" % (
                        cid, c["name"], gid, sorted(types), sorted(set(copy_auras[cid]))))
                    continue
            joined.append(gid)
        # a group the copy reaches through a nested group it joins needs no row of its own
        joined = [gid for gid in joined if not any(gid in reach(g2) and gid != g2 for g2 in joined)]
        for gid in joined:
            joins[gid].append(cid)
        model_c = gm.with_rows({gid: [cid] for gid in joined}, {})
        # 2. the pairs: rule 4 with the normal versions, rule 0 with an inert one
        base = GROUP_BAND[0] + (cid - COPY_BAND[0]) * GROUPS_PER_COPY
        mine = []
        for x in sorted(want, key=lambda s: (-want[s], s)):
            if model_c.rule_between(cid, x) == want[x]:
                continue
            counted = model_c.counted(cid, x)
            nonzero = [gid for gid in counted if model_c.rules.get(gid, 0)]
            if want[x] == STACK_HIGHEST:
                first4 = next((gid for gid in nonzero if model_c.rules[gid] == STACK_HIGHEST), None)
                nest = [gid for gid in nonzero if model_c.rules[gid] != STACK_HIGHEST and (first4 is None or gid < first4)]
            else:
                nest = nonzero
            pid = base + len(mine)
            if len(mine) >= GROUPS_PER_COPY or not GROUP_BAND[0] <= pid <= GROUP_BAND[1]:
                problems.append("copy %d needs more than %d pair groups" % (cid, GROUPS_PER_COPY))
                break
            mine.append(pid)
            pairs[pid] = [x, cid]
            rules[pid] = want[x]
            descr[pid] = "Token shop: %s (%s) %s %d" % (c["name"], RANK_TEXT, "with" if want[x] else "has no rule with", x)
            for gid in nest:
                nests[gid].append(pid)
        c["groups_existing"], c["groups_new"] = joined, mine
    # ---- the proof, on the model with every row of the plan ----------------------------------------------------------
    plan = dict(joins={k: sorted(v) for k, v in joins.items()}, nests={k: sorted(v) for k, v in nests.items()}, pairs=pairs,
                rules=rules, descr=descr)
    members = {gid: list(v) for gid, v in plan["joins"].items()}
    for gid, es in plan["nests"].items():
        members.setdefault(gid, []).extend(-e for e in es)
    members.update({pid: list(v) for pid, v in pairs.items()})
    final = gm.with_rows(members, rules)
    copy_ids = {c["id"] for c in copies}
    for c in copies:
        cid = c["id"]
        for x, w in sorted(c["want"].items()):
            r = final.rule_between(cid, x)
            if r != w:
                problems.append("copy %d vs %d: rule %d, wanted %d (groups %s)" % (cid, x, r, w, final.counted(cid, x)))
        # every other spell: the rule the original has with it
        related = set()
        for gid in final.groups_of.get(cid, ()):
            related |= final.expanded[gid]
        for y in sorted(related - {cid} - copy_ids - set(c["want"])):
            fin = final.rule_between(cid, y)
            allowed = {gm.rule_between(o, y) for o in c["originals_firsts"]}
            if fin not in allowed:
                problems.append("copy %d vs %d: rule %d, the original has %s (groups %s)" % (cid, y, fin, sorted(allowed), final.counted(cid, y)))
    for i, c1 in enumerate(copies):
        for c2 in copies[i + 1:]:
            fin = final.rule_between(c1["id"], c2["id"])
            allowed = {gm.rule_between(o1, o2) for o1 in c1["originals_firsts"] for o2 in c2["originals_firsts"]}
            if fin not in allowed:
                problems.append("copies %d / %d: rule %d, the originals have %s (groups %s)" % (
                    c1["id"], c2["id"], fin, sorted(allowed), final.counted(c1["id"], c2["id"])))
    touched = sorted(set(plan["joins"]) | set(plan["nests"]))
    for gid in touched:
        spells = sorted(gm.expanded.get(gid, ()))
        for i, a in enumerate(spells):
            for b in spells[i + 1:]:
                if gm.rule_between(a, b) != final.rule_between(a, b):
                    problems.append("pair %d / %d of group %d changed its rule from %d to %d" % (
                        a, b, gid, gm.rule_between(a, b), final.rule_between(a, b)))
    # a same-effect group's aura type is what the loader guesses from its members: it must stay the same, and every copy
    # in it must carry one of its types (else the core logs an error at boot)
    copy_groups = {g_ for cid_ in copy_ids for g_ in final.groups_of.get(cid_, ())}
    for gid in sorted(g_ for g_ in copy_groups if gm.rules.get(g_) == 3):
        before, tie_before = types_of_counts(type_counts(gm, gid, sp, {}))
        after, tie_after = types_of_counts(type_counts(final, gid, sp, copy_auras))
        if after != before or tie_after != tie_before:
            problems.append("same-effect group %d: the copies change its guessed aura type %s -> %s" % (gid, sorted(before), sorted(after)))
        for cid in sorted(copy_ids & final.expanded.get(gid, set())):
            if not after & set(copy_auras[cid]):
                problems.append("copy %d is in same-effect group %d without one of its aura types %s" % (cid, gid, sorted(after)))
    # the loader drops a member that is no spell or has a rank above 1 and logs an error: every spell of a pair group is a first rank
    for pid, ms in sorted(pairs.items()):
        for x in ms:
            if x not in sp and x not in copy_ids:
                problems.append("pair group %d names spell %d, which is not in the server's spell data" % (pid, x))
            if gm.first_of(x) != x:
                problems.append("pair group %d names spell %d, which is not the first rank of its chain" % (pid, x))
    return plan, notes, problems


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
            for donor, didx in opts.get("add", []):       # an effect of another spell fills the next free slot
                if donor not in sp or donor not in client.index:
                    problems.append("%s: donor spell %d is not in the server data and the client Spell.dbc" % (shop, donor))
                    continue
                ent, part, _area = analyse_effect(sp[donor], didx, donor)
                slot = next((k for k, e in enumerate(an["effects"]) if e is None), None)
                if not ent or ent["kind"] != "scaled":
                    problems.append("%s: effect %d of donor %d is not an amount the shop scales" % (shop, didx, donor))
                elif slot is None:
                    problems.append("%s: no free effect slot for the effect of donor %d" % (shop, donor))
                else:
                    ent["donor"] = (donor, didx)
                    an["effects"][slot] = ent
                    an["what"].append(part)
                    for col in ("Effect", "EffectAura", "EffectBasePoints", "EffectDieSides", "EffectMiscValue"):
                        col = "%s_%d" % (col, didx + 1)
                        cv = client.rec(donor)[IDX[col]]
                        if cv != g(sp[donor], col):       # the client's donor row must hold the numbers the server's does
                            problems.append("%s: the client row of donor %d holds %s = %r, the server's %r" % (
                                shop, donor, col, cv, g(sp[donor], col)))
            if g(rec, "CastingTimeIndex") not in (0, 1):
                problems.append("%s (%d) has a cast time (index %d)" % (shop, source, g(rec, "CastingTimeIndex")))
            cid = ids[sid]
            nm = g(crec, "Name_Lang_enUS")
            if cid in band and (band[cid][0] != nm or not band[cid][1]):
                problems.append("copy id %d (%s) is taken in the server data by %r" % (cid, shop, band[cid][0]))
            if cid in client.index and client.rec(cid)[IDX["Name_Lang_enUS"]] != nm:
                problems.append("copy id %d (%s) is taken in the client Spell.dbc by %r" % (cid, shop, client.rec(cid)[IDX["Name_Lang_enUS"]]))
            effect_set, expect, donors = numbers_of(rec, an, sp)
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
                     area=an["area"], analysis=an, set=set_, effect_set=effect_set, expect=expect, donors=donors,
                     clear_bits={"Attributes": CLEAR_ATTR0},
                     texts=texts, src_texts=src_texts, text_changed=changed_cols,
                     scope=find_scope(sp, gm, source, opts, fam >= 12),
                     exclude=list(opts.get("exclude", [])), inert=list(opts.get("inert", [])),
                     originals=sorted({sid, source}),
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
    plan, gnotes, gproblems = plan_groups(gm, sp, copies)
    return copies, plan, problems + gproblems, notes + gnotes


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
        if c["donors"]:
            tag.append("plus the effect of %s (the script's damage reduction; its mana proc is not part of the copy)" % ", ".join(
                str(d) for d in sorted(c["donors"])))
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


def group_rows(plan):
    """The rows of the plan in `spell_group`: ([(older group, copy)], [(older group, -pair group)], [(pair group, spell)])."""
    joined = [(gid, cid) for gid in sorted(plan["joins"]) for cid in plan["joins"][gid]]
    nested = [(gid, -pid) for gid in sorted(plan["nests"]) for pid in plan["nests"][gid]]
    pair_rows = [(pid, s) for pid in sorted(plan["pairs"]) for s in plan["pairs"][pid]]
    return joined, nested, pair_rows


def sql_file(copies, sp, plan):
    ids = sorted(c["id"] for c in copies)
    joined, nested, pair_rows = group_rows(plan)
    lines = [
        "-- mod-kill-collector: the token shop's class buffs as spells of their own. GENERATED by tools/gen_shop_buffs.py; do not edit.",
        "--",
        "-- spell_dbc: one row per shop buff, ids %d-%d (vault 06-custom-ids.md, band %d-%d): a copy of the class buff's top-rank" % (ids[0], ids[-1], COPY_BAND[0], COPY_BAND[1]),
        "-- row with every amount x1.5, one hour (SpellDuration index %d), a self buff, no cost or cooldown, no spell family," % DURATION_INDEX,
        "-- rank text '%s'." % RANK_TEXT,
        "-- spell_group / spell_group_stack_rules: a copy follows every stacking rule its original follows (it joins the groups of",
        "-- rule exclusive, per caster and same effect the original sits in) and is exclusive-highest with the normal versions of",
        "-- itself, so a normal cast of the original on someone holding the copy fails with 'A more powerful spell is already",
        "-- active'. The core takes the first non-zero rule of the groups two spells share, lowest group id first; so each such",
        "-- pair has a group of its own in the band %d-%d (the copy and that spell; rule 4, or no rule for a spell the" % GROUP_BAND,
        "-- original's script drives and that has no amount), and where an older group would come first, the pair group is also",
        "-- nested in that group (a row with a negative spell id: the core skips a group when a group nested in it holds both",
        "-- spells). The client rows come from fl-pipeline 214_token_shop_buff_spells.py (patch-9); the shop itself is",
        "-- fl-lua-scripts TokenShop/.",
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
    lines += ["", "DELETE FROM `spell_group` WHERE `spell_id` BETWEEN %d AND %d OR `id` BETWEEN %d AND %d OR `spell_id` BETWEEN %d AND %d;" % (
        COPY_BAND + GROUP_BAND + (-GROUP_BAND[1], -GROUP_BAND[0])),
        "", "-- the copies in the groups their originals (or the originals' normal versions) sit in",
        "INSERT INTO `spell_group` (`id`, `spell_id`) VALUES",
        ",\n".join("(%d, %d)" % r for r in joined) + ";"]
    if nested:
        lines += ["", "-- the pair groups nested in the older groups that would otherwise come first",
                  "INSERT INTO `spell_group` (`id`, `spell_id`) VALUES", ",\n".join("(%d, %d)" % r for r in nested) + ";"]
    lines += ["", "-- the pair groups: a normal version of the spell (or an inert one) and the copy",
              "INSERT INTO `spell_group` (`id`, `spell_id`) VALUES", ",\n".join("(%d, %d)" % r for r in pair_rows) + ";"]
    lines += ["", "DELETE FROM `spell_group_stack_rules` WHERE `group_id` BETWEEN %d AND %d;" % GROUP_BAND,
              "INSERT INTO `spell_group_stack_rules` (`group_id`, `stack_rule`, `description`) VALUES"]
    lines.append(",\n".join("(%d, %d, %s)" % (pid, plan["rules"][pid], sql_text(plan["descr"][pid])) for pid in sorted(plan["rules"])) + ";")
    return "\n".join(lines) + "\n"


def spec_json(copies):
    out = {"about": "Written by mod-kill-collector tools/gen_shop_buffs.py; fl-pipeline 214_token_shop_buff_spells.py applies it to the "
                    "client's Spell.dbc. Do not edit: change PICKS and regenerate.",
           "factor": FACTOR, "duration_index": DURATION_INDEX, "rank_text": RANK_TEXT, "copy_band": list(COPY_BAND),
           "common": {"set": CLEAR_COLUMNS, "clear_bits": {"Attributes": CLEAR_ATTR0}},
           "copies": []}
    for c in sorted(copies, key=lambda x: x["id"]):
        row = {
            "id": c["id"], "source": c["source"], "spell": c["spell"], "key": c["key"], "class": c["cls"], "name": c["name"],
            "what": c["what"], "set": c["effect_set"], "expect": c["expect"],
            "texts": {k: c["texts"][k] for k in c["text_changed"]}, "source_texts": c["src_texts"],
            "tooltip": {col: render(c["texts"][col], c["set"]) for col in ("Description_Lang_enUS", "AuraDescription_Lang_enUS")},
        }
        if c["donors"]:      # rows of other spells an effect was taken from: 214 checks them before it writes
            row["donors"] = {str(d): c["donors"][d] for d in sorted(c["donors"])}
        out["copies"].append(row)
    return json.dumps(out, indent=1, ensure_ascii=False) + "\n"


def same_value(k, a, b):
    t = TYPES[k]
    if t == "float":
        return abs(float(a) - float(b)) <= 1e-4 * max(1.0, abs(float(a)))
    if t in ("varchar", "text"):
        # mysql --batch writes a line feed as the two characters \n and python's text mode turns a carriage return into a
        # line feed: compare without any line break (and with U+FFFD as the apostrophe it stands for in the SQL)
        flat = lambda s: re.sub(r"\\n|\\r|\r|\n", "", str(s).replace(chr(0xFFFD), "'"))
        return flat(a) == flat(b)
    if UNSIGNED[COLS[k]]:
        mask = 0xFFFFFFFFFFFFFFFF if t == "bigint" else 0xFFFFFFFF
        return (int(a) & mask) == (int(b) & mask)
    return int(a) == int(b)


def installed(copies, sp, plan):
    """Read-only: do the LIVE tables hold exactly the rows this generator writes (the module SQL was applied and nothing
    has changed them since)? -> list of report lines, a line starting with DIFFERENT for each table that differs."""
    out = []
    want = {c["id"]: server_row(c, sp) for c in copies}
    got = {}
    for f in split_rows(mysql("SELECT * FROM acore_world.spell_dbc WHERE ID BETWEEN %d AND %d" % COPY_BAND, raw_rows=True)):
        rec = parse_db_row(f)
        got[rec[0]] = rec
    diffs = []
    for sid in sorted(set(want) | set(got)):
        if sid not in got:
            diffs.append("spell_dbc %d is missing" % sid)
        elif sid not in want:
            diffs.append("spell_dbc %d is in the table but not in the plan" % sid)
        else:
            cols = [COLS[k] for k in range(234) if not same_value(k, want[sid][k], got[sid][k])]
            if cols:
                diffs.append("spell_dbc %d differs in %s" % (sid, ", ".join(cols[:6]) + (" ..." if len(cols) > 6 else "")))
    out.append("spell_dbc: %d rows planned, %d in the table: %s" % (len(want), len(got), "IDENTICAL" if not diffs else "DIFFERENT"))
    out += ["    " + d for d in diffs[:20]]
    joined, nested, pair_rows = group_rows(plan)
    want_g = set(joined) | set(nested) | set(pair_rows)
    got_g = {(int(a), int(b)) for a, b in mysql(
        "SELECT id, spell_id FROM acore_world.spell_group WHERE spell_id BETWEEN %d AND %d OR id BETWEEN %d AND %d OR spell_id BETWEEN %d AND %d" % (
            COPY_BAND + GROUP_BAND + (-GROUP_BAND[1], -GROUP_BAND[0])))}
    d_g = ["spell_group row (%d, %d) is missing" % r for r in sorted(want_g - got_g)] + [
        "spell_group row (%d, %d) is in the table but not in the plan" % r for r in sorted(got_g - want_g)]
    out.append("spell_group: %d rows planned, %d in the table: %s" % (len(want_g), len(got_g), "IDENTICAL" if not d_g else "DIFFERENT"))
    out += ["    " + d for d in d_g[:20]]
    want_r = {pid: plan["rules"][pid] for pid in plan["rules"]}
    got_r = {int(a): int(b) for a, b, *_ in mysql(
        "SELECT group_id, stack_rule FROM acore_world.spell_group_stack_rules WHERE group_id BETWEEN %d AND %d" % GROUP_BAND)}
    d_r = ["stack rule of group %d is %s in the table, planned %s" % (pid, got_r.get(pid), want_r.get(pid))
           for pid in sorted(set(want_r) | set(got_r)) if want_r.get(pid) != got_r.get(pid)]
    out.append("spell_group_stack_rules: %d rows planned, %d in the table: %s" % (len(want_r), len(got_r), "IDENTICAL" if not d_r else "DIFFERENT"))
    out += ["    " + d for d in d_r[:20]]
    return out


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
    ap.add_argument("--installed", action="store_true",
                    help="read-only: do the live tables (spell_dbc, spell_group, spell_group_stack_rules) hold exactly the generated rows?")
    args = ap.parse_args()

    sp, in_table, band = load_spells()
    durations = load_durations()
    if durations.get(DURATION_INDEX) != DURATION_MS:
        raise SystemExit("SpellDuration.dbc index %d is %r, not %d" % (DURATION_INDEX, durations.get(DURATION_INDEX), DURATION_MS))
    client = Dbc(CLIENT_SPELL_DBC)
    gm = load_groups()
    ids = load_ids()
    new_ids = assign_ids([it[0] for _c, lst in PICKS for it in lst], ids)
    copies, plan, problems, notes = build(sp, band, client, gm, ids)
    problems += check_tooltips(copies)
    for n in notes:
        print("NOTE:", n, file=sys.stderr)
    for p in problems:
        print("PROBLEM:", p, file=sys.stderr)
    if problems:
        return 1
    lua = lua_rows(copies)
    sql = sql_file(copies, sp, plan)
    spec = spec_json(copies)
    ids_text = json.dumps({"about": "Sticky copy ids of tools/gen_shop_buffs.py: original spell id -> copy id (band %d-%d). "
                                    "Never edit by hand; commit changes." % COPY_BAND,
                           "ids": {str(k): v for k, v in sorted(ids.items(), key=lambda kv: kv[1])}}, indent=1) + "\n"
    print("%d buffs (copies %d-%d), %d older groups joined or nested into (%d copy rows, %d nested rows), %d pair groups, %d new ids assigned" % (
        len(copies), min(c["id"] for c in copies), max(c["id"] for c in copies), len(set(plan["joins"]) | set(plan["nests"])),
        sum(len(v) for v in plan["joins"].values()), sum(len(v) for v in plan["nests"].values()), len(plan["pairs"]), len(new_ids)),
        file=sys.stderr)
    if args.list:
        for c in sorted(copies, key=lambda x: x["id"]):
            print("%d <- %d%s  %-16s %-26s %s" % (
                c["id"], c["source"], "" if c["source"] == c["spell"] else " (cast %d)" % c["spell"], c["cls"], c["name"], c["what"]))
            print("%-8s groups joined %s | pair groups %s" % ("", c["groups_existing"] or "-", " ".join(
                "%d=%s%d" % (pid, "no rule with " if not plan["rules"][pid] else "4 with ", plan["pairs"][pid][0]) for pid in c["groups_new"]) or "-"))
    if args.tooltips:
        for c in sorted(copies, key=lambda x: x["id"]):
            print("%d %-26s D: %s" % (c["id"], c["name"], render(c["texts"]["Description_Lang_enUS"], c["set"])))
            print("%-33s A: %s" % ("", render(c["texts"]["AuraDescription_Lang_enUS"], c["set"])))
    if args.installed or args.verify:
        bad = 0
        if args.installed:
            lines = installed(copies, sp, plan)
            print("\n".join(lines))
            bad += sum(1 for x in lines if "DIFFERENT" in x)
        pairs = []
        if args.verify:
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
