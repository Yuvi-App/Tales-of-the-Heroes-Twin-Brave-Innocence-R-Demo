import shutil
from pathlib import Path

from loguru import logger

default_iso: Path = Path("twin_brave.iso")
iso_files: Path = Path("0_disc")
original_eboot: Path = Path("0_disc/PSP_GAME/SYSDIR/EBOOT.BIN")
namco_bdi: Path = Path("0_disc/PSP_GAME/USRDIR/namco.bdi")
extracted_files: Path = Path("1_extracted")
bdi_files: Path = Path("1_extracted/all")
decrypted_eboot: Path = Path("1_extracted/EBOOT.BIN")
translation_files: Path = Path("2_translated")
patched_files: Path = Path("3_patched")
game_builds: Path = Path("4_builds")
binaries: Path = Path("tools/bin")
hashes: Path = Path("project/hashes.json")

def clean_folder(path: Path) -> None:
    target_files = list(path.iterdir())
    if len(target_files) == 0:
        return

    logger.info("Cleaning folder...")
    for file in target_files:
        if file.is_dir():
            shutil.rmtree(file)
        elif file.name.lower() not in (".gitignore", ".gitkeep"):
            file.unlink(missing_ok=False)


def clean_builds(path: Path) -> None:
    target_files = sorted(path.glob("*.iso"), key=lambda x: x.name)[:-4]
    if len(target_files) == 0:
        return

    logger.info("Cleaning builds folder...")
    for file in target_files:
        logger.info(f"deleting {str(file.name)}...")
        file.unlink()
