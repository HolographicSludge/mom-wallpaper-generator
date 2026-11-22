import os, ctypes, sys, shutil, time, urllib.request
from datetime import datetime as dt
from pathlib import Path
from ctypes import HRESULT, POINTER, c_uint
from ctypes.wintypes import LPCWSTR
from comtypes import GUID, IUnknown, COMMETHOD, CoCreateInstance


""" links:
claude chat for this project: https://claude.ai/chat/80f02176-aa0e-42a0-b871-15a68cbe69c9
ai model i'm using: https://huggingface.co/Photoroom/prx-1024-t2i-beta
i'm bad at commenting my shit so this is all you get future me, suck my balls
"""


# helper shit for setting the wallpaper slideshow, from claude
# i can't explain this part, just DON'T FUCKING TOUCH IT.
# seriously, this is your 2fort cow. NO. TOUCH.
class IDesktopWallpaper(IUnknown):
# Windows' wallpaper control interface. The ORDER of methods must match Windows exactly.
# Only SetSlideshow, SetSlideshowOptions and AdvanceSlideshow have real arguments; the rest are placeholders to keep the order correct. Never call the placeholders.
    _iid_ = GUID("{B92B56A9-8B55-4E14-9A89-0199BBB6F93B}")
    _methods_ = [
        COMMETHOD([], HRESULT, "SetWallpaper"),
        COMMETHOD([], HRESULT, "GetWallpaper"),
        COMMETHOD([], HRESULT, "GetMonitorDevicePathAt"),
        COMMETHOD([], HRESULT, "GetMonitorDevicePathCount"),
        COMMETHOD([], HRESULT, "GetMonitorRECT"),
        COMMETHOD([], HRESULT, "SetBackgroundColor"),
        COMMETHOD([], HRESULT, "GetBackgroundColor"),
        COMMETHOD([], HRESULT, "SetPosition"),
        COMMETHOD([], HRESULT, "GetPosition"),
        COMMETHOD([], HRESULT, "SetSlideshow",
                  (["in"], POINTER(IUnknown), "items")),
        COMMETHOD([], HRESULT, "GetSlideshow"),
        COMMETHOD([], HRESULT, "SetSlideshowOptions",
                  (["in"], c_uint, "options"),
                  (["in"], c_uint, "slideshowTick")),
        COMMETHOD([], HRESULT, "GetSlideshowOptions"),
        COMMETHOD([], HRESULT, "AdvanceSlideshow",
                  (["in"], LPCWSTR, "monitorID"),
                  (["in"], c_uint, "direction")),
        COMMETHOD([], HRESULT, "GetStatus"),
        COMMETHOD([], HRESULT, "Enable"),
    ]
CLSID_DesktopWallpaper = GUID("{C2CF3110-460E-4FC1-B9D0-8A1C0C9CC4BD}")
IID_IShellItem         = GUID("{43826D1E-E718-42EE-BC55-A1E261C37BFE}")
IID_IShellItemArray    = GUID("{B63EA76D-1F85-456F-A19C-48159EFA858B}")
DSO_SHUFFLEIMAGES = 0x1   # option flag: shuffle the order
DSD_FORWARD = 0           # direction for AdvanceSlideshow


# constants
# folder the program lives in. as an .exe that's sys.executable's folder; as a .py
# (while testing) sys.executable is python.exe, so use the script's folder instead
if getattr(sys, "frozen", False):
    WORKING_DIR = Path(sys.executable).parent
else:
    WORKING_DIR = Path(__file__).resolve().parent
SUBDIR = WORKING_DIR / "images"                 # the folder the slideshow shows. ONLY wallpapers go in here
DOWNLOAD_DIR = WORKING_DIR / "images_download"  # temp folder, so a failed download never wipes the current wallpapers
NUM_IMAGES = 10           # MUST match NUM_IMAGES in generate.py
SLIDESHOW_INTERVAL = 10   # time in minutes
BASE_URL = "https://raw.githubusercontent.com/HolographicSludge/mom-wallpaper-generator/images"
DOWNLOAD_TRIES = 10       # wifi often isn't connected yet right after logging in,
RETRY_WAIT = 30           # so retry for a while (10 tries x 30 seconds = 5 minutes)


