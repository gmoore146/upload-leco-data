"""C LECO auto-sorter: watches an incoming folder and files LECO outputs into
OneDrive (moved) and a local Processed archive (copied), by sample code."""

import datetime
import logging
import os
import re
import shutil
import sys
import threading
import time
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv
from watchdog.events import FileSystemEventHandler
from watchdog.observers import Observer

# ---------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------
# Anchored to the script folder so the log location doesn't depend on the working directory
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "leco_sorter_log.txt")

handlers = [RotatingFileHandler(LOG_FILE, maxBytes=5_000_000, backupCount=3, encoding="utf-8")]
if sys.stdout:  # sys.stdout is None under pythonw
    handlers.append(logging.StreamHandler(sys.stdout))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=handlers,
)

load_dotenv()

# ---------------------------------------------------------
# Directory Configurations
# ---------------------------------------------------------
WATCH_DIRECTORY = os.path.abspath(os.getenv("WATCH_DIRECTORY", r"C:\LabOutputs\Incoming"))
PROCESSED_DIRECTORY = os.path.abspath(os.getenv("PROCESSED_DIRECTORY", r"C:\Users\leco\Desktop\LECO Results\Processed_new"))

raw_onedrive = os.getenv("ONEDRIVE_DIRECTORY", "")
ONEDRIVE_DIRECTORY = os.path.abspath(raw_onedrive) if raw_onedrive else ""

# Pattern for WNxyz
WN_PATTERN = re.compile(r"WN\d{3}", re.IGNORECASE)

# Pattern for G400 variations followed by a dash and exactly 2 digits (e.g., -01) -> target folder format G400+-xy
G400_PATTERN = re.compile(r"(G400Plus|G400\+|G\+)-(\d{2})", re.IGNORECASE)

# The initial scan and watchdog events run on different threads; serialise so a file is never handled twice
_process_lock = threading.Lock()


def wait_for_file_completion(file_path, timeout=30):
    start_time = time.time()
    last_size = -1

    while time.time() - start_time < timeout:
        try:
            current_size = os.path.getsize(file_path)
            if current_size == last_size and current_size > 0:
                with open(file_path, "a+"):  # fails on Windows while the instrument still has it open
                    return True
            last_size = current_size
        except OSError:
            pass
        time.sleep(1)

    return False


# Helper to avoid duplicate file names
def get_unique_destination(target_folder, file_name):
    base_name, extension = os.path.splitext(file_name)
    destination_path = os.path.join(target_folder, file_name)
    counter = 1

    while os.path.exists(destination_path):
        destination_path = os.path.join(target_folder, f"{base_name}_{counter}{extension}")
        counter += 1

    return os.path.abspath(destination_path)


def get_relative_target(file_name):
    """Return the sample sub-path for a file name (e.g. 'WN123' or 'G400+/G400+-01'), or None if unrecognised."""
    wn_match = WN_PATTERN.search(file_name)
    if wn_match:
        return wn_match.group(0).upper()

    g400_match = G400_PATTERN.search(file_name)
    if g400_match:
        return os.path.join("G400+", f"G400+-{g400_match.group(2)}")

    return None


def process_file(file_path):
    # Never let one bad file kill the watcher thread
    try:
        with _process_lock:
            _process_file(file_path)
    except Exception:
        logging.exception(f"[ERROR] Failed to process '{file_path}'")


