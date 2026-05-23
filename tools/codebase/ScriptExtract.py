#!/usr/bin/env python3
"""
EZBind Extractor - Recursively extracts EZBIND archives and inflates .scr files.
Supports both gzip and ZIP compressed .scr files.
"""

import argparse
import gzip
import os
import re
import struct
import zipfile
from collections import defaultdict, deque
from pathlib import Path
from typing import Dict, List, Set, Tuple

EZBIND_MAGIC = b"EZBIND"
GZIP_MAGIC = b"\x1f\x8b"
ZIP_MAGIC = b"PK"
FACECHAT_MAGIC = b"FaceChat"

# Metadata pattern that appears before pointer table in SCR files
SCR_METADATA_PATTERN = bytes([
    0x6c, 0x00, 0x65, 0x00, 0x0a, 0x00, 0x50, 0x00,
    0x04, 0x00, 0x0d, 0x00, 0x1e, 0x00, 0x4c, 0x00,
    0x6c, 0x00, 0x80, 0x00, 0x18, 0x00
])

# Windows reserved names
RESERVED_NAMES = frozenset(
    {"CON", "PRN", "AUX", "NUL"}
    | {f"COM{i}" for i in range(1, 10)}
    | {f"LPT{i}" for i in range(1, 10)}
)


# -------------------------
# Helpers
# -------------------------

def read_u32le(f) -> int:
    b = f.read(4)
    if len(b) != 4:
        raise EOFError("Unexpected EOF while reading u32")
    return struct.unpack("<I", b)[0]


def read_magic(path: Path, size: int = 6) -> bytes:
    try:
        with path.open("rb") as f:
            return f.read(size)
    except Exception:
        return b""


def is_ezbind(path: Path) -> bool:
    return read_magic(path, 6) == EZBIND_MAGIC


def is_scr(path: Path) -> bool:
    return path.is_file() and path.suffix.lower() == ".scr"


def sanitize_filename(name: str) -> str:
    name = name.replace("\x00", "").strip()
    name = name.replace("/", "_").replace("\\", "_")
    name = re.sub(r'[<>:"|?*\x00-\x1F]', "_", name)
    if name.split(".")[0].upper() in RESERVED_NAMES:
        name = f"_{name}"
    return name or "unnamed"


def uniquify(path: Path, is_dir: bool = False) -> Path:
    if not path.exists():
        return path
    stem, suffix = (path.name, "") if is_dir else (path.stem, path.suffix)
    for n in range(2, 10000):
        candidate = path.parent / f"{stem}_{n}{suffix}"
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"Could not uniquify: {path}")


def rel_or_abs(p: Path, root: Path) -> str:
    try:
        return str(p.relative_to(root))
    except ValueError:
        return str(p)


# -------------------------
# EZBIND parsing + extraction
# -------------------------

def parse_ezbind(file_path: Path) -> Tuple[int, List[str], List[int], List[int], int]:
    """Parse EZBIND header and file table."""
    with file_path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        file_size = f.tell()

        f.seek(0)
        if f.read(6) != EZBIND_MAGIC:
            raise ValueError("Not an EZBIND file")

        f.seek(0x8)
        count = read_u32le(f)

        filenames = [""] * count
        pointers = [0] * count
        sizes = [0] * count
        nameindex = [0] * (count + 1)

        for j in range(count):
            f.seek(0x10 + j * 0x10)
            nameindex[j] = read_u32le(f)
            sizes[j] = read_u32le(f)
            pointers[j] = read_u32le(f)

        nameindex[count] = pointers[0] if count else 0

        for k in range(count):
            start, end = nameindex[k], nameindex[k + 1]
            if 0 <= start <= end <= file_size:
                f.seek(start)
                raw = f.read(end - start)
                decoded = raw.decode("gbk", errors="replace")
                filenames[k] = decoded.split("\x00", 1)[0] or "unnamed"
            else:
                filenames[k] = "unnamed"

        return count, filenames, pointers, sizes, file_size


