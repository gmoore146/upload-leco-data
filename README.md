# upload-LECO-data

Automated background service to monitor incoming C LECO lab outputs and organise them into dedicated subfolders within SharePoint/OneDrive.

**Supported Naming Conventions:**
*   `WNxyz` -> Moves to `Puraffinity - C744\WNxyz\`
*   `G400Plus-xy`, `G400+-xy`, `G+-xy` -> Moves to `Puraffinity - C744\G400+\G400+-xy\`

## Requirements

- Requires OneDrive to be synced to the lab PC.
- Requires `uv` to be installed on the lab PC.

## Setup Instructions

### 1. Download the repository

**Option A: Manual Download (If Git is not installed)**
1. Open a web browser on the lab PC and go to your GitHub repository for this project.
2. Click the green **Code** button and select **Download ZIP**.
3. Extract the downloaded ZIP file.
4. Move the extracted files to create the folder: `C:\Users\leco\upload_LECO_data`.
5. Open Command Prompt and navigate to the folder:
```cmd
cd C:\Users\leco\upload_LECO_data
```

**Option B: Using Git**
Open Command Prompt and clone the project to the lab PC:
```cmd
cd C:\Users\leco
git clone <your-github-repo-url> upload_LECO_data
cd upload_LECO_data
```

*(Note: We run this as a standalone script using `uv`'s inline dependencies, so running `uv sync` or building a virtual environment is not strictly required).*

### 2. Configure Local Environment Variables
Create your local `.env` file from the example template:
```cmd
copy .env.example .env
```
Open `.env` in Notepad and set your local directory paths to match the lab PC:
```bash
WATCH_DIRECTORY="C:\Users\leco\Incoming"
ONEDRIVE_DIRECTORY="C:\Users\leco\OneDrive - Puraffinity\Puraffinity - C744"
```

### 3. Setup Desktop Controls (Start/Stop Buttons)
Create two `.bat` files on the Desktop to easily start and stop the script without needing to use the terminal.

**Start_LECO_Sorter.bat**
```cmd
cd C:\Users\leco\upload_LECO_data
C:\Users\leco\.local\bin\uv.exe run --with watchdog --with python-dotenv pythonw main.py
```

**Stop_Sorter.bat** *(Note: If you already made this for another script, it will stop all Python watchers)*
```cmd
taskkill /F /IM pythonw.exe /T
taskkill /F /IM python.exe /T
taskkill /F /IM uv.exe /T
```

### 4. Running Automatically on Windows Startup
To run the script quietly in the background every time the PC is logged into:

1. Press `Win + R`, type `taskschd.msc`, and press **Enter** to open **Task Scheduler**.
2. Click **Create Basic Task...** in the right sidebar.
3. Set **Name** to `C LECO Auto Sorter`.
4. Set **Trigger** to `When I log on`.
5. Set **Action** to `Start a program`:
   * **Program/script:** `C:\Users\leco\.local\bin\uv.exe`
   * **Add arguments:** `run --with watchdog --with python-dotenv pythonw main.py`
   * **Start in:** `C:\Users\leco\upload_LECO_data`
6. Click **Finish**.

## Updating the Script

When new changes are made to the code on GitHub, follow these steps on the lab PC to update:

1. Double-click your **Stop_Sorter.bat** on the desktop to kill the current background process.
2. Update the files:
   * **If using Manual Download:** Download the new ZIP from GitHub, extract it, and replace the old `main.py` with the new one.
   * **If using Git:** Open Command Prompt, navigate to `C:\Users\leco\upload_LECO_data`, and run `git pull`.
3. Double-click your **Start_LECO_Sorter.bat** to restart the background script with the new code.