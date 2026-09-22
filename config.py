"""
config.py
One small job: find secrets without ever writing them into the code.

Import it from any script in this folder:
    from config import load_secret
    token = load_secret("FREESOUND_TOKEN")

Lookup order:
    1. a real environment variable (what a server or CI system would use)
    2. a .env file sitting next to this script (convenient on one machine)

.env is listed in .gitignore, so the secret never travels with the code.
"""

from pathlib import Path
from typing import Optional
import os

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_PATH = SCRIPT_DIR / ".env"


def load_secret(name: str) -> Optional[str]:
    """Return the value of a secret, or None if it is nowhere to be found."""
    # .get() returns None when the key is missing. os.environ[name] would raise KeyError.
    value = os.environ.get(name)
    if value:
        return value

    if not ENV_PATH.exists():
        return None

    for line in ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue                      # skip blank lines and comments
        # partition splits at the FIRST "=" only, so a value containing "=" survives intact.
        key, separator, value = line.partition("=")
        if separator and key.strip() == name:
            return value.strip().strip('"').strip("'")
    return None


def require_secret(name: str) -> str:
    """Same as load_secret, but stop the program with a clear message if it is missing."""
    value = load_secret(name)
    if not value:
        raise SystemExit(
            f"{name} is not set.\n"
            f"Put a line like  {name}=your_key_here  in {ENV_PATH}\n"
            f"or set it as an environment variable."
        )
    return value

# ------------------------------------------------------------------
# Keeping the machine awake during a long job
# ------------------------------------------------------------------
#
# This lives here rather than in one script because THREE scripts now run for
# tens of minutes: the harvester, the downloader and the transcoder. A helper
# copied into three files is a helper that will be fixed in one of them.

import ctypes
import sys

ES_CONTINUOUS = 0x80000000        # the request stays in force until changed
ES_SYSTEM_REQUIRED = 0x00000001   # ...and what it asks for is "do not sleep"


def keep_awake(label: str = "") -> bool:
    """
    Ask Windows not to sleep until this process exits.

    SetThreadExecutionState is the same call a video player uses to stop the
    machine dozing mid-film. Windows drops the request automatically when the
    process ends, so there is nothing to undo and no setting is changed.

    Note what this does NOT do: it does not stop the monitor turning off. That is
    a separate flag (ES_DISPLAY_REQUIRED) and we do not want it. A dark screen is
    harmless to a running job, and keeping a monitor lit for half an hour to no
    purpose is rude to the hardware.

    Returns False anywhere but Windows, and never raises: a convenience must not
    be the thing that stops the actual work.
    """
    if sys.platform != "win32":
        return False
    try:
        ctypes.windll.kernel32.SetThreadExecutionState(ES_CONTINUOUS | ES_SYSTEM_REQUIRED)
        if label:
            print(f"Asked Windows not to sleep until {label} finishes.")
        return True
    except (AttributeError, OSError):
        return False
