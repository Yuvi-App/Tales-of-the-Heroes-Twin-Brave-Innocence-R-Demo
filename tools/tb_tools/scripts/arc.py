import argparse
from pathlib import Path

import tb_tools.project.paths as tb_paths
from tb_tools.formats.arc import Arc

__SCRIPT_CMD = "arc"
__SCRIPT_DESC = "ARC/EZBIND tools"


def main(args):
    out: Path = args.output
    arc = Arc(args.extract)

    out.mkdir(exist_ok=True, parents=True)
    for file in arc.files:
        p = out / file.name
        print(file.name)
        p.write_bytes(file.data)
    print("Done!")


def add_arguments_to_parser(parser: argparse.ArgumentParser):
    parser.add_argument(
        "--extract",
        help="path to arc file",
        type=Path,
        required=True,
        metavar="PATH",
    )
    parser.add_argument(
        "--output",
        help="path to output folder",
        type=Path,
        required=True,
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
