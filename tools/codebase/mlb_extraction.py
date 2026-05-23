import os
import struct
import xml.etree.ElementTree as ET

SCRIPT_DIR = os.path.dirname(__file__)

INPUT_DIR = os.path.normpath(
    os.path.join(SCRIPT_DIR, "../../1_extracted/arc/mlt")
)

OUTPUT_DIR = os.path.normpath(
    os.path.join(SCRIPT_DIR, "../../2_translated/menu")
)


def read_u8(f):
    return struct.unpack("<B", f.read(1))[0]


def read_u32(f):
    return struct.unpack("<I", f.read(4))[0]


def read_string_at(f, offset):
    if offset == 0:
        return "<empty>"

    file_size = f.seek(0, 2)
    if offset >= file_size:
        return "<empty>"

    current = f.tell()
    f.seek(offset)

    if f.read(1) != b"\x40":
        f.seek(current)
        return "<empty>"

    data = bytearray()

    while True:
        b = f.read(1)
        if not b or b == b"\x00":
            break
        data.append(b[0])

    f.seek(current)

    try:
        return data.decode("euc_jp", errors="replace")
    except:
        return "<empty>"


def parse_file(input_path, output_path):
    with open(input_path, "rb") as f:

        if f.read(3) != b"MLT":
            print(f"[SKIP] {input_path}")
            return

        try:
            section_count = read_u8(f)
            section_ptrs = [read_u32(f) for _ in range(section_count)]
        except:
            print(f"[ERROR] header: {input_path}")
            return

        root = ET.Element("MenuText")

        global_id = 1

        for sec_id, sec_ptr in enumerate(section_ptrs):
            if sec_ptr == 0:
                continue

            # 🔥 One <Strings> per section
            strings = ET.SubElement(root, "Strings")

            section_elem = ET.SubElement(strings, "Section")
            section_elem.text = f"Section {sec_id + 1}"

            try:
                f.seek(sec_ptr)
                entry_count = read_u32(f)
                entry_ptrs = [read_u32(f) for _ in range(entry_count)]
            except:
                print(f"[ERROR] section {sec_id}: {input_path}")
                continue

            for entry_id, entry_ptr in enumerate(entry_ptrs):

                entry_elem = ET.SubElement(strings, "Entry")

                ptr_elem = ET.SubElement(entry_elem, "PointerOffset")
                ptr_elem.text = str(entry_ptr)

                text = read_string_at(f, entry_ptr)

                jp_elem = ET.SubElement(entry_elem, "JapaneseText")
                jp_elem.text = text

                en_elem = ET.SubElement(entry_elem, "EnglishText")
                en_elem.text = ""

                notes_elem = ET.SubElement(entry_elem, "Notes")
                notes_elem.text = ""

                id_elem = ET.SubElement(entry_elem, "Id")
                id_elem.text = str(global_id)

                status_elem = ET.SubElement(entry_elem, "Status")
                status_elem.text = "To Do"

                global_id += 1

        # Write XML
        os.makedirs(OUTPUT_DIR, exist_ok=True)

        tree = ET.ElementTree(root)
        ET.indent(tree, space="  ", level=0)

        tree.write(
            output_path,
            encoding="utf-8",
            xml_declaration=False,
            short_empty_elements=True
        )

        # 🔥 Ensure no space in empty tags (<tag/> instead of <tag />)
        with open(output_path, "r", encoding="utf-8") as f:
            xml_content = f.read()

        xml_content = xml_content.replace(" />", "/>")

        with open(output_path, "w", encoding="utf-8") as f:
            f.write(xml_content)


def main():
    print("Input:", INPUT_DIR)
    print("Output:", OUTPUT_DIR)

    count = 0

    for root_dir, _, files in os.walk(INPUT_DIR):
        for name in files:
            if not name.endswith(".mlb"):
                continue

            count += 1

            input_path = os.path.join(root_dir, name)
            base_name = os.path.splitext(name)[0]
            output_path = os.path.join(OUTPUT_DIR, base_name + ".xml")

            print(f"[PROCESS] {name}")

            parse_file(input_path, output_path)

    print(f"Done. Files processed: {count}")


if __name__ == "__main__":
    main()