# no "date = dt.now()" default on purpose: python only evaluates that once
def period(date=None):
    if date is None:
        date = dt.now()
    y = date.year - 2026
    m = date.month
    halfm = 0 if date.day<=15 else 1
    return (y*12 + m-1) * 2 + halfm


# pop-up error box. sys.exit's message would vanish when the window closes
def showError(message):
    ctypes.windll.user32.MessageBoxW(None, message, "Wallpaper error", 0x10)   # 0x10 = red X icon
    sys.exit(1)

# middle-aged-mom-friendly error message
def momError(whatFailed, e):
    showError(f"{whatFailed}\n\nPlease restart the computer to try again.\n"
              f"If the problem keeps happening, please show Skyler this message.\n\nError code: {e}")


# downloads all of this period's images into DOWNLOAD_DIR. raises an exception if any fail
def downloadImages(p):
    shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)
    DOWNLOAD_DIR.mkdir()
    for i in range(NUM_IMAGES):
        url = f"{BASE_URL}/{p}/{i:02d}.jpg"
        request = urllib.request.Request(url, headers={"User-Agent": "mom-wallpaper"})
        with urllib.request.urlopen(request, timeout=60) as response:
            data = response.read()
        (DOWNLOAD_DIR / f"{p}_{i:02d}.jpg").write_bytes(data)


# folderPath must be an absolute path, interval is in minutes
def setWallpaperSlideshow(folderPath, interval):
    # everything in this try block is from claude, no touchy
    try:
        # 1. Turn the folder path into a "shell item", then into a "shell item array"
        folder_item = POINTER(IUnknown)()
        hr = ctypes.windll.shell32.SHCreateItemFromParsingName(
            str(folderPath), None, ctypes.byref(IID_IShellItem), ctypes.byref(folder_item))
        if hr != 0:   # hr == 0 means success; anything else is an error code
            raise OSError(f"SHCreateItemFromParsingName failed, HRESULT {hr & 0xFFFFFFFF:#010x}")

        item_array = POINTER(IUnknown)()
        hr = ctypes.windll.shell32.SHCreateShellItemArrayFromShellItem(
            folder_item, ctypes.byref(IID_IShellItemArray), ctypes.byref(item_array))
        if hr != 0:
            raise OSError(f"SHCreateShellItemArrayFromShellItem failed, HRESULT {hr & 0xFFFFFFFF:#010x}")

        # 2. Connect to Windows' wallpaper controller
        wallpaper = CoCreateInstance(CLSID_DesktopWallpaper, interface=IDesktopWallpaper)

        # 3. Set the slideshow, its timing, and show the first image now
        wallpaper.SetSlideshow(item_array)
        wallpaper.SetSlideshowOptions(DSO_SHUFFLEIMAGES, interval*60*1000)   # use 0 instead of DSO_SHUFFLEIMAGES for no shuffle
        wallpaper.AdvanceSlideshow(None, DSD_FORWARD)                        # None = all monitors

    except Exception as e:
        momError("Error changing wallpaper.", e)


def main():
    p = period()

    # this period's wallpapers are already here, nothing to do
    if (SUBDIR / f"{p}_00.jpg").is_file():
        return

    # download the new images, retrying in case the internet isn't connected yet
    for attempt in range(1, DOWNLOAD_TRIES + 1):
        try:
            downloadImages(p)
            break
        except Exception as e:
            if attempt == DOWNLOAD_TRIES:
                shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)
                momError("Couldn't download the new wallpapers. Is the computer connected to the internet?", e)
            time.sleep(RETRY_WAIT)

    # only now that ALL new images downloaded: delete the old ones and move the new ones in
    SUBDIR.mkdir(exist_ok=True)
    for file in SUBDIR.iterdir():
        if file.is_file():
            file.unlink()
    for file in DOWNLOAD_DIR.iterdir():
        shutil.move(str(file), str(SUBDIR / file.name))
    shutil.rmtree(DOWNLOAD_DIR, ignore_errors=True)

    # set rotating wallpaper
    setWallpaperSlideshow(SUBDIR, SLIDESHOW_INTERVAL)


if __name__ == "__main__":
    main()
