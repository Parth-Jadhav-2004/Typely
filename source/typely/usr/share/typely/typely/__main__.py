import argparse

from typely.app import run_app


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Typely - Speech-to-text transcription")
    parser.add_argument(
        "--show-window",
        action="store_true",
        help="Show control window immediately on startup",
    )
    args = parser.parse_args()
    run_app(show_window=args.show_window)
