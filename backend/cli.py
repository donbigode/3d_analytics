"""CLI mínimo. Subagentes posteriores adicionam comandos."""
import argparse


def main() -> None:
    p = argparse.ArgumentParser(prog="3d-analytics")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("version")
    args = p.parse_args()
    if args.cmd == "version":
        print("0.1.0")


if __name__ == "__main__":
    main()
