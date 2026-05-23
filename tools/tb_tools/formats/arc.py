import gzip
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path

from tb_tools.utils.fileio import FileIO

ARC_MAGIC = b"EZBIND\x00\x00"
GZIP_MAGIC = b"\x1f\x8b"
ZIP_MAGIC = b"PK"


def _grouper(iterable, n, fillvalue=None):
    args = [iter(iterable)] * n
    return zip_longest(*args, fillvalue=fillvalue)


@dataclass(slots=True)
class ArcFile:
    name: str
    data: bytes
    hash: int
    is_compressed: bool = False


class Arc:
    def __init__(self, path: Path):
        with FileIO(path) as f:
            if f.read(8) != ARC_MAGIC:
                raise ValueError("Invalid EZBIND magic!")

            count = f.read_int32()
            self.alignment = f.read_int32()
            data = f.read_struct(f"<{count * 4}I")
            names = []
            for _ in range(count):
                names.append(f.read_string())
            self._names = names

            files = []
            for name_idx, size, offset, hsh in _grouper(data, 4):
                data = f.read_at(offset, size)
                is_comp = False

                if data[:2] == ZIP_MAGIC:
                    raise ValueError("ZIP-based compressed files not supported!")

                if data[:2] == GZIP_MAGIC:
                    data = gzip.decompress(data)
                    is_comp = True

                name = f.read_string(pos=name_idx)

                calc_hash = 0
                for c in name:
                    calc_hash *= 0x25
                    calc_hash += ord(c)
                    calc_hash &= 0xFFFFFFFF

                if calc_hash != hsh:
                    raise ValueError("Mismatched hashes in file list!")

                file = ArcFile(name, data, hsh, is_comp)
                files.append(file)
            self.files: list[ArcFile] = files
