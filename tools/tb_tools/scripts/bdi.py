import argparse
from pathlib import Path

import tb_tools.project.paths as tb_paths
from tb_tools.formats.bdi import Bdi

__SCRIPT_CMD = "bdi"
__SCRIPT_DESC = "BDI tools"

def main(args):
    with Bdi(args.extract, args.hashes) as bdi:
        out: Path = args.output
        if args.files is None:
            bdi.save_all_p(out)
        else:
            for file in args.files:
                p, b = bdi.get_file(file)
                if p is not None:
                    print(f"Extracting {p.as_posix()}")
                    o = out / p
                    o.parent.mkdir(parents=True, exist_ok=True)
                    o.write_bytes(b)
        print("Done!")

def add_arguments_to_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        "--extract",
        help="path to bdi file",
        type=Path,
        required=True,
        metavar="PATH",
    )
    parser.add_argument(
        "--hashes",
        help="path to a json with hash-name pairs",
        type=Path,
        default=tb_paths.hashes,
        metavar="PATH",
    )
    parser.add_argument(
        "--output",
        help="path to output folder",
        type=Path,
        default=Path("bdi"),
        metavar="PATH",
    )
    parser.add_argument(
        "--files",
        help=(
            "Extract selected file(s) from the bdi, accepts paths "
            "or hashes if prefixed with a $"
        ),
        nargs="*",
        type=str,
        metavar="PATH",
    )


def process_arguments(args: argparse.Namespace):
    main(args)

def add_subparser(subparser: argparse._SubParsersAction):
    parser = subparser.add_parser(
        __SCRIPT_CMD, help=__SCRIPT_DESC, description=__SCRIPT_DESC
    )
    add_arguments_to_parser(parser)
    parser.set_defaults(func=process_arguments)


parser = argparse.ArgumentParser(description=__SCRIPT_DESC)
add_arguments_to_parser(parser)

if __name__ == "__main__":
    args = parser.parse_args()
    process_arguments(args)
