import tb_tools

from .utils import argparser_ext as argparse


def tools_main():
    parser = argparse.ArgumentParser(
        description="Tools to manipulate Tales of the World: Twin Brave files",
        prog="tb-tools",
    )

    subparsers = parser.add_subparsers(
        description="tool", help="The utility to run", required=True
    )

    proj_group = subparsers.add_parser_group("Project tools:")  # type: ignore
    tb_tools.project.extract.add_subparser(proj_group)

    file_group = subparsers.add_parser_group("Single File tools:")  # type: ignore
    tb_tools.scripts.bdi.add_subparser(file_group)
    tb_tools.scripts.arc.add_subparser(file_group)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    tools_main()