def extract_ezbind(file_path: Path, out_dir: Path, verbose: bool = True) -> Tuple[Dict[str, int], List[Path]]:
    """Extract all files from an EZBIND archive."""
    count, filenames, pointers, sizes, file_size = parse_ezbind(file_path)
    out_dir.mkdir(parents=True, exist_ok=True)

    ext_counts: Dict[str, int] = defaultdict(int)
    extracted: List[Path] = []

    if verbose:
        print(f"[EZBIND] {file_path.name} -> {out_dir} ({count} files)")

    with file_path.open("rb") as f:
        for i in range(count):
            ptr, sz = pointers[i], sizes[i]

            if ptr > file_size:
                if verbose:
                    print(f"  [!] skip {i}: ptr 0x{ptr:X} > file size")
                continue

            sz = min(sz, file_size - ptr)
            out_path = uniquify(out_dir / sanitize_filename(filenames[i]))

            f.seek(ptr)
            out_path.write_bytes(f.read(sz))
            extracted.append(out_path)

            ext = out_path.suffix.lower() or "(none)"
            ext_counts[ext] += 1

    ext_counts["_total"] = len(extracted)
    return dict(ext_counts), extracted


# -------------------------
# SCR inflation (gzip or ZIP)
# -------------------------

def inflate_scr(scr_path: Path, verbose: bool = True) -> Tuple[bool, Path | None, str | None]:
    """
    Inflate a .scr file (gzip or ZIP format).
    Returns: (success, output_path, error_message)
    """
    magic = read_magic(scr_path, 2)

    if magic == GZIP_MAGIC:
        return _inflate_gzip(scr_path, verbose)
    elif magic == ZIP_MAGIC:
        return _inflate_zip(scr_path, verbose)
    else:
        return False, None, f"Unknown format (magic: {magic.hex()})"


def _inflate_gzip(scr_path: Path, verbose: bool) -> Tuple[bool, Path | None, str | None]:
    """Decompress gzip .scr file into SCR_{filename} folder."""
    out_dir = uniquify(scr_path.parent / f"SCR_{scr_path.name}", is_dir=True)

    try:
        with gzip.open(scr_path, "rb") as gz:
            data = gz.read()

        out_dir.mkdir(parents=True, exist_ok=True)
        out_file = out_dir / scr_path.name  # e.g., "FC_S113a.scr" inside "SCR_FC_S113a.scr/"
        out_file.write_bytes(data)

        if verbose:
            print(f"  [SCR-GZ] {scr_path.name} -> {out_dir.name}/ ({len(data)} bytes)")
        return True, out_dir, None

    except gzip.BadGzipFile:
        return False, None, "Invalid gzip"
    except Exception as e:
        return False, None, str(e)


def _inflate_zip(scr_path: Path, verbose: bool) -> Tuple[bool, Path | None, str | None]:
    """Extract ZIP .scr file to folder."""
    out_dir = uniquify(scr_path.parent / f"SCR_{scr_path.name}", is_dir=True)

    try:
        with zipfile.ZipFile(scr_path, "r") as zf:
            if (bad := zf.testzip()) is not None:
                return False, None, f"Corrupt ZIP member: {bad}"

            out_dir.mkdir(parents=True, exist_ok=True)

            for member in zf.infolist():
                mp = Path(member.filename)
                if mp.is_absolute() or ".." in mp.parts:
                    continue

                target = out_dir / member.filename
                target.parent.mkdir(parents=True, exist_ok=True)

                if member.is_dir():
                    target.mkdir(parents=True, exist_ok=True)
                else:
                    target.write_bytes(zf.read(member))

        if verbose:
            print(f"  [SCR-ZIP] {scr_path.name} -> {out_dir}")
        return True, out_dir, None

    except zipfile.BadZipFile:
        return False, None, "Invalid ZIP"
    except Exception as e:
        return False, None, str(e)


# -------------------------
# SCR Text Parsing (FaceChat format)
# -------------------------

