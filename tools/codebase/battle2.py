# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "lxml",
# ]
# ///
import re
from dataclasses import dataclass
from pathlib import Path
import sys

from lxml import etree as ET

p = Path("1_extracted/all/entry")

macro_start_re = re.compile(
    r'DEFINE_(SCENARIO|SYSTEM|DIALOG)_MESSAGE\s*\('
)

macro_full_re = re.compile(
    r'DEFINE_(SCENARIO|SYSTEM|DIALOG)_MESSAGE\s*\((.*?)\)',
    re.DOTALL
)


def split_args(arg_string):
    args = []
    current = []
    in_string = False
    escape = False

    for c in arg_string:
        if in_string:
            current.append(c)

            if escape:
                escape = False
            elif c == '\\':
                escape = True
            elif c == '"':
                in_string = False

        else:
            if c == '"':
                in_string = True
                current.append(c)

            elif c == ',':
                args.append(''.join(current).strip())
                current = []

            else:
                current.append(c)

    if current:
        args.append(''.join(current).strip())

    return args


def unquote(s):
    s = s.strip()

    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]

    return s.replace(r'\"', '"')


def parse_macro(macro_type, args, block_comment, inline_comment):
    if macro_type == "SCENARIO":
        if len(args) >= 5:
            return {
                "type": "Scenario",
                "msg_type": args[0],
                "character": args[1],
                "flag": args[2],
                "msg_id": args[3],
                "text": unquote(args[4]).replace("\\n", "\n"),
                "block_comment": block_comment,
                "inline_comment": inline_comment,
            }

    elif macro_type == "SYSTEM":
        if len(args) >= 5:
            return {
                "type": "System",
                "id": args[0],
                "character": args[1],
                "flag": args[2],
                "msg_id": args[3],
                "text": unquote(args[4]).replace("\\n", "\n"),
                "block_comment": block_comment,
                "inline_comment": inline_comment,
            }

    elif macro_type == "DIALOG":
        if len(args) >= 3:
            return {
                "type": "Dialog",
                "msg_type": args[0],
                "character": unquote(args[1]),
                "text": unquote(args[2]).replace("\\n", "\n"),
                "block_comment": block_comment,
                "inline_comment": inline_comment,
            }

    return None


def parse_file(path):
    with open(path, 'r', encoding='euc_jp') as f:
        lines = f.readlines()

    results = []

    current_block_comment = None

    collecting = False
    macro_lines = []

    for line in lines:

        stripped = line.strip().replace("#=====", "=====")

        if stripped.startswith("#") and not collecting:
            current_block_comment = stripped[1:].strip()
            continue

        if macro_start_re.search(line):
            collecting = True

        if collecting:
            macro_lines.append(line)

            if ')' in line:
                full = ''.join(macro_lines)

                collecting = False
                macro_lines = []

                m = macro_full_re.search(full)

                if m:
                    macro_type = m.group(1)
                    arg_blob = m.group(2)

                    inline_comment = None

                    clean_lines = []

                    for l in full.splitlines():
                        if '#' in l:
                            code, comment = l.split('#', 1)

                            if code.strip():
                                l = code.rstrip()

                                if inline_comment is None:
                                    inline_comment = comment.strip()

                        clean_lines.append(l)

                    full = '\r\n'.join(clean_lines)

                    args = split_args(arg_blob)

                    entry = parse_macro(
                        macro_type,
                        args,
                        current_block_comment,
                        inline_comment
                    )

                    if entry:
                        results.append(entry)

    return results

@dataclass
class trEntry:
    jp_text: str
    en_text: str
    notes: str
    id: int
    status: str
    voice_id: int | None = None
    speaker_id: int | None = None


@dataclass
class rmXml:
    friend_name: str | None
    names: list[trEntry]
    text: dict[str, list[trEntry]]

def makeNode(root: ET._Element, n: trEntry, id: int) -> ET._Element:
    entry = ET.SubElement(root, "Entry")

    # if n.offsets is not None:
    #     ET.SubElement(entry, "PointerOffset").text = ",".join(
    #         [str(x) for x in n.offsets]
    #     )
    # else:
    #     ET.SubElement(entry, "PointerOffset").text = None
    ET.SubElement(entry, "PointerOffset").text = None

    if n.voice_id is not None:
        ET.SubElement(entry, "VoiceId").text = n.voice_id

    ET.SubElement(entry, "JapaneseText").text = n.jp_text.replace("\r\n", "\n")
    ET.SubElement(entry, "EnglishText").text = n.en_text
    ET.SubElement(entry, "Notes").text = n.notes

    if n.speaker_id is not None:
        ET.SubElement(entry, "SpeakerId").text = str(n.speaker_id)

    ET.SubElement(entry, "Id").text = str(id)
    ET.SubElement(entry, "Status").text = n.status
    return entry


def makeXml(data: rmXml) -> bytes:
    root = ET.Element("SceneText")

    if data.friend_name is not None:
        ET.SubElement(root, "FriendlyName").text = data.friend_name

    names_node = ET.SubElement(root, "Speakers")
    ET.SubElement(names_node, "Section").text = "Speaker"
    for n in data.names:
        makeNode(names_node, n, n.id)

    for name, items in data.text.items():
        if len(items) == 0:
            continue
        text_node = ET.SubElement(root, "Strings")
        ET.SubElement(text_node, "Section").text = name
        for n in items:
            makeNode(text_node, n, n.id)

    return ET.tostring(root, encoding="UTF-8", pretty_print=True).replace(b"\n", b"\r\n")

ids = {}

