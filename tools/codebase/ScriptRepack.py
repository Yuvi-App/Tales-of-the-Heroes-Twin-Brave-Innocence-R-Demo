#!/usr/bin/env python3
"""
SCR Repacker - Rebuilds FaceChat .scr binary files from translated XML.

Directory layout (relative to this script in tools/codebase/):
  ../../1_extracted/all/facechat/<name>.arc/<name>.scr   <- original SCR (binary reference)
  ../../2_translated/story/<name>.xml                    <- translated XML
  ../../3_patched/all/facechat/<name>.arc/<name>.scr     <- output (repacked SCR)

For each entry:
  - Uses EnglishText if non-empty, otherwise falls back to JapaneseText.
  - Text is encoded as plain ASCII where possible; non-ASCII chars use EUC-JP.
  - Newlines in XML (\n) are written as \r\n in the binary, matching the originals.
  - Everything before and including the pointer table region is copied verbatim
    from the original SCR; only the text data section is replaced.
"""

import struct
import sys
from pathlib import Path
from xml.etree import ElementTree as ET

# ---------------------------------------------------------------------------
# Constants (must match ScriptExtract.py)
# ---------------------------------------------------------------------------

FACECHAT_MAGIC = b"FaceChat"

SCR_METADATA_PATTERN = bytes([
    0x6c, 0x00, 0x65, 0x00, 0x0a, 0x00, 0x50, 0x00,
    0x04, 0x00, 0x0d, 0x00, 0x1e, 0x00, 0x4c, 0x00,
    0x6c, 0x00, 0x80, 0x00, 0x18, 0x00
])

SCR_METADATA_PATTERN2 = bytes([
    0x6c, 0x00, 0x65, 0x00, 0x0a, 0x00, 0x50, 0x00,
    0x04, 0x00, 0x0d, 0x00, 0x1e, 0x00, 0x4c, 0x00,
    0x00, 0x01, 0x6c, 0x00, 0x80, 0x00, 0x18, 0x00
])


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------

def resolve_dirs(script_path: Path):
    """Return (extracted_root, translated_root, patched_root) from script location."""
    # Script lives at tools/codebase/ -> go up two levels to project root
    project_root = script_path.resolve().parent.parent.parent
    extracted   = project_root / "1_extracted"  / "all" / "facechat"
    translated  = project_root / "2_translated" / "story"
    patched     = project_root / "3_patched"    / "all" / "facechat"
    return extracted, translated, patched


# ---------------------------------------------------------------------------
# Encoding helper
# ---------------------------------------------------------------------------

def encode_text(text: str) -> bytes:
    """
    Encode a string for the binary SCR file.
    - Newlines are normalised to \\r\\n.
    - ASCII characters are kept as-is (single byte).
    - Non-ASCII characters are encoded with EUC-JP.
    """
    # Normalise newlines: \r\n -> \n first (idempotent), then \n -> \r\n
    text = text.replace("\r\n", "\n").replace("\n", "\r\n")

    out = bytearray()
    i = 0
    while i < len(text):
        ch = text[i]
        # \r\n pair: write raw bytes
        if ch == "\r" and i + 1 < len(text) and text[i + 1] == "\n":
            out += b"\r\n"
            i += 2
            continue
        cp = ord(ch)
        if cp < 0x80:
            # Pure ASCII - single byte
            out.append(cp)
        else:
            # Non-ASCII - encode as EUC-JP
            try:
                out += ch.encode("euc_jp")
            except (UnicodeEncodeError, LookupError):
                # Fallback: replace with '?' if character is unencodable
                print(f"    [WARN] Cannot encode U+{cp:04X} '{ch}' as EUC-JP, substituting '?'")
                out.append(ord("?"))
        i += 1
    return bytes(out)


# ---------------------------------------------------------------------------
# XML parsing
# ---------------------------------------------------------------------------

def load_xml_entries(xml_path: Path) -> dict[int, str]:
    """
    Parse the translated XML and return a dict mapping slot_id -> text.

    For each <Entry>:
      - If <EnglishText> is non-empty, use it.
      - Otherwise fall back to <JapaneseText>.

    Only <Strings> sections are processed (both 'Main Text' and 'Unreferenced').
    The <Speakers> section is intentionally skipped — speaker names are embedded
    in the script bytecode and are not part of the pointer table.
    """
    tree = ET.parse(xml_path)
    root = tree.getroot()

    entries: dict[int, str] = {}

    for strings_node in root.findall("Strings"):
        section = strings_node.findtext("Section", "").strip()
        # Skip non-text sections (shouldn't occur, but be safe)
        if section not in ("Main Text", "Unreferenced"):
            continue

        for entry in strings_node.findall("Entry"):
            id_text = entry.findtext("Id", "").strip()
            if not id_text.isdigit():
                continue
            slot_id = int(id_text)

            english  = (entry.findtext("EnglishText")  or "").strip()
            japanese = (entry.findtext("JapaneseText") or "").strip()

            text = english if english else japanese
            entries[slot_id] = text

    return entries


# ---------------------------------------------------------------------------
# SCR parsing
# ---------------------------------------------------------------------------

