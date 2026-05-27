# /// script
# requires-python = ">=3.11"
# dependencies = [
#     "lxml",
# ]
# ///
"""
repack.py — reverse of battle2.py
Reads translated XMLs from 2_translated/map/*.xml and the original .es files
from 1_extracted/all/entry/*.es, then writes patched .es files (with English
text substituted) to 3_patched/all/entry/*.es.

Rules:
  - If EnglishText is blank / missing for an entry → skip (keep JP original).
  - Status "To Do" or empty also treated as untranslated → keep JP.
  - Output encoding: euc_jp (same as source).
  - Output directory: 3_patched/all/entry/ (created if needed).
"""

import re
from pathlib import Path

from lxml import etree as ET

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ES_IN  = Path("../../1_extracted/all/entry")
XML_IN = Path("../../2_translated/map")
ES_OUT = Path("../../3_patched/all/entry")

# ---------------------------------------------------------------------------
# Macro parsing helpers (mirrors battle2.py)
# ---------------------------------------------------------------------------

macro_full_re = re.compile(
    r'DEFINE_(SCENARIO|SYSTEM|DIALOG)_MESSAGE\s*\((.*?)\)',
    re.DOTALL
)


def split_args(arg_string: str) -> list[str]:
    args = []
    current: list[str] = []
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


def unquote(s: str) -> str:
    s = s.strip()
    if s.startswith('"') and s.endswith('"'):
        s = s[1:-1]
    return s.replace(r'\"', '"')


def quote_text(s: str) -> str:
    """Escape and wrap a string in double-quotes for .es output."""
    return '"' + s.replace('\\', '\\\\').replace('"', r'\"').replace('\n', '\\n') + '"'


# ---------------------------------------------------------------------------
# Load translations from one XML file
# ---------------------------------------------------------------------------

def load_xml(xml_path: Path) -> dict:
    """
    Returns a dict with:
      "speaker_jp_to_en" : { jp_text -> en_text }
          Built from the Speakers section — used to translate DIALOG title args.

      "strings_by_section" : { section_name -> [ en_text, ... ] }
          Per-section list indexed by order of appearance (0, 1, 2 ...).
          This matches the per-type counters in the extractor (battle2.py uses
          a separate `i` counter that resets for each section).
          Entries where EnglishText is empty or Status is "To Do" store None
          (so the original JP is kept in those positions).
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    speaker_jp_to_en: dict[str, str] = {}
    strings_by_section: dict[str, list[str | None]] = {}

    # Speakers → title lookup for DIALOG macro arg[1]
    for speakers_node in root.xpath("Speakers"):
        for entry in speakers_node.findall("Entry"):
            status = (entry.findtext("Status") or "").strip()
            en     = (entry.findtext("EnglishText") or "").strip()
            jp     = (entry.findtext("JapaneseText") or "").strip()
            if not en or status == "To Do":
                continue
            if jp:
                speaker_jp_to_en[jp] = en

    # Strings sections → ordered translation lists
    for strings_node in root.xpath("Strings"):
        section = (strings_node.findtext("Section") or "").strip()
        items: list[str | None] = []
        for entry in strings_node.findall("Entry"):
            status = (entry.findtext("Status") or "").strip()
            en     = (entry.findtext("EnglishText") or "").strip()
            if en and status != "To Do":
                items.append(en)
            else:
                items.append(None)   # keep JP for this slot
        strings_by_section[section] = items

    return {
        "speaker_jp_to_en":  speaker_jp_to_en,
        "strings_by_section": strings_by_section,
    }


# ---------------------------------------------------------------------------
# Patch one .es file
# ---------------------------------------------------------------------------

def patch_file(es_path: Path, xml_path: Path, out_path: Path) -> None:
    translations     = load_xml(xml_path)
    speaker_jp_to_en = translations["speaker_jp_to_en"]
    strings          = translations["strings_by_section"]

    # Per-section occurrence counters (reset per section, just like battle2.py)
    counters: dict[str, int] = {}

    with open(es_path, "r", encoding="euc_jp") as f:
        source = f.read()

    def replace_macro(m: re.Match) -> str:
        macro_type = m.group(1)   # SCENARIO | SYSTEM | DIALOG
        arg_blob   = m.group(2)
        args = split_args(arg_blob)

        full        = m.group(0)
        paren_open  = full.index('(')
        paren_close = full.rindex(')')
        prefix      = full[:paren_open + 1]
        suffix      = full[paren_close:]

        def rebuilt(new_args: list[str]) -> str:
            return prefix + " " + ", ".join(new_args) + " " + suffix

        # Map macro type to section name (matches battle2.py section keys)
        section = macro_type.capitalize()   # Scenario | System | Dialog

        idx = counters.get(section, 0)
        counters[section] = idx + 1

        section_list = strings.get(section, [])
        en_text = section_list[idx] if idx < len(section_list) else None

        if macro_type in ("SCENARIO", "SYSTEM"):
            if len(args) < 5 or en_text is None:
                return full
            new_args = args[:4] + [quote_text(en_text)] + args[5:]
            return rebuilt(new_args)

        elif macro_type == "DIALOG":
            if len(args) < 3 or en_text is None:
                return full
            # arg[1] = dialog title (JP), look up EN equivalent in Speakers
            jp_title = unquote(args[1])
            en_title = speaker_jp_to_en.get(jp_title)
            new_arg1 = quote_text(en_title) if en_title else args[1]
            new_args = args[:1] + [new_arg1, quote_text(en_text)] + args[3:]
            return rebuilt(new_args)

        return full

    patched = macro_full_re.sub(replace_macro, source)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    with open(out_path, "w", encoding="euc_jp") as f:
        f.write(patched)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    xml_files = list(XML_IN.glob("*.xml"))

    if not xml_files:
        print(f"No XML files found in {XML_IN}")
        return

    patched = 0
    skipped = 0

    for xml_path in sorted(xml_files):
        es_path = ES_IN / xml_path.with_suffix(".es").name
        if not es_path.exists():
            print(f"  [skip] no matching .es for {xml_path.name}")
            skipped += 1
            continue

        out_path = ES_OUT / es_path.name
        try:
            patch_file(es_path, xml_path, out_path)
            print(f"  [ok]   {es_path.name} → {out_path}")
            patched += 1
        except Exception as e:
            print(f"  [ERR]  {es_path.name}: {e}")
            skipped += 1

    print(f"\nDone: {patched} patched, {skipped} skipped.")


if __name__ == "__main__":
    main()
