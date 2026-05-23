import gzip
import json
import mmap
import struct
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import BinaryIO

from tb_tools.formats.arc import ARC_MAGIC
from tqdm.rich import tqdm

GZIP_MAGIC = b"\x1f\x8b"


@dataclass
class BdiFile:
    hash: int
    offset: int
    size: int
    # Marks either NBI (False) or everything else (True)
    is_file: bool
    rel_path: Path
    is_compressed: bool = False
    is_arc: bool = False


class Bdi:
    def __init__(self, path: Path, names_path: Path | None = None, crc_bits: int = 15):
        self.path: Path = path
        self.names_path: Path | None = names_path
        self._fp: BinaryIO | None = None
        self._mm = None
        self._crc_bits = crc_bits
        self.files: list[BdiFile] = []
        self.name_map: dict[int, str] = {}
        self._name_mapi: dict[str, int] = {}
        self.file_map: dict[int, BdiFile] = {}
        self.timestamp: int = 0
        self.initialized = False

        self._parse_hashes()

    def __enter__(self):
        self._fp = self.path.open("rb")
        self._mm = mmap.mmap(self._fp.fileno(), 0, access=mmap.ACCESS_READ)
        self._parse_header()
        self.initialized = True
        return self

    def __exit__(self, exc_type, exc, tb):
        self.close()
        return False

    def close(self):
        if self._mm is not None:
            self._mm.close()
            self._mm = None
        if self._fp is not None:
            self._fp.close()
            self._fp = None

    def _parse_hashes(self):
        if self.names_path is None:
            return

        def _Keys2int(x):
            if isinstance(x, dict):
                return {int(k, base=16): v for k, v in x.items()}
            return x

        with self.names_path.open("r") as f:
            data = json.load(f, object_hook=_Keys2int)
            self.name_map = data
            self._name_mapi = {v: k for k, v in data.items()}

    def _parse_header(self):
        fp = self._fp
        assert fp is not None

        # Format starts with an index table using the lower N bits of
        # the filename CRC32 hash as the index, each entry is a short
        # so skip that
        fp.seek((1 << self._crc_bits) * 2)

        # First 2 entries are dummies that hold the file count and
        # a creation timestamp, after that each file entry is 2 ints
        # file hash followed by packed offset + padding
        _, file_count, _, ts = struct.unpack("<IIII", fp.read(16))
        self.timestamp = ts

        file_count += 2
        pairs = struct.unpack(f"<{file_count * 2}I", fp.read(file_count * 8))

        for i in range(file_count - 1):
            file_hash = pairs[i * 2 + 0]
            file_off = pairs[i * 2 + 1] & 0x7FFFF800
            file_pad = pairs[i * 2 + 1] & 0x000007FF
            flag = (pairs[i * 2 + 1] & 0x80000000) != 0
            next_off = pairs[i * 2 + 3] & 0x7FFFF800
            file_size = next_off - file_off - file_pad

            file_path = Path(self.name_map.get(file_hash, f"_no_name/${file_hash:08X}"))
            file = BdiFile(file_hash, file_off, file_size, flag, file_path)
            file.is_compressed = self._is_gz_file(file)
            file.is_arc = self._is_arc_file(file)
            self.files.append(file)
            self.file_map[file_hash] = file

    def _is_gz_file(self, p: BdiFile) -> bool:
        assert self._mm is not None
        start = p.offset
        return self._mm[start : start + 2] == GZIP_MAGIC

    def _is_arc_file(self, p: BdiFile) -> bool:
        assert self._mm is not None
        start = p.offset
        return self._mm[start : start + 8] == ARC_MAGIC

    def _scramble_audio(self, b: bytes) -> bytes:
        decoded = bytearray(0x80)
        for i in range(0x80):
            j = (7 + 11 * i) & 0x7F
            decoded[j] = b[i] ^ j
        return bytes(decoded) + b[0x80:]

    def _read_blob(self, p: BdiFile) -> tuple[Path, bytes]:
        fp = self._fp
        mm = self._mm

        assert fp is not None
        assert mm is not None

        start = p.offset
        end = start + p.size

        b = mm[start:end]

        # Handle gzipped files
        if p.is_compressed:
            b = gzip.decompress(b)

        # Handle scrambled audio
        if p.rel_path.suffix in (".na", ".at3"):
            b = self._scramble_audio(b)

        return p.rel_path, b

    def update_files(self, path: Path):
        pass

    def get_file(self, name: str) -> tuple[Path, bytes] | tuple[None, None]:
        if not self.initialized:
            raise ValueError("BDI file not initialized yet!")

        if name.startswith("$"):
            _hash = int(name[1:], base=16)
        else:
            _hash = self._name_mapi.get(name, 0)

        p: BdiFile | None = self.file_map.get(_hash)
        if p is not None:
            return self._read_blob(p)

        return None, None

    def get_timestamp(self) -> str:
        dt = datetime.fromtimestamp(self.timestamp)
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def iter_files(self) -> Iterator[tuple[Path, bytes]]:
        if not self.initialized:
            raise ValueError("BDI file not initialized yet!")

        for file in self.files:
            yield self._read_blob(file)

    def save_all(self, out_dir: Path):
        for rel_path, data in self.iter_files():
            out_path: Path = out_dir / rel_path
            out_path.parent.mkdir(parents=True, exist_ok=True)
            out_path.write_bytes(data)

    def save_all_p(self, out_dir: Path):
        with tqdm(total=len(self.files), desc="Extracting") as pbar:
            for rel_path, data in self.iter_files():
                pbar.set_description(f"{rel_path.as_posix()}")

                out_path: Path = out_dir / rel_path
                out_path.parent.mkdir(parents=True, exist_ok=True)
                out_path.write_bytes(data)
                pbar.update(1)