def parse_scr(data: bytes):
    """
    Parse a FaceChat SCR binary.
    Returns (textbox_count, metadata_pos, ptr_table_start, text_base)
    or raises ValueError if the file is not a valid FaceChat SCR.
    """
    if len(data) < 12 or data[:8] != FACECHAT_MAGIC:
        raise ValueError("Not a FaceChat SCR file")

    textbox_count = int.from_bytes(data[0x0A:0x0C], "little")

    # Try all known metadata patterns
    patterns = [SCR_METADATA_PATTERN, SCR_METADATA_PATTERN2]

    for pattern in patterns:
        metadata_pos = data.find(pattern)
        if metadata_pos != -1:
            ptr_table_start = metadata_pos + len(pattern)
            break
    else:
        raise ValueError("Metadata pattern not found")

    text_base = ptr_table_start + textbox_count * 2

    if text_base > len(data):
        raise ValueError(f"text_base 0x{text_base:X} exceeds file size {len(data)}")

    return textbox_count, metadata_pos, ptr_table_start, text_base


# ---------------------------------------------------------------------------
# SCR repacking
# ---------------------------------------------------------------------------

def repack_scr(original_data: bytes, entries: dict[int, str]) -> bytes:
    """
    Rebuild a FaceChat SCR binary with translated text.

    The header + script bytecode + metadata pattern are copied verbatim.
    Only the pointer table and text data section are rebuilt.
    """
    textbox_count, _meta_pos, ptr_table_start, text_base = parse_scr(original_data)

    # Read the original text slots so we have a fallback for any slot
    # not covered by the XML (shouldn't happen, but be defensive).
    original_texts: dict[int, bytes] = {}
    for i in range(textbox_count):
        ptr_off = ptr_table_start + i * 2
        rel     = int.from_bytes(original_data[ptr_off:ptr_off + 2], "little")
        abs_off = text_base + rel
        end     = abs_off
        while end < len(original_data) and original_data[end] != 0:
            end += 1
        original_texts[i] = original_data[abs_off:end]  # raw bytes, no null

    # Build the new text blobs in slot order
    new_text_blobs: list[bytes] = []
    for i in range(textbox_count):
        if i in entries:
            blob = encode_text(entries[i])
        else:
            # No XML entry for this slot -> keep original bytes
            print(f"    [WARN] slot {i:02d} not found in XML, keeping original")
            blob = original_texts[i]
        new_text_blobs.append(blob)

    # Build new pointer table (relative offsets from text_base)
    new_ptr_table = bytearray()
    offset = 0
    for blob in new_text_blobs:
        new_ptr_table += struct.pack("<H", offset)
        offset += len(blob) + 1  # +1 for null terminator

    # Build new text section (null-terminated blobs)
    new_text_section = bytearray()
    for blob in new_text_blobs:
        new_text_section += blob
        new_text_section.append(0x00)

    # Assemble: original prefix (up to and including metadata pattern) +
    #           new pointer table + new text section
    prefix = original_data[:ptr_table_start]
    return prefix + bytes(new_ptr_table) + bytes(new_text_section)


# ---------------------------------------------------------------------------
# Batch processing
# ---------------------------------------------------------------------------

def process_file(xml_path: Path, extracted_root: Path, patched_root: Path) -> bool:
    """Process one XML file -> one patched SCR. Returns True on success."""
    stem = xml_path.stem  # e.g. "FC_S101a"
    arc_name  = stem + ".arc"
    scr_name  = stem + ".scr"

    original_scr = extracted_root / arc_name / scr_name
    output_scr   = patched_root   / arc_name / scr_name

    print(f"[{stem}]")

    # Load original SCR
    if not original_scr.exists():
        print(f"  [ERROR] Original SCR not found: {original_scr}")
        return False

    original_data = original_scr.read_bytes()

    # Validate
    try:
        textbox_count, _, _, _ = parse_scr(original_data)
    except ValueError as e:
        print(f"  [ERROR] Cannot parse original SCR: {e}")
        return False

    print(f"  Original: {original_scr}  ({len(original_data)} bytes, {textbox_count} slots)")

    # Load XML
    entries = load_xml_entries(xml_path)
    print(f"  XML entries loaded: {len(entries)}")

    # Repack
    try:
        patched_data = repack_scr(original_data, entries)
    except Exception as e:
        print(f"  [ERROR] Repack failed: {e}")
        return False

    # Write output
    output_scr.parent.mkdir(parents=True, exist_ok=True)
    output_scr.write_bytes(patched_data)
    print(f"  Output:   {output_scr}  ({len(patched_data)} bytes)")
    return True


def main():
    script_path = Path(__file__)
    extracted_root, translated_root, patched_root = resolve_dirs(script_path)

    print(f"Project root : {script_path.resolve().parent.parent.parent}")
    print(f"Extracted SCR: {extracted_root}")
    print(f"Translated XML: {translated_root}")
    print(f"Patched output: {patched_root}")
    print()

    xml_files = sorted(translated_root.glob("*.xml"))
    if not xml_files:
        print(f"[ERROR] No XML files found in {translated_root}")
        sys.exit(1)

    print(f"Found {len(xml_files)} XML file(s) to process.\n")

    ok_count   = 0
    fail_count = 0

    for xml_path in xml_files:
        success = process_file(xml_path, extracted_root, patched_root)
        if success:
            ok_count += 1
        else:
            fail_count += 1
        print()

    print(f"[DONE] {ok_count} succeeded, {fail_count} failed.")
    if fail_count:
        sys.exit(1)


if __name__ == "__main__":
    main()