def parse_scr_text(data: bytes) -> Tuple[int, List[Tuple[int, str]]] | None:
    """
    Parse text from a FaceChat SCR file.
    
    Returns: (textbox_count, [(absolute_offset, text), ...]) or None if not a valid SCR
    
    SCR Format:
    - 0x00-0x07: Magic "FaceChat"
    - 0x08-0x09: Unknown (u16 LE)
    - 0x0A-0x0B: TextBox count (u16 LE)
    - Variable: Script commands
    - 22 bytes: Metadata pattern (fixed)
    - N * 2 bytes: Pointer table (relative offsets, u16 LE)
    - Variable: Text data (EUC-JP, null-terminated)
    """
    if len(data) < 12 or data[:8] != FACECHAT_MAGIC:
        return None

    textbox_count = int.from_bytes(data[0x0A:0x0C], "little")
    if textbox_count == 0:
        return textbox_count, []

    # Find metadata pattern to locate pointer table
    metadata_pos = data.find(SCR_METADATA_PATTERN)
    if metadata_pos == -1:
        return None

    ptr_table_start = metadata_pos + len(SCR_METADATA_PATTERN)
    text_base = ptr_table_start + textbox_count * 2

    if text_base > len(data):
        return None

    # Read pointers and extract text
    texts: List[Tuple[int, str]] = []
    for i in range(textbox_count):
        ptr_off = ptr_table_start + i * 2
        if ptr_off + 2 > len(data):
            break

        rel_offset = int.from_bytes(data[ptr_off:ptr_off + 2], "little")
        abs_offset = text_base + rel_offset

        if abs_offset >= len(data):
            continue

        # Find null terminator
        end = abs_offset
        while end < len(data) and data[end] != 0:
            end += 1

        try:
            text = data[abs_offset:end].decode("euc_jp", errors="replace")
        except Exception:
            text = data[abs_offset:end].decode("latin-1", errors="replace")

        texts.append((abs_offset, text))

    return textbox_count, texts


def extract_scr_text(scr_path: Path, out_path: Path | None = None, verbose: bool = True) -> bool:
    """
    Extract text from an SCR file to a text file.
    Handles both raw and gzip-compressed SCR files.
    
    Returns True on success.
    """
    try:
        # Read and decompress if needed
        raw_data = scr_path.read_bytes()
        
        if raw_data[:2] == GZIP_MAGIC:
            import gzip as gz
            data = gz.decompress(raw_data)
        else:
            data = raw_data

        result = parse_scr_text(data)
        if result is None:
            if verbose:
                print(f"  [SCR-TXT] {scr_path.name}: Not a valid FaceChat SCR")
            return False

        textbox_count, texts = result

        if out_path is None:
            out_path = scr_path.with_suffix(".txt")

        with out_path.open("w", encoding="utf-8") as f:
            f.write(f"# SCR Text Export: {scr_path.name}\n")
            f.write(f"# TextBox Count: {textbox_count}\n")
            f.write(f"# Entries: {len(texts)}\n\n")

            for i, (offset, text) in enumerate(texts):
                f.write(f"[{i:03d}] @0x{offset:04X}\n")
                f.write(f"{text}\n\n")

        if verbose:
            print(f"  [SCR-TXT] {scr_path.name} -> {out_path.name} ({len(texts)} entries)")
        return True

    except Exception as e:
        if verbose:
            print(f"  [SCR-TXT] {scr_path.name}: Error - {e}")
        return False


# -------------------------
# Main
# -------------------------