def _process_file(file_path):
    file_name = os.path.basename(file_path)

    if file_name.startswith("~") or file_name.lower().endswith(".tmp"):
        return

    # Already handled (e.g. picked up by both the initial scan and a watchdog event)
    if not os.path.isfile(file_path):
        return

    relative_target = get_relative_target(file_name)
    if relative_target is None:
        logging.info(f"[SKIPPED] '{file_path}' — No WNxyz or G400+-xy code detected.")
        return

    if not wait_for_file_completion(file_path):
        logging.warning(f"Could not access '{file_path}' (file write timeout). It will be retried on next startup.")
        return

    # Current month formatted as "08 August"
    month_folder_name = datetime.datetime.now().strftime("%m %B").title()

    onedrive_target = os.path.join(ONEDRIVE_DIRECTORY, relative_target)
    processed_target = os.path.join(PROCESSED_DIRECTORY, month_folder_name, relative_target)

    for target_folder in (onedrive_target, processed_target):
        if not os.path.isdir(target_folder):
            os.makedirs(target_folder, exist_ok=True)
            logging.info(f"[CREATED FOLDER] {target_folder}")

    onedrive_dest = get_unique_destination(onedrive_target, file_name)
    processed_dest = get_unique_destination(processed_target, file_name)

    # 1. Copy to local Processed folder
    shutil.copy2(file_path, processed_dest)

    # 2. Move to OneDrive (removes the original from the Watch folder)
    try:
        shutil.move(file_path, onedrive_dest)
    except Exception:
        # Roll back the local copy so a retry doesn't leave a duplicate "_1" file behind
        try:
            os.remove(processed_dest)
        except OSError:
            logging.warning(f"Could not remove partial local copy '{processed_dest}'.")
        raise

    logging.info(
        f"[SUCCESS] '{file_path}' saved to both:\n"
        f"   -> OneDrive: {onedrive_dest}\n"
        f"   -> Local: {processed_dest}"
    )


class LECODataHandler(FileSystemEventHandler):
    def on_created(self, event):
        if not event.is_directory:
            process_file(os.path.abspath(event.src_path))

    # Some software writes a temp file then renames it into place
    def on_moved(self, event):
        if not event.is_directory:
            process_file(os.path.abspath(event.dest_path))


def check_config():
    """Exit with a logged error rather than a silent crash (pythonw has no console)."""
    if not ONEDRIVE_DIRECTORY:
        logging.critical("ONEDRIVE_DIRECTORY is not set in environment variables or .env file. Exiting.")
        sys.exit(1)

    # Don't create OneDrive root ourselves: a typo would silently send files to an unsynced folder
    if not os.path.isdir(ONEDRIVE_DIRECTORY):
        logging.critical(f"ONEDRIVE_DIRECTORY does not exist: '{ONEDRIVE_DIRECTORY}'. Is OneDrive synced? Exiting.")
        sys.exit(1)

    for name, path in (("WATCH_DIRECTORY", WATCH_DIRECTORY), ("PROCESSED_DIRECTORY", PROCESSED_DIRECTORY)):
        try:
            os.makedirs(path, exist_ok=True)
        except OSError as e:
            logging.critical(f"Cannot create {name} '{path}': {e}. Exiting.")
            sys.exit(1)


def run():
    check_config()

    logging.info("--- C LECO Auto-Sorter Starting ---")
    logging.info(f"Monitoring: {WATCH_DIRECTORY}")
    logging.info(f"OneDrive Destination: {ONEDRIVE_DIRECTORY}")
    logging.info(f"Local Processed Destination base: {PROCESSED_DIRECTORY}")

    # Start watching before the scan so files arriving mid-scan aren't missed
    observer = Observer()
    observer.schedule(LECODataHandler(), path=WATCH_DIRECTORY, recursive=False)
    observer.start()

    try:
        logging.info("Scanning for existing files in the incoming directory...")
        for file_name in os.listdir(WATCH_DIRECTORY):
            process_file(os.path.join(WATCH_DIRECTORY, file_name))
        logging.info("Initial scan complete. Real-time monitoring active.")

        while observer.is_alive():
            time.sleep(1)
        logging.critical("File observer stopped unexpectedly. Exiting.")
    except KeyboardInterrupt:
        logging.info("Shutting down observer...")
    finally:
        observer.stop()
        observer.join()


if __name__ == "__main__":
    try:
        run()
    except Exception:
        logging.exception("Fatal error — sorter has stopped.")
        sys.exit(1)
