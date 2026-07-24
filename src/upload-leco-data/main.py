import os
import re
import time
import shutil
from dotenv import load_dotenv
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

load_dotenv() 

USERNAME = os.getlogin() 

RAW_WATCH = os.getenv("WATCH_DIRECTORY", r"C:\LabOutputs\Incoming") 
RAW_ONEDRIVE = os.getenv("ONEDRIVE_DIRECTORY", "") 

WATCH_DIRECTORY = RAW_WATCH.format(USERNAME=USERNAME) 
ONEDRIVE_DIRECTORY = RAW_ONEDRIVE.format(USERNAME=USERNAME) 

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

class LECODataHandler(FileSystemEventHandler): 
    def on_created(self, event): 
        if event.is_directory: 
            return

        file_path = event.src_path 
        file_name = os.path.basename(file_path) 

        if file_name.startswith("~") or file_name.endswith(".tmp"): 
            return

        if not wait_for_file_completion(file_path): 
            print(f"[WARNING] Could not access '{file_name}' (file write timeout).")
            return

        wn_match = WN_PATTERN.search(file_name)
        g400_match = G400_PATTERN.search(file_name)

        if wn_match:
            folder_name = wn_match.group(0).upper() 
            target_folder = os.path.join(ONEDRIVE_DIRECTORY, folder_name) 
            print_path = folder_name
            
        elif g400_match:
            digits = g400_match.group(2) # Gets the 'xy' number
            folder_name = f"G400+-{digits}"
            # Routes to: Raw Data Files \ G400+ \ G400+-xy
            target_folder = os.path.join(ONEDRIVE_DIRECTORY, "G400+", folder_name)
            print_path = f"G400+\\{folder_name}"
            
        else:
            print(f"[SKIPPED] '{file_name}' — No WNxyz or G400+-xy code detected.") 
            return

        if not os.path.exists(target_folder): 
            os.makedirs(target_folder) 
            print(f"[CREATED FOLDER] {target_folder}")

        base_name, extension = os.path.splitext(file_name)
        destination_path = os.path.join(target_folder, file_name)
        
        counter = 1
        while os.path.exists(destination_path): 
            new_name = f"{base_name}_{counter}{extension}" 
            destination_path = os.path.join(target_folder, new_name)
            counter += 1

        try:
            shutil.move(file_path, destination_path) 
            final_name = os.path.basename(destination_path)
            print(f"[MOVED] '{file_name}' -> '{print_path}\\{final_name}'")
        except Exception as e:
            print(f"[ERROR] Failed to move '{file_name}': {e}")

def run(): 
    if not ONEDRIVE_DIRECTORY: 
        raise ValueError("ONEDRIVE_DIRECTORY is not set in environment variables or .env file.")

    event_handler = LECODataHandler() 
    observer = Observer() 
    
    observer.schedule(event_handler, path=WATCH_DIRECTORY, recursive=False) 

    print("--- C LECO Auto-Sorter Active ---")
    print(f"Monitoring: {WATCH_DIRECTORY}")
    print(f"Destination: {ONEDRIVE_DIRECTORY}\n")

    observer.start() 

    try:
        while True: 
            time.sleep(1)
    except KeyboardInterrupt: 
        observer.stop() 

    observer.join() 

if __name__ == "__main__":
    run()