__names = {
    "eEventCharaID_System": "System",
    "eEventCharaID_Cless": "Cless",
    "eEventCharaID_Kyle": "Kyle",
    "eEventCharaID_YoungmanA": "Young Man A",
    "eEventCharaID_Chester": "Chester",
    "eEventCharaID_Reala": "Reala",
    "eEventCharaID_SoldierD": "Soldier D",
    "eEventCharaID_Lloyd": "Lloyd",
    "eEventCharaID_Zelos": "Zelos",
    "eEventCharaID_SoldierB": "Soldier B",
    "eEventCharaID_Asbel": "Asbel",
    "eEventCharaID_Cheria": "Cheria",
    "eEventCharaID_Marta": "Marta",
    "eEventCharaID_Emil": "Emil",
    "eEventCharaID_Lion": "Leon",
    "eEventCharaID_Stan": "Stahn",
    "eEventCharaID_Milla": "Milla",
    "eEventCharaID_Jude": "Jude",
    "eEventCharaID_Thief": "Thief",
    "eEventCharaID_Chloe": "Chloe",
    "eEventCharaID_Senel": "Senel",
    "eEventCharaID_Farmer": "Farmer",
    "eEventCharaID_Shing": "Shing",
    "eEventCharaID_Kohak": "Kohaku",
    "eEventCharaID_Elrane": "Elraine",
    "eEventCharaID_Tytree": "Tytree",
    "eEventCharaID_Veigue": "Veigue",
    "eEventCharaID_Ruca": "Ruca",
    "eEventCharaID_Spada": "Spada",
    "eEventCharaID_Caius": "Caius",
    "eEventCharaID_Rubia": "Rubia",
    "eEventCharaID_Flynn": "Flynn",
    "eEventCharaID_Yuri": "Yuri",
    "eEventCharaID_Farah": "Farah",
    "eEventCharaID_Rid": "Rid",
    "eEventCharaID_SoldierG": "Soldier G",
    "eEventCharaID_Guy": "Guy",
    "eEventCharaID_Luke": "Luke",
    "eEventCharaID_SoldierC": "Soldier C",
    "eEventCharaID_SoldierA": "Soldier A",
    "eEventCharaID_Schwarz": "Schwarz",
    "eEventCharaID_Duke": "Duke",
    "eEventCharaID_SoldierE": "Soldier E",
    "eEventCharaID_Emil2": "Emil2",
    "eEventCharaID_SoldierF": "Soldier F",
    "eEventCharaID_CommonerRTM": "Commoner RTM",
    "eEventCharaID_SoldierRTM": "Soldier RTM",
    "eEventCharaID_ThiefRTM": "Thief RTM",
    "eEventCharaID_Guest1": "Guest 1",
    "eEventCharaID_Guest2": "Guest 2",
}

for path in p.glob("*.es"):
    names = {}
    text = path.read_text(encoding="euc-jp")
    if "autoEntry ver" in text:
        friendly_name = text.split("\t autoEntry ver")[0].split("#\t")[1]
    else:
        friendly_name = None
    xml = rmXml(friendly_name, [], {"System": [], "Scenario": [], "Dialog": []})
    results = parse_file(path)

    if len(results) == 0:
        continue
    # print(r)
    # break
    # Add names
    for nm in results:
        names[nm["character"]] = None

    out = Path("./2_translated/map/" + path.stem)
    out = out.with_suffix(".xml")
    _xml = ET.parse(out)
    root = _xml.getroot()
    strings = {}
    for foo in root.xpath("Speakers"):
        for node in foo.findall("Entry"):
            # print(node.findtext("EnglishText"))
            strings[node.findtext("JapaneseText")] = (node.findtext("Status"), node.findtext("Notes"), node.findtext("EnglishText"))

    name_ids = {}
    for id, nm in enumerate(names):
        notes = None
        if nm not in __names:
            oentry = strings.get(nm, (None, None, None))
            n = nm
            if oentry[2]:
                nt = oentry[2]
                st = oentry[0]
                notes = oentry[1] if oentry[1] else None
            else:
                nt = None
                st = "To Do"
        else:
            n = __names[nm]
            nt = n
            st = "Done"
        names[nm] = id
        xml.names.append(trEntry(n, nt, notes, id, st))

    strings = {}
    for foo in root.xpath("Strings"):
        for node in foo.findall("Entry"):
            # print(node.findtext("EnglishText"))
            strings[node.findtext("JapaneseText")] = (node.findtext("Status"), node.findtext("Notes"), node.findtext("EnglishText"))

    # break
    for i, r in enumerate(results):
        notes = ""
        if r["block_comment"]:
            notes += r["block_comment"]
        if r["inline_comment"]:
            notes = notes + "\n | " + r["inline_comment"] if notes != "" else r["inline_comment"]
        if r["type"] in ("Scenario", "System") and r["msg_id"] and r["msg_id"] != "0":
            notes = notes + "\n | Audio file: na/" + r["msg_id"] + ".na" if notes != "" else "Audio file: na/" + r["msg_id"] + ".na"

        n = None if not r["character"] else names[r["character"]]
        oentry = strings.get(r["text"], (None, None, None))
        # if oentry[1]:
        #     notes = oentry[1] + "\n | " + notes if notes != "" else oentry[1]
        if notes == "":
            notes = None
        etext = None
        if oentry[2]:
            etext = oentry[2]

        xml.text[r["type"]].append(trEntry(r["text"], etext, notes, i, oentry[0], None, n))
        ids[r["character"]] = True

    with out.open("wb") as o:
        o.write(makeXml(xml))
    # break
    # text = path.read_text(encoding="euc-jp")
    # matches = pattern.findall(text)
    # for m in matches:
    #     print(m)

# for id in ids:
#     print(id)
