import os
import re
import time
import shutil
import logging
import sys
import datetime
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# ---------------------------------------------------------
# Logging Configuration
# ---------------------------------------------------------
LOG_FILE = "leco_sorter_log.txt"
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    handlers=[
        logging.FileHandler(LOG_FILE),       # Saves to the continuous text file
        logging.StreamHandler(sys.stdout)    # Prints to the console
    ]
)

load_dotenv() 

# ---------------------------------------------------------
# Directory Configurations
# ---------------------------------------------------------
# Pulls the exact path from .env, or uses the default fallback
WATCH_DIRECTORY = os.path.abspath(os.getenv("WATCH_DIRECTORY", r"C:\LabOutputs\Incoming"))
PROCESSED_DIRECTORY = os.path.abspath(os.getenv("PROCESSED_DIRECTORY", r"C:\Users\leco\Desktop\LECO Results\Processed_new"))

raw_onedrive = os.getenv("ONEDRIVE_DIRECTORY", "")
ONEDRIVE_DIRECTORY = os.path.abspath(raw_onedrive) if raw_onedrive else ""

# Pattern for WNxyz
WN_PATTERN = re.compile(r"WN\d{3}", re.IGNORECASE) 

# Pattern for G400 variations followed by a dash and exactly 2 digits (e.g., -01) -> target folder format G400+-xy
G400_PATTERN = re.compile(r"(G400Plus|G400\+|G\+)-(\d{2})", re.IGNORECASE)

def wait_for_file_completion(file_path, timeout=30): 
    start_time = time.time() 
    last_size = -1 

    while time.time() - start_time < timeout: 
        try:
            current_size = os.path.getsize(file_path) 
            if current_size == last_size and current_size > 0: 
                with open(file_path, "a+"): 
                    return True 
            last_size = current_size 
        except (OSError, PermissionError): 
            pass 
        time.sleep(1) 
        
    return False 

# Helper to avoid duplicate file names
def get_unique_destination(target_folder, file_name):
    base_name, extension = os.path.splitext(file_name)
    destination_path = os.path.join(target_folder, file_name)
    counter = 1
    
    while os.path.exists(destination_path): 
        new_name = f"{base_name}_{counter}{extension}" 
        destination_path = os.path.join(target_folder, new_name)
        counter += 1
        
    return os.path.abspath(destination_path)

# Main logic for sorting a single file
def process_file(file_path):
    file_name = os.path.basename(file_path) 

    if file_name.startswith("~") or file_name.endswith(".tmp"): 
        return

    if not wait_for_file_completion(file_path): 
        logging.warning(f"Could not access '{file_path}' (file write timeout).")
        return

    wn_match = WN_PATTERN.search(file_name)
    g400_match = G400_PATTERN.search(file_name)
    
    # Get the current month formatted as "08 AUGUST"
    month_folder_name = datetime.datetime.now().strftime("%m %B").upper()

    # Determine target folders based on regex matches
    if wn_match:
        folder_name = wn_match.group(0).upper() 
        onedrive_target = os.path.abspath(os.path.join(ONEDRIVE_DIRECTORY, folder_name))
        
        # Local Processed path includes the month folder (e.g., ...\08 AUGUST\WN123)
        processed_target = os.path.abspath(os.path.join(PROCESSED_DIRECTORY, month_folder_name, folder_name))
        
    elif g400_match:
        digits = g400_match.group(2) # Gets the 'xy' number
        folder_name = f"G400+-{digits}"
        
        # Routes to: Raw Data Files \ G400+ \ G400+-xy
        onedrive_target = os.path.abspath(os.path.join(ONEDRIVE_DIRECTORY, "G400+", folder_name))
        
        # Local Processed path includes the month folder (e.g., ...\08 AUGUST\G400+\G400+-01)
        processed_target = os.path.abspath(os.path.join(PROCESSED_DIRECTORY, month_folder_name, "G400+", folder_name))
        
    else:
        logging.info(f"[SKIPPED] '{file_path}' — No WNxyz or G400+-xy code detected.") 
        return

    # Ensure both target directories exist (os.makedirs creates intermediate folders like the month folder automatically)
    for target_folder in [onedrive_target, processed_target]:
        if not os.path.exists(target_folder): 
            os.makedirs(target_folder) 
            logging.info(f"[CREATED FOLDER] {target_folder}")

    # Get unique file paths for both destinations
    onedrive_dest = get_unique_destination(onedrive_target, file_name)
    processed_dest = get_unique_destination(processed_target, file_name)

    try:
        # 1. Copy to local Processed folder
        shutil.copy2(file_path, processed_dest)
        
        # 2. Move to OneDrive (this removes the original from Watch folder)
        shutil.move(file_path, onedrive_dest) 
        
        logging.info(
            f"[SUCCESS] '{file_path}' saved to both:\n"
            f"   -> OneDrive: {onedrive_dest}\n"
            f"   -> Local: {processed_dest}"
        )
    except Exception as e:
        logging.error(f"[ERROR] Failed to process '{file_path}': {e}")

class LECODataHandler(FileSystemEventHandler): 
    def on_created(self, event): 
        if event.is_directory: 
            return
        
        # Pass the new file to our processor
        process_file(os.path.abspath(event.src_path))

def run(): 
    if not ONEDRIVE_DIRECTORY: 
        raise ValueError("ONEDRIVE_DIRECTORY is not set in environment variables or .env file.")

    # Ensure the watch directory exists before trying to scan it
    if not os.path.exists(WATCH_DIRECTORY):
        os.makedirs(WATCH_DIRECTORY)
        logging.info(f"Created Watch Directory: {WATCH_DIRECTORY}")

    logging.info("--- C LECO Auto-Sorter Starting ---")
    logging.info(f"Monitoring: {WATCH_DIRECTORY}")
    logging.info(f"OneDrive Destination: {ONEDRIVE_DIRECTORY}")
    logging.info(f"Local Processed Destination base: {PROCESSED_DIRECTORY}\n")

    # --- INITIAL SCAN ---
    logging.info("Scanning for existing files in the incoming directory...")
    for file_name in os.listdir(WATCH_DIRECTORY):
        file_path = os.path.join(WATCH_DIRECTORY, file_name)
        if os.path.isfile(file_path):
            process_file(file_path)
    logging.info("Initial scan complete. Beginning real-time monitoring.\n")

    # --- REAL-TIME MONITORING ---
    event_handler = LECODataHandler() 
    observer = Observer() 
    
    observer.schedule(event_handler, path=WATCH_DIRECTORY, recursive=False) 
    observer.start() 

    try:
        while True: 
            time.sleep(1)
    except KeyboardInterrupt: 
        logging.info("Shutting down observer...")
        observer.stop() 

    observer.join() 

if __name__ == "__main__":
    run()