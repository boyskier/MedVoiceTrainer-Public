import sys
import ctypes

if sys.platform == 'win32':
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        # shcore is unavailable on older Windows; fall back to legacy API.
        try:
            ctypes.windll.user32.SetProcessDPIAware()
        except (AttributeError, OSError):
            pass

import os
import argparse
from dotenv import load_dotenv

import config

# Load the app-managed .env (next to the exe / source) first, then also honor a
# .env in the current working directory. load_dotenv does not override values
# that are already set, so the first one wins.
load_dotenv(config.ENV_PATH)
load_dotenv()

from app.db.database import init_db, seed_data_if_needed
from app.ui.main_window import MainWindow


def main():
    parser = argparse.ArgumentParser(description="MedVoiceTrainer")
    parser.add_argument("--dev", action="store_true", help="Enable mock/dev mode")
    args = parser.parse_args()

    dev_mode = args.dev

    init_db()
    seed_data_if_needed()

    app = MainWindow(dev_mode=dev_mode)
    app.run()


if __name__ == "__main__":
    main()
