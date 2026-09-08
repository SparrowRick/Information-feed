"""Allow `python -m review --date YYYY-MM-DD` as well as `python -m review.build`."""

from review.build import main

if __name__ == "__main__":
    raise SystemExit(main())