def main():
    ap = argparse.ArgumentParser(
        description="Recursively extract EZBIND archives and inflate .scr files (gzip/ZIP)."
    )
    ap.add_argument("input_dir", help="Directory to scan for EZBIND files")
    ap.add_argument("--extract-root", help="Root folder for extracted output")
    ap.add_argument("--non-ezbind-out", help="Write non-EZBIND file list here")
    ap.add_argument("--scr-report", help="Write SCR inflation report here")
    ap.add_argument("--extract-scr-text", action="store_true", 
                    help="Also extract text from SCR files to .txt files")
    ap.add_argument("--scr-text-out", 
                    help="Directory to place extracted SCR text files (default: next to SCR)")
    ap.add_argument("-q", "--quiet", action="store_true")
    args = ap.parse_args()

    input_dir = Path(args.input_dir)
    if not input_dir.is_dir():
        raise SystemExit(f"Not a directory: {input_dir}")

    extract_root = Path(args.extract_root) if args.extract_root else None
    scr_text_out_dir = Path(args.scr_text_out) if args.scr_text_out else None
    if scr_text_out_dir:
        scr_text_out_dir.mkdir(parents=True, exist_ok=True)
    verbose = not args.quiet

    # Initial scan
    all_files = [p for p in input_dir.rglob("*") if p.is_file()]
    initial_ezbind = [p for p in all_files if is_ezbind(p)]
    initial_non_ezbind = [p for p in all_files if not is_ezbind(p)]

    if verbose:
        print(f"[+] Scanned {len(all_files)} files: {len(initial_ezbind)} EZBIND, {len(initial_non_ezbind)} other")

    # Process queue
    queue: deque[Tuple[Path, Path]] = deque()
    processed: Set[Path] = set()
    nested_non_ezbind: List[Path] = []

    global_ext: Dict[str, int] = defaultdict(int)
    scr_stats = {"found": 0, "ok": 0, "fail": 0}
    scr_report: List[str] = []

    for ez in initial_ezbind:
        base = extract_root or ez.parent
        queue.append((ez, base))

    while queue:
        ez_path, base_out = queue.popleft()
        key = ez_path.resolve()

        if key in processed:
            continue
        processed.add(key)

        out_dir = uniquify(base_out / f"EZBIND_{ez_path.name}", is_dir=True)

        try:
            stats, extracted = extract_ezbind(ez_path, out_dir, verbose)
        except Exception as e:
            print(f"[!] Failed: {ez_path} - {e}")
            continue

        for k, v in stats.items():
            global_ext[k] += v

        for p in extracted:
            if is_ezbind(p):
                queue.append((p, out_dir))
            else:
                nested_non_ezbind.append(p)
                if is_scr(p):
                    scr_stats["found"] += 1
                    ok, out, err = inflate_scr(p, verbose)
                    if ok:
                        scr_stats["ok"] += 1
                        scr_report.append(f"OK\t{p}\t{out}")
                        # Extract text if requested
                        if args.extract_scr_text:
                            if scr_text_out_dir:
                                txt_out = uniquify(scr_text_out_dir / (p.stem + ".txt"))
                            else:
                                txt_out = p.with_suffix(".txt")
                            extract_scr_text(p, txt_out, verbose)
                    else:
                        scr_stats["fail"] += 1
                        scr_report.append(f"FAIL\t{p}\t{err}")

    # Summary
    print(f"\n[SUMMARY]")
    print(f"  EZBIND processed: {len(processed)}")
    print(f"  Files extracted: {global_ext.get('_total', 0)}")

    if ext_list := {k: v for k, v in global_ext.items() if k != "_total"}:
        print("  By extension:", ", ".join(f"{k}:{v}" for k, v in sorted(ext_list.items())))

    print(f"  SCR: {scr_stats['found']} found, {scr_stats['ok']} ok, {scr_stats['fail']} failed")

    # Optional outputs
    if args.non_ezbind_out:
        out = Path(args.non_ezbind_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            f.write(f"[INITIAL] count={len(initial_non_ezbind)}\n")
            for p in initial_non_ezbind:
                f.write(f"{rel_or_abs(p, input_dir)}\n")
            f.write(f"\n[NESTED] count={len(nested_non_ezbind)}\n")
            for p in nested_non_ezbind:
                f.write(f"{p}\n")
        print(f"  Non-EZBIND list: {out}")

    if args.scr_report:
        out = Path(args.scr_report)
        out.parent.mkdir(parents=True, exist_ok=True)
        with out.open("w", encoding="utf-8") as f:
            f.write("status\tpath\tresult\n")
            f.writelines(f"{line}\n" for line in scr_report)
        print(f"  SCR report: {out}")


if __name__ == "__main__":
    main()