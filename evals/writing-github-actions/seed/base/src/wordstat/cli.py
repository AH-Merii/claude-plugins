import sys

from wordstat import top


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    n = int(args[0]) if args else 3
    for word, k in top(sys.stdin.read(), n):
        print(f"{k}\t{word}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
