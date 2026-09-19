# Imports
# GUI (Primary And Fallback)
import webview
import customtkinter as ctk
from tkinter import messagebox
# Text Parsing
import json
import re
# Misc
import traceback
import threading
import subprocess
import requests
import io
import base64
import time
import sys
import webbrowser
import os
import shutil
import math
import random
from pathlib import Path
# Computer Vision
import cv2
import numpy as np
# Capture
if sys.platform == "win32":
    try:
        import dxcam
    except:
        dxcam = None
else:
    dxcam = None
import mss
# Keyboard And Mouse Clicks (Platform-specific)
from pynput.keyboard import Listener as KeyListener, Key
from pynput import keyboard, mouse
from pynput.keyboard import Controller as KeyboardController
from pynput.mouse import Controller as MouseController
from pynput.mouse import Button
if sys.platform == "win32":
    import ctypes
    from ctypes import wintypes
elif sys.platform == "darwin":
    import Quartz
    import AppKit
elif sys.platform == "linux":
    from Xlib import X, XK, display as Xdisplay
    from Xlib.ext import xtest
# Check For OCR
try:
    import pytesseract
    possible = shutil.which("tesseract")
    if possible:
        pytesseract.pytesseract.tesseract_cmd = possible
except (ImportError, OSError):
    pytesseract = None
# Define Platform-Specific Constants
# All Platforms
keyboard_controller = KeyboardController()
mouse_controller = MouseController()
APP_VERSION = 5.11
BETA_VERSION = 0
DEVELOPER = "Catman2608"
def load_misc_settings(last_config_path):
    try:
        with open(last_config_path, "r", encoding="utf-8") as file:
            data = json.load(file)
        return data
    except:
        return {}
def get_macos_menu_offset():
    if sys.platform != "darwin":
        return 0

    try:
        screen = AppKit.NSScreen.mainScreen()
        full_frame = screen.frame()
        visible_frame = screen.visibleFrame()
        return int(full_frame.size.height - visible_frame.size.height)

    except Exception:
        return 0
if sys.platform == "darwin":
    import Quartz
    _QUARTZ_SRGB_COLOR_SPACE = Quartz.CGColorSpaceCreateWithName(
        Quartz.kCGColorSpaceSRGB
    )
    # Cache display P3 color space (what MSS typically returns on modern Macs)
    _QUARTZ_P3_COLOR_SPACE = Quartz.CGColorSpaceCreateWithName(
        Quartz.kCGColorSpaceDisplayP3
    )
else:
    _QUARTZ_SRGB_COLOR_SPACE = None
    _QUARTZ_P3_COLOR_SPACE = None

def mss_to_srgb_numpy(image, source_is_p3=True):
    """
    Convert an untagged raw MSS/Fastgrab frame buffer from Display P3 to sRGB
    using macOS native ColorSync engine for identical Quartz output.
    """
    if image is None or getattr(image, "ndim", 0) != 3 or image.shape[2] not in (3, 4):
        return image

    if sys.platform != "darwin" or not source_is_p3:
        bgr = image[:, :, :3]
        return bgr if bgr.flags["C_CONTIGUOUS"] else np.ascontiguousarray(bgr)

    height, width = image.shape[:2]
    
    # 1. Ensure input buffer is BGRA (4 channels required by CGDataProvider)
    if image.shape[2] == 3:
        bgra = np.empty((height, width, 4), dtype=np.uint8)
        bgra[:, :, :3] = image
        bgra[:, :, 3] = 255
    else:
        bgra = image

    # 2. Wrap raw NumPy buffer in CGImage tagged as Display P3
    bytes_per_row = width * 4
    provider = Quartz.CGDataProviderCreateWithData(None, bgra.tobytes(), len(bgra.tobytes()), None)
    
    src_cg_image = Quartz.CGImageCreate(
        width, height, 8, 32, bytes_per_row,
        _QUARTZ_P3_COLOR_SPACE,
        Quartz.kCGImageAlphaPremultipliedFirst | Quartz.kCGBitmapByteOrder32Little, # BGRA
        provider, None, False, Quartz.kCGRenderingIntentDefault
    )

    # 3. Draw into an sRGB context (CoreGraphics handles exact ColorSync transformation)
    out_raw = np.empty((height, width, 4), dtype=np.uint8)
    context = Quartz.CGBitmapContextCreate(
        out_raw, width, height, 8, bytes_per_row,
        _QUARTZ_SRGB_COLOR_SPACE,
        Quartz.kCGImageAlphaPremultipliedLast | Quartz.kCGBitmapByteOrder32Big
    )
    
    Quartz.CGContextDrawImage(context, Quartz.CGRectMake(0, 0, width, height), src_cg_image)

    # 4. Extract BGR uint8 result matching Quartz/MSS consumers
    return np.ascontiguousarray(out_raw[:, :, :3][:, :, ::-1])

def cgimage_to_srgb_numpy(image):
    if sys.platform == "darwin":
        width = Quartz.CGImageGetWidth(image)
        height = Quartz.CGImageGetHeight(image)
        bytes_per_row = width * 4
        raw = np.empty((height, width, 4), dtype=np.uint8)
        context = Quartz.CGBitmapContextCreate(
            raw,
            width,
            height,
            8,
            bytes_per_row,
            _QUARTZ_SRGB_COLOR_SPACE,
            Quartz.kCGImageAlphaPremultipliedLast |
            Quartz.kCGBitmapByteOrder32Big,
        )
        if context is None:
            return None

        Quartz.CGContextDrawImage(
            context,
            Quartz.CGRectMake(0, 0, width, height),
            image,
        )
        return raw[:, :, :3][:, :, ::-1]

    return image

# Screen Dimensions Via MSS — Use Monitor[1] (Primary) Not Monitor[0] (Virtual Combined).
# On Windows With Dpi Scaling, Pywebview'S X/Y/Width/Height Use Physical Pixels,
# So We Must Query The Raw Physical Resolution, Not The Scaled Logical Resolution.
try:
    MSS = mss.MSS
except AttributeError:
    MSS = mss.mss
with MSS() as _sct:
    if len(_sct.monitors) > 1:
        _m = _sct.monitors[1]   # Primary monitor
    else:
        _m = _sct.monitors[0]   # Fallback: only one entry exists
    SCREEN_WIDTH  = _m["width"]
    SCREEN_HEIGHT = _m["height"]
    SCREEN_LEFT   = _m["left"]
    SCREEN_TOP    = _m["top"]
HALF_WIDTH = int(SCREEN_WIDTH / 2)
HALF_HEIGHT = int(SCREEN_HEIGHT / 2)
# Windows (Transparency And Ctypes Windll)
if sys.platform == "win32":
    windll = ctypes.windll.user32
    MOUSEEVENTF_MOVE = 0x0001
    MOUSEEVENTF_LEFTDOWN = 0x0002
    MOUSEEVENTF_LEFTUP = 0x0004
    MOUSEEVENTF_RIGHTDOWN = 0x0008
    MOUSEEVENTF_RIGHTUP = 0x0010
    # Ctypes GUI Constants
    SW_MAXIMIZE = 3
    user32 = ctypes.windll.user32
    user32.GetWindowLongW.restype = wintypes.LONG
    user32.GetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetWindowLongW.restype = wintypes.LONG
    user32.SetWindowLongW.argtypes = [wintypes.HWND, ctypes.c_int, wintypes.LONG]
    user32.SetLayeredWindowAttributes.restype = wintypes.BOOL
    user32.SetLayeredWindowAttributes.argtypes = [wintypes.HWND, wintypes.COLORREF, ctypes.c_byte, wintypes.DWORD]
    user32.ShowWindow.restype = wintypes.BOOL
    user32.ShowWindow.argtypes = [
        wintypes.HWND,
        ctypes.c_int
    ]
    # Set Dpi Awareness Early To Ensure Consistent Coordinate Handling
    try:
        windll.shcore.SetProcessDpiAwareness(1)  # PROCESS_PER_MONITOR_DPI_AWARE
        # Dpi Awareness Successfully Set
    except:
        try:
            windll.user32.SetProcessDPIAware()  # Fallback for older Windows
            # Dpi Awareness Set (Fallback Method)
        except:
            pass  # DPI awareness could not be set - coordinates may be inconsistent

    # Windows Api Related Functions
    def get_scale_factor():
        return 1

    def _get_hwnd(window):
        """Return a Windows HWND int from a pywebview window/native object."""
        native = getattr(window, "native", window)
        candidates = (
            native,
            getattr(native, "Handle", None),# WinForms BrowserForm -> System.IntPtr
            getattr(window, "Handle", None),
            getattr(window, "hwnd", None),
        )
        for candidate in candidates:
            if not candidate:
                continue

            if isinstance(candidate, int):
                return candidate

            if hasattr(candidate, "value") and candidate.value:
                return int(candidate.value)

            if hasattr(candidate, "ToInt64"):
                value = int(candidate.ToInt64())
                if value:
                    return value

            if hasattr(candidate, "ToInt32"):
                value = int(candidate.ToInt32())
                if value:
                    return value

            try:
                value = int(candidate)
            except (TypeError, ValueError):
                continue

            if value:
                return value

        return None

# macOS (Keyboard, Scale Factor, Mouse Button)
elif sys.platform == "darwin":
    _scale_cache = None
    MAC_KEY_MAP = {
        "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
        "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20,
        "4": 21, "6": 22, "5": 23, "equal": 24, "9": 25, "7": 26, "minus": 27, "8": 28, "0": 29, "o": 31,
        "u": 32, "i": 34, "p": 35, "l": 37, "j": 38, "k": 40, "semicolon": 41, "comma": 43, "slash": 44, "n": 45,
        "m": 46, "period": 47, "space": 49, "return": 36, "enter": 76, "tab": 48, "escape": 53,
    }
    def get_scale_factor():
        global _scale_cache
        if _scale_cache is not None:
            return _scale_cache

        try:
            _scale_cache = float(AppKit.NSScreen.mainScreen().backingScaleFactor())
        except Exception:
            _scale_cache = 1.0
        return _scale_cache

    def get_mouse_position():
        event = Quartz.CGEventCreate(None)
        loc = Quartz.CGEventGetLocation(event)
        return loc.x, loc.y

    def _move_mouse(x, y):
        """Expects logical points."""
        point = Quartz.CGPointMake(x, y)
        Quartz.CGWarpMouseCursorPosition(point)
        Quartz.CGAssociateMouseAndMouseCursorPosition(True)
    def _mouse_event(button="left", press=True, x=None, y=None):
        """Unified cross-platform mouse event.
        button: 'left'/'right'/'middle' or 1/2/3
        press=True → down, False → up
        """
        if x is None or y is None:
            x, y = get_mouse_position()
        # Map Button → (Quartz Button Constant, Down Event, Up Event)
        button_map = {
            "left":   (Quartz.kCGMouseButtonLeft, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp),
            1:        (Quartz.kCGMouseButtonLeft, Quartz.kCGEventLeftMouseDown, Quartz.kCGEventLeftMouseUp),
            "right":  (Quartz.kCGMouseButtonRight,Quartz.kCGEventRightMouseDown,Quartz.kCGEventRightMouseUp),
            3:        (Quartz.kCGMouseButtonRight,Quartz.kCGEventRightMouseDown,Quartz.kCGEventRightMouseUp),
            "middle": (Quartz.kCGMouseButtonCenter, Quartz.kCGEventOtherMouseDown,Quartz.kCGEventOtherMouseUp),
            2:        (Quartz.kCGMouseButtonCenter, Quartz.kCGEventOtherMouseDown,Quartz.kCGEventOtherMouseUp),
        }
        key = button.lower() if isinstance(button, str) else button
        if key not in button_map:
            key = "left"
        btn, down_evt, up_evt = button_map[key]
        event_type = down_evt if press else up_evt
        event = Quartz.CGEventCreateMouseEvent(
            None,
            event_type,
            Quartz.CGPointMake(float(x), float(y)),
            btn
        )
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
    def send_key(key, delay=0.05, click_type=0):
        """
        Send a keyboard event.
        click_type:
            0 = click (press + release)   [default]
            1 = hold (press only)
            2 = release (release only)
        """
        keycode = MAC_KEY_MAP.get(str(key).lower())
        if keycode is None:
            return

        if click_type == 0:           # Click (press + release)
            Quartz.CGEventPost(
                Quartz.kCGHIDEventTap,
                Quartz.CGEventCreateKeyboardEvent(None, keycode, True)   # key down
            )
            time.sleep(delay)
            Quartz.CGEventPost(
                Quartz.kCGHIDEventTap,
                Quartz.CGEventCreateKeyboardEvent(None, keycode, False)  # key up
            )
        elif click_type == 1:         # Hold (press only)
            Quartz.CGEventPost(
                Quartz.kCGHIDEventTap,
                Quartz.CGEventCreateKeyboardEvent(None, keycode, True)   # key down
            )
        elif click_type == 2:         # Release only
            Quartz.CGEventPost(
                Quartz.kCGHIDEventTap,
                Quartz.CGEventCreateKeyboardEvent(None, keycode, False)  # key up
            )
        else:
            # Fallback To Normal Click If Invalid Value Is Passed
            Quartz.CGEventPost(
                Quartz.kCGHIDEventTap,
                Quartz.CGEventCreateKeyboardEvent(None, keycode, True)
            )
            time.sleep(delay)
            Quartz.CGEventPost(
                Quartz.kCGHIDEventTap,
                Quartz.CGEventCreateKeyboardEvent(None, keycode, False)
            )
# Linux (Mouse Positions And Xdisplay)
elif sys.platform.startswith("linux"):
    _xdisplay = None
    def _get_xdisplay():
        global _xdisplay
        if _xdisplay is None:
            _xdisplay = Xdisplay.Display()
        return _xdisplay

    def get_scale_factor():
        """
        X11 normally works in physical pixels.
        Return 1.0 unless you implement desktop-specific scaling detection.
        """
        return 1.0

    def get_mouse_position():
        d = _get_xdisplay()
        root = d.screen().root
        pointer = root.query_pointer()
        return pointer.root_x, pointer.root_y

    def _move_mouse(x, y):
        d = _get_xdisplay()
        root = d.screen().root
        root.warp_pointer(int(x), int(y))
        d.sync()
    def _mouse_event(button="left", press=True, x=None, y=None):
        """Unified cross-platform mouse event.
        button: 'left'/'right'/'middle' or 1/2/3
        press=True → down, False → up
        """
        d = _get_xdisplay()
        if x is not None and y is not None:
            _move_mouse(x, y)   # move first so the click happens at the desired location
        button_map = {
            "left": 1, 1: 1,
            "middle": 2, 2: 2,
            "right": 3, 3: 3,
        }
        key = button.lower() if isinstance(button, str) else button
        btn = button_map.get(key, 1)
        xtest.fake_input(
            d,
            X.ButtonPress if press else X.ButtonRelease,
            btn
        )
        d.sync()
    def send_key(key, delay=0.05, click_type=0):
        d = _get_xdisplay()
        keysym = XK.string_to_keysym(str(key))
        if keysym == 0:
            keysym = XK.string_to_keysym(str(key).lower())
        if keysym == 0:
            return

        keycode = d.keysym_to_keycode(keysym)
        if keycode == 0:
            return

        if click_type == 0:
            xtest.fake_input(d, X.KeyPress, keycode)
            d.sync()
            time.sleep(delay)
            xtest.fake_input(d, X.KeyRelease, keycode)
            d.sync()
        elif click_type == 1:
            xtest.fake_input(d, X.KeyPress, keycode)
            d.sync()
        elif click_type == 2:
            xtest.fake_input(d, X.KeyRelease, keycode)
            d.sync()
        else:
            xtest.fake_input(d, X.KeyPress, keycode)
            d.sync()
            time.sleep(delay)
            xtest.fake_input(d, X.KeyRelease, keycode)
            d.sync()
# Path Management
def _is_frozen():
    return bool(getattr(sys, "frozen", False))

def get_exe_dir():
    """Directory that contains the running executable (or the .py file in dev)."""
    if _is_frozen():
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.resolve()

def get_resource_path():
    """
    Packaged assets (ui/, images/, bundled default configs/).
    Compiled macOS/Linux: PyInstaller onedir --add-data folder (sys._MEIPASS,
    typically <app>/_internal or .app/Contents/Frameworks).
    Compiled Windows: directory next to the .exe (unchanged).
    Dev: project directory.
    """
    if _is_frozen():
        if sys.platform == "win32":
            return Path(sys.executable).parent.resolve()
        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS).resolve()
        return Path(sys.executable).parent.resolve()
    return Path(__file__).parent.resolve()

def get_appdata_path():
    """Writable user data. Compiled → platform AppData; dev → project directory."""
    if _is_frozen():
        if sys.platform == "darwin":
            return os.path.join(
                os.path.expanduser("~"),
                "Library", "Application Support",
                "SolarFishingV5"
            )
        elif sys.platform == "win32":
            return os.path.join(
                os.path.expanduser("~"),
                "AppData", "Roaming",
                "SolarFishingV5"
            )
        else:
            return os.path.join(os.path.expanduser("~"), "SolarFishingV5")
    return str(Path(__file__).parent.resolve())

def find_bundled_configs(resource_path, exe_dir):
    """Locate the packaged configs folder shipped with the onedir build."""
    candidates = [
        os.path.join(resource_path, "configs"),
        os.path.join(exe_dir, "configs"),
        os.path.join(exe_dir, "_internal", "configs"),
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return candidates[0]

def seed_configs_from_bundle(bundled_configs, configs_path):
    """If AppData has no configs folder, copy the packaged defaults into it."""
    if os.path.isdir(configs_path):
        return
    if os.path.isdir(bundled_configs):
        shutil.copytree(bundled_configs, configs_path)
    else:
        os.makedirs(configs_path, exist_ok=True)

# Establish Paths For Solar Fishing V5
RESOURCE_PATH = str(get_resource_path())
EXE_DIR = str(get_exe_dir())
IS_COMPILED = _is_frozen()
APPDATA_PATH = get_appdata_path()
# Writable Files (Last_Config.Json, Debug Shots, Logs) Live Here.
# Compiled → Appdata; Dev → Project Directory.
BASE_PATH = APPDATA_PATH if IS_COMPILED else RESOURCE_PATH
os.makedirs(BASE_PATH, exist_ok=True)
IMAGES_PATH = os.path.join(RESOURCE_PATH, "images")
UI_PATH = os.path.join(RESOURCE_PATH, "ui")
if IS_COMPILED:
    CONFIGS_PATH = os.path.join(APPDATA_PATH, "configs")
    BUNDLED_CONFIGS_PATH = find_bundled_configs(RESOURCE_PATH, EXE_DIR)
    seed_configs_from_bundle(BUNDLED_CONFIGS_PATH, CONFIGS_PATH)
else:
    BUNDLED_CONFIGS_PATH = os.path.join(RESOURCE_PATH, "configs")
    CONFIGS_PATH = BUNDLED_CONFIGS_PATH
LAST_CONFIG = os.path.join(BASE_PATH, "last_config.json")
# File Management
def open_folder(folder):
    if sys.platform == "win32":
        os.startfile(folder)
    elif sys.platform == "darwin":  # Macos
        subprocess.run(["open", folder])
    else:  # Linux
        subprocess.run(["xdg-open", folder])

def open_base_folder():
    # Writable User Data (Configs, Debug Shots, Logs)
    open_folder(BASE_PATH)
# Central Area Definitions.  To Add A New Selectable Area:
# 1. Add An Entry Below (Key, Color, Label, Default Ratios 0–1).
# 2. That'S It — Selector Ui, Save/Load, Defaults, And The Show/Hide Menu
#      all pick it up automatically.  Use get_areas("your_key") later if needed.
AREA_CONFIG = {
    "shake": {
        "color": "#df0000",
        "label": "Shake Box",
        "default": {"x": 0.1041, "y": 0.0925, "width": 0.7917, "height": 0.6963},
    },
    "fish": {
        "color": "#00beff",
        "label": "Fish Box",
        "default": {"x": 0.2844, "y": 0.7981, "width": 0.4297, "height": 0.0389},
    },
    "friend": {
        "color": "#ffed00",
        "label": "Friend Box (Fish End)",
        "default": {"x": 0.0046, "y": 0.8583, "width": 0.0355, "height": 0.0817},
    },
    "totem": {
        "color": "#00de07",
        "label": "Totem Box (Day/Night)",
        "default": {"x": 0.9504, "y": 0.8305, "width": 0.0234, "height": 0.0490},
    },
    "sovereign": {
        "color": "#d994ff",
        "label": "Sovereign Box (Bar)",
        "default": {"x": 0.2844, "y": 0.8184, "width": 0.4297, "height": 0.0185},
    },
    "noiseform": {
        "color": "#2a8d4f",
        "label": "Noiseform Box (Shapes)",
        "default": {"x": 0.4222, "y": 0.3543, "width": 0.2056, "height": 0.2762},
    },
    "lullaby": {
        "color": "#fdeeca",
        "label": "Lullaby Box (Above Fish)",
        "default": {"x": 0.4222, "y": 0.7043, "width": 0.1556, "height": 0.1360},
    },
    "chat": {
        "color": "#004383",
        "label": "Chat Box",
        "default": {"x": 0.0030, "y": 0.0683, "width": 0.2536, "height": 0.3323},
    },
    "backpack": {
        "color": "#ffe195",
        "label": "Backpack Box",
        "default": {"x": 0.3373, "y": 0.6108, "width": 0.3254, "height": 0.2656},
    },
    "treasure_appraisal": {
        "color": "#4f35f6",
        "label": "Treasure Appraisal Box (Grid)",
        "default": {"x": 0.3343, "y": 0.4156, "width": 0.3385, "height": 0.1629},
    },
    "appraisal_hotbar": {
        "color": "#e78300",
        "label": "Hotbar Box (Appraisal)",
        "default": {"x": 0.5529, "y": 0.8905, "width": 0.0373, "height": 0.0619},
    },
    "enchantment": {
        "color": "#008363",
        "label": "Enchantment Box (Text)",
        "default": {"x": 0.3061, "y": 0.3932, "width": 0.3649, "height": 0.1674},
    },
    "angler_quest": {
        "color": "#9BFF9B",
        "label": "Quest Box (Angler)",
        "default": {"x": 0.0139, "y": 0.5006, "width": 0.2316, "height": 0.1276},
    },
}
# Display / Iteration Order (Also Used For Numberkey Toggles 1–9 In The Selector)
AREA_ORDER = list(AREA_CONFIG.keys())

def get_tesseract_path(configured_path=None):
    """
    Return a valid Tesseract path for the current operating system.

    If an imported config contains a Tesseract path from another OS,
    automatically fall back to the current OS's Tesseract installation.
    """

    # 1. Try the path stored in the config first
    if configured_path:
        try:
            configured_path = str(configured_path).strip().strip('"')

            if Path(configured_path).is_file():
                return configured_path

        except (OSError, ValueError, TypeError):
            pass

    # 2. Check if Tesseract is already available in PATH
    detected = shutil.which("tesseract")

    if detected:
        return detected

    # 3. Check common paths for the CURRENT operating system
    if sys.platform == "win32":
        possible_paths = [
            r"C:\Program Files\Tesseract-OCR\tesseract.exe",
            r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        ]

    elif sys.platform == "darwin":
        possible_paths = [
            "/opt/homebrew/bin/tesseract",   # Apple Silicon Homebrew
            "/usr/local/bin/tesseract",      # Intel Homebrew
        ]

    else:
        # Linux
        possible_paths = [
            "/usr/bin/tesseract",
            "/usr/local/bin/tesseract",
        ]

    for path in possible_paths:
        if Path(path).is_file():
            return path

    # Nothing found
    return None

def _schedule_webview_destroy(win, after=None, delay=0.05):
    """Destroy a pywebview window after the current JS/GUI call returns.

    Calling Window.destroy() from that window's js_api deadlocks pywebview
    (the bridge waits for destroy; destroy waits for the bridge). The stall
    freezes every other window too. Tear windows down from a short-lived
    thread instead.
    """
    if win is None:
        if after:
            try:
                after()
            except Exception:
                pass
        return

    def _destroy():
        if delay:
            time.sleep(delay)
        try:
            win.destroy()
        except Exception:
            pass
        if after:
            try:
                after()
            except Exception:
                pass

    threading.Thread(target=_destroy, daemon=True).start()


class AreaSelector:
    """
    Fullscreen transparent overlay implemented as a second pywebview window.
    Long-lived instance: call show() / hide() / update() as needed.
    Areas are fully data-driven via the module-level AREA_CONFIG / AREA_ORDER.
    Adding a new area requires only a new entry in AREA_CONFIG.
    """
    # Prevent Pywebview From Walking This Object When The Main Api Is Js_Api
    # (Window.Native.Accessibilityobject.Bounds Recursion / Webview2 Com).
    _serializable = False
    HTML_FILE = os.path.join(UI_PATH, "area_selector.html")
    def __init__(self, parent_app):
        self.parent_app = parent_app
        self.area_window = None
        self._open = False
        self._areas = {}
        self._visible = {name: True for name in AREA_ORDER}
        self._screen_capture = None
        self._screenshot_b64 = None
        # Css Client Size Of The Overlay (Reported By Js). Used For Pixel↔Ratio
        # Conversion So Boxes Align When Display Scale ≠ 100%. Falls Back To
        # Screen_* Until Window_Ready Reports The Real Size.
        self._view_w = float(SCREEN_WIDTH)
        self._view_h = float(SCREEN_HEIGHT)
    def _capture_and_crop(self):
        """Capture full screen and remove the macOS menu bar strip so the
        image matches the frameless window geometry (no menu bar)."""
        frame = self.parent_app.capture_single_frame()
        if frame is None:
            return None

        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = frame[:, :, :3].copy()
        menu_offset = get_macos_menu_offset()
        scale = get_scale_factor()
        if scale <= 0:
            scale = 1.0
        self._scale = scale
        if menu_offset > 0:
            crop = int(round(menu_offset * scale))
            if 0 < crop < frame.shape[0]:
                frame = frame[crop:, :, :].copy()
        frame = np.clip(frame.astype(np.int16) - 15, 0, 255).astype(np.uint8)
        return frame

    def _encode_screenshot(self, frame):
        """Encode BGR numpy frame as a JPEG data-URL for the canvas."""
        if frame is None:
            return None

        try:
            # Jpeg Keeps The Payload Small Enough For Evaluate_Js
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                return None

            b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            return "data:image/jpeg;base64," + b64

        except Exception:
            return None

    def show(self):
        """Thin js_api object — only exposes the methods the HTML page calls.
        Do NOT pass `self` (or any object that holds a reference to the
        pywebview Window): on macOS Cocoa that triggers infinite recursion
        via AccessibilityObject.Bounds."""
        outer = self
        class _AreaApi:
            def get_area_config(self):
                return outer.get_area_config()

            def set_visibility(self, visible_dict):
                return outer.set_visibility(visible_dict)

            def get_areas(self):
                return outer.get_areas()

            def on_mouse_move(self, mouse_x, mouse_y, current_boxes):
                return outer.on_mouse_move(mouse_x, mouse_y, current_boxes)

            def on_point_select(self, name, xr, yr):
                return outer.on_point_select(name, xr, yr)

            def save_areas(self, areas):
                return outer.save_areas(areas)

            def get_screenshot_data(self):
                return outer.get_screenshot_data()

            def window_ready(self, win_x, win_y, width=None, height=None):
                return outer.window_ready(win_x, win_y, width, height)

        if self._open and self.area_window:
            return

        self._screen_capture = self._capture_and_crop()
        self._screenshot_b64 = self._encode_screenshot(self._screen_capture)
        menu_offset = get_macos_menu_offset()
        # Default View Size Until Js Reports The Real Css Client Size.
        # At Scale ≠ 100% These Often Differ From Screen_* (Physical).
        self._view_w = float(SCREEN_WIDTH)
        self._view_h = float(max(1, SCREEN_HEIGHT - menu_offset))
        self.area_window = webview.create_window(
            "Area Selector", self.HTML_FILE, js_api=_AreaApi(),
            transparent=True, frameless=True, easy_drag=False, on_top=True,
            resizable=False, width=SCREEN_WIDTH, height=SCREEN_HEIGHT - menu_offset,
            x=SCREEN_LEFT, y=SCREEN_TOP, background_color="#000000",
        )
        self._open = True
        self.area_window.events.closed += self._on_closed
        if sys.platform == "win32":
            def maximize_area_selector():
                try:
                    hwnd = _get_hwnd(self.area_window)
                    if hwnd:
                        user32.ShowWindow(wintypes.HWND(hwnd), SW_MAXIMIZE)
                except Exception as e:
                    try:
                        self.parent_app.set_status(f"Failed to maximize area selector: {e}")
                    except Exception:
                        print("Failed to maximize area selector:", e)
            self.area_window.events.shown += maximize_area_selector
    def _to_ratios(self, area):
        """Accept normalized areas and legacy pixel areas, store normalized values."""
        if not isinstance(area, dict):
            return {"x": 0.0, "y": 0.0, "width": 0.0, "height": 0.0}

        values = {
            "x": float(area.get("x", 0)),
            "y": float(area.get("y", 0)),
            "width": float(area.get("width", area.get("w", 0))),
            "height": float(area.get("height", area.get("h", 0))),
        }
        if any(abs(values[key]) > 1 for key in values):
            values["x"] /= SCREEN_WIDTH
            values["y"] /= SCREEN_HEIGHT
            values["width"] /= SCREEN_WIDTH
            values["height"] /= SCREEN_HEIGHT
        return values

    def update(self, area_name, area_dict):
        """Set one area by name (ratios or legacy pixels)."""
        self._areas[area_name] = self._to_ratios(area_dict)
    def update_all(self, areas_dict):
        """Bulk-load every known area from a {name: dict} mapping."""
        for name in AREA_ORDER:
            src = (areas_dict or {}).get(name)
            if not isinstance(src, dict):
                src = AREA_CONFIG[name]["default"]
            self._areas[name] = self._to_ratios(src)
    def get_area_config(self):
        """Return colours, labels, order and visibility so JS stays data-driven."""
        return {

            "order": list(AREA_ORDER),
            "areas": {
                name: {"color": cfg["color"], "label": cfg["label"]}
                for name, cfg in AREA_CONFIG.items()
            },
            "visible": dict(self._visible),
        }
    def set_visibility(self, visible_dict):
        """Keep Python in sync when the overlay panel toggles boxes."""
        if isinstance(visible_dict, dict):
            for name, val in visible_dict.items():
                if name in self._visible:
                    self._visible[name] = bool(val)
    def get_areas(self):
        """Return canvas-relative pixel boxes for JS (menu-bar offset subtracted).
        Uses the CSS client size reported by the page (_view_w / _view_h) so
        boxes line up with the canvas at any display scale. Falls back to
        SCREEN_* only before window_ready has reported the real size.
        """
        menu_offset = get_macos_menu_offset()
        vw = float(self._view_w) if self._view_w and self._view_w > 0 else float(SCREEN_WIDTH)
        vh = float(self._view_h) if self._view_h and self._view_h > 0 else float(max(1, SCREEN_HEIGHT - menu_offset))
        # Reconstruct Fullscreen Height In The Same Units As The View So
        # Stored Ratios (Relative To The Full Screen Including Menu Bar)
        # Map Correctly Into The Overlay'S Client Coordinate Space.
        full_h = vh + float(menu_offset)
        result = {}
        for name, area in self._areas.items():
            result[name] = {
                "x": area["x"] * vw,
                "y": area["y"] * full_h - menu_offset,
                "width": area["width"] * vw,
                "height": area["height"] * full_h,
            }
        return result

    def on_mouse_move(self, mouse_x, mouse_y, current_boxes):
        if not self._open:
            return

        menu_offset = get_macos_menu_offset()
        for name in AREA_ORDER:
            box = current_boxes.get(name, {})
            if box:
                self._areas[name] = self._pixels_to_ratios(box, menu_offset)
            b = current_boxes.get(name)
            if b and self._visible.get(name, True):
                bx, by = float(b.get("x", 0)), float(b.get("y", 0))
                bw = float(b.get("width", b.get("w", 0)) or 1)
                bh = float(b.get("height", b.get("h", 0)) or 1)
                mx, my = float(mouse_x or 0), float(mouse_y or 0)
                if bx <= mx <= bx + bw and by <= my <= by + bh:
                    xr = round((mx - bx) / bw, 2)
                    yr = round((my - by) / bh, 2)
                    try:
                        self.parent_app.set_status(f"{name.upper()} → X: {xr:.2f}  Y: {yr:.2f}")
                    except Exception:
                        pass

                    break

    def on_point_select(self, name, xr, yr):
        """Called by JS when Select Point mode is on and user clicks.
        Click inside an area → ratios relative to that area box.
        Click outside any area → full-screen (viewport) ratios 0–1 under the
        name "screen". Shows ratios in the status bar and closes the selector
        without the generic 'Area selector closed' message so the ratios remain visible."""
        if not self._open:
            return

        try:
            xr = float(xr)
            yr = float(yr)
        except (TypeError, ValueError):
            return

        xr = max(0.0, min(1.0, xr))
        yr = max(0.0, min(1.0, yr))
        # name may be None / "screen" / unknown when the click missed every box
        if not name or name == "screen" or name not in AREA_CONFIG:
            label = "SCREEN"
        else:
            label = (AREA_CONFIG.get(name) or {}).get("label", name)
        status_msg = f"{label.upper()}  →  X RATIO: {xr:.4f}  Y RATIO: {yr:.4f}"
        # Persist Current Areas, Then Close Without Overwriting The Ratio Status.
        try:
            self.parent_app.bar_areas.update(self._areas)
            self.parent_app.save_misc_settings()
        except Exception:
            pass

        self._open = False
        try:
            self.parent_app.set_status(status_msg)
        except Exception:
            pass

        win = self.area_window
        self.area_window = None
        _schedule_webview_destroy(win)

    def _pixels_to_ratios(self, box, menu_offset=0):
        """Convert JS canvas-pixel boxes back to full-screen ratios.
        Divides by the CSS client size (_view_w / _view_h) reported by the
        page so the ratio is correct even when that size differs from
        SCREEN_WIDTH / SCREEN_HEIGHT (common at display scale ≠ 100%).
        """
        vw = float(self._view_w) if self._view_w and self._view_w > 0 else float(SCREEN_WIDTH)
        vh = float(self._view_h) if self._view_h and self._view_h > 0 else float(max(1, SCREEN_HEIGHT - menu_offset))
        full_h = vh + float(menu_offset)
        if vw <= 0:
            vw = 1.0
        if full_h <= 0:
            full_h = 1.0
        return {

            "x": float(box.get("x", 0)) / vw,
            "y": (float(box.get("y", 0)) + menu_offset) / full_h,
            "width": float(box.get("width", box.get("w", 0))) / vw,
            "height": float(box.get("height", box.get("h", 0))) / full_h,
        }
    def window_ready(self, win_x, win_y, width=None, height=None):
        """JS signals the page is ready — record CSS client size and push screenshot.
        width/height are window.innerWidth / innerHeight (CSS pixels). Using
        these for box conversion fixes the off-screen drawing that happens
        when display scale ≠ 100% and SCREEN_* (physical) ≠ canvas size.
        """
        try:
            if width is not None and height is not None:
                w = float(width)
                h = float(height)
                if w > 0 and h > 0:
                    self._view_w = w
                    self._view_h = h
        except (TypeError, ValueError):
            pass

        if self._screenshot_b64 and self.area_window and self._open:
            # Inject Via A Short Data Reference; Js Stores It And Draws.
            try:
                # Pass As Return Value Of A Dedicated Getter Instead Of
                # Embedding A Huge String In Evaluate_Js When Possible.
                self.area_window.evaluate_js(
                    "window.__applyScreenshot && window.__applyScreenshot()"
                )
            except Exception:
                pass

        return None

    def save_areas(self, areas):
        if not self._open:
            return

        menu_offset = get_macos_menu_offset()
        for name in AREA_ORDER:
            if name in areas:
                self._areas[name] = self._pixels_to_ratios(areas[name], menu_offset)
        self.parent_app.bar_areas.update(self._areas)
        self.parent_app.save_misc_settings()
        self._open = False
        self.parent_app.set_status("Area selector closed")
        win = self.area_window
        self.area_window = None
        _schedule_webview_destroy(win)

    def get_screenshot_data(self):
        """Return the data-URL of the frozen (menu-bar-cropped) screenshot."""
        return self._screenshot_b64 or ""

    def _on_closed(self):
        if self._open:
            self.parent_app.bar_areas.update(self._areas)
            self.parent_app.save_misc_settings()
            self.parent_app.set_status("Area selector closed")
        self.area_window = None
        self._open = False
    def is_open(self):
        return self._open and self.area_window is not None

    def hide(self):
        if self.is_open():
            self.close()
    def close(self):
        if self.is_open():
            self.save_areas(self.get_areas())
        elif self.area_window:
            win = self.area_window
            self.area_window = None
            self._open = False
            _schedule_webview_destroy(win)
# Eyedropper Class
class Eyedropper:
    """
    Fullscreen transparent overlay for color picking using pywebview.
    Captures a frozen screenshot (menu bar cropped so it matches the
    frameless window), renders it in the canvas, and returns the picked color.
    """
    # Prevent Pywebview From Walking This Object When The Main Api Is Js_Api
    # (Window.Native.Accessibilityobject.Bounds Recursion / Webview2 Com).
    _serializable = False
    HTML_FILE = os.path.join(UI_PATH, "eyedropper.html")
    def __init__(self, parent_app):
        self.parent = parent_app
        self.eyedropper_window = None
        self._open = False
        self._visible = False
        self.last_picked_color = None
        self._cancelled = False
        self._color_key = None
        self._scale = 1.0
        self._screen_capture = None
        self._screenshot_b64 = None
        self.left = 0
        self.top = 0
        self.width = 0
        self.height = 0
    def _capture_and_crop(self):
        """Capture full screen and remove the macOS menu bar strip so the
        image matches the frameless window geometry (no menu bar)."""
        frame = self.parent.capture_single_frame()
        if frame is None:
            return None

        if frame.ndim == 3 and frame.shape[2] == 4:
            frame = frame[:, :, :3].copy()
        menu_offset = get_macos_menu_offset()
        scale = get_scale_factor()
        if scale <= 0:
            scale = 1.0
        self._scale = scale
        if menu_offset > 0:
            crop = int(round(menu_offset * scale))
            if 0 < crop < frame.shape[0]:
                frame = frame[crop:, :, :].copy()
        return frame

    def _encode_screenshot(self, frame):
        """Encode BGR numpy frame as a JPEG data-URL for the canvas."""
        if frame is None:
            return None

        try:
            # Jpeg Keeps The Payload Small Enough For Evaluate_Js
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                return None

            b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            return "data:image/jpeg;base64," + b64

        except Exception:
            return None

    def show(self, color_key=None):
        """Open the eyedropper overlay. Optional color_key is the settings
        field that should receive the picked color (e.g. 'fish_color').
        Thin js_api object — only exposes the methods the HTML page calls.
        Do NOT pass `self` (or any object that holds a reference to the
        pywebview Window): on macOS Cocoa that triggers infinite recursion
        via AccessibilityObject.Bounds (same crash previously fixed for
        AreaSelector).
        """
        if self._open and self.eyedropper_window:
            return

        outer = self
        class _EyedropperApi:
            def window_ready(self, win_x, win_y):
                return outer.window_ready(win_x, win_y)

            def get_screenshot_data(self):
                return outer.get_screenshot_data()

            def get_pixel_at(self, x, y):
                return outer.get_pixel_at(x, y)

            def pick_color(self, hex_color):
                return outer.pick_color(hex_color)

            def close_eyedropper(self):
                return outer.close_eyedropper()

        self.last_picked_color = None
        self._cancelled = False
        self._color_key = color_key
        self._screen_capture = self._capture_and_crop()
        self._screenshot_b64 = self._encode_screenshot(self._screen_capture)
        menu_offset = get_macos_menu_offset()
        win_h = max(1, SCREEN_HEIGHT - menu_offset)
        self.left = SCREEN_LEFT
        self.top = SCREEN_TOP
        self.width = SCREEN_WIDTH
        self.height = win_h
        self.eyedropper_window = webview.create_window(
            "Eyedropper",
            self.HTML_FILE,
            js_api=_EyedropperApi(),
            transparent=True,
            frameless=True,
            easy_drag=False,
            on_top=True,
            resizable=False,
            width=self.width,
            height=self.height,
            x=self.left,
            y=self.top,
            background_color="#000000",
        )
        self._open = True
        self._visible = True
        self.eyedropper_window.events.closed += self._on_closed
        if sys.platform == "win32":
            # Maximize On Windows After The Window Is Created
            def maximize_area_selector():
                try:
                    hwnd = _get_hwnd(self.eyedropper_window)
                    if hwnd:
                        user32.ShowWindow(wintypes.HWND(hwnd), SW_MAXIMIZE)
                except Exception as e:
                    self.parent.set_status("Failed to maximize area selector:", e)
            self.eyedropper_window.events.shown += maximize_area_selector
        try:
            self.parent.set_status(
                "Eyedropper opened • Hover to preview • Click to pick • Esc to cancel"
            )
        except Exception:
            pass

    def is_open(self):
        return self._open and self.eyedropper_window is not None

    def hide(self):
        """Destroy the overlay without freezing the GUI.

        pywebview deadlocks if destroy() runs on the same window whose JS
        bridge is still inside pick_color() / close_eyedropper(). That also
        stalls the main window ("not responding"). Clear flags immediately,
        then destroy on a short-lived thread so the JS call can return first.
        """
        win = self.eyedropper_window
        if not win or not self._open:
            self._open = False
            self._visible = False
            return

        self._open = False
        self._visible = False
        self.eyedropper_window = None
        _schedule_webview_destroy(win, after=self._on_closed)
    def close(self):
        """Alias used by shutdown / toggle paths."""
        self.hide()
    # ── Js Api Methods (Called From Eyedropper.Html) ──
    def window_ready(self, win_x, win_y):
        """JS signals the page is ready — push the frozen screenshot."""
        if self._screenshot_b64 and self.eyedropper_window and self._open:
            # Inject Via A Short Data Reference; Js Stores It And Draws.
            try:
                # Pass As Return Value Of A Dedicated Getter Instead Of
                # Embedding A Huge String In Evaluate_Js When Possible.
                self.eyedropper_window.evaluate_js(
                    "window.__applyScreenshot && window.__applyScreenshot()"
                )
            except Exception:
                pass

        return None

    def get_screenshot_data(self):
        """Return the data-URL of the frozen (menu-bar-cropped) screenshot."""
        return self._screenshot_b64 or ""

    def get_pixel_at(self, x, y):
        """Sample the frozen capture at logical canvas coordinates (x, y).
        Menu bar was already cropped out, so no y-offset is needed."""
        if not self.is_open():
            return "#000000"

        frame = self._screen_capture
        if frame is None:
            return "#000000"

        scale = self._scale if self._scale > 0 else 1.0
        px = int(x * scale)
        py = int(y * scale)
        if px < 0 or py < 0 or py >= frame.shape[0] or px >= frame.shape[1]:
            return "#000000"

        b = int(frame[py, px, 0])
        g = int(frame[py, px, 1])
        r = int(frame[py, px, 2])
        hex_color = f"#{r:02X}{g:02X}{b:02X}"
        try:
            self.parent.set_status(f"{hex_color} • Click to pick • Esc to cancel")
        except Exception:
            pass

        return hex_color

    def pick_color(self, hex_color):
        """Called by JS when user clicks to pick a color.
        Stores the color, pushes it to the main UI, and closes the overlay."""
        if not self.is_open():
            return None

        if not hex_color or not isinstance(hex_color, str):
            return None

        hex_color = hex_color.strip()
        if not hex_color.startswith("#"):
            hex_color = "#" + hex_color
        self.last_picked_color = hex_color
        self._cancelled = False
        # Write Into Settings Vars When A Target Key Was Provided
        color_key = self._color_key
        if color_key:
            try:
                self.parent.vars[color_key] = hex_color
            except Exception:
                pass

        # Notify The Main Webview So The Color Input Updates
        self._notify_main_ui(hex_color, color_key)
        try:
            self.parent.set_status(f"Picked color: {hex_color}")
        except Exception:
            pass

        self.hide()
        return hex_color

    def close_eyedropper(self):
        """Called by JS on Escape — cancel without picking."""
        if not self.is_open():
            return

        self._cancelled = True
        self.last_picked_color = None
        try:
            self.parent.set_status("Eyedropper cancelled")
        except Exception:
            pass

        self.hide()
    def _notify_main_ui(self, hex_color, color_key=None):
        """Push the picked color into the main pywebview window."""
        try:
            safe = hex_color.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"')
            key_js = "null"
            if color_key:
                key_js = "'" + str(color_key).replace("\\", "\\\\").replace("'", "\\'") + "'"
            script = (
                f"(function(){{"
                f"var c='{safe}',k={key_js};"
                f"if(window.onColorPicked)window.onColorPicked(c,k);"
                f"if(window.setPickedColor)window.setPickedColor(c,k);"
                f"if(k){{var el=document.getElementById(k)||document.querySelector('[data-color-key=\"'+k+'\"]')"
                f"||document.querySelector('input[name=\"'+k+'\"]');"
                f"if(el){{el.value=c;el.dispatchEvent(new Event('input',{{bubbles:true}}));"
                f"el.dispatchEvent(new Event('change',{{bubbles:true}}));}}"
                f"}}"
                f"}})()"
            )
            # Main Window Is The First Created Window
            if webview.windows:
                webview.windows[0].evaluate_js(script)
        except Exception:
            pass

    def _on_closed(self, *args):
        """Lifecycle cleanup when the overlay is destroyed."""
        self.eyedropper_window = None
        self._open = False
        self._visible = False
        self._screenshot_b64 = None
        # Keep Last_Picked_Color So The Main Ui Can Still Poll It
class FishOverlay:
    # Prevent Pywebview From Walking This Object When The Main Api Is Js_Api
    # (Window.Native.Accessibilityobject.Bounds Recursion / Webview2 Com).
    _serializable = False
    HTML_FILE = os.path.join(UI_PATH, "fish_overlay.html")
    def __init__(self, parent_app):
        self.parent_app = parent_app
        self._overlay_window = None
        self._open = False
        self._visible = False
        # Track Active Viewport Geometry (Logical Points For Pywebview)
        self.left = 0
        self.top = 0
        self.width = 0
        self.height = 0
    def _to_window_coords(self, left, top, width, height):
        """
        Convert physical-pixel geometry (from _get_areas / capture) into the
        logical points pywebview expects for window x/y/width/height.
        On Windows scale is always 1; on macOS Retina it is typically 2.0.
        Also clamps width/height so a bad (e.g. post-reset) size cannot make
        the overlay cover the entire screen or exceed monitor bounds.
        """
        scale = get_scale_factor()
        if scale <= 0:
            scale = 1.0
        left = int(left / scale)
        top = int(top / scale)
        width = max(1, int(width / scale))
        height = max(1, int(height / scale))
        # Clamp So The Window Stays Onscreen (Logical Screen Size)
        screen_w = max(1, SCREEN_WIDTH)
        screen_h = max(1, SCREEN_HEIGHT)
        width = min(width, screen_w)
        height = min(height, screen_h)
        left = max(0, min(left, max(0, screen_w - width)))
        top = max(0, min(top, max(0, screen_h - height)))
        return left, top, width, height

    def show(self, left, top, width, height):
        """Creates and displays the transparent frameless overlay window.
        Arguments are physical-pixel screen coordinates (same space as
        _get_areas / capture_frame). They are converted to logical points
        for pywebview.
        """
        left, top, width, height = self._to_window_coords(left, top, width, height)
        if self._open and self._overlay_window:
            # If Already Open, Shift/Resize It Instead Of Duplicating
            self.resize(left, top, width, height, already_logical=True)
            return

        self.left = left
        self.top = top
        self.width = width
        self.height = height
        self._overlay_window = webview.create_window(
            "Fish Overlay",
            url=self.HTML_FILE,
            transparent=False,
            frameless=True,
            easy_drag=False,
            on_top=True,
            resizable=False,
            width=self.width,
            height=self.height,
            x=self.left,
            y=self.top,
            background_color="#ffffff",
            min_size=(0.03 * SCREEN_WIDTH, 0.05 * SCREEN_HEIGHT),
        )
        self._open = True
        self._visible = True
        self._overlay_window.events.closed += self._on_closed
    def hide(self):
        """Destroys the current window instance completely.
        Clear _open BEFORE destroy so concurrent minigame threads that still
        call clear()/draw_box()/_eval skip the disposed WebView2 and avoid
        ObjectDisposedException (logged by pywebview as 'Error occurred in script').
        Destroy is scheduled off the caller thread so a stop/hotkey/shutdown
        path cannot deadlock pywebview the way Eyedropper/AreaSelector did.
        """
        win = self._overlay_window
        if not win or not self._open:
            self._open = False
            self._visible = False
            return

        self._open = False
        self._visible = False
        self._overlay_window = None
        _schedule_webview_destroy(win, after=self._on_closed)
    def resize(self, left, top, width, height, already_logical=False):
        """Resizes and moves the window dynamically if it exists.
        By default arguments are physical pixels (same as show()).
        Pass already_logical=True when the caller has already converted them.
        """
        if not already_logical:
            left, top, width, height = self._to_window_coords(left, top, width, height)
        self.left = left
        self.top = top
        self.width = width
        self.height = height
        if self._overlay_window and self._open:
            try:
                self._overlay_window.move(self.left, self.top)
                self._overlay_window.resize(self.width, self.height)
            except Exception:
                # Window May Already Be Disposed (Race With Stop_Macro / Hide)
                self._open = False
                self._overlay_window = None
    def clear(self):
        """Clears rendering elements inside the web view context."""
        self._eval("window.fishOverlay && window.fishOverlay.clear()")
    def draw_box(self, x1, y1, x2, y2, color, show_bar_center=False):
        """Evaluates JS drawing contexts based on calculations inside the viewport.
        bar_center / box_size / canvas_offset are in physical pixels relative to
        the fish capture region; they are converted to logical CSS pixels for
        the overlay canvas (which matches the logical window size).
        """
        # Ensure The Overlay Exists Before Trying To Execute Scripts On It
        if not self._open or not self._overlay_window:
            return

        # Failsafe if shape is None
        if x1 is None:
            return

        scale = get_scale_factor()
        if scale <= 0:
            scale = 1.0
        shape = {
            "x1": int(x1 / scale),
            "y1": int(y1 / scale),
            "x2": int(x2 / scale),
            "y2": int(y2 / scale),
            "color": str(color),
            "show_bar_center": bool(show_bar_center)
        }
        self._eval(f"window.fishOverlay && window.fishOverlay.draw({json.dumps(shape)})")
    def _eval(self, script):
        """Safely executes JavaScript strings within the running window environment.
        Catches ObjectDisposedException (and any other failure) that can occur
        when the overlay is destroyed from another thread while the minigame
        loop is still drawing."""
        if not (self._overlay_window and self._open):
            return
        try:
            self._overlay_window.evaluate_js(script)
        except Exception:
            # Webview2 May Already Be Disposed; Mark Closed So We Stop Trying
            self._open = False
            self._overlay_window = None
    def _on_closed(self):
        """Internal callback cleaning lifecycle states upon execution exit."""
        self._overlay_window = None
        self._open = False
        self._visible = False
class StatusOverlay:
    # Prevent Pywebview From Walking This Object When The Main Api Is Js_Api.
    # Statusoverlay.Show() Runs During Api.__Init__, So Overlay_Window Is A Live
    # Window By The Time Create_Window(..., Js_Api=Api) Runs — That Is What
    # Produced Status_Overlay.Overlay_Window.Native.Accessibilityobject.Bounds
    # recursion and the WebView2 "must be accessed from the UI thread" errors.
    _serializable = False
    HTML_FILE = os.path.join(UI_PATH, "status_overlay.html")
    def __init__(self, parent_app):
        self.parent_app = parent_app
        self._overlay_window = None
        self._open = False
        self._visible = False
        # Track Active Viewport Geometry
        # (Logical Points For Pywebview)
        self.left = 0
        self.top = 0
        self.width = 0
        self.height = 0
    def _to_window_coords(self, left, top, width, height):
        """
        Convert physical-pixel geometry into logical points
        for pywebview.
        On Windows scale is usually 1.
        On macOS Retina it is typically 2.0.
        """
        scale = get_scale_factor()
        if scale <= 0:
            scale = 1.0
        left = int(left / scale)
        top = int(top / scale)
        width = max(1, int(width / scale))
        height = max(1, int(height / scale))
        # Clamp Window Dimensions To Screen Bounds
        screen_w = max(1, SCREEN_WIDTH)
        screen_h = max(1, SCREEN_HEIGHT)
        width = min(width, screen_w)
        height = min(height, screen_h)
        left = max(0, min(left, max(0, screen_w - width)))
        top = max(0, min(top, max(0, screen_h - height)))
        return left, top, width, height

    def show(self, left, top, width, height):
        """
        Creates and displays the status overlay window.
        Arguments are physical-pixel screen coordinates.
        """
        left, top, width, height = self._to_window_coords(
            left, top, width, height
        )
        if self._open and self._overlay_window:
            self.resize(
                left,
                top,
                width,
                height,
                already_logical=True
            )
            return

        self.left = left
        self.top = top
        self.width = width
        self.height = height
        self._overlay_window = webview.create_window(
            "Status Overlay",
            url=self.HTML_FILE,
            transparent=False,
            frameless=True,
            easy_drag=False,
            on_top=True,
            resizable=False,
            width=self.width,
            height=self.height,
            x=self.left,
            y=self.top,
            background_color="#000000",
            min_size=(0.1 * SCREEN_WIDTH, 0.1 * SCREEN_HEIGHT),
        )
        self._open = True
        self._visible = True
        self._overlay_window.events.closed += self._on_closed
    def hide(self):
        """
        Destroys the current window instance completely.
        Scheduled so hide() from stop_macro / main-window close cannot
        deadlock the pywebview GUI thread.
        """
        win = self._overlay_window
        if not win or not self._open:
            self._open = False
            self._visible = False
            return

        self._open = False
        self._visible = False
        self._overlay_window = None
        _schedule_webview_destroy(win, after=self._on_closed)
    def resize(self, left, top, width, height, already_logical=False):
        """
        Resizes and moves the window dynamically.
        By default arguments are physical pixels.
        Pass already_logical=True when already converted.
        """
        if not already_logical:
            left, top, width, height = self._to_window_coords(
                left,
                top,
                width,
                height
            )
        self.left = left
        self.top = top
        self.width = width
        self.height = height
        if self._overlay_window and self._open:
            try:
                self._overlay_window.move(
                    self.left,
                    self.top
                )
                self._overlay_window.resize(
                    self.width,
                    self.height
                )
            except Exception:
                self._open = False
                self._overlay_window = None
    def set_title(self, title):
        """
        Updates the overlay title.
        """
        self._eval(
            f"window.statusOverlay && "
            f"window.statusOverlay.setTitle("
            f"{json.dumps(str(title))})"
        )
    def set_main_status(self, status):
        """
        Updates the main process/status label.
        """
        self._eval(
            f"window.statusOverlay && "
            f"window.statusOverlay.setMainStatus("
            f"{json.dumps(str(status))})"
        )
    def set_line(self, number, label, value):
        """
        Updates one of the three status lines.
        number must be 1, 2, or 3.
        """
        if number not in (1, 2, 3):
            raise ValueError("Status line number must be 1, 2, or 3")

        self._eval(
            f"window.statusOverlay && "
            f"window.statusOverlay.setLine("
            f"{number}, "
            f"{json.dumps(str(label))}, "
            f"{json.dumps(str(value))})"
        )
    def set_status( self, title, main_status, line1, line2, line3 ):
        """
        Updates the entire status overlay.
        Each line should be a (label, value) tuple.
        """
        self.set_title(title)
        self.set_main_status(main_status)
        self.set_line(1,line1[0],line1[1])
        self.set_line(2,line2[0],line2[1])
        self.set_line(3,line3[0],line3[1])
    def clear(self):
        """
        Resets the status overlay to its default state.
        """
        self._eval(
            "window.statusOverlay && "
            "window.statusOverlay.clear()"
        )
    def _eval(self, script):
        """
        Safely executes JavaScript within the WebView.
        Prevents calls against a WebView that has already been destroyed.
        """
        if not (self._overlay_window and self._open):
            return

        try:
            self._overlay_window.evaluate_js(script)
        except Exception:
            self._open = False
            self._overlay_window = None
    def _on_closed(self):
        """
        Cleans lifecycle state when the window closes.
        """
        self._overlay_window = None
        self._open = False
        self._visible = False
class Api:
    def __init__(self):
        self.vars = {} # Save Entry Variables Here
        self.current_config = self.get_last_config()
        self.load_settings_into_vars(self.current_config)
        # Start Hotkey Listener
        try:
            self.key_listener = KeyListener(on_press=self.on_key_press)
            self.key_listener.daemon = True
            self.key_listener.start()
        except Exception as e:
            self.set_status(f"Key Listener error: {e}")
        # Store Screen Width And Height To Use Later
        self.SCREEN_WIDTH = SCREEN_WIDTH
        self.SCREEN_HEIGHT = SCREEN_HEIGHT
        self.SCREEN_LEFT = SCREEN_LEFT
        self.SCREEN_TOP = SCREEN_TOP
        self.SCREEN_SCALE = ((self.SCREEN_WIDTH / 1920) + (self.SCREEN_HEIGHT / 1080)) / 2
        # Macro State
        self.macro_running = False
        self.macro_thread = None
        # Screen Capture
        self.capture_thread = None
        self.capture_frame = None
        self.capture_id = 0
        self.scan_delay = 0.1
        # Utility Classes
        self.area_selector = AreaSelector(self)
        self.eyedropper = Eyedropper(self)
        self.fish_overlay = FishOverlay(self)
        self.status_overlay = StatusOverlay(self)
        # Safe Defaults Before Key Listener Starts (Will Be Overwritten By Load_Misc_Settings)
        scale = get_scale_factor()
        menu_offset = get_macos_menu_offset()
        self.bar_areas = {name: None for name in AREA_ORDER}
        self.current_rod_name = "Default"
        self.scale_x_1440 = SCREEN_WIDTH / 2560
        self.scale_y_1440 = SCREEN_HEIGHT / 1440
        self.scale_x_1080 = SCREEN_WIDTH / 1920
        self.scale_y_1080 = SCREEN_HEIGHT / 1080
        self.status_left = 20
        self.status_top = (menu_offset * scale) + 40
        self.status_right = (300 * scale * self.scale_x_1080)
        self.status_bottom = (200 * scale * self.scale_y_1080)
        self.status_overlay.hide()
        # Noiseform (Shapes) Warn-Kind State — Port Of DeepFish NoiseWarnKind()
        self._reset_noiseform_warn_state()
        # Load Settings
        self._load_misc_settings()
    def _refresh_screen_dimensions(self):
        """
        Re-query mss for the primary monitor's current resolution and update all
        screen-dimension instance variables.  Call this whenever the capture monitor
        changes (hot-plug, resolution switch, etc.) so that _get_areas, the capture pipelines,
        and the fish-overlay layout all use the correct pixel dimensions.
        Invalidating _thread_local forces the capture pipelines to rebuild its cached
        monitor dict on the next capture call.
        """
        with MSS() as _sct:
            if len(_sct.monitors) > 1:
                _m = _sct.monitors[1]
            else:
                _m = _sct.monitors[0]
        self.SCREEN_WIDTH  = _m["width"]
        self.SCREEN_HEIGHT = _m["height"]
        self.SCREEN_LEFT   = _m["left"]
        self.SCREEN_TOP    = _m["top"]
        self.SCREEN_SCALE  = ((self.SCREEN_WIDTH / 1920) + (self.SCREEN_HEIGHT / 1080)) / 2
        self.scale_x_1440  = self.SCREEN_WIDTH  / 2560
        self.scale_y_1440  = self.SCREEN_HEIGHT / 1440
        # Force The Capture Pipelines To Rebuild The Threadlocal Monitor Dict.
        self._thread_local = threading.local()
    # Save Config
    def _get_prompt_defaults(self):
        defaults = {}
        index_path = os.path.join(UI_PATH, "index.html")
        try:
            with open(index_path, "r", encoding="utf-8") as f:
                html = f.read()
        except Exception:
            return defaults

        input_pattern = re.compile(r"<input\b(?=[^>]*\bid\s*=\s*['\"]?([^'\"\s>]+))" r"(?=[^>]*\bplaceholder\s*=\s*['\"]([^'\"]*)['\"])[^>]*>", re.IGNORECASE,)
        for field_id, placeholder in input_pattern.findall(html):
            prompt = placeholder.strip()
            defaults[field_id] = prompt
        select_pattern = re.compile( r"<select\b(?=[^>]*\bid\s*=\s*['\"]?([^'\"\s>]+))[^>]*>" r"(.*?)</select>", re.IGNORECASE | re.DOTALL, )
        option_pattern = re.compile( r"<option\b[^>]*\bvalue\s*=\s*['\"]?([^'\"\s>]+)", re.IGNORECASE, )
        for field_id, body in select_pattern.findall(html):
            match = option_pattern.search(body)
            if match:
                defaults[field_id] = match.group(1).strip()
        return defaults

    def _get_saved_default_config(self):
        default_path = os.path.join(CONFIGS_PATH, "Default", "config.json")
        try:
            with open(default_path, "r") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}

        except Exception:
            return {}

    def _get_config_defaults(self):
        defaults = self._get_saved_default_config()
        defaults.update(self._get_prompt_defaults())
        return defaults

    def _fill_blank_settings(self, settings):
        clean_settings = dict(settings or {})
        defaults = self._get_config_defaults()
        for key, value in list(clean_settings.items()):
            if isinstance(value, str) and value.strip() == "" and key in defaults:
                clean_settings[key] = defaults[key]
        return clean_settings

    def _load_settings_data(self, config_name):
        config_path = os.path.join(CONFIGS_PATH, config_name, "config.json")
        with open(config_path, "r") as f:
            settings = json.load(f)
        settings = self._fill_blank_settings(settings)
        return settings, config_path

    def _is_global_settings_enabled(self, settings=None):
        """Return True if Global Settings is currently enabled."""
        source = settings if settings is not None else self.vars
        value = source.get("global_settings", "off")
        if isinstance(value, bool):
            return value
        return str(value).strip().lower() in ("on", "true", "1", "yes")

    def _color_setting_keys(self):
        """Keys treated as per-config color settings (excluded from Global Settings)."""
        return set(self.get_default_colors().keys())

    def _non_color_settings(self, settings):
        """Return a copy of settings with color-related keys removed."""
        color_keys = self._color_setting_keys()
        return {k: v for k, v in (settings or {}).items() if k not in color_keys}

    def _propagate_global_settings(self, settings, only_flag=False):
        """Write shared settings into every config, preserving each config's colors.
        When only_flag is True, only the global_settings checkbox value is synced
        (used when Global Settings is turned off so the flag stays consistent).
        """
        if only_flag:
            keys_to_write = {
                "global_settings": (settings or {}).get("global_settings", "off")
            }
        else:
            keys_to_write = self._non_color_settings(settings)
        if not keys_to_write:
            return

        color_keys = self._color_setting_keys()
        for name in self.list_configs():
            try:
                folder = os.path.join(CONFIGS_PATH, name)
                config_path = os.path.join(folder, "config.json")
                existing = {}
                if os.path.exists(config_path):
                    with open(config_path, "r", encoding="utf-8") as f:
                        existing = json.load(f)
                    if not isinstance(existing, dict):
                        existing = {}
                merged = dict(existing)
                merged.update(keys_to_write)
                # Preserve Perconfig Colors (In Case A Key Was Mistakenly Included)
                for ck in color_keys:
                    if ck in existing:
                        merged[ck] = existing[ck]
                os.makedirs(folder, exist_ok=True)
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(merged, f, indent=4)
            except Exception:
                continue

    def save_settings(self, config_name, settings, text="Settings saved"):
        try:
            if not config_name:
                return {"success": False, "error": "No config selected."}

            self.active_config = config_name

            folder = os.path.join(CONFIGS_PATH,config_name)
            os.makedirs(folder, exist_ok=True)
            settings = self._fill_blank_settings(settings)
            self.vars.update(settings)
            self.current_config = config_name
            self.save_last_config(config_name)
            config_path = os.path.join(folder, "config.json")
            with open(config_path, "w") as f:
                json.dump(settings,f,indent=4)
            # Global Settings: Share Every Setting Except Colors Across All Configs.
            # When Turned Off, Still Keep The Global_Settings Flag Itself In Sync
            # So Switching Configs Does Not Reenable It From An Old File.
            if self._is_global_settings_enabled(settings):
                self._propagate_global_settings(settings, only_flag=False)
            else:
                self._propagate_global_settings(settings, only_flag=True)
            self.save_misc_settings()
            self.set_status(text)
            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # Load Config
    def load_settings(self, config_name):
        try:
            if not config_name:
                return {"success": False, "error": "No config selected."}

            self.active_config = config_name

            settings, config_path = self._load_settings_data(config_name)
            # If Global Settings Is Active (In The Session Or The Loaded File), Keep
            # Noncolor Values Shared And Only Swap In This Config'S Colors.
            was_global = self._is_global_settings_enabled(self.vars)
            file_global = self._is_global_settings_enabled(settings)
            if was_global or file_global:
                color_keys = self._color_setting_keys()
                shared = self._non_color_settings(self.vars) if was_global else self._non_color_settings(settings)
                # Always Force The Flag On So It Stays Consistent Across Configs
                shared["global_settings"] = "on"
                merged = dict(settings)
                merged.update(shared)
                # Ensure Colors Still Come From The Config Being Loaded
                for ck in color_keys:
                    if ck in settings:
                        merged[ck] = settings[ck]
                settings = merged
            with open(config_path, "w") as f:
                json.dump(settings,f,indent=4)
            self.vars = settings.copy()
            self.current_config = config_name
            self.save_last_config(config_name)
            self._load_misc_settings()
            return {"success": True, "settings": settings}

        except Exception as e:
            return {"success": False, "error": str(e)}

    # List Configs
    def list_configs(self):
        try:
            configs = sorted([folder for folder in os.listdir(CONFIGS_PATH) if os.path.isdir(os.path.join(CONFIGS_PATH, folder))])
            return configs

        except Exception:
            return []

    # Settings State
    def update_settings(self, settings):
        self.vars.update(settings)
        return {"success": True}

    def get_last_config(self):
        try:
            if os.path.exists(LAST_CONFIG):
                with open(LAST_CONFIG, "r") as f:
                    data = json.load(f)
                return data.get("last_config", "")

        except Exception:
            pass

        return ""

    def save_last_config(self, config_name):
        try:
            data = {}
            if os.path.exists(LAST_CONFIG):
                with open(LAST_CONFIG, "r") as f:
                    data = json.load(f)
            data["last_config"] = config_name
            with open(LAST_CONFIG, "w") as f:
                json.dump(data, f, indent=4)
        except Exception as e:
            self.set_status(f"Error saving last config: {e}")
    def resolve_config_name(self, config_name):
        configs = self.list_configs()
        if config_name in configs:
            return config_name

        for name in configs:
            if name.lower() == str(config_name).lower():
                return name

        return configs[0] if configs else ""

    def load_settings_into_vars(self, config_name):
        config_name = self.resolve_config_name(config_name)
        if not config_name:
            return

        try:
            settings, config_path = self._load_settings_data(config_name)
            with open(config_path, "w") as f:
                json.dump(settings,f,indent=4)
            self.vars = settings
            self.current_config = config_name
            self.save_last_config(config_name)
        except Exception as e:
            self.set_status(f"Error loading config: {e}")
    def get_startup_config(self):
        config_name = self.resolve_config_name(self.current_config)
        if not config_name:
            return {

                "success": False,
                "error": "No configs found."
            }
        result = self.load_settings(config_name)
        if result.get("success"):
            result["config_name"] = config_name
        return result

    # Delete Config
    def delete_config(self, config_name):
        try:
            folder = os.path.join( CONFIGS_PATH, config_name )
            config_path = os.path.join( folder, "config.json" )
            if os.path.exists(config_path):
                os.remove(config_path)
            if os.path.exists(folder):
                os.rmdir(folder)
            return { "success": True }

        except Exception as e:
            return { "success": False, "error": str(e) }

    def _load_misc_settings(self):
        """Load miscellaneous settings from last_config.json."""
        current_path = os.path.join(BASE_PATH, "last_config.json")
        data = load_misc_settings(current_path)
        # Bar Areas
        try:
            loaded_areas = data.get("bar_areas", {})
            for key in AREA_ORDER:
                area = loaded_areas.get(key)
                if isinstance(area, dict):
                    self.bar_areas[key] = {
                        "x": float(area.get("x", 0)),
                        "y": float(area.get("y", 0)),
                        "width": float(area.get("width", 0)),
                        "height": float(area.get("height", 0)),
                    }
        except:
            pass
        # Hotkeys
        if "start_key" in self.vars and "area_selector_key" in self.vars and "stop_key" in self.vars:
            # Case 1: Hotkeys Are In Self.Vars
            pass
        elif "start_key" in data and "area_selector_key" in data and "stop_key" in data:
            # Case 2: Hotkeys Are In Data
            self.vars["start_key"] = data["start_key"]
            self.vars["area_selector_key"] = data["area_selector_key"]
            self.vars["stop_key"] = data["stop_key"]
        else:
            # Case 3: Hotkeys Are Not In Self.Vars And Data
            self.vars["start_key"] = "F5"
            self.vars["area_selector_key"] = "F6"
            self.vars["stop_key"] = "F7"
        # Images
        try:
            sun = cv2.imread(os.path.join(IMAGES_PATH, "sun.png"))
            moon = cv2.imread(os.path.join(IMAGES_PATH, "moon.png"))
        except:
            self.message_box_javascript("Missing required image files:\nsun.png, moon.png\nAuto Totem will be disabled")
    def save_misc_settings(self):
        """Save miscellaneous settings."""
        path = os.path.join(BASE_PATH, "last_config.json")
        # Existing Data
        data = {}
        if os.path.exists(path):
            try:
                with open(path, "r") as f:
                    data = json.load(f)
            except:
                pass

        # Clean Areas
        clean_bar_areas = {}
        for key in AREA_ORDER:
            area = self.bar_areas.get(key)
            if isinstance(area, dict):
                clean_bar_areas[key] = {
                    "x": float(area.get("x", 0)),
                    "y": float(area.get("y", 0)),
                    "width": float(area.get("width", 0)),
                    "height": float(area.get("height", 0)),
                }
            else:
                clean_bar_areas[key] = None
        # Save
        data["bar_areas"] = clean_bar_areas
        # Hotkeys
        data["start_key"] = self.vars["start_key"]
        data["area_selector_key"] = self.vars["area_selector_key"]
        data["stop_key"] = self.vars["stop_key"]
        with open(path, "w") as f:
            json.dump(data, f, indent=4)
    def open_base_folder(self):
        open_base_folder()
    def get_default_settings(self):
        return self._get_config_defaults()

    def get_default_colors(self):
        default_settings = self.get_default_settings()
        color_keys = [
            "left_color",
            "right_color",
            "arrow_color",
            "fish_color",
            "left_tolerance",
            "right_tolerance",
            "arrow_tolerance",
            "fish_tolerance",
            "shake_color",
            "shake_tolerance",
            "green_cast_color",
            "green_cast_tolerance",
            "white_cast_color",
            "white_cast_tolerance",
            "pinion_notes_color",
            "pinion_notes_tolerance",
            "sovereign_recharge_color",
            "sovereign_recharge_tolerance",
            "friends_color",
            "friends_tolerance",
        ]
        return {

            key: default_settings[key]
            for key in color_keys
            if key in default_settings
        }
    def reset_settings(self, config_name):
        try:
            config_folder = os.path.join(
                CONFIGS_PATH,
                config_name
            )
            config_path = os.path.join(
                config_folder,
                "config.json"
            )
            os.makedirs(
                config_folder,
                exist_ok=True
            )
            existing_config = {}
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    existing_config = json.load(f)
            # Full Defaults
            default_settings = self.get_default_settings()
            # Preserve Colors
            for color_key in self.get_default_colors().keys():
                if color_key in existing_config:
                    default_settings[color_key] = (
                        existing_config[color_key]
                    )
            # Keep The Current Global Settings Flag (Do Not Force It Off On Reset)
            if "global_settings" in existing_config:
                default_settings["global_settings"] = existing_config["global_settings"]
            elif "global_settings" in self.vars:
                default_settings["global_settings"] = self.vars["global_settings"]
            with open(config_path, "w") as f:
                json.dump(
                    default_settings,
                    f,
                    indent=4
                )
            # When Global Settings Is On, Reset Noncolor Settings Across Every Config
            # While Still Preserving Each Config'S Own Colors.
            if self._is_global_settings_enabled(default_settings):
                self._propagate_global_settings(default_settings, only_flag=False)
            self.message_box_javascript("Settings reset to default")
            return {

                "success": True
            }
        except Exception as e:
            self.message_box_javascript(f"Error resetting settings: {e}")
            return {

                "success": False,
                "error": str(e)
            }
    def reset_colors(self, config_name):
        try:
            config_folder = os.path.join(
                CONFIGS_PATH,
                config_name
            )
            config_path = os.path.join(
                config_folder,
                "config.json"
            )
            os.makedirs(
                config_folder,
                exist_ok=True
            )
            if os.path.exists(config_path):
                with open(config_path, "r") as f:
                    config_data = json.load(f)
            else:
                config_data = {}
            # Reset Only Colors
            config_data.update(
                self.get_default_colors()
            )
            with open(config_path, "w") as f:
                json.dump(
                    config_data,
                    f,
                    indent=4
                )
            self.message_box_javascript("Colors reset to default")
            return {

                "success": True
            }
        except Exception as e:
            self.message_box_javascript(f"Error resetting colors: {e}")
            return {

                "success": False,
                "error": str(e)
            }
    def reset_areas(self):
        """Reset areas to default"""
        try:
            config_path = os.path.join(
                BASE_PATH,
                "last_config.json"
            )
            if not os.path.exists(config_path):
                return {

                    "success": True
                }
            with open(config_path, "r") as f:
                config_data = json.load(f)
            # Remove Saved Custom Areas
            config_data.pop("bar_areas", None)
            with open(config_path, "w") as f:
                json.dump(config_data, f, indent=4)
            # Also Reset The Inmemory Areas So They Take Effect Immediately.
            # Use Area_Config Defaults (Ratios) Rather Than {} So Get_Areas And
            # Any Code That Inspects Bar_Areas Directly Still See Valid Geometry.
            if hasattr(self, "bar_areas"):
                self.bar_areas = {
                    name: dict(AREA_CONFIG[name]["default"])
                    for name in AREA_ORDER
                }
            self.message_box_javascript("Areas reset to default")
            return {"success": True}

        except Exception as e:
            self.message_box_javascript(f"Error resetting areas: {e}")
            return {

                "success": False,
                "error": str(e)
            }
    def import_config(self, config_name, settings):
        try:
            if not config_name:
                return {"success": False, "error": "No config name provided."}

            if config_name in (".", "..") or "/" in config_name or "\\" in config_name:
                return {"success": False, "error": "Invalid config name."}

            folder = os.path.join(CONFIGS_PATH, config_name)
            os.makedirs(folder, exist_ok=True)
            settings = self._fill_blank_settings(settings)
            config_path = os.path.join(folder, "config.json")
            with open(config_path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4)
            return {"success": True}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def select_import_config(self):
        try:
            path = webview.windows[0].create_file_dialog(
                webview.FileDialog.OPEN,
                allow_multiple=False,
                file_types=("JSON files (*.json)",)
            )
            if not path:
                return {"success": False, "cancelled": True}

            if isinstance(path, (list, tuple)):
                path = path[0]
            with open(path, "r", encoding="utf-8") as f:
                settings = json.load(f)
            return {
                "success": True,
                "settings": settings,
                "filename": os.path.basename(path)
            }
        except json.JSONDecodeError:
            return {
                "success": False,
                "error": "Invalid config file."
            }
        except Exception as e:
            return {
                "success": False,
                "error": str(e)
            }
    def export_config(self, settings):
        try:
            path = webview.windows[0].create_file_dialog(
                webview.FileDialog.SAVE,
                save_filename=f"{self.current_config}.json"
            )
            if not path:
                return {"success": False, "error": "Cancelled"}

            if isinstance(path, (list, tuple)):
                path = path[0]
            with open(path, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=4)
            self.message_box_javascript(f"Exported {self.current_config}.json")
            return {"success": True, "path": path}

        except Exception as e:
            return {"success": False, "error": str(e)}

    def open_link(self, url):
        """Open a URL in the default web browser."""
        try:
            webbrowser.open(url)
            return {

                "success": True
            }
        except Exception as e:
            return {

                "success": False,
                "error": str(e)
            }
    def get_macro_version(self):
        return APP_VERSION

    def set_status(self, message):
        """Push a status message to the main webview window's JS."""
        if IS_COMPILED == False:
            # print("Debug: ", message)
            pass

        try:
            safe = message.replace("\\", "\\\\").replace("`", "\\`").replace("'", "\\'")
            window.evaluate_js("window.setStatus && window.setStatus('" + safe + "')")
        except Exception:
            pass

    def message_box_javascript(self, message, dialogue_type="ok"):
        try:
            # Escape Characters That Could Break The Javascript String
            escaped_message = (
                message
                .replace("\\", "\\\\")
                .replace('"', '\\"')
                .replace("\n", "\\n")
                .replace("\r", "\\r")
            )
            if dialogue_type == "askyesno":
                js_code = f"""
                (function() {{
                    return confirm("{escaped_message}");
                }})();
                """
                return window.evaluate_js(js_code)

            else:
                js_code = f"""
                (function() {{
                    alert("{escaped_message}");
                    return null;
                }})();
                """
                window.evaluate_js(js_code)
                return None

        except Exception:
            return False if dialogue_type == "askyesno" else None

    def copy_to_clipboard(self, text):
        """Copy text to the system clipboard. Returns True on success."""
        if text is None:
            return False
        text = str(text)
        try:
            if sys.platform == "darwin":
                pasteboard = AppKit.NSPasteboard.generalPasteboard()
                pasteboard.clearContents()
                # NSPasteboardTypeString Is Preferred; Fall Back To Legacy Type Name
                paste_type = getattr(AppKit, "NSPasteboardTypeString", None) or AppKit.NSStringPboardType
                return bool(pasteboard.setString_forType_(text, paste_type))
            elif sys.platform == "win32":
                # Prefer Powershell Setclipboard For Reliable Unicode Support
                try:
                    completed = subprocess.run(
                        [
                            "powershell",
                            "-NoProfile",
                            "-Command",
                            "Set-Clipboard -Value ([Console]::In.ReadToEnd())",
                        ],
                        input=text,
                        text=True,
                        capture_output=True,
                        timeout=5,
                    )
                    if completed.returncode == 0:
                        return True
                except Exception:
                    pass
                # Fallback: Clip.Exe With Utf16Le
                try:
                    completed = subprocess.run(
                        ["clip"],
                        input=text.encode("utf-16le"),
                        capture_output=True,
                        timeout=5,
                    )
                    return completed.returncode == 0
                except Exception:
                    return False
            else:
                # Linux: Try Xclip, Then Xsel
                payload = text.encode("utf-8")
                for cmd in (
                    ["xclip", "-selection", "clipboard"],
                    ["xsel", "--clipboard", "--input"],
                ):
                    try:
                        completed = subprocess.run(
                            cmd,
                            input=payload,
                            capture_output=True,
                            timeout=5,
                        )
                        if completed.returncode == 0:
                            return True
                    except FileNotFoundError:
                        continue
                    except Exception:
                        continue
                return False
        except Exception:
            return False

    def get_error_line(self, lines):
        matches = re.findall(r'\bline\s+(\d+)\b', lines)
        if not matches:
            return None

        return int(matches[-1])

    # Area Selector
    def open_area_selector(self):
        # Build Current Areas From Bar_Areas Or Area_Config Defaults (All Keys, Including Appraisal)
        areas = {}
        for name in AREA_ORDER:
            a = self.bar_areas.get(name)
            areas[name] = a if isinstance(a, dict) else dict(AREA_CONFIG[name]["default"])
        if hasattr(self, "area_selector") and self.area_selector and self.area_selector.is_open():
            self.area_selector.hide()
            self.status_overlay.show(self.status_left, self.status_top, self.status_right, self.status_bottom)
        else:
            self.status_overlay.hide()
            self.area_selector.show()
            self.area_selector.update_all(areas)
    # Debug Screenshots
    def take_debug_screenshot(self):
        """
        Capture every area in AREA_ORDER plus a full-screen shot, and save
        debug images as debug_<name>.png / debug_full.png.
        """
        full_img = self.capture_single_frame()
        if full_img is None:
            self.set_status("Full screen is empty")
            return

        try:
            cv2.imwrite(os.path.join(BASE_PATH, "debug_full.png"), full_img)
        except Exception as e:
            self.set_status(f"Error saving full screenshot: {e}")
            return

        saved = ["full"]
        try:
            for name in AREA_ORDER:
                left, top, right, bottom, _, _ = self.get_areas(name)
                # Clamp To Image Bounds
                h, w = full_img.shape[:2]
                top = max(0, min(top, h - 1))
                bottom = max(top + 1, min(bottom, h))
                left = max(0, min(left, w - 1))
                right = max(left + 1, min(right, w))
                crop = full_img[top:bottom, left:right]
                if crop.size == 0:
                    continue

                cv2.imwrite(os.path.join(BASE_PATH, f"debug_{name}.png"), crop)
                saved.append(name)
        except Exception as e:
            self.set_status(f"Error saving region screenshots: {e}")
            return

        self.set_status(f"Saved debug screenshots ({', '.join(saved)})")
    # Eyedropper
    def start_eyedropper(self, color_key=None):
        """Open the color picker overlay.
        color_key (optional): settings field name to write the result into
        (e.g. 'fish_color', 'shake_color'). The main UI is also notified via
        onColorPicked / setPickedColor and by updating matching input elements.
        """
        if not hasattr(self, "eyedropper") or self.eyedropper is None:
            self.eyedropper = Eyedropper(self)
        # Toggle Off If Already Open
        if self.eyedropper.is_open():
            self.eyedropper.hide()
            return None

        self.eyedropper.show(color_key=color_key)
        return None

    def get_last_picked_color(self):
        """Return (and clear) the most recently picked eyedropper color.
        The main UI can poll this after start_eyedropper if it does not
        implement onColorPicked / setPickedColor callbacks."""
        if not hasattr(self, "eyedropper") or self.eyedropper is None:
            return None

        color = self.eyedropper.last_picked_color
        self.eyedropper.last_picked_color = None
        return color

    # Hotkeys
    def _get_hotkeys(self):
        try:
            start_key = self.normalize_key(str(self.vars["start_key"]))
            areas_key = self.normalize_key(str(self.vars["area_selector_key"]))
            stop_key = self.normalize_key(str(self.vars["stop_key"]))
        except Exception as e:
            self.set_status(f"Get hotkeys failed: {e}")
            start_key = "f5"
            areas_key = "f6"
            stop_key = "f7"
        return start_key, areas_key, stop_key

    def normalize_key(self, key):
        try:
            return key.char.lower()  # Letter Keys

        except AttributeError:
            return str(key).replace("Key.", "").replace(" ", "").lower()

    def on_key_press(self, key):
        key = self.normalize_key(key)
        start_key, area_selector_key, stop_key = self._get_hotkeys()
        automation_mode = self.vars["automation_mode"]
        if not automation_mode == "disabled":
            if key == start_key:
                window.hide()
                if self.macro_running == True:
                    return

                else:
                    # Set Flag Before Starting Threads To Avoid Race Where
                    # The Capture Thread Starts, Sees Macro_Runningfalse, And Exits Immediately.
                    self.macro_running = True
                    # Save Current Settings To Config Before Starting
                    self.save_settings(self.current_config, self.vars)
                    if automation_mode == "fishing":
                        self.macro_thread = threading.Thread(target=self.start_fishing, daemon=True)
                    elif automation_mode == "appraisal":
                        self.macro_thread = threading.Thread(target=self.start_appraisal, daemon=True)
                    elif automation_mode == "enchant":
                        self.macro_thread = threading.Thread(target=self.start_enchantment, daemon=True)
                    elif automation_mode == "angler":
                        self.macro_thread = threading.Thread(target=self.start_angler, daemon=True)
                    elif automation_mode == "treasure_appraisal":
                        self.macro_thread = threading.Thread(target=self.start_treasure_appraisal, daemon=True)
                    self.macro_thread.start()
                    if dxcam is not None:
                        self.camera = dxcam.create(output_color="BGR")
                        self.camera.start()
                    else:
                        if sys.platform == "darwin":
                            self.capture_thread = threading.Thread(target=self.capture_loop_quartz, daemon=True)
                        else:
                            self.capture_thread = threading.Thread(target=self.capture_loop_mss, daemon=True)
                        self.capture_thread.start()
            elif key == area_selector_key:
                # Guard To Prevent Area Selector From Being Opened The Second The Macro Started
                if self.macro_running == True:
                    return

                self.open_area_selector()
            elif key == stop_key:
                window.show()
                self.stop_macro()
        else:
            self.save_settings(self.current_config, self.vars, f"Pressed: {key}")
            start_key, area_selector_key, stop_key = self._get_hotkeys()
            self.status_overlay.set_line(1, "Start Key: ", start_key.upper())
            self.status_overlay.set_line(2, "Area Selector Key: ", area_selector_key.upper())
            self.status_overlay.set_line(3, "Stop Key: ", stop_key.upper())
    def _string_to_key(self, key_string):
        key_string = key_string.strip().lower()
        # Try Special Keys
        if hasattr(Key, key_string):
            return getattr(Key, key_string)

        # Fallback To Character
        return key_string

    # Keyboard/Mouse Functions (Platformspecific)
    # Hold Mouse
    def hold_mouse(self, mouse=False):
        "Hold mouse. True for right click, False for left click."
        if self.macro_running == False:
            return

        if sys.platform == "win32":
            if mouse:
                windll.mouse_event(MOUSEEVENTF_RIGHTDOWN, 0, 0, 0, 0)
            else:
                windll.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
        elif sys.platform == "darwin":
            _mouse_event(button="right" if mouse else "left", press=True)
        else:
            # Linux  Now Uses The Unified X11 Implementation
            _mouse_event(button="right" if mouse else "left", press=True)
    # Release Mouse
    def release_mouse(self, mouse=False):
        "Release mouse. True for right click, False for left click."
        if self.macro_running == False:
            return

        if sys.platform == "win32":
            if mouse:
                windll.mouse_event(MOUSEEVENTF_RIGHTUP, 0, 0, 0, 0)
            else:
                windll.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
        elif sys.platform == "darwin":
            _mouse_event(button="right" if mouse else "left", press=False)
        else:
            # Linux - Now Uses The Unified X11 Implementation
            _mouse_event(button="right" if mouse else "left", press=False)
    # Click At
    def _click_at(self, x, y, click_count=1):
        if self.macro_running == False:
            return

        if x is None or y is None:
            return

        # Convert Coordinates If Needed (Retina Scaling)
        if sys.platform == "darwin":
            scale = get_scale_factor()
            x = int(x / scale)
            y = int(y / scale)
        # Seperate Branches For Windows And macOS Mouse Events
        if sys.platform == "win32":
            windll.SetCursorPos(x, y)
            windll.mouse_event(MOUSEEVENTF_MOVE, 0, 1, 0, 0)
            for i in range(click_count):
                windll.mouse_event(MOUSEEVENTF_LEFTDOWN, 0, 0, 0, 0)
                windll.mouse_event(MOUSEEVENTF_LEFTUP, 0, 0, 0, 0)
                if i < click_count - 1:
                    time.sleep(0.03)
        else:
            _move_mouse(x, y)
            _move_mouse(x + 5, y + 5)
            _move_mouse(x, y)
            for i in range(click_count):
                _mouse_event(button="left", press=True)   # mouse down
                _mouse_event(button="left", press=False)  # mouse up
                if i < click_count - 1:
                    time.sleep(0.03)
    # Keyboard
    def _send_key(self, key2, delay=0.05, click_type=0):
        """
        Send a keyboard event.
        delay: Delay between send and release
        click_type:
            0 = click (press + release)   [default]
            1 = hold (press only)
            2 = release (release only)
        """
        if self.macro_running == False:
            return

        key = str(key2)
        if sys.platform == "darwin":
            send_key(key2, delay=delay, click_type=click_type)
        else:
            # Convert Special Key Names
            special_keys = {
                "enter": Key.enter,
                "return": Key.enter,
                "tab": Key.tab,
                "space": Key.space,
                "esc": Key.esc,
                "escape": Key.esc,
                "backspace": Key.backspace,
                "delete": Key.delete,
                "up": Key.up,
                "down": Key.down,
                "left": Key.left,
                "right": Key.right,
            }
            key = special_keys.get(key.lower(), key)
            try:
                if click_type == 0:
                    keyboard_controller.press(key)
                    time.sleep(delay)
                    keyboard_controller.release(key)
                elif click_type == 1:
                    keyboard_controller.press(key)
                elif click_type == 2:
                    keyboard_controller.release(key)
            except Exception as e:
                print("Error sending keys:", e)
    # Interruptible Sleep
    def interruptible_sleep(self, duration):
        duration = max(0.01, duration)
        end_time = time.perf_counter() + duration
        while True:
            if not self.macro_running:
                break  # Interrupted

            remaining = end_time - time.perf_counter()
            if remaining <= 0:
                break

            # Sleep For At Most 10Ms Or Whatever Fraction Of Remaining Time Is Left
            time.sleep(min(0.01, remaining))
    # Get Values
    def get_areas(self, area_key):
        """Apply scale factor.  All area values (saved or default) are ratios 0–1.
        Returning physical pixels here.  The previous default path returned
        Already pixel coordinates and then multiplied by screen_* again,
        Producing enormous sizes (fullscreen overlay after reset_areas)."""
        scale = get_scale_factor()
        area_data = self.bar_areas.get(area_key)
        if (isinstance(area_data, dict) and area_data.get("width", 0) > 0 and area_data.get("height", 0) > 0):
            left   = float(area_data["x"])
            top    = float(area_data["y"])
            right  = left + float(area_data["width"])
            bottom = top + float(area_data["height"])
            width  = float(area_data["width"])
            height = float(area_data["height"])
        else:
            left, top, right, bottom = self._get_default_areas(area_key)
            width  = right - left
            height = bottom - top
        left2   = int(left * scale * self.SCREEN_WIDTH)
        top2    = int(top * scale * self.SCREEN_HEIGHT)
        right2  = int(right * scale * self.SCREEN_WIDTH)
        bottom2 = int(bottom * scale * self.SCREEN_HEIGHT)
        width2  = int(width * scale * self.SCREEN_WIDTH)
        height2 = int(height * scale * self.SCREEN_HEIGHT)
        return left2, top2, right2, bottom2, width2, height2

    def _get_default_areas(self, area):
        """Return (left, top, right, bottom) as ratios 0-1 from AREA_CONFIG defaults.
        Must stay in ratio space so get_areas can apply scale * SCREEN_* once."""
        cfg = AREA_CONFIG.get(area)
        if cfg:
            d = cfg["default"]
            left   = float(d["x"])
            top    = float(d["y"])
            right  = left + float(d["width"])
            bottom = top + float(d["height"])
        else:
            left, top, right, bottom = 0.0, 0.0, 1.0, 1.0
        return left, top, right, bottom

    def _get_var_number(self, key, default, cast=float):
        """Returns a key from the GUI with Exception handling"""
        try:
            value = self.vars.get(key)
            if value is None:
                # Compatibility Mapping For 1600Plus Key Differences
                if key == "perfect_cast_timing_1600_plus":
                    value = self.vars.get("perfect_cast_timing_1600plus")
                if value is None:
                    return default

            if isinstance(value, str):
                value = value.strip()
                if value == "":
                    return default

            return cast(value)

        except Exception:
            return default

    # Detection
    def _hex_to_bgr(self, hex_color):
        "Convert hex color to BGR tuple for OpenCV."
        if hex_color is None or hex_color.lower() in ["none", "# None", ""]:
            return None

        hex_color = hex_color.lstrip('# ')
        if len(hex_color) == 6:
            try:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return (b, g, r)  # Bgr Format For Opencv

            except ValueError:
                return None

        return None

    def capture_single_frame(self):
        """
        Capture a single full-screen frame without touching self.macro_running.
        Used by debug screenshots, eyedropper freeze, and Discord screenshot logging.
        """
        if sys.platform == "darwin":
            image = Quartz.CGWindowListCreateImage(
                Quartz.CGRectInfinite,
                Quartz.kCGWindowListOptionOnScreenOnly,
                Quartz.kCGNullWindowID,
                Quartz.kCGWindowImageDefault
            )
            if image is None:
                return None

            return cgimage_to_srgb_numpy(image)

        else:
            scale = get_scale_factor()
            with MSS() as sct:
                monitor = {
                    "top": 0,
                    "left": 0,
                    "width": int(SCREEN_WIDTH * scale),
                    "height": int(SCREEN_HEIGHT * scale),
                }
                return np.asarray(sct.grab(monitor))[:, :, :3]

    def capture_loop_mss(self):
        """Continuous capture loop for the macro (Windows fallback). Assumes self.macro_running is already True."""
        if not self.macro_running:
            return

        self.capture_id = 0
        scale = get_scale_factor()
        with MSS() as sct:
            monitor = {
                "top": 0,
                "left": 0,
                "width": int(SCREEN_WIDTH * scale),
                "height": int(SCREEN_HEIGHT * scale),
            }
            while self.macro_running:
                self.capture_frame = np.asarray(sct.grab(monitor))[:, :, :3]
                self.capture_id += 1
                time.sleep(self.scan_delay)
    def capture_loop_quartz(self):
        """Continuous capture loop for the macro (macOS fallback). Assumes self.macro_running is already True."""
        if not self.macro_running:
            return

        self.capture_id = 0
        while self.macro_running:
            if sys.platform == "darwin":
                image = Quartz.CGWindowListCreateImage(
                    Quartz.CGRectInfinite,
                    Quartz.kCGWindowListOptionOnScreenOnly,
                    Quartz.kCGNullWindowID,
                    Quartz.kCGWindowImageDefault
                )
            else:
                image = None
            if image is None:
                time.sleep(0.01)
                continue

            frame = cgimage_to_srgb_numpy(image)
            if frame is None:
                time.sleep(0.01)
                continue

            self.capture_frame = frame
            self.capture_id += 1
            time.sleep(self.scan_delay)

    def process_image_for_ocr(self, img):
        # Convert To Grayscale
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        # Upscale
        gray = cv2.resize(gray,None,fx=3,fy=3,interpolation=cv2.INTER_CUBIC)
        # Adaptive Threshold Works Better With Different Text Colors
        binary = cv2.adaptiveThreshold(gray,255,cv2.ADAPTIVE_THRESH_GAUSSIAN_C,cv2.THRESH_BINARY,31,8)
        return binary

    def extract_number_from_text(self, text):
        """
        Extracts numeric value from OCR text, handling common issues.
        Returns None if no valid number is found.
        """
        # Clean Up Common OCR Artifacts
        cleaned = text.strip()
        # Replace Common OCR Mistakes (O > 0, L > 1, Etc.)
        cleaned = cleaned.replace('O', '0').replace('o', '0')
        cleaned = cleaned.replace('l', '1').replace('I', '1')
        # Find Number With Optional Decimal
        # This Pattern Handles: 0.5, .5, 100, 100.0, Etc.
        match = re.search(r'(\d+\.?\d*|\.\d+)', cleaned)
        if match:
            try:
                return float(match.group(1))

            except ValueError:
                return None

        return None
    
    def pixel_search(self, frame, hex, tolerance, mode=0):
        """
        Searches for the first or last pixel based on mode.
        Mode 0: First pixel; Mode 1: Last pixel
        """
        if frame is None or frame.size == 0:
            return None, None

        if mode not in (0, 1):
            raise RuntimeError("Invalid detection mode")

        # Convert Tolerance To Int First, Handling String Inputs
        try:
            tolerance = int(tolerance)
        except (ValueError, TypeError):
            tolerance = 0  # or some default value
        # Failsafe: None Hex
        if hex is None:
            return None, None
        
        try:
            tolerance = int(np.clip(tolerance, 0, 255))
            b, g, r = self._hex_to_bgr(hex)
            target = np.array([b, g, r], dtype=np.int32)
            frame_i = frame.astype(np.int32)
            diff = frame_i - target
            mask = np.sqrt(np.sum(diff ** 2, axis=-1)) <= tolerance
            coords = np.argwhere(mask)
            if coords.size > 0:
                if mode == 0:
                    y, x = coords[0]
                else:
                    y, x = coords[-1]
                return int(x), int(y)
        except:
            return None, None

        return None, None

    def find_color_cluster(self, frame, target_color_hex, tolerance=8, min_area=10):
        """
        Find the largest color cluster and return its center.
        Args:
            frame: BGR image
            target_color_hex: hex color string
            tolerance: color tolerance
            min_area: minimum cluster size to be valid
        Returns:
            (center_x, center_y) or None
        """
        # Required_Fish_Pixels
        if frame is None:
            return None, None

        # Color Mask (Vectorized Like Your Fast Version)
        target_bgr = np.array(self._hex_to_bgr(target_color_hex), dtype=np.int16)
        frame_int = frame.astype(np.int16)
        tol = int(np.clip(tolerance, 0, 255))
        mask = np.all(np.abs(frame_int - target_bgr) <= tol, axis=2).astype(np.uint8)
        if not np.any(mask):
            return None, None

        # Connected Components (Cluster Detection)
        num_labels, labels, stats, centroids = cv2.connectedComponentsWithStats(mask, connectivity=8)
        if num_labels <= 1:
            return None, None  # Only Background

        # Skip Label 0 (Background)
        largest_label = None
        largest_area = 0
        for label in range(1, num_labels):
            area = stats[label, cv2.CC_STAT_AREA]
            if area > largest_area and area >= min_area:
                largest_area = area
                largest_label = label
        if largest_label is None:
            return None, None

        # Centroid
        center_x, center_y = centroids[largest_label]
        return int(center_x), int(center_y)

    def _find_circles(self, frame):
        """
        Detect circles in frame using strict Hough Circle Transform for perfect circles only.
        Specifically optimized for SHAKE button detection with strict filtering.
        Returns (center_x, center_y) of the best circle found, or None if no circles.
        Args:
            frame: BGR image from dxcam/mss
        """
        try:
            # Convert Bgr To Grayscale
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Scale Circle Detection Parameters Based On Resolution
            # Reference Values Are For 2560X1440 Resolution
            # Use Average Of Scale_X_1440 And Scale_Y_1440 For Uniform Circle Scaling
            scale_factor = (self.scale_x_1440 + self.scale_y_1440) / 2
            # Scale Parameters Proportionally To Resolution
            scaled_min_dist = int(150 * scale_factor)
            scaled_min_radius = int(50 * scale_factor)
            scaled_max_radius = int(300 * scale_factor)
            scaled_good_min_radius = int(50 * scale_factor)
            scaled_good_max_radius = int(120 * scale_factor)
            # Hough Circle Transform With Strict Parameters For Perfect Circles Only
            circles = cv2.HoughCircles(
                gray,
                cv2.HOUGH_GRADIENT,
                dp=1, # Inverse ratio of accumulator resolution
                minDist=scaled_min_dist,  # Increased distance between circles to avoid overlapping detections
                param1=100,   # Higher Canny threshold for edge detection
                param2=100,   # Much higher accumulator threshold - only perfect circles
                minRadius=scaled_min_radius, # Larger minimum radius to ignore small false positives
                maxRadius=scaled_max_radius   # Maximum circle radius
            )
            if circles is not None:
                circles = np.round(circles[0, :]).astype("int")
                # Additional Filtering: Only Accept Circles With Good Radius Range For Shake Buttons
                good_circles = []
                for (x, y, r) in circles:
                    # Shake Buttons Are Typically 50120 Pixels Radius (Scaled)
                    if scaled_good_min_radius <= r <= scaled_good_max_radius:
                        good_circles.append((x, y, r))
                if good_circles:
                    # Return The Largest Good Circle (Most Likely To Be Shake Button)
                    largest_circle = max(good_circles, key=lambda c: c[2])
                    x, y, r = largest_circle
                    # print(f"    🔍 Circle detected at local ({x}, {y}) with radius {r} (scale: {scale_factor:.3f})")
                    return int(x), int(y)

            # Only Use Strict Houghcircles Detection - No Backup Methods To Avoid False Positives
            return None, None

        except Exception as e:
            self.set_status(f"    Error in circle detection: {e}")
            return None, None

    def _find_all_circles(self, frame):
        """
        Detect all circles in frame.
        Returns:
            [(x1, y1), (x2, y2), ...]
            or [] if no valid circles found.
        All returned circles must have similar radii to reduce false positives.
        """
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            scale_factor = (self.scale_x_1440 + self.scale_y_1440) / 2
            scaled_min_dist = int(150 * scale_factor)
            scaled_min_radius = int(50 * scale_factor)
            scaled_max_radius = int(300 * scale_factor)
            scaled_good_min_radius = int(50 * scale_factor)
            scaled_good_max_radius = int(120 * scale_factor)
            circles = cv2.HoughCircles(
                gray,
                cv2.HOUGH_GRADIENT,
                dp=1,
                minDist=scaled_min_dist,
                param1=100,
                param2=100,
                minRadius=scaled_min_radius,
                maxRadius=scaled_max_radius
            )
            if circles is None:
                return []

            circles = np.round(circles[0, :]).astype("int")
            # First Radius Filter
            good_circles = [
                (x, y, r)
                for (x, y, r) in circles
                if scaled_good_min_radius <= r <= scaled_good_max_radius
            ]
            if not good_circles:
                return []

            # Require Similar Sizes
            radii = [r for _, _, r in good_circles]
            median_radius = np.median(radii)
            # Allow ±15% Size Difference
            tolerance = median_radius * 0.15
            similar_circles = [
                (x, y)
                for (x, y, r) in good_circles
                if abs(r - median_radius) <= tolerance
            ]
            return similar_circles

        except Exception as e:
            self.set_status(f"    Error in circle detection: {e}")
            return []

    def _detect_lines_in_frame(self, frame, original_width=None):
        """
        Detect vertical lines in frame using Laplacian edge detection.
        Based on b.py line detection pipeline with brightness and density filtering.
        NLM denoising removed for 10x speedup (30 FPS -> 300 FPS).
        Frame is normalized to reference fish box dimensions (1035x43 at 2560x1440)
        for consistent detection across all resolutions. line coordinates are scaled
        back to match the original frame dimensions.
        Returns list of x-coordinates of detected vertical lines.
        Args:
            frame: BGR image from dxcam/mss
            original_width: Original frame width before normalization (for coordinate scaling back)
        """
        try:
            # Get Minimum Line Density From Settings (Configurable Via GUI)
            MIN_LINE_DENSITY = float(self._get_var_number("fish_line_min_density", 0.8))
            BRIGHTNESS_THRESHOLD = 10  # Minimum brightness for edge pixels
            # Reference Fish Box Dimensions At 1280X720 (Lower Detail For Better Edge Detection)
            # At 1280X720: Fish Box Is 762*(1280/2560) To 1797*(1280/2560)  381 To 898 (Width517)
            # Height: 1215*(720/1440) To 1258*(720/1440)  607 To 629 (Height22)
            REFERENCE_FISH_WIDTH = 517   # Fish box width at 720p
            REFERENCE_FISH_HEIGHT = 22   # Fish box height at 720p
            # Store Original Dimensions For Coordinate Scaling
            original_height, original_frame_width = frame.shape[:2]
            if original_width is None:
                original_width = original_frame_width
            # Normalize Frame To Reference Dimensions For Consistent Detection
            if original_frame_width != REFERENCE_FISH_WIDTH or original_height != REFERENCE_FISH_HEIGHT:
                frame = cv2.resize(frame, (REFERENCE_FISH_WIDTH, REFERENCE_FISH_HEIGHT), interpolation=cv2.INTER_LINEAR)
                width_scale = original_width / REFERENCE_FISH_WIDTH
            else:
                width_scale = 1.0
            # Step 1: Convert To Grayscale
            grayscale = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            # Step 2: Laplacian Edge Detection (Nlm Removed For 10X Speedup)
            laplacian = cv2.Laplacian(grayscale, cv2.CV_8U)
            # Step 3: Filter Vertical Lines By Brightness Threshold And Density
            height, width = laplacian.shape
            # Vectorized Column Density Calculation (10X Faster Than Python Loop)
            column_densities = np.sum(laplacian > BRIGHTNESS_THRESHOLD, axis=0) / height
            line_coords = np.where(column_densities >= MIN_LINE_DENSITY)[0].tolist()
            # Merge Adjacent Lines (Consecutive Xcoordinates) Into Single Lines
            # Takes The Middle Position Of Each Group Of Adjacent Pixels
            # Lines Must Be Within 2 Pixels To Be Considered Part Of The Same Group
            if line_coords:
                merged_lines = []
                group_start = line_coords[0]
                group_end = line_coords[0]
                for i in range(1, len(line_coords)):
                    if line_coords[i] <= group_end + 2:
                        # Within 2 Pixels, Extend Current Group
                        group_end = line_coords[i]
                    else:
                        # Gap > 2 Pixels Detected, Save Current Group'S Middle Position
                        middle = (group_start + group_end) // 2
                        merged_lines.append(middle)
                        # Start New Group
                        group_start = line_coords[i]
                        group_end = line_coords[i]
                # Don'T Forget The Last Group
                middle = (group_start + group_end) // 2
                merged_lines.append(middle)
                line_coords = merged_lines
            # Scale Line Coordinates Back To Original Frame Dimensions
            if width_scale != 1.0:
                line_coords = [int(x * width_scale) for x in line_coords]
            # Sort Coordinates For Consistent Processing
            line_coords.sort()
            return line_coords

        except Exception as e:
            # print(f"    Error in line detection: {e}")
            return []

    def _reset_noiseform_warn_state(self):
        """Reset NoiseWarnKind rolling baselines / rings. Call on init and minigame start."""
        self._noise_w_base = 0
        self._noise_w_base_ml = 0
        self._noise_w_dthr = 6
        self._noise_dk_ring = [-1] * 32
        self._noise_ml_ring = [-1] * 32
        self._noise_d6_ring = [-1] * 32
        self._noise_dk_idx = 0
        self._noise_dk_n = 0
        self._noise_w_gt = 0.0
        self._noise_w_now = ""
        self._noise_w_blk = 0
        self._noise_w_bn = 0
        self._noise_w_gr = 0
        self._noise_w_dk = 0
        self._noise_w_d6 = 0
        self._noise_w_ml = -1
        # NoiseGimmickTarget / NoiseZoneScanAll
        self._noise_z_wx = -1
        self._noise_z_gx = -1
        self._noise_z_kx = -1
        self._noise_z_ok = False
        self._noise_z_prev_ok = False
        self._noise_z_scan_t = 0.0
        self._noise_z_fresh_t = 0.0
        self._noise_pend_kind = ""
        self._noise_pend_t = 0.0
        self._noise_zone_tgt = -1
        self._noise_zone_t = 0.0
        self._noise_zone_kind = ""
        self._noise_z_bd = 0
        self._noise_z_bb = 0
        self._noise_z_bl = 0
        self._noise_z_bg = 0

    def detect_noiseform_color(self, img):
        """Classify the Noiseform warning flash: WHITE / GREEN / BLACK / "".

        Port of DeepFish ALPHA v1.4 NoiseWarnKind(). `img` is the Noiseform Box
        crop from capture_frame (BGR). Geometry is computed in screen pixels
        (center at 50% x, 51.94% y) then mapped into this crop, matching AHK's
        WindowWidth/Height minus FishBarLeft/NoteTop mapping.
        """
        if img is None or img.size == 0 or img.ndim < 2:
            return ""
        h, w = img.shape[:2]
        if h < 80 or w < 100:
            return ""

        try:
            noiseform_left, noiseform_top, _, _, _, _ = self.get_areas("noiseform")
        except Exception:
            noiseform_left, noiseform_top = 0, 0

        screen_w = max(1, int(getattr(self, "SCREEN_WIDTH", SCREEN_WIDTH) or SCREEN_WIDTH))
        screen_h = max(1, int(getattr(self, "SCREEN_HEIGHT", SCREEN_HEIGHT) or SCREEN_HEIGHT))

        # AHK: wcx := Round((WindowWidth * 0.500) - FishBarLeft)
        wcx = int(round((screen_w * 0.500) - noiseform_left))
        wcy = int(round((screen_h * 0.5194) - noiseform_top))
        whw = int(round(screen_w * 0.082))
        wskip = int(round(screen_w * 0.023))
        whh = int(round(screen_h * 0.052))

        wx0 = max(0, wcx - whw)
        wx1 = min(w - 1, wcx + whw)
        wy0 = max(0, wcy - whh)
        wy1 = min(h - 1, wcy + whh)
        if wx1 - wx0 < 24 or wy1 - wy0 < 24:
            return ""

        # Adaptive dark threshold from rolling mean-luminance baseline.
        # NoiseWML is mean(vl)*100 (0–25500). dthr = clamp(round(base_ml*45/10000), 6, 60).
        base_ml = int(getattr(self, "_noise_w_base_ml", 0) or 0)
        if base_ml >= 200:
            dthr = int(round((base_ml * 45) / 10000.0))
            dthr = max(6, min(60, dthr))
        else:
            dthr = 6
        self._noise_w_dthr = dthr

        ys = np.arange(wy0, wy1 + 1, 9)
        xs = np.arange(wx0, wx1 + 1, 9)
        # Skip the vertical band around screen-center (AHK wskip).
        xs = xs[np.abs(xs - wcx) > wskip]
        if ys.size == 0 or xs.size == 0:
            return ""

        sample = img[np.ix_(ys, xs)]
        if sample.size == 0:
            return ""

        bgr = sample.astype(np.int16)
        b = bgr[..., 0]
        g = bgr[..., 1]
        r = bgr[..., 2]
        brightness = (r + g + b) // 3
        wn = int(brightness.size)
        if wn < 30:
            return ""

        white = (
            (brightness > 120)
            & (np.abs(r - g) < 40)
            & (np.abs(g - b) < 40)
        )
        # AHK: white else-if green (mutually exclusive).
        green = (
            (~white)
            & (g > r + 40)
            & (g > b + 30)
            & (g > 90)
        )
        dark = brightness < 28
        dark6 = brightness < dthr

        wbn = int(np.count_nonzero(white))
        wgr = int(np.count_nonzero(green))
        wdk = int(np.count_nonzero(dark))
        wd6 = int(np.count_nonzero(dark6))
        wls = int(np.sum(brightness, dtype=np.int64))

        # Integer percents, same as AHK `(count * 100) // wn`.
        noise_w_bn = (wbn * 100) // wn
        noise_w_gr = (wgr * 100) // wn
        noise_w_dk = (wdk * 100) // wn
        noise_w_d6 = (wd6 * 100) // wn
        noise_w_ml = (wls * 100) // wn
        self._noise_w_bn = noise_w_bn
        self._noise_w_gr = noise_w_gr
        self._noise_w_dk = noise_w_dk
        self._noise_w_d6 = noise_w_d6
        self._noise_w_ml = noise_w_ml

        now = time.perf_counter()
        if noise_w_bn > 35:
            self._noise_w_now = "WHITE"
            self._noise_w_gt = now
            return "WHITE"
        if noise_w_gr > 35:
            self._noise_w_now = "GREEN"
            self._noise_w_gt = now
            return "GREEN"

        # Rolling 32-sample rings used only for BLACK (sudden darken after a flash).
        dk_idx = int(getattr(self, "_noise_dk_idx", 0) or 0)
        dk_n = int(getattr(self, "_noise_dk_n", 0) or 0)
        self._noise_dk_ring[dk_idx] = noise_w_dk
        self._noise_ml_ring[dk_idx] = noise_w_ml
        self._noise_d6_ring[dk_idx] = noise_w_d6
        dk_idx = (dk_idx + 1) % 32
        if dk_n < 32:
            dk_n += 1
        self._noise_dk_idx = dk_idx
        self._noise_dk_n = dk_n

        past_min = 999
        past_max_l = -1
        if dk_n >= 12:
            for kk in range(3, 10):
                pri = (dk_idx - kk + 64) % 32
                pv = self._noise_d6_ring[pri]
                if pv >= 0 and pv < past_min:
                    past_min = pv
                pm = self._noise_ml_ring[pri]
                if pm > past_max_l:
                    past_max_l = pm

        gap_t = 9.0
        last_flash = float(getattr(self, "_noise_w_gt", 0.0) or 0.0)
        if last_flash > 0:
            gap_t = now - last_flash

        blk_hit = False
        if past_min < 999 and past_max_l > 0:
            if (noise_w_ml * 100) <= (past_max_l * 70) and (noise_w_d6 - past_min) >= 8:
                blk_hit = True

        if gap_t >= 1.60 and blk_hit:
            self._noise_w_now = "BLACK"
            self._noise_w_blk = int(getattr(self, "_noise_w_blk", 0) or 0) + 1
            return "BLACK"

        self._noise_w_now = ""
        if self._noise_w_base < 1:
            self._noise_w_base = noise_w_dk
        else:
            self._noise_w_base = ((self._noise_w_base * 24) + noise_w_dk) // 25
        if self._noise_w_base_ml < 1:
            self._noise_w_base_ml = noise_w_ml
        else:
            self._noise_w_base_ml = ((self._noise_w_base_ml * 24) + noise_w_ml) // 25
        return ""

    def scan_noiseform_zones(self, fish_img):
        """Locate WHITE / GREEN / BLACK segments on the fish-bar strip.

        Port of DeepFish ALPHA v1.4 NoiseZoneScanAll(). `fish_img` is the Fish
        Box crop (BGR), the same strip AHK keeps in pCaptureBits.

        Returns True only when all three zones are found this pass. Zone X
        values are stored on self as bar-relative pixels (0 = fish_left).
        """
        self._noise_z_wx = -1
        self._noise_z_gx = -1
        self._noise_z_kx = -1
        self._noise_z_bd = 0
        self._noise_z_bb = 0
        self._noise_z_bl = 0
        self._noise_z_bg = 0
        if fish_img is None or fish_img.size == 0 or fish_img.ndim < 2:
            return False
        h, w = fish_img.shape[:2]
        if w < 200 or h < 14:
            return False
        zw = int(round(w * 0.12))
        if zw < 24:
            return False

        rows = np.arange(3, h - 3, 5)
        if rows.size < 3:
            return False
        strip = fish_img[rows]
        b = strip[..., 0].astype(np.int32)
        g = strip[..., 1].astype(np.int32)
        r = strip[..., 2].astype(np.int32)
        zl = (r + g + b) // 3
        zm = np.maximum(r, b)
        c_l = zl.sum(axis=0, dtype=np.int64)
        c_g = (g - zm).sum(axis=0, dtype=np.int64)
        c_b = (zl > 140).sum(axis=0, dtype=np.int64)
        c_d = np.zeros(w, dtype=np.int64)
        c_d[1:] = np.abs(zl[:, 1:] - zl[:, :-1]).sum(axis=0, dtype=np.int64)

        nrow = int(rows.size)
        tot = zw * nrow
        if tot < 1:
            return False

        # Prefix sums so each 12%-wide window is O(1), same a += 16 walk as AHK.
        p_l = np.concatenate(([0], np.cumsum(c_l, dtype=np.int64)))
        p_g = np.concatenate(([0], np.cumsum(c_g, dtype=np.int64)))
        p_d = np.concatenate(([0], np.cumsum(c_d, dtype=np.int64)))
        p_b = np.concatenate(([0], np.cumsum(c_b, dtype=np.int64)))

        r_wa = r_ga = r_ka = -1
        r_wn = r_gn = r_kn = 0
        b_wa = b_ga = b_ka = -1
        b_wn = b_gn = b_kn = 0

        a = 0
        while a + zw <= w:
            s_l = int(p_l[a + zw] - p_l[a])
            s_g = int(p_g[a + zw] - p_g[a])
            s_d = int(p_d[a + zw] - p_d[a])
            s_b = int(p_b[a + zw] - p_b[a])
            m_l = s_l // tot
            m_g = s_g // tot
            m_d = s_d // tot
            m_b = (s_b * 100) // tot
            if m_d > self._noise_z_bd:
                self._noise_z_bd = m_d
                self._noise_z_bl = m_l
                self._noise_z_bg = m_g
            if m_l < 60 and m_b > self._noise_z_bb:
                self._noise_z_bb = m_b
            is_w = (m_d >= 8 and m_l > 110 and m_g < 45)
            is_g = (m_d >= 8 and m_l > 40 and m_l < 115 and m_g > 45)
            is_k = (m_l < 60 and m_b >= 3 and m_d >= 2 and not is_w and not is_g)
            if is_w:
                if r_wa < 0:
                    r_wa = a
                r_wn += 1
                if r_wn > b_wn:
                    b_wn = r_wn
                    b_wa = r_wa
            else:
                r_wa = -1
                r_wn = 0
            if is_g:
                if r_ga < 0:
                    r_ga = a
                r_gn += 1
                if r_gn > b_gn:
                    b_gn = r_gn
                    b_ga = r_ga
            else:
                r_ga = -1
                r_gn = 0
            if is_k:
                if r_ka < 0:
                    r_ka = a
                r_kn += 1
                if r_kn > b_kn:
                    b_kn = r_kn
                    b_ka = r_ka
            else:
                r_ka = -1
                r_kn = 0
            a += 16

        # Center of the longest run. AHK adds FishBarLeft; we stay bar-relative
        # so the value can be assigned to fish_x the same way notes use note_x.
        half = zw // 2
        if b_wn > 0:
            self._noise_z_wx = int(round(b_wa + (((b_wn - 1) * 16) // 2) + half))
        if b_gn > 0:
            self._noise_z_gx = int(round(b_ga + (((b_gn - 1) * 16) // 2) + half))
        if b_kn > 0:
            self._noise_z_kx = int(round(b_ka + (((b_kn - 1) * 16) // 2) + half))

        if self._noise_z_kx >= 0 and self._noise_z_wx >= 0 and abs(self._noise_z_kx - self._noise_z_wx) < zw:
            self._noise_z_kx = -1
        if self._noise_z_kx >= 0 and self._noise_z_gx >= 0 and abs(self._noise_z_kx - self._noise_z_gx) < zw:
            self._noise_z_kx = -1
        if self._noise_z_wx >= 0 and self._noise_z_gx >= 0 and abs(self._noise_z_wx - self._noise_z_gx) < zw:
            if b_wn >= b_gn:
                self._noise_z_gx = -1
            else:
                self._noise_z_wx = -1
        return self._noise_z_wx >= 0 and self._noise_z_gx >= 0 and self._noise_z_kx >= 0

    def detect_noiseform_target(self, noiseform_img, fish_img):
        """Pick the bar-relative X for the current Noiseform warning.

        Port of DeepFish ALPHA v1.4 NoiseGimmickTarget() / NoteTarget() for
        Noiseform. Calls detect_noiseform_color (warn flash) then
        scan_noiseform_zones (bar segments).

        Returns (kind, x) where kind is this frame's WHITE/GREEN/BLACK/"" and
        x is a locked zone coordinate or None (same role as note_x).
        """
        now = time.perf_counter()
        gk = self.detect_noiseform_color(noiseform_img)

        seq = self._noise_pend_t > 0 and (now - self._noise_pend_t) < 2.0
        if gk:
            if gk != "BLACK":
                self._noise_pend_kind = gk
                self._noise_pend_t = now
            elif self._noise_pend_kind == "" or self._noise_pend_kind == "BLACK" or not seq:
                self._noise_pend_kind = "BLACK"
                self._noise_pend_t = now

        pend = self._noise_pend_t > 0 and (now - self._noise_pend_t) < 2.20
        gint = 0.15 if (pend or self._noise_zone_tgt >= 0) else 1.00
        zlock = self._noise_z_fresh_t > 0 and (now - self._noise_z_fresh_t) < 0.60

        if self._noise_z_scan_t < 1 or (now - self._noise_z_scan_t) >= gint:
            self._noise_z_scan_t = now
            zp_w, zp_g, zp_k = self._noise_z_wx, self._noise_z_gx, self._noise_z_kx
            if self.scan_noiseform_zones(fish_img):
                self._noise_z_fresh_t = now
                if zlock:
                    self._noise_z_wx = zp_w
                    self._noise_z_gx = zp_g
                    self._noise_z_kx = zp_k
            else:
                self._noise_z_wx = zp_w
                self._noise_z_gx = zp_g
                self._noise_z_kx = zp_k

        self._noise_z_prev_ok = self._noise_z_ok
        self._noise_z_ok = self._noise_z_fresh_t > 0 and (now - self._noise_z_fresh_t) < 0.60

        if self._noise_zone_tgt >= 0:
            zage = now - self._noise_zone_t
            zgap = (now - self._noise_z_fresh_t) if self._noise_z_fresh_t > 0 else 99.0
            if zage < 1.85 and zgap < 1.00:
                return gk, self._noise_zone_tgt
            if zage < 4.00 and self._noise_z_ok:
                return gk, self._noise_zone_tgt
            self._noise_zone_tgt = -1
            self._noise_zone_kind = ""
            self._noise_pend_kind = ""
            self._noise_pend_t = 0.0

        if not pend or not self._noise_z_ok:
            return gk, None

        if self._noise_pend_kind == "WHITE":
            gz = self._noise_z_wx
        elif self._noise_pend_kind == "GREEN":
            gz = self._noise_z_gx
        elif self._noise_pend_kind == "BLACK":
            gz = self._noise_z_kx
        else:
            gz = -1
        if gz < 0:
            return gk, None

        self._noise_zone_tgt = gz
        self._noise_zone_t = now
        self._noise_zone_kind = self._noise_pend_kind
        self._noise_pend_t = 0.0
        return gk, gz

    def auto_crop_template(self, template, lower_white=200):
        """
        Crop padding from template using the same thresholding logic
        as your image_search function
        """
        # 1. Convert To Grayscale
        if len(template.shape) == 3:
            gray_temp = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        else:
            gray_temp = template
        # 2. Threshold To Find Only White/Bright Pixels (Same As Image_Search)
        _, thresh_temp = cv2.threshold(gray_temp, lower_white, 255, cv2.THRESH_BINARY)
        # 3. Find All White Pixels (The Actual Totem Content)
        coords = cv2.findNonZero(thresh_temp)
        # If No White Pixels Found, Return Original
        if coords is None:
            return template

        # 4. Get Bounding Box Of White Pixels
        x, y, w, h = cv2.boundingRect(coords)
        # 5. Crop The Original Template (Not The Thresholded Version)
        # To Preserve Color/Quality
        cropped = template[y:y+h, x:x+w]
        return cropped

    def image_search_totem(self, screenshot, template, lower_white=200, threshold=0.8):
        # 1. Resize Screenshot (Assuming Template Is Already Resized)
        screenshot_cropped = self.auto_crop_template(screenshot)
        template_height, template_width, _ = template.shape # template_height
        screenshot_resized = cv2.resize(screenshot_cropped, (template_width, template_height))
        # 2. Convert Screenshot & Template To Grayscale
        gray_screen = cv2.cvtColor(screenshot_resized, cv2.COLOR_BGR2GRAY)
        gray_temp = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        # 3. Threshold Both Images So Only White/Bright Pixels Remain (255) And Rest Is Black (0)
        _, thresh_screen = cv2.threshold(gray_screen, lower_white, 255, cv2.THRESH_BINARY)
        _, thresh_temp = cv2.threshold(gray_temp, lower_white, 255, cv2.THRESH_BINARY)
        # 4. Perform Template Matching On Binary Masks
        result = cv2.matchTemplate(thresh_screen, thresh_temp, cv2.TM_CCOEFF_NORMED)
        min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(result)
        if max_val >= threshold:
            return True, max_loc, max_val

        return False, None, max_val

    def image_search(self, screenshot, template, tolerance=2):
        # Convert to float for precise calculations
        screenshot_float = screenshot.astype(np.float32)
        template_float = template.astype(np.float32)

        # Match template
        result = cv2.matchTemplate(
            screenshot_float,
            template_float,
            cv2.TM_CCOEFF_NORMED
        )

        # Get the best match
        _, confidence, _, location = cv2.minMaxLoc(result)

        # Threshold can be adjusted
        threshold = 0.8

        if confidence >= threshold:
            x, y = location

            return int(x), int(y), float(confidence)

        return None, None, float(confidence)

    def _calculate_speed_and_predict(self, white_positions, timestamps):
        """
        Calculate white pixel movement speed using linear regression on recent
        positions for smooth, stable velocity estimation.
        Returns velocity /second (positive = moving down, negative = up),
        or None if insufficient data.
        """
        if len(white_positions) < 2:
            return None

        n = len(white_positions)
        y_values = [pos[1] for pos in white_positions]
        time_values = [t - timestamps[0] for t in timestamps]
        mean_t = sum(time_values) / n
        mean_y = sum(y_values) / n
        numerator = sum(t * y for t, y in zip(time_values, y_values)) - n * mean_t * mean_y
        denominator = sum(t * t for t in time_values) - n * mean_t * mean_t
        if abs(denominator) < 0.0001:
            return None

        return numerator / denominator

    # Utility Functions
    def test_logging(self):
        logging_mode = self.vars["logging_mode"].capitalize()
        self.send_logging(f"**{logging_mode} is working**", "Macro Stopped")
    def send_logging(self, text, loop_count, catch_rate=-1):
        logging_mode = self.vars["logging_mode"].lower()
        if logging_mode == "disabled":
            self.set_status("⚠ Logging is disabled.")
            return

        webhook_url = None
        if logging_mode != "file":
            webhook_url = self.vars["logging_url"].strip()
            if not webhook_url.startswith("https://discord.com/api/webhooks/"):
                self.set_status("Error: Invalid webhook URL.")
                return

        self.set_status("Sending log...")
        if logging_mode == "screenshot":
            thread = threading.Thread(
                target=self._discord_screenshot_worker,
                args=(webhook_url, f"{text}\n", loop_count, catch_rate),
                daemon=True
            )
        elif logging_mode == "file":
            thread = threading.Thread(
                target=self._debug_log_worker,
                args=(text, loop_count, catch_rate),
                daemon=True
            )
        else:
            thread = threading.Thread(
                target=self._discord_text_worker,
                args=(webhook_url, f"{text}\n", loop_count, catch_rate),
                daemon=True
            )
        thread.start()
        thread.join()  # Wait for Discord/file log to finish before continuing
    def _discord_text_worker(self, webhook_url, message_prefix, loop_count, catch_rate):
        """Worker function to send text webhook."""
        logging_name = self.vars["logging_name"]
        try:
            if catch_rate == -1:
                catch_rate = "N/A"
            payload = {
                'content': f'{message_prefix}🎣 Cycle Completed\n🔄 {loop_count}\nCatch rate: {catch_rate}\n🕐 {time.strftime("%Y-%m-%d %H:%M:%S")}',
                'username': logging_name,
                'embeds': [{
                    'description': f'{loop_count}',
                    'color': 0x5865F2,
                    'timestamp': time.strftime("%Y-%m-%dT%H:%M:%S")
                }]
            }
            response = requests.post(webhook_url, json=payload, timeout=10)
            if response.status_code == 200 or response.status_code == 204:
                self.set_status(f"Discord text sent ({loop_count})")
            else:
                self.set_status(f"Error: Discord text failed: {response.status_code}")
        except Exception as e:
            self.set_status(f"Error sending Discord text: {e}")
    def _discord_screenshot_worker(self, webhook_url, message_prefix, loop_count, catch_rate):
        logging_name = self.vars["logging_name"]
        try:
            screenshot = self.capture_single_frame()
            if screenshot is None:
                self.set_status("Error: failed to capture screenshot for Discord")
                return

            # Ensure Bgr For Imencode (MSS Already Bgr; Quartz Conversion Is Bgr)
            if screenshot.shape[2] == 4:
                screenshot = cv2.cvtColor(screenshot, cv2.COLOR_BGRA2BGR)
            _, buffer = cv2.imencode(".png", screenshot)
            img_byte_arr = io.BytesIO(buffer.tobytes())
            files = {'file': ('screenshot.png', img_byte_arr, 'image/png')}
            if catch_rate == -1:
                catch_rate = "N/A"
            payload = {
                'content': f'{message_prefix}🎣 **Cycle Completed**\n🔄 {loop_count}\n🎯 Catch rate: {catch_rate}\n🕐 {time.strftime("%Y-%m-%d %H:%M:%S")}',
                'username': logging_name
            }
            response = requests.post(webhook_url, data=payload, files=files, timeout=10)
            if response.status_code in (200, 204):
                self.set_status(f"Discord screenshot sent ({loop_count})")
            else:
                self.set_status(f"Error: Discord screenshot failed: {response.status_code}")
        except Exception as e:
            self.set_status(f"Error sending Discord screenshot: {e}")
    def _debug_log_worker(self, text, loop_count, catch_rate):
        """Write debug logs to a text file."""
        try:
            # Use Base Path For Logs
            log_dir = BASE_PATH
            os.makedirs(log_dir, exist_ok=True)
            # Daily Log File
            log_file = os.path.join(
                log_dir,
                f"debug_{time.strftime('%Y-%m-%d')}.txt"
            )
            timestamp = time.strftime("%Y-%m-%d %H:%M:%S")
            log_entry = (
                "==========\n"
                f"🎣 {text}\n"
                f"🔄 {loop_count}\n"
                f"🕐 {timestamp}\n"
                f"🎯 Catch rate: {catch_rate}\n"
                "==========\n\n"
            )
            with open(log_file, "a", encoding="utf-8") as f:
                f.write(log_entry)
            self.set_status(f"Debug log saved ({loop_count})")
        except Exception as e:
            self.set_status(f"Error writing debug log: {e}")
    def start_appraisal(self):
        # Validate Tesseract
        try:
            tesseract_path = get_tesseract_path( self.vars.get("tesseract_path") )
            if tesseract_path:
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                # Repair the imported config in memory
                self.vars["tesseract_path"] = tesseract_path
            else:
                raise RuntimeError("⚠️ Tesseract could not be found.")
            self.macro_running = True
        except Exception as e:
            time.sleep(0.2)
            full_error = traceback.format_exc()
            result = self.message_box_javascript(f"""An error occured during appraisal. 
            Please copy the error and report the bug:\\n{e}\\n
            Would you like to copy the full crash log to your clipboard?""", "askyesno")
            if result == True:
                if self.copy_to_clipboard(full_error):
                    self.message_box_javascript("Error copied over to clipboard")
                else:
                    self.message_box_javascript("Failed to copy error to clipboard")
            self.macro_running = False
            self.stop_macro(f"Appraisal error: {e}")
            return
        # Get Areas
        hotbar_left, hotbar_top, hotbar_right, hotbar_bottom, _, _ = self.get_areas("appraisal_hotbar")
        # Split Mutations (Sometimes It Contains , At The End)
        appraisal_mode = self.vars["appraisal_mode"].lower()
        appraisal_mutations = self.vars["appraisal_mutations"]
        appraisal_mutations_list = appraisal_mutations.split(",")
        # Delays
        appraisal_delay = float(self.vars["appraisal_delay"])
        # Configure appraisal delay
        if appraisal_mode == "normal":
            # Normal Appraisal
            raw_normal_appraisal_ratio = self.vars["normal_appraisal_click"]
            normal_appraisal_ratio = raw_normal_appraisal_ratio.replace(" ", "").split(",")
            try:
                appraisal_x_ratio = float(normal_appraisal_ratio[0])
                appraisal_y_ratio = float(normal_appraisal_ratio[1])
            except:
                pass
        else:
            # Gamepass Appraisal
            raw_gamepass_appraisal_ratio = self.vars["gamepass_appraisal_click"]
            gamepass_appraisal_ratio = raw_gamepass_appraisal_ratio.replace(" ", "").split(",")
            try:
                appraisal_x_ratio = float(gamepass_appraisal_ratio[0])
                appraisal_y_ratio = float(gamepass_appraisal_ratio[1])
            except:
                pass
            # Gamepass Appraisal 2
            raw_gamepass_appraisal_ratio2 = self.vars["gamepass_appraisal_click2"]
            gamepass_appraisal_ratio2 = raw_gamepass_appraisal_ratio2.replace(" ", "").split(",")
            try:
                appraisal_x_ratio2 = float(gamepass_appraisal_ratio2[0])
                appraisal_y_ratio2 = float(gamepass_appraisal_ratio2[1])
            except:
                pass
        appraisal_x = int(SCREEN_WIDTH * appraisal_x_ratio)
        appraisal_y = int(SCREEN_HEIGHT * appraisal_y_ratio)
        appraisal_x2 = int(SCREEN_WIDTH * appraisal_x_ratio2)
        appraisal_y2 = int(SCREEN_HEIGHT * appraisal_y_ratio2)
        # Other Calculations
        logging_cycle = int(self.vars["logging_cycle"])
        logging_mode = self.vars["logging_mode"].lower()
        attempts = 0.0
        # Main Loop
        time.sleep(0.1)
        if appraisal_mode == "normal":
            self._send_key("e", 0.05)
        try:
            while self.macro_running:
                attempts = attempts + 1
                # Click
                if appraisal_mode == "normal":
                    time.sleep(appraisal_delay)
                    self._click_at(appraisal_x, appraisal_y)
                else:
                    self._click_at(appraisal_x, appraisal_y)
                    time.sleep(appraisal_delay)
                    self._click_at(appraisal_x2, appraisal_y2)
                    time.sleep(appraisal_delay)
                    time.sleep(appraisal_delay)
                # Check If Dxcam Is Available
                if dxcam is not None:
                    self.capture_frame = self.camera.get_latest_frame()
                    self.capture_id = self.capture_id + 1
                fish = self.capture_frame[hotbar_top:hotbar_bottom, hotbar_left:hotbar_right]
                processed_img = self.process_image_for_ocr(fish)
                text = pytesseract.image_to_string(processed_img, config="--psm 7")
                for match in range(len(appraisal_mutations_list)):
                    # print("Requirements:", appraisal_mutations_list[match].lower().rstrip(",").replace(" ", ""))
                    # print("Text:", text.lower().rstrip(",").replace(" ", ""))
                    if appraisal_mutations_list[match].lower().rstrip(",").replace(" ", "") in text.lower().rstrip(",").replace(" ", ""):
                        self.stop_macro("Appraisal finished")
                if self.macro_running == False:
                    self.stop_macro("")
                if round(attempts) == attempts and logging_mode != "disabled":
                    if attempts == logging_cycle:
                        self.send_logging("**Attempts Checkpoint**", f"Attempt #{attempts}", -1)
                    logging_cycle = logging_cycle + attempts
        except Exception as e:
            time.sleep(0.2)
            full_error = traceback.format_exc()
            result = self.message_box_javascript(f"""An error occured during appraisal. 
            Please copy the error and report the bug:\\n{e}\\n
            Would you like to copy the full crash log to your clipboard?""", "askyesno")
            if result == True:
                if self.copy_to_clipboard(full_error):
                    self.message_box_javascript("Error copied over to clipboard")
                else:
                    self.message_box_javascript("Failed to copy error to clipboard")
            self.macro_running = False
            self.stop_macro(f"Appraisal error: {e}")
            return
        self.set_status("Macro Stopped")
    def start_treasure_appraisal(self):
        # Validate Tesseract
        try:
            tesseract_path = get_tesseract_path( self.vars.get("tesseract_path") )
            if tesseract_path:
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                # Repair the imported config in memory
                self.vars["tesseract_path"] = tesseract_path
            else:
                raise RuntimeError("⚠️ Tesseract could not be found.")
            self.macro_running = True
        except Exception as e:
            time.sleep(0.2)
            full_error = traceback.format_exc()
            result = self.message_box_javascript(f"""An error occured during appraisal.
            Please copy the error and report the bug:\\n{e}\\n
            Would you like to copy the full crash log to your clipboard?""", "askyesno")
            if result == True:
                if self.copy_to_clipboard(full_error):
                    self.message_box_javascript("Error copied over to clipboard")
                else:
                    self.message_box_javascript("Failed to copy error to clipboard")
            self.macro_running = False
            self.stop_macro(f"Appraisal error: {e}")
            return
        # Areas
        treasure_left, treasure_top, treasure_right, treasure_bottom, treasure_width, treasure_height = self.get_areas("treasure_appraisal")
        # Area Calculations
        treasure_click_center = treasure_left + int(treasure_width / 2)
        treasure_click_left = treasure_left + int(treasure_width / 5)
        treasure_click_right = treasure_right - int(treasure_width / 5)
        treasure_click_y_multiplier = int(treasure_height / 7.25)
        # Settings
        treasure_appraisal_text = self.vars["treasure_appraisal_text"].replace(" ", "").split(",")
        try:
            treasure_appraisal_text_x = float(treasure_appraisal_text[0]) * SCREEN_WIDTH
            treasure_appraisal_text_y = float(treasure_appraisal_text[1]) * SCREEN_HEIGHT
        except:
            pass
        treasure_appraisal_click = self.vars["treasure_appraisal_click"].replace(" ", "").split(",")
        try:
            treasure_appraisal_click_x = float(treasure_appraisal_click[0]) * SCREEN_WIDTH
            treasure_appraisal_click_y = float(treasure_appraisal_click[1]) * SCREEN_HEIGHT
        except:
            pass
        ocr_width = int((treasure_width / 357) * 80) # Scaled at 720p
        ocr_height = int((treasure_height / 459) * 15) # Scaled at 720p
        ocr_left = treasure_appraisal_text_x - int(ocr_width / 2)
        ocr_top = treasure_appraisal_text_y - int(ocr_height / 2)
        ocr_right = treasure_appraisal_text_x + int(ocr_width / 2)
        ocr_bottom = treasure_appraisal_text_y + int(ocr_height / 2)
        minimum_multiplier = float(self.vars["minimum_multiplier"])
        logging_mode = self.vars["logging_mode"].lower()
        # Cache Values (Failsafe)
        attempts = 0
        # Main Loop
        try:
            while self.macro_running:
                attempts = attempts + 1
                # Main Loop (Appraise 7 Times)
                for i in range(7):
                    slot = random.randint(1, 3)
                    if slot == 1:
                        current_click_x = treasure_click_left
                    elif slot == 2:
                        current_click_x = treasure_click_center
                    else:
                        current_click_x = treasure_click_right
                    current_click_y = treasure_top + (treasure_click_y_multiplier * (i + 1))
                    self._click_at(current_click_x, current_click_y)
                    time.sleep(0.5)
                time.sleep(2)
                # Check If Dxcam Is Available
                if dxcam is not None:
                    self.capture_frame = self.camera.get_latest_frame()
                    self.capture_id = self.capture_id + 1
                ocr_image = self.capture_frame[ocr_top:ocr_bottom, ocr_left:ocr_right]
                processed_img = self.process_image_for_ocr(ocr_image)
                text = pytesseract.image_to_string(processed_img, config="--psm 7")
                extracted_value = float(self.extract_number_from_text(text))
                if extracted_value is not None:
                    if extracted_value > minimum_multiplier:
                        self.stop_macro("Treasure Appraisal finished")
                    else:
                        self.set_status("Treasure Appraisal: extracted_value < minimum_multiplier")
                else:
                    self.set_status("Treasure Appraisal: extracted_value == None")
                self._click_at(treasure_appraisal_click_x, treasure_appraisal_click_y)
                if self.macro_running == False:
                    self.stop_macro("")
                if round(attempts) == attempts and logging_mode != "disabled":
                    if attempts == logging_cycle:
                        self.send_logging("**Attempts Checkpoint**", f"Attempt #{attempts}", -1)
                    logging_cycle = logging_cycle + attempts
        except Exception as e:
            time.sleep(0.2)
            full_error = traceback.format_exc()
            error_lines = full_error.splitlines()
            error_line = self.get_error_line(error_lines[1])
            result = self.message_box_javascript(f"""An error at line {error_line} occured. 
                                                 Please copy the error and report the bug:\\n{e}\\n
                                                 Would you like to copy the full crash log to your clipboard?""", "askyesno")
            if result == True:
                if self.copy_to_clipboard(full_error):
                    self.message_box_javascript("Error copied over to clipboard")
                else:
                    self.message_box_javascript("Failed to copy error to clipboard")
            if IS_COMPILED == False:
                print(full_error)
            self.macro_running = False
            self.stop_macro(f"Error at line {error_line}: {e}")
    def start_enchantment(self):
        # Validate Tesseract
        try:
            tesseract_path = get_tesseract_path( self.vars.get("tesseract_path") )
            if tesseract_path:
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                # Repair the imported config in memory
                self.vars["tesseract_path"] = tesseract_path
            else:
                raise RuntimeError("⚠️ Tesseract could not be found.")
            self.macro_running = True
        except Exception as e:
            time.sleep(0.2)
            full_error = traceback.format_exc()
            result = self.message_box_javascript(f"""An error occured during enchantment. 
            Please copy the error and report the bug:\\n{e}\\n
            Would you like to copy the full crash log to your clipboard?""", "askyesno")
            if result == True:
                if self.copy_to_clipboard(full_error):
                    self.message_box_javascript("Error copied over to clipboard")
                else:
                    self.message_box_javascript("Failed to copy error to clipboard")
            self.macro_running = False
            self.stop_macro(f"Enchantment error: {e}")
            return
        # Get Areas
        enchantment_left, enchantment_top, enchantment_right, enchantment_bottom, enchantment_width, enchantment_height = self.get_areas("enchantment")
        # Split Enchantments
        enchantment_mode = self.vars["enchantment_mode"].lower()
        enchant_enchants = self.vars["enchant_enchants"]
        enchant_enchants_list = enchant_enchants.split(",")
        # Positions
        enchantment_e_delay = float(self.vars["enchantment_e_delay"])
        enchantment_click_delay = float(self.vars["enchantment_click_delay"])
        enchantment_click_delay2 = float(self.vars["enchantment_click_delay2"])
        enchantment_click_delay3 = float(self.vars["enchantment_click_delay3"])
        enchantment_click_position = self.vars["enchantment_click_position"].replace(" ", "").split(",")
        try:
            enchantment_click_position_x = float(enchantment_click_position[0]) * SCREEN_WIDTH
            enchantment_click_position_y = float(enchantment_click_position[1]) * SCREEN_HEIGHT
        except:
            pass
        enchantment_click_position2 = self.vars["enchantment_click_position2"].replace(" ", "").split(",")
        try:
            enchantment_click_position_x2 = float(enchantment_click_position2[0]) * SCREEN_WIDTH
            enchantment_click_position_y2 = float(enchantment_click_position2[1]) * SCREEN_HEIGHT
        except:
            pass
        # Other Calculations
        logging_cycle = int(self.vars["logging_cycle"])
        logging_mode = self.vars["logging_mode"].lower()
        attempts = 0.0
        # Main Loop
        try:
            while self.macro_running:
                time.sleep(0.1)
                if enchantment_mode == "normal":
                    self._send_key("e")
                    time.sleep(enchantment_e_delay)
                    self._click_at(enchantment_click_position_x, enchantment_click_position_y)
                    time.sleep(enchantment_click_delay)
                else:
                    self._click_at(enchantment_click_position_x, enchantment_click_position_y)
                    time.sleep(enchantment_click_delay)
                    self._click_at(enchantment_click_position_x2, enchantment_click_position_y2)
                    time.sleep(enchantment_click_delay2)
                # Check If Dxcam Is Available
                if dxcam is not None:
                    self.capture_frame = self.camera.get_latest_frame()
                    self.capture_id = self.capture_id + 1
                text = self.capture_frame[enchantment_top:enchantment_bottom, enchantment_left:enchantment_right]
                gray = self.process_image_for_ocr(text)
                text = pytesseract.image_to_string(gray, config="--psm 7")
                for match in range(len(enchant_enchants_list)):
                    # print("Requirements:", appraisal_mutations_list[match].lower().rstrip(",").replace(" ", ""))
                    # print("Text:", text.lower().rstrip(",").replace(" ", ""))
                    if enchant_enchants_list[match].lower().rstrip(",").replace(" ", "") in text.lower().rstrip(",").replace(" ", ""):
                        self.stop_macro("Enchantment finished")
                time.sleep(enchantment_click_delay3)
                if self.macro_running == False:
                    self.stop_macro("")
                if round(attempts) == attempts and logging_mode != "disabled":
                    if attempts == logging_cycle:
                        self.send_logging("**Attempts Checkpoint**", f"Attempt #{attempts}", -1)
                    logging_cycle = logging_cycle + attempts
            self.set_status("Macro Stopped")
        except Exception as e:
            time.sleep(0.2)
            full_error = traceback.format_exc()
            error_lines = full_error.splitlines()
            error_line = self.get_error_line(error_lines[1])
            result = self.message_box_javascript(f"""An error at line {error_line} occured. 
                                                 Please copy the error and report the bug:\\n{e}\\n
                                                 Would you like to copy the full crash log to your clipboard?""", "askyesno")
            if result == True:
                if self.copy_to_clipboard(full_error):
                    self.message_box_javascript("Error copied over to clipboard")
                else:
                    self.message_box_javascript("Failed to copy error to clipboard")
            if IS_COMPILED == False:
                print(full_error)
            self.macro_running = False
            self.stop_macro(f"Error at line {error_line}: {e}")
    def start_angler(self):
        # Validate Tesseract
        try:
            tesseract_path = get_tesseract_path( self.vars.get("tesseract_path") )
            if tesseract_path:
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                # Repair the imported config in memory
                self.vars["tesseract_path"] = tesseract_path
            else:
                raise RuntimeError("⚠️ Tesseract could not be found.")
            self.macro_running = True
        except Exception as e:
            time.sleep(0.2)
            full_error = traceback.format_exc()
            result = self.message_box_javascript(f"""An error occured during angler. 
            Please copy the error and report the bug:\\n{e}\\n
            Would you like to copy the full crash log to your clipboard?""", "askyesno")
            if result == True:
                if self.copy_to_clipboard(full_error):
                    self.message_box_javascript("Error copied over to clipboard")
                else:
                    self.message_box_javascript("Failed to copy error to clipboard")
            self.macro_running = False
            self.stop_macro(f"Angler error: {e}")
            return
        # Areas
        backpack_left, backpack_top, _, _, backpack_width, backpack_height = self.get_areas("backpack")
        quest_left, quest_top, quest_right, quest_bottom, _, _ = self.get_areas("angler_quest")
        backpack_slot = str(self.vars["backpack_slot"])
        # Delays
        angler_cooldown = int(self.vars["angler_cooldown"])
        angler_e_delay = float(self.vars["angler_e_delay"])
        angler_click_position = self.vars["angler_click_position"].replace(" ", "").split(",")
        try:
            angler_click_position_x = float(angler_click_position[0]) * SCREEN_WIDTH
            angler_click_position_y = float(angler_click_position[1]) * SCREEN_HEIGHT
        except:
            pass
        angler_click_position2 = self.vars["angler_click_position2"].replace(" ", "").split(",")
        try:
            angler_click_position_x2 = float(angler_click_position2[0]) * SCREEN_WIDTH
            angler_click_position_y2 = float(angler_click_position2[1]) * SCREEN_HEIGHT
        except:
            pass
        # Main Loop
        try:
            while self.macro_running:
                time.sleep(0.1)
                # Step 1: Click E → Open Quest Dialogue
                self._send_key("e")
                time.sleep(angler_e_delay)
                # Click At Angler Area (Accept Quest)
                self._click_at(angler_click_position_x, angler_click_position_y)
                # Step 2: OCR Quest Area — Get Required Fish Text
                time.sleep(3)
                quest = self.capture_frame[quest_top:quest_bottom, quest_left:quest_right]
                gray = cv2.cvtColor(quest, cv2.COLOR_BGR2GRAY)
                gray = cv2.resize(gray, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
                gray = cv2.threshold(gray, 150, 255, cv2.THRESH_BINARY)[1]
                quest_text = pytesseract.image_to_string(gray)
                lines = [
                    line.strip().lower()
                    for line in quest_text.splitlines()
                    if line.strip()
                ]
                required_fish = lines[-1] if lines else ""
                self.set_status(f"Quest fish: {required_fish}")
                if not required_fish:
                    self.set_status("Could not read fish name")
                    time.sleep(angler_cooldown)
                    continue

                # Step 3: Open Backpack
                self._send_key(backpack_slot)
                time.sleep(0.5)
                # Step 4: Click Search Bar + Type Fish Name
                self._click_at(angler_click_position_x2, angler_click_position_y2)
                time.sleep(0.5)
                # Type Fish Name
                for char in required_fish:
                    self._send_key(char)
                time.sleep(1.5)
                # Step 5: Locate Quest_Text In Quest Area Via OCR And Click It
                # Check If Dxcam Is Available
                if dxcam is not None:
                    self.capture_frame = self.camera.get_latest_frame()
                    self.capture_id = self.capture_id + 1
                quest_region = self.capture_frame[quest_top:quest_bottom, quest_left:quest_right]
                gray_q = cv2.cvtColor(quest_region, cv2.COLOR_BGR2GRAY)
                gray_q = cv2.resize(gray_q, None, fx=3, fy=3, interpolation=cv2.INTER_CUBIC)
                gray_q = cv2.threshold(gray_q, 150, 255, cv2.THRESH_BINARY)[1]
                ocr_data_q = pytesseract.image_to_data(
                    gray_q,
                    output_type=pytesseract.Output.DICT,
                    config="--psm 11"
                )
                quest_click_x, quest_click_y = None, None
                for i, text_tok in enumerate(ocr_data_q["text"]):
                    tok = text_tok.strip().lower()
                    try:
                        conf = float(ocr_data_q["conf"][i])
                    except Exception:
                        conf = -1
                    if conf < 40 or not tok:
                        continue

                    if tok in required_fish or required_fish in tok:
                        qx = ocr_data_q["left"][i]
                        qy = ocr_data_q["top"][i]
                        qw = ocr_data_q["width"][i]
                        qh = ocr_data_q["height"][i]
                        # Undo The 3× Upscale To Get Back To Screen Coords
                        quest_click_x = quest_left + (qx + qw // 2) // 3
                        quest_click_y = quest_top  + (qy + qh // 2) // 3
                        break

                if quest_click_x is not None:
                    self.set_status(
                        f"Quest text '{required_fish}' found at "
                        f"{quest_click_x}, {quest_click_y} — clicking"
                    )
                    self._click_at(quest_click_x, quest_click_y)
                else:
                    self.set_status(
                        f"Quest text '{required_fish}' not found via OCR, skipping click"
                    )
                time.sleep(0.25)
                # Step 6: Close Backpack
                self._send_key(backpack_slot)
                time.sleep(0.5)
                # Step 7: Click E → Finish Quest (Pixel Search Or Ratio)
                self._send_key("e")
                time.sleep(1.2)
                # Click At Angler Area To Exit Quest
                self._click_at(angler_click_position_x, angler_click_position_y)
                # Step 8: Cooldown
                time.sleep(angler_cooldown)
        except Exception as e:
            time.sleep(0.2)
            full_error = traceback.format_exc()
            result = self.message_box_javascript(f"""An error occured during angler. 
            Please copy the error and report the bug:\\n{e}\\n
            Would you like to copy the full crash log to your clipboard?""", "askyesno")
            if result == True:
                if self.copy_to_clipboard(full_error):
                    self.message_box_javascript("Error copied over to clipboard")
                else:
                    self.message_box_javascript("Failed to copy error to clipboard")
            self.macro_running = False
            self.stop_macro(f"Angler error: {e}")
            return
        self.set_status("Macro Stopped")
    def start_fishing(self):
        try:
            self.status_overlay.set_main_status("Initialization")
            # 1. Core Config & Modes
            scale = get_scale_factor()
            self.macro_running = True
            casting_mode = self.vars["casting_mode"].lower()
            shake_mode = self.vars["shake_mode"].lower()
            logging_mode = self.vars["logging_mode"].lower()
            fishing_profile = self.vars["fishing_profile"].lower()
            sovereign_recharge = self.vars["sovereign_recharge"]
            click_after_minigame = self.vars["click_after_minigame"].lower()
            target_time = self.vars["target_time"].lower()
            logging_cycle = int(self.vars["logging_cycle"])
            hunt_cycles = int(self.vars["hunt_cycles"])
            auto_reconnect = self.vars["auto_reconnect"]
            hunt_detect = int(self._get_var_number("hunt_detect", 20, float))
            minimum_percentage = float(self.vars["minimum_percentage"].strip("%"))
            maximum_percentage = float(self.vars["maximum_percentage"].strip("%"))
            # 2. Hotkey & Inventory Slots
            bag_slot = str(self.vars["bag_slot"])
            rod_slot = str(self.vars["rod_slot"])
            sundial_slot = str(self.vars["sundial_slot"])
            target_slot = str(self.vars["target_slot"])
            relic_slot = str(self.vars["relic_slot"])
            # 3. Delays & Timings
            select_rod_duration = float(self.vars["select_rod_duration"])
            delay_before_casting = float(self._get_var_number("delay_before_casting", 0.5, float))
            delay_after_casting = float(self._get_var_number("cast_delay", 1.0, float))
            sundial_delay = float(self.vars["sundial_delay"])
            totem_delay = float(self.vars["totem_delay"])
            status_overlay = self.vars["status_overlay"]
            # 4. Screen Regions & Coordinates
            shake_left, shake_top, shake_right, shake_bottom, shake_w, shake_h = self.get_areas("shake")
            fish_left, fish_top, fish_right, fish_bottom, _, fish_height = self.get_areas("fish")
            friend_left_s, friend_top_s, friend_right_s, friend_bottom_s, _, _ = self.get_areas("friend")
            totem_left, totem_top, totem_right, totem_bottom, _, _ = self.get_areas("totem")
            sovereign_left, sovereign_top, sovereign_right, sovereign_bottom, sovereign_width, _ = self.get_areas("sovereign")
            shake_x = shake_left + (shake_w // 2)
            shake_y = shake_top + (shake_h // 2)
            detection_method = self.vars["detection_method"].lower()
            # 5. Features & Overlay Settings
            shake_failsafe = int(self.vars["shake_failsafe"])
            fish_color = self.vars["fish_color"]
            fish_tolerance = int(self.vars["fish_tolerance"])
            friend_color = self.vars["friends_color"]
            friend_tolerance = int(self.vars["friends_tolerance"])
            sovereign_recharge_color = self.vars["sovereign_recharge_color"]
            sovereign_recharge_tolerance = int(self.vars["sovereign_recharge_tolerance"])
            auto_refresh = self.vars["auto_refresh"]
            auto_totem = self.vars["auto_totem"]
            fish_overlay = self.vars["fish_overlay"]
            minigame_click_position = self.vars["minigame_click_position"]
            animation_delay = float(self.vars["animation_delay"])
            minigame_click_amounts = int(float(self.vars["minigame_click_amounts"]))
            enchantment_click_position = self.vars["enchantment_click_position"].replace(" ", "").split(",")
            try:
                enchantment_click_position_x = float(enchantment_click_position[0]) * SCREEN_WIDTH
                enchantment_click_position_y = float(enchantment_click_position[1]) * SCREEN_HEIGHT
            except:
                pass
            enchantment_click_position2 = self.vars["enchantment_click_position2"].replace(" ", "").split(",")
            try:
                enchantment_click_position_x2 = float(enchantment_click_position2[0]) * SCREEN_WIDTH
                enchantment_click_position_y2 = float(enchantment_click_position2[1]) * SCREEN_HEIGHT
            except:
                pass
            enchantment_click_delay = float(self.vars["enchantment_click_delay"])
            enchantment_click_delay2 = float(self.vars["enchantment_click_delay2"])
            # 6. Optimized Opencv Template Matching Setup
            try:
                sun = cv2.imread(os.path.join(IMAGES_PATH, "sun.png"))
                moon = cv2.imread(os.path.join(IMAGES_PATH, "moon.png"))
                sun_resized = self.auto_crop_template(sun)
                moon_resized = self.auto_crop_template(moon)
            except:
                self.set_status("Error: Can't find sun.png and moon.png. Auto Totem is disabled.")
                self.send_logging("Error: Can't find sun.png and moon.png. Auto Totem is disabled.", 0, -1)
                auto_totem = "off"
            # 7. Internal Tracking State
            self.scan_delay = 0.1
            self.current_cycle = 0
            current_time = None
            current_hunt = ""
            # Catch Metrics (0 - Success, 1 - Failed, 2 - N/A Initial State)
            self.catch_success = 2
            self.catch_rate = 0.0
            successful_catches = 0
            logging_cycle2 = logging_cycle
            hunt_cycles2 = hunt_cycles
            # Fish Overlay
            if fish_overlay == "on":
                # Position The Overlay Just Above Or Below The Fish Bar So It Does
                # Not Cover The Actual Minigame.  Show() Expects (Left, Top, Width,
                # Height) In Physical Pixels — Not Right/Bottom.
                fish_center = int((fish_top + fish_bottom) / 2)
                if fish_center > HALF_HEIGHT:
                    fish_top_overlay = fish_top + fish_height + fish_height
                else:
                    fish_top_overlay = fish_top - fish_height - fish_height
                overlay_width = fish_right - fish_left
                overlay_height = int(fish_height / 1.5)
                self.fish_overlay.show(
                    fish_left,
                    fish_top_overlay,
                    overlay_width,
                    overlay_height,
                )
            else:
                self.fish_overlay.hide()
            # Status Overlay
            if status_overlay == "on":
                # Position The Status Overlay At The Top Left, But Avoiding The macOS Menu Offset.
                self.status_overlay.show(self.status_left, self.status_top, self.status_right, self.status_bottom)
            else:
                self.status_overlay.hide()
        except KeyError as e:
            self.stop_macro("Config Error: ", e)
        # Main Loop (With Bug Reports)
        try:
            while self.macro_running:
                self.status_overlay.set_main_status("Resetting Statistics")
                self.set_status("Resetting statistics")
                self.capture_id = 0
                if auto_refresh == "on":
                    time.sleep(delay_before_casting)
                    self._send_key(bag_slot)
                    self.interruptible_sleep(select_rod_duration)
                    self._send_key(rod_slot)
                    self.interruptible_sleep(delay_after_casting / 2)
                self.set_status("Using Utilities")
                # Auto Totem
                if auto_totem == "on":
                    self.status_overlay.set_main_status("Auto Totem")
                    self.set_status("Auto Totem")
                    time.sleep(0.1)
                    if not target_time == "disabled":
                        if dxcam is not None:
                            self.capture_frame = self.camera.get_latest_frame()
                        totem = self.capture_frame[totem_top:totem_bottom, totem_left:totem_right]
                        sun_found, _, sun_confidence = self.image_search_totem(totem, sun_resized)
                        moon_found, _, moon_confidence = self.image_search_totem(totem, moon_resized)
                        if sun_found == False and moon_found == False:
                            current_time = None
                            self.send_logging("**Sundial Failed**", f"Cycle #{self.current_cycle}", "N/A")
                        elif sun_found == True:
                            current_time = "Day"
                        elif moon_found == True:
                            current_time = "Night"
                        else:
                            if sun_confidence > moon_confidence:
                                current_time = "Day"
                            else:
                                current_time = "Night"
                        if not target_time == current_time:
                            self._send_key(sundial_slot)
                            self._click_at(shake_x, shake_y)
                            self.interruptible_sleep(sundial_delay)
                            self.send_logging("**Sundial Success**", f"Cycle #{self.current_cycle}", "N/A")
                    self._send_key(target_slot)
                    self._click_at(shake_x, shake_y)
                    self.interruptible_sleep(totem_delay)
                    self._send_key(rod_slot)
                    time.sleep(delay_after_casting / 4)
                if auto_reconnect == "on":
                    self.status_overlay.set_main_status("Auto Reconnect")
                    self._auto_reconnect(shake_x, shake_y)
                if hunt_detect == "on":
                    self.status_overlay.set_main_status("Hunt Detect")
                    if self.current_cycle == hunt_cycles:
                        self.hunt_detect(current_hunt)
                        hunt_cycles = hunt_cycles2 + self.current_cycle
                if sovereign_recharge == "on":
                    self.status_overlay.set_main_status("Sovereign Recharge")
                    sovereign_img = self.capture_frame[sovereign_top:sovereign_bottom, sovereign_left:sovereign_right]
                    sovereign_right2, _ = self.pixel_search(sovereign_img, sovereign_recharge_color, sovereign_recharge_tolerance)
                    if sovereign_right2 is not None:
                        distance = round(abs(sovereign_right2 - sovereign_left) / sovereign_width, 2)
                        while distance < maximum_percentage:
                            if distance < minimum_percentage:
                                self._send_key(rod_slot)
                                time.sleep(0.1)
                                self._send_key(relic_slot)
                                self._click_at(enchantment_click_position_x, enchantment_click_position_y)
                                time.sleep(enchantment_click_delay)
                                self._click_at(enchantment_click_position_x2, enchantment_click_position_y2)
                                time.sleep(enchantment_click_delay2)
                            elif distance > maximum_percentage:
                                break

                            time.sleep(0.01)
                # Update Current Cycle
                self.current_cycle = self.current_cycle + 1
                # Cast
                self.set_status(f"Casting ({casting_mode})")
                self.status_overlay.set_main_status(f"Casting ({casting_mode})")
                time.sleep(delay_before_casting)
                if casting_mode == "perfect":
                    self._execute_cast_perfect()
                else:
                    self._execute_cast_normal()
                time.sleep(delay_after_casting)
                # Shake
                self.set_status("Shaking")
                self.status_overlay.set_main_status(f"Shaking ({shake_mode})")
                self.scan_delay = float(self.vars["shake_scan_delay"])
                for attempts in range(shake_failsafe):
                    self.status_overlay.set_line(1, "Attempts", attempts)
                    if dxcam is not None:
                        self.capture_frame = self.camera.get_latest_frame()
                    if self.capture_frame is None:
                        attempts = attempts - 1
                        continue
                    if detection_method == "friend_area":
                        friend_img = self.capture_frame[friend_top_s:friend_bottom_s, friend_left_s:friend_right_s]
                        friend_x, friend_y = self.pixel_search(friend_img, friend_color, friend_tolerance)
                        if friend_x is None or friend_y is None:
                            break

                    else:
                        fish_img = self.capture_frame[fish_top:fish_bottom, fish_left:fish_right]
                        fish_x, fish_y = self.pixel_search(fish_img, fish_color, fish_tolerance)
                        if fish_x is not None or fish_y is not None:
                            break

                    if self.macro_running == False:
                        break

                    elif shake_mode == "navigation":
                        keyboard_controller.press(Key.enter)
                        time.sleep(0.01)
                        keyboard_controller.release(Key.enter)
                    else:
                        self._execute_shake_click(shake_mode)
                    time.sleep(self.scan_delay)
                # Minigame — Sets Self.Catch_Success = 0 At Start; Flips To 1 If Fish Ever Leaves The Bar
                time.sleep(animation_delay)
                if self.macro_running == True:
                    self.set_status("Playing Bar Minigame")
                    self.status_overlay.set_main_status(f"Playing Bar Minigame ({fishing_profile})")
                    if fishing_profile == "reverse":
                        self._enter_minigame_dreambreaker()
                    elif fishing_profile == "dual":
                        self._enter_minigame_bellona()
                    elif fishing_profile == "lanes":
                        self._enter_minigame_tranquility()
                    elif fishing_profile == "metronome":
                        self.enter_minigame_lullaby()
                    else:
                        self._enter_minigame()
                    if click_after_minigame == "on":
                        try:
                            time.sleep(select_rod_duration)
                            minigame_click_positions = minigame_click_position.replace(" ", "").split(",")
                            minigame_click_position_xr = float(minigame_click_positions[0])
                            minigame_click_position_yr = float(minigame_click_positions[1])
                            minigame_click_position_x = int(minigame_click_position_xr * SCREEN_WIDTH)
                            minigame_click_position_y = int(minigame_click_position_yr * SCREEN_HEIGHT)
                            for clicks in range(minigame_click_amounts - 1):
                                self._click_at(minigame_click_position_x, minigame_click_position_y)
                                time.sleep(1)
                            self._click_at(HALF_WIDTH, HALF_HEIGHT)
                            time.sleep(2.5)
                        except:
                            pass
                # Update Catch Rate After The Minigame Finishes
                if self.catch_success == 0:
                    successful_catches += 1
                self.catch_rate = successful_catches / self.current_cycle
                catch_rate_percentage = int(self.catch_rate * 100)
                if logging_mode != "disabled":
                    if self.current_cycle == logging_cycle:
                        self.send_logging("**Cycle Checkpoint**", f"Cycle #{self.current_cycle}", catch_rate_percentage)
                        logging_cycle = logging_cycle2 + self.current_cycle
            self.stop_macro("")
            return

        except Exception as e:
            time.sleep(0.2)
            full_error = traceback.format_exc()
            error_line = self.get_error_line(full_error)
            result = self.message_box_javascript(f"""An error at line {error_line} occured. 
            Please copy the error and report the bug:\\n{e}\\n
            Would you like to copy the full crash log to your clipboard?""", "askyesno")
            if result == True:
                if self.copy_to_clipboard(full_error):
                    self.message_box_javascript("Error copied over to clipboard")
                else:
                    self.message_box_javascript("Failed to copy error to clipboard")
            if IS_COMPILED == False:
                print(full_error)
            else:
                self.send_logging(f"Error at line {error_line}: {e}", 0, -1)
            self.macro_running = False
            self.stop_macro(f"Error at line {error_line}: {e}")
            return
    def _auto_reconnect(self, center_x, center_y):
        reconnect_threshold = int(self.vars["reconnect_threshold"])
        reconnect_wait_time = int(self.vars["reconnect_wait_time"])
        mirror_ratio = self.vars["mirror_ratio"]
        mirror_splitted = mirror_ratio.replace(" ", "").split(",")
        try:
            mirror_xr = float(mirror_splitted[0])
            mirror_yr = float(mirror_splitted[1])
        except:
            self.send_logging("**Reconnect Failed**", f"Cycle #{self.current_cycle}", 1)
            return
        mirror_slot = str(self.vars["mirror_slot"])
        shake_left, shake_top, shake_right, shake_bottom, shake_width, shake_height = self.get_areas("shake")
        mirror_click_x = int(SCREEN_WIDTH * mirror_xr)
        # 0.59
        mirror_click_y = int(SCREEN_HEIGHT * mirror_yr)
        # 1520
        reconnect_threshold = int((reconnect_threshold / 1500) * (SCREEN_WIDTH / 1.8))
        if dxcam is not None:
            self.capture_frame = self.camera.get_latest_frame()
        img = self.capture_frame[shake_top:shake_bottom, shake_left:shake_right]
        disconnect_x, disconnect_y = self.find_color_cluster(img, "#393b3d", 5, reconnect_threshold)
        reconnect_x, reconnect_y = self.find_color_cluster(img, "#FFFFFF", 8, int(reconnect_threshold / 2))
        while self.macro_running:
            if disconnect_x is not None and reconnect_x is not None:
                self.interruptible_sleep(1)
                reconnect_x_screen = reconnect_x + shake_left
                reconnect_y_screen = reconnect_y + shake_top
                self._click_at(reconnect_x_screen, reconnect_y_screen)
                self.interruptible_sleep(reconnect_wait_time)
                self._click_at(center_x, center_y)
                self.interruptible_sleep(2.5)
                keyboard_controller.press(mirror_slot)
                self.interruptible_sleep(0.05)
                keyboard_controller.release(mirror_slot)
                self._click_at(center_x, center_y)
                self.interruptible_sleep(0.2)
                self._click_at(mirror_click_x, mirror_click_y)
                self.send_logging("**Reconnect Success**", f"Cycle #{self.current_cycle}", 1)
            else:
                self.send_logging("**Reconnect Failed**", f"Cycle #{self.current_cycle}", 1)
            return

    def hunt_detect(self, current_hunt):
        "current_hunt: Does nothing"
        try:
            tesseract_path = get_tesseract_path( self.vars.get("tesseract_path") )
            if tesseract_path:
                pytesseract.pytesseract.tesseract_cmd = tesseract_path
                # Repair the imported config in memory
                self.vars["tesseract_path"] = tesseract_path
            else:
                raise RuntimeError("⚠️ Tesseract could not be found.")
        except:
            return

        chat_left, chat_top, chat_right, chat_bottom = self.get_areas("chat")
        hunt_fishes = self.vars["hunt_fishes"].lower()
        user_id = int(self.vars["user_id"])
        hunt_fishes_list = hunt_fishes.split(",")
        text = self.capture_frame[
            chat_top:chat_bottom,
            chat_left:chat_right
        ]
        gray = self.process_image_for_ocr(text)
        text = pytesseract.image_to_string(
            gray,
            config="--psm 6"
        )
        # Get The Bottommost Nonempty OCR Line
        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]
        if not lines:
            return

        latest_line = lines[-1]
        # Check Only The Latest Chat Message
        latest_line_normalized = latest_line.lower().replace(" ", "")
        for hunt in hunt_fishes_list:
            hunt = hunt.strip()
            current_hunt = hunt
            if hunt.lower().replace(" ", "") in latest_line_normalized:
                self.send_logging(
                    f"<@{user_id}> Found {hunt}",
                    self.current_cycle
                )
                return current_hunt

        return current_hunt

    def _execute_cast_perfect(self):
        # Areas
        shake_left, shake_top, shake_right, shake_bottom, _, shake_height = self.get_areas("shake")
        # Colors
        white_cast_color = self.vars["white_cast_color"]
        pinion_notes_color = self.vars["green_cast_color"]
        # Tolerance
        white_cast_tolerance = int(self.vars["white_cast_tolerance"])
        green_cast_tolerance = int(self.vars["green_cast_tolerance"])
        # Perfect Cast Settings
        perfect_cast_method = self.vars["perfect_cast_method"].lower()
        fall_scan_timeout = float(self.vars["fall_scan_timeout"])
        self.scan_delay = float(self.vars["cast_scan_delay"])
        # Last Values (Failsafe)
        last_capture_id = 0
        is_initial_run = True
        is_green_tracking = False
        green_detected = False
        start_time = time.time()
        last_time = time.time()
        self.hold_mouse()
        green_padding = 50
        released = False
        # Simple Method Variables
        speed_samples = []
        white_positions = []
        white_timestamps = []
        max_speed_samples = 20
        release_delay = float(self.vars["release_delay_simple"])
        perfect_threshold = float(self.vars["perfect_threshold"])  # Hardcoded value - setting removed in later versions
        release_timing = max(-50.0, min(50.0, release_delay))
        # Velocity Method Variables
        if perfect_cast_method == "velocity":
            white_positions = []
            white_timestamps = []
            MAX_VELOCITY_SAMPLES = 10
            last_time_to_impact = None
            # Get Screen Resolution For Scaling
            scaling_factor = 1920 / SCREEN_WIDTH
        if perfect_cast_method == "prediction":
            highest_cast_percentage = 100
            highest_cast_percentage_updated = False
        # Initialize Tracking Variables
        green_abs_top = 0
        green_abs_left = 0
        green_abs_right = 0
        green_abs_bottom = 0
        reached_bottom_5_percent = True
        last_fill_percentage = None
        last_frame_time = None
        # Loop
        while self.macro_running:
            # Check If Dxcam Is Available
            if dxcam is not None:
                self.capture_frame = self.camera.get_latest_frame()
                self.capture_id = last_capture_id + 1
            # Get Image From Self.Capture_Frame
            if self.capture_id == last_capture_id:
                time.sleep(self.scan_delay)
                continue

            if self.capture_frame is None:
                time.sleep(self.scan_delay)
                continue

            # Scan Time Calculations
            current_time = time.time()
            elapsed_time = current_time - start_time
            time_delta = current_time - last_time
            if elapsed_time >= fall_scan_timeout:
                self.release_mouse()
                released = True
                break

            # Check If Macro Stopped During Perfect Cast
            if not self.macro_running:
                self.release_mouse()
                released = True
                break

            # Status Overlay
            self.status_overlay.set_line(1, "Green: ", f"Undefined")
            self.status_overlay.set_line(2, "White: ", f"Undefined")

            # Scanning From Shake_Left, Shake_Top To Shake_Right, Shake_Bottom
            shake_img = self.capture_frame[shake_top:shake_bottom, shake_left:shake_right]
            # Green Detection
            if is_green_tracking:
                # Track In Subregion Around Last Known Green Position
                green_area_top = max(0, green_abs_top - green_padding)
                green_area_bottom = min(shake_img.shape[0], green_abs_top + green_padding)
                green_area_left = max(0, green_abs_left - green_padding)
                green_area_right = min(shake_img.shape[1], green_abs_right + green_padding)
                green_area = shake_img[green_area_top:green_area_bottom, green_area_left:green_area_right]
                g_left, g_top = self.pixel_search(green_area, pinion_notes_color, green_cast_tolerance)
                g_right, g_bottom = self.pixel_search(green_area, pinion_notes_color, green_cast_tolerance, 1)
                if None not in (g_left, g_top, g_right, g_bottom):
                    # Convert From Green_Area Coordinates To Shake_Img Coordinates
                    green_abs_left = g_left + green_area_left
                    green_abs_top = g_top + green_area_top
                    green_abs_right = g_right + green_area_left
                    green_abs_bottom = g_bottom + green_area_top
                    green_detected = True
                else:
                    green_detected = False
                    is_green_tracking = False
                    if perfect_cast_method == "simple":
                        speed_samples.clear()
                    else:
                        white_positions.clear()
                        white_timestamps.clear()
                    self.status_overlay.set_line(1, "Green: ", f"None (Full Scan)")
                    continue  # Skip this frame, try full scan next frame

            if not is_green_tracking:
                # Full Scan For Green
                g_left, g_top = self.pixel_search(shake_img, pinion_notes_color, green_cast_tolerance)
                g_right, g_bottom = self.pixel_search(shake_img, pinion_notes_color, green_cast_tolerance, 1)
                if None not in (g_left, g_top, g_right, g_bottom):
                    green_abs_left = g_left
                    green_abs_top = g_top
                    green_abs_right = g_right
                    green_abs_bottom = g_bottom
                    green_detected = True
                    is_green_tracking = True
                else:
                    self.status_overlay.set_line(1, "Green: ", f"None (Skipped)")
                    continue  # No green found, try again
            # Show Status For Green
            self.status_overlay.set_line(1, "Green: ", f"{green_abs_left}, {green_abs_top}")

            # White Detection
            # Search vertically below the center of the green bar.
            green_center_x = (green_abs_left + green_abs_right) // 2

            # Keep the coordinate inside shake_img.
            green_center_x = max(
                0,
                min(green_center_x, shake_img.shape[1] - 1)
            )

            # Comet-style vertical scan:
            # start at the green bar and scan all the way to the
            # bottom of the captured region.
            scan_start_y = max(0, green_abs_top)
            scan_end_y = shake_img.shape[0]

            white_column = shake_img[
                scan_start_y:scan_end_y,
                green_center_x:green_center_x + 1,
                :
            ]

            # Per-channel tolerance:
            # a pixel matches when every B/G/R channel is within
            # white_cast_tolerance of the target color.
            white_b, white_g, white_r = self._hex_to_bgr(white_cast_color)

            white_target = np.array(
                [white_b, white_g, white_r],
                dtype=np.int16
            )

            white_column_i = white_column.astype(np.int16)

            white_diff = np.abs(
                white_column_i - white_target
            )

            white_mask = (
                np.max(white_diff, axis=2)
                <= white_cast_tolerance
            )

            # Get every matching Y position on the center column.
            white_rows = np.flatnonzero(white_mask[:, 0])

            if white_rows.size == 0:
                self.status_overlay.set_line(2, "White: ", f"None (Skipped)")
                continue

            # First matching pixel = top of the white target.
            white_abs_top = scan_start_y + int(white_rows[0])

            # Last matching pixel = bottom of the white target.
            # Keeping this allows Solar's existing Simple and Prediction
            # methods to continue using total_distance.
            white_abs_bottom = scan_start_y + int(white_rows[-1])

            # Existing Solar distance calculations.
            total_distance = white_abs_bottom - green_abs_top
            current_distance = white_abs_top - green_abs_top

            if total_distance <= 0:
                self.status_overlay.set_line(
                    2,
                    "White: ",
                    f"{total_distance} (Invalid)"
                )
                continue

            self.status_overlay.set_line(
                2,
                "White: ",
                f"{green_center_x}, {white_abs_top}"
            )

            # Release Logic Based On Selected Method
            if perfect_cast_method == "simple":
                # Simple (Percentage-Based) Method
                actual_fill_percentage = (1 - (current_distance / total_distance)) * 100
                fill_speed = 0.0
                position_offset_percent = 0.0
                if last_fill_percentage is not None and last_frame_time is not None:
                    time_delta = current_time - last_frame_time
                    if time_delta > 0:
                        fill_change = actual_fill_percentage - last_fill_percentage
                        if fill_change < -50:
                            last_fill_percentage = None
                            last_frame_time = None
                            reached_bottom_5_percent = False
                            speed_samples.clear()
                        elif fill_change > 0:
                            instant_fill_speed = fill_change / time_delta
                            speed_samples.append(instant_fill_speed)
                            if len(speed_samples) > max_speed_samples:
                                speed_samples.pop(0)
                if speed_samples:
                    fill_speed = sum(speed_samples) / len(speed_samples)
                    base_offset = 1.5 * math.log(1 + fill_speed / 25.0)
                    if release_timing < 0:
                        base_multiplier = 1.0 - (release_timing / 5.0)
                        speed_scale = min(6.0, (fill_speed / 100.0) ** 2)
                        timing_multiplier = 1.0 + (base_multiplier - 1.0) * speed_scale
                        position_offset_percent = max(0.0, min(50.0, base_offset * timing_multiplier))
                    else:
                        position_offset_percent = max(0.0, min(50.0, base_offset))
                predicted_fill_percentage = actual_fill_percentage + position_offset_percent
                self.status_overlay.set_line(3, "Percentage: ", predicted_fill_percentage)
                offset_pixels = int((position_offset_percent / 100.0) * total_distance)
                predicted_white_y_top = white_abs_top - offset_pixels
                bottom_threshold = 5.0 + position_offset_percent
                if predicted_fill_percentage <= bottom_threshold and not reached_bottom_5_percent:
                    reached_bottom_5_percent = True
                    last_fill_percentage = None
                    last_frame_time = None
                    speed_samples.clear()
                if release_timing <= 0:
                    release_threshold = perfect_threshold
                else:
                    release_threshold = perfect_threshold + (release_timing / 50.0) * 4.5
                if reached_bottom_5_percent and predicted_fill_percentage >= release_threshold:
                    released = True
                    break

                last_fill_percentage = actual_fill_percentage
                last_frame_time = current_time
            elif perfect_cast_method == "velocity":  # perfect_cast_method == "velocity" (VELOCITY-BASED METHOD)
                # Velocity Tracking
                white_positions.append((0, white_abs_top))  # x is irrelevant; track Y only
                white_timestamps.append(current_time)
                if len(white_positions) > MAX_VELOCITY_SAMPLES:
                    white_positions.pop(0)
                    white_timestamps.pop(0)
                # Local_Distance: Pixels Remaining Until White Reaches Green
                local_distance = current_distance  # white_abs_top - green_abs_top; positive = white below green
                # Velocity-Band Predictive Release
                if len(white_positions) >= 3:
                    velocity_y = self._calculate_speed_and_predict(white_positions, white_timestamps)
                    min_speed = 5 * scaling_factor
                    if velocity_y is not None and abs(velocity_y) > min_speed:
                        white_above_green = white_abs_top < green_abs_top
                        moving_toward_green = (white_above_green and velocity_y > 0) or (not white_above_green and velocity_y < 0)
                        if moving_toward_green and local_distance > 0:
                            time_to_impact = local_distance / abs(velocity_y)
                            self.status_overlay.set_line(3, "Time To Impact: ", round(time_to_impact, 2))
                            # Bounce/Miss Detection: If Tti Suddenly Grows When Very Close, We Passed Green
                            bounce_threshold = 40 * scaling_factor
                            if last_time_to_impact is not None and local_distance < bounce_threshold:
                                if time_to_impact > last_time_to_impact * 1.3:
                                    self.release_mouse()
                                    released = True
                            if not released:
                                # Velocity-Band Reaction Delays (Tuned At 1440P)
                                v = abs(velocity_y)
                                if v < 700 * scaling_factor:
                                    reaction_delay = 0.060
                                    timing_key = "perfect_cast_timing_700"
                                elif v < 800 * scaling_factor:
                                    reaction_delay = 0.058
                                    timing_key = "perfect_cast_timing_800"
                                elif v < 900 * scaling_factor:
                                    reaction_delay = 0.057
                                    timing_key = "perfect_cast_timing_900"
                                elif v < 1000 * scaling_factor:
                                    reaction_delay = 0.056
                                    timing_key = "perfect_cast_timing_1000"
                                elif v < 1100 * scaling_factor:
                                    reaction_delay = 0.055
                                    timing_key = "perfect_cast_timing_1100"
                                elif v < 1200 * scaling_factor:
                                    reaction_delay = 0.050
                                    timing_key = "perfect_cast_timing_1200"
                                elif v < 1300 * scaling_factor:
                                    reaction_delay = 0.048
                                    timing_key = "perfect_cast_timing_1300"
                                elif v < 1400 * scaling_factor:
                                    reaction_delay = 0.047
                                    timing_key = "perfect_cast_timing_1400"
                                elif v < 1500 * scaling_factor:
                                    reaction_delay = 0.046
                                    timing_key = "perfect_cast_timing_1500"
                                elif v < 1600 * scaling_factor:
                                    reaction_delay = 0.050
                                    timing_key = "perfect_cast_timing_1600"
                                else:
                                    reaction_delay = 0.049
                                    timing_key = "perfect_cast_timing_1600_plus"
                                timing_adjustment_ms = self._get_var_number(timing_key, 0, int)
                                reaction_delay += timing_adjustment_ms * 0.001
                                if time_to_impact <= reaction_delay:
                                    self.release_mouse()
                                    released = True
                            last_time_to_impact = time_to_impact
                # Slow-Speed / Emergency Distance Fallbacks
                if not released:
                    slow_threshold = total_distance * 0.05  # within 5% of green
                    emergency_threshold = total_distance * 0.025
                    self.status_overlay.set_line(3, "Local Distance: ", local_distance)
                    if local_distance <= emergency_threshold:
                        self.release_mouse()
                        released = True
                    elif local_distance <= slow_threshold and len(white_positions) >= 3:
                        # Confirm Approach: Latest Distance < Oldest Distance
                        recent_dists = [p[1] - green_abs_top for p in white_positions[-3:]]
                        if recent_dists[-1] < recent_dists[0]:
                            self.release_mouse()
                            released = True
                if released:
                    break
            elif perfect_cast_method == "prediction":  # perfect_cast_method == "prediction" (PREDICTION METHOD)
                # Simple (Percentage-Based) Method
                actual_fill_percentage = (1 - (current_distance / total_distance)) * 100
                fill_speed = 0.0
                position_offset_percent = 0.0
                if last_fill_percentage is not None and last_frame_time is not None:
                    time_delta = current_time - last_frame_time
                    if time_delta > 0:
                        fill_change = actual_fill_percentage - last_fill_percentage
                        if fill_change < -50:
                            last_fill_percentage = None
                            last_frame_time = None
                            reached_bottom_5_percent = False
                            speed_samples.clear()
                        elif fill_change > 0:
                            instant_fill_speed = fill_change / time_delta
                            speed_samples.append(instant_fill_speed)
                            if len(speed_samples) > max_speed_samples:
                                speed_samples.pop(0)
                if speed_samples:
                    fill_speed = sum(speed_samples) / len(speed_samples)
                    base_offset = 1.5 * math.log(1 + fill_speed / 25.0)
                    if release_timing < 0:
                        base_multiplier = 1.0 - (release_timing / 5.0)
                        speed_scale = min(6.0, (fill_speed / 100.0) ** 2)
                        timing_multiplier = 1.0 + (base_multiplier - 1.0) * speed_scale
                        position_offset_percent = max(0.0, min(50.0, base_offset * timing_multiplier))
                    else:
                        position_offset_percent = max(0.0, min(50.0, base_offset))
                predicted_fill_percentage = actual_fill_percentage + position_offset_percent
                offset_pixels = int((position_offset_percent / 100.0) * total_distance)
                predicted_white_y_top = white_abs_top - offset_pixels
                bottom_threshold = 5.0 + position_offset_percent
                if predicted_fill_percentage <= bottom_threshold and not reached_bottom_5_percent:
                    reached_bottom_5_percent = True
                    last_fill_percentage = None
                    last_frame_time = None
                    speed_samples.clear()
                if last_fill_percentage is not None:
                    cast_velocity = actual_fill_percentage - last_fill_percentage
                else:
                    cast_velocity = 0.1
                if cast_velocity < 0:
                    if highest_cast_percentage_updated == False:
                        # Store The Highest Percentage From The Previous Bar Movement
                        highest_cast_percentage = last_fill_percentage
                        highest_cast_percentage_updated = True
                        time.sleep(0.2)
                if release_timing <= 0:
                    release_threshold = highest_cast_percentage
                else:
                    release_threshold = highest_cast_percentage + (release_timing / 50.0) * 4.5
                self.status_overlay.set_line(3, "Highest Cast Percentage: ", round(highest_cast_percentage, 2))
                if reached_bottom_5_percent and predicted_fill_percentage >= release_threshold:
                    released = True
                    break

                last_fill_percentage = actual_fill_percentage
                last_frame_time = current_time
            if time.time() - start_time > fall_scan_timeout:
                break

            # Cleanup
            time.sleep(self.scan_delay)
            last_capture_id = self.capture_id
            is_initial_run = False
            last_time = current_time
        # Final Cleanup
        self.release_mouse()
        self._fish_overlay_cast_bounds = None
        return

    def _execute_cast_normal(self):
        if self.macro_running == False:
            return

        cast_duration = float(self._get_var_number("cast_duration", 0.5, float))
        self.status_overlay.set_line(1, "Casting For: (seconds)", cast_duration)
        self.hold_mouse(False)
        self.interruptible_sleep(cast_duration)
        self.release_mouse(False)
        return

    def _execute_shake_click(self, shake_mode):
        scale = get_scale_factor()
        shake_left, shake_top, shake_right, shake_bottom, _, _ = self.get_areas("shake")
        shake_color = self.vars["shake_color"]
        shake_tolerance = self.vars["shake_tolerance"]
        if dxcam is not None:
            self.capture_frame = self.camera.get_latest_frame()
        shake_img = self.capture_frame[shake_top:shake_bottom, shake_left:shake_right]
        if shake_mode == "pixel":
            shake_x, shake_y = self.pixel_search(shake_img, shake_color, shake_tolerance)
        else:
            shake_x, shake_y = self._find_circles(shake_img)
        try:
            shake_x_screen = int((shake_x / scale) + shake_left)
            shake_y_screen = int((shake_y / scale) + shake_top)
        except:
            shake_x_screen = None
            shake_y_screen = None
        self._click_at(shake_x_screen, shake_y_screen)
        return

    def _enter_minigame_tranquility(self):
        # Colors
        left_color = self.vars["left_color"]
        right_color = self.vars["right_color"]
        arrow_color = self.vars["arrow_color"]
        fish_color = self.vars["fish_color"]
        friend_color = self.vars["friends_color"]
        # Tolerance
        left_tolerance = int(self.vars["left_tolerance"])
        right_tolerance = int(self.vars["right_tolerance"])
        arrow_tolerance = int(self.vars["arrow_tolerance"])
        fish_tolerance = int(self.vars["fish_tolerance"])
        friends_tolerance = int(self.vars["friends_tolerance"])
        # Minigame Variables
        tranquility_note_ratio = float(self.vars["tranquility_note_ratio"])
        target_delay = float(self.vars["target_delay"])
        tranquility_mode = self.vars["tranquility_mode"].lower()
        self.scan_delay = float(self.vars["minigame_scan_delay"])
        restart_delay = float(self.vars["restart_delay"])
        restart_method = self.vars["restart_method"].lower()
        last_capture_id = 0
        # Get Hotkeys
        tranquility_key_1 = str(self.vars["tranquility_key_1"])
        tranquility_key_2 = str(self.vars["tranquility_key_2"])
        tranquility_key_3 = str(self.vars["tranquility_key_3"])
        tranquility_key_4 = str(self.vars["tranquility_key_4"])
        # Last Values (Cache)
        is_initial_run = True
        # Initial Note Positions.
        # The First Four Detected Notes Are Ignored For The Initial State.
        initial_left = []
        initial_right = []
        initial_arrow = []
        initial_fish = []
        # Perframe Detected Note Positions.
        lowest_left = []
        lowest_right = []
        lowest_arrow = []
        lowest_fish = []
        # Get Areas
        shake_left, shake_top, shake_right, shake_bottom, shake_width, shake_height = self.get_areas("shake")
        friend_left, friend_top, friend_right, friend_bottom, _, _ = self.get_areas("friend")
        # Resize Overlay
        left_offset = shake_left - int(shake_width / 3.8)
        overlay_width = int(shake_width / 4)
        self.fish_overlay.resize(left_offset, shake_top, overlay_width, shake_height)
        time.sleep(0.5)
        while self.macro_running:
            # Check If Dxcam Is Available
            if dxcam is not None:
                self.capture_frame = self.camera.get_latest_frame()
                self.capture_id = last_capture_id + 1
            if self.capture_id == last_capture_id:
                time.sleep(self.scan_delay)
                continue
            elif self.capture_frame is None:
                time.sleep(self.scan_delay)
                continue
            else:
                friend_img = self.capture_frame[friend_top:friend_bottom, friend_left:friend_right]
                detection_img = self.capture_frame[shake_top:shake_bottom, shake_left:shake_right]
            friend_x, friend_y = self.pixel_search(friend_img, friend_color, friends_tolerance)
            self.fish_overlay.clear()
            if restart_method == "friends":
                if friend_x is not None:
                    time.sleep(restart_delay)
                    return

            circles = self._find_all_circles(detection_img)
            self.status_overlay.set_line(1, "Circles: ", len(circles))
            # Collect The Four Starting Note Positions.
            # Nothing Is Pressed During The Initial Run.
            if is_initial_run:
                for circle in range(len(circles)):
                    circle_x_ratio = round(circles[circle][0] / shake_width, 2)
                    circle_y_ratio = round(circles[circle][1] / shake_height, 2)
                    if 0.0 <= circle_x_ratio <= 0.25:
                        initial_left.append(circle_y_ratio)
                    elif 0.25 < circle_x_ratio <= 0.5:
                        initial_right.append(circle_y_ratio)
                    elif 0.5 < circle_x_ratio <= 0.75:
                        initial_arrow.append(circle_y_ratio)
                    elif 0.75 < circle_x_ratio <= 1.0:
                        initial_fish.append(circle_y_ratio)
                    self.fish_overlay.draw_box(
                        x1=int(overlay_width * 0.15),
                        y1=circles[circle][1],
                        x2=int(overlay_width * 0.85),
                        y2=circles[circle][1] + 67,
                        color=f"#{min(circle * 3500, 9999)}ff"
                    )
                # Wait Until The Four Initial Notes Have Been Detected.
                initial_note_count = (
                    len(initial_left)
                    + len(initial_right)
                    + len(initial_arrow)
                    + len(initial_fish)
                )
                if initial_note_count >= 4:
                    is_initial_run = False
                last_capture_id = self.capture_id
                time.sleep(self.scan_delay)
                continue

            # Normal Detection After The Initial Four Notes Have Been Recorded.
            for circle in range(len(circles)):
                circle_x_ratio = round(circles[circle][0] / shake_width, 2)
                circle_y_ratio = round(circles[circle][1] / shake_height, 2)
                if 0.0 <= circle_x_ratio <= 0.25:
                    lowest_left.append(circle_y_ratio)
                elif 0.25 < circle_x_ratio <= 0.5:
                    lowest_right.append(circle_y_ratio)
                elif 0.5 < circle_x_ratio <= 0.75:
                    lowest_arrow.append(circle_y_ratio)
                elif 0.75 < circle_x_ratio <= 1.0:
                    lowest_fish.append(circle_y_ratio)
                # Print(
                #     f"Circle #{circle}: "
                #     f"x{circles[circle][0]} y{circles[circle][1]} "
                #     f"xr{circle_x_ratio} yr{circle_y_ratio}"
                # )
                self.fish_overlay.draw_box(
                    x1=int(overlay_width * 0.15),
                    y1=circles[circle][1],
                    x2=int(overlay_width * 0.85),
                    y2=circles[circle][1] + 67,
                    color=f"#{min(circle * 3500, 9999)}ff"
                )
            # A Note At Its Original Starting Position Is Still Part Of
            # The Protected Initial State, So Do Nothing.
            # If The Original Position Disappeared Because Two Circles
            # Connected, The Newly Detected Position Will Not Match The
            # Starting Position And Can Be Processed Normally.
            self.status_overlay.set_line(2, "Waiting for notes", "")
            for circle_y_ratio in lowest_left:
                if circle_y_ratio in initial_left:
                    continue

                if circle_y_ratio > tranquility_note_ratio:
                    self.status_overlay.set_line(2, f"Pressing {tranquility_key_1}", circle_y_ratio)
                    self._send_key(tranquility_key_1, 0.01)
            for circle_y_ratio in lowest_right:
                if circle_y_ratio in initial_right:
                    continue

                if circle_y_ratio > tranquility_note_ratio:
                    self.status_overlay.set_line(2, f"Pressing {tranquility_key_2}", circle_y_ratio)
                    self._send_key(tranquility_key_2, 0.01)
            for circle_y_ratio in lowest_arrow:
                if circle_y_ratio in initial_arrow:
                    continue

                if circle_y_ratio > tranquility_note_ratio:
                    self.status_overlay.set_line(2, f"Pressing {tranquility_key_3}", circle_y_ratio)
                    self._send_key(tranquility_key_3, 0.01)
            for circle_y_ratio in lowest_fish:
                if circle_y_ratio in initial_fish:
                    continue

                if circle_y_ratio > tranquility_note_ratio:
                    self.status_overlay.set_line(2, f"Pressing {tranquility_key_4}", circle_y_ratio)
                    self._send_key(tranquility_key_4, 0.01)
            lowest_left.clear()
            lowest_right.clear()
            lowest_arrow.clear()
            lowest_fish.clear()
            last_capture_id = self.capture_id
            is_initial_run = False
            time.sleep(self.scan_delay)
        return

    def _enter_minigame_dreambreaker(self):
        # Helper Functions
        mouse_down = False
        def hold_mouse(mouse_state=False):
            "Hold mouse. False for left click, True for right click."
            nonlocal mouse_down
            if not mouse_down:
                self.hold_mouse(mouse_state)
                mouse_down = True
        def release_mouse(mouse_state=False):
            "Release mouse. False for left click, True for right click."
            nonlocal mouse_down
            if mouse_down:
                self.release_mouse(mouse_state)
                mouse_down = False
        # Areas
        fish_left, fish_top, fish_right, fish_bottom, fish_width, fish_height = self.get_areas("fish")
        friend_left, friend_top, friend_right, friend_bottom, _, _ = self.get_areas("friend")
        # Area Calculations
        fish_x = int((fish_left + fish_right) / 2)
        fish_y = int((fish_top + fish_bottom) / 2)
        fish_overlay = self.vars["fish_overlay"]
        if fish_overlay == "on":
            # Position The Overlay Just Above Or Below The Fish Bar So It Does
            # Not Cover The Actual Minigame.  Show() Expects (Left, Top, Width,
            # Height) In Physical Pixels — Not Right/Bottom.
            fish_center = int((fish_top + fish_bottom) / 2)
            if fish_center > HALF_HEIGHT:
                fish_top_overlay = fish_top + fish_height + fish_height
            else:
                fish_top_overlay = fish_top - fish_height - fish_height
            overlay_width = fish_right - fish_left
            overlay_height = int(fish_height / 1.5)
            self.fish_overlay.show(
                fish_left,
                fish_top_overlay,
                overlay_width,
                overlay_height,
            )
        # Colors
        left_color = self.vars["left_color"]
        right_color = self.vars["right_color"]
        arrow_color = self.vars["arrow_color"]
        fish_color = self.vars["fish_color"]
        friends_color = self.vars["friends_color"]
        # Tolerance
        try:
            left_tolerance = int(self.vars["left_tolerance"])
            right_tolerance = int(self.vars["right_tolerance"])
            arrow_tolerance = int(self.vars["arrow_tolerance"])
            fish_tolerance = int(self.vars["fish_tolerance"])
            friends_tolerance = int(self.vars["friends_tolerance"])
        except:
            left_tolerance = 8
            right_tolerance = 8
            arrow_tolerance = 8
            fish_tolerance = 4
            friends_tolerance = 5
        # Minigame Settings
        lock_cursor = self.vars["lock_cursor"]
        self.scan_delay = float(self.vars["minigame_scan_delay"])
        restart_delay = float(self.vars["restart_delay"])
        restart_method = self.vars["restart_method"].lower()
        # Last Values (Failsafe)
        scale = get_scale_factor()
        last_left_x = 0
        last_right_x = 0
        last_capture_id = 0
        last_bar_size = 0
        last_bar_center = 0
        last_detection_source = 0
        while self.macro_running:
            # Check If Dxcam Is Available
            if dxcam is not None:
                self.capture_frame = self.camera.get_latest_frame()
                self.capture_id = last_capture_id + 1
            # Get Image From Self.Capture_Frame
            if self.capture_id == last_capture_id:
                time.sleep(self.scan_delay)
                continue

            elif self.capture_frame is None:
                time.sleep(self.scan_delay)
                continue

            else:
                fish_img = self.capture_frame[fish_top:fish_bottom, fish_left:fish_right]
                friend_img = self.capture_frame[friend_top:friend_bottom, friend_left:friend_right]
            self.fish_overlay.clear()
            fish_x, fish_y = self.pixel_search(fish_img, fish_color, fish_tolerance)
            left_x, left_y = self.pixel_search(fish_img, left_color, left_tolerance)
            right_x, right_y = self.pixel_search(fish_img, right_color, right_tolerance, 1)
            if left_x == None:
                left_x, left_y = self.pixel_search(fish_img, right_color, right_tolerance)
            if right_x == None:
                right_x, right_y = self.pixel_search(fish_img, left_color, left_tolerance, 1)
            if left_x is None or right_x is None:
                detection_source = 1
                # Bars Not Found  Scan For Arrows
                arrow_x, arrow_y = self.pixel_search(fish_img, arrow_color, arrow_tolerance)
                # Reconstruct Missing Bar Edge From Previous Geometry Instead Of Mouse State
                if arrow_x is not None:
                    # Treat 0 As Unknown To Match The Previous None Semantics
                    if last_left_x == 0:
                        last_left_x = None
                    if last_right_x == 0:
                        last_right_x = None
                    # If Exactly One Edge Is Missing, Reconstruct It Using The Last Known Bar Size
                    if last_left_x is None and last_right_x is not None:
                        last_left_x = last_right_x - last_bar_size
                    elif last_right_x is None and last_left_x is not None:
                        last_right_x = last_left_x + last_bar_size
                if arrow_x is not None:
                    bar_detected = True
                    arrow_on_left_side = arrow_x < last_bar_center
                    dist_to_left = abs(arrow_x - last_left_x) if last_left_x is not None else fish_width
                    dist_to_right = abs(arrow_x - last_right_x) if last_right_x is not None else fish_width
                    proximity_threshold = int(last_bar_size / 4)
                    # Flip Decision If Wrong
                    if arrow_on_left_side:
                        if dist_to_right < dist_to_left and dist_to_right < proximity_threshold:
                            # Arrow Is Actually Closer To Right Bar  We Were Wrong!
                            arrow_on_left_side = False  # Flip the decision
                    else:
                        if dist_to_left < dist_to_right and dist_to_left < proximity_threshold:
                            # Arrow Is Actually Closer To Left Bar  We Were Wrong!
                            arrow_on_left_side = True  # Flip the decision
                    if arrow_on_left_side:
                        left_x = arrow_x
                        right_x = last_right_x
                        if right_x is None:
                            right_x = left_x + last_bar_size
                    else:
                        right_x = arrow_x
                        left_x = last_left_x
                        if left_x is None:
                            left_x = right_x - last_bar_size
            else:
                detection_source = 0
            try:
                bar_size = right_x - left_x
                bar_center = left_x + int(bar_size / 2)
            except:
                bar_size = 0
                bar_center = 0
            # Friend And Fish Restart
            if restart_method == "friend_area":
                friend_x, friend_y = self.pixel_search(friend_img, friends_color, friends_tolerance)
                if friend_x is not None and friend_y is not None:
                    self.interruptible_sleep(restart_delay)
                    return

            else:
                try:
                    if fish_x is None:
                        self.interruptible_sleep(restart_delay)
                        return

                except:
                    time.sleep(self.scan_delay)
                    continue

            if lock_cursor == "on":
                mouse_controller.position = (int(fish_x / scale), int(fish_y / scale))
            # Draw
            if left_x is not None:
                self.fish_overlay.draw_box(x1=left_x, y1=overlay_height*0.15, x2=right_x, y2=overlay_height*0.85, color="green")
            # Controller Output
            self.status_overlay.set_line(1, f"Detection Source: ", detection_source)
            self.status_overlay.set_line(2, f"Last Source: ", last_detection_source)
            if detection_source == 1 and last_detection_source == 0:
                if mouse_down == False:
                    hold_mouse()
                elif mouse_down == True:
                    release_mouse()
            # Cleanup
            last_bar_center = bar_center
            last_bar_size = bar_size
            last_capture_id = self.capture_id
            last_detection_source = detection_source
    def _enter_minigame_bellona(self):
        # Helper Functions
        mouse_down = False
        def hold_mouse(mouse_state=False):
            "Hold mouse. False for left click, True for right click."
            nonlocal mouse_down
            if not mouse_down:
                self.hold_mouse(mouse_state)
                mouse_down = True
        def release_mouse(mouse_state=False):
            "Release mouse. False for left click, True for right click."
            nonlocal mouse_down
            if mouse_down:
                self.release_mouse(mouse_state)
                mouse_down = False
        # Areas
        shake_left, shake_top, shake_right, shake_bottom, _, shake_height = self.get_areas("shake")
        raw_fish_left, fish_top, raw_fish_right, fish_bottom, raw_fish_width, fish_height = self.get_areas("fish")
        friend_left, friend_top, friend_right, friend_bottom, _, _ = self.get_areas("friend")
        # Area Calculations
        fish_center = raw_fish_left + int(raw_fish_width / 2)
        fish_left = raw_fish_left
        fish_right = fish_center
        fish_left2 = fish_center
        fish_right2 = raw_fish_right
        shake_x = int((shake_left + shake_right) / 2)
        shake_y = int((shake_top + shake_bottom) / 2)
        fish_overlay = self.vars["fish_overlay"]
        if fish_overlay == "on":
            # Position The Overlay Just Above Or Below The Fish Bar So It Does
            # Not Cover The Actual Minigame.  Show() Expects (Left, Top, Width,
            # Height) In Physical Pixels — Not Right/Bottom.
            fish_center = int((fish_top + fish_bottom) / 2)
            if fish_center > HALF_HEIGHT:
                fish_top_overlay = fish_top + fish_height + fish_height
            else:
                fish_top_overlay = fish_top - fish_height - fish_height
            overlay_width = fish_right2 - fish_left
            overlay_height = int(fish_height / 1.5)
            self.fish_overlay.show(
                fish_left,
                fish_top_overlay,
                overlay_width,
                overlay_height,
            )
        # Colors
        left_color = self.vars["left_color"]
        right_color = self.vars["right_color"]
        arrow_color = self.vars["arrow_color"]
        fish_color = self.vars["fish_color"]
        friends_color = self.vars["friends_color"]
        # Tolerance
        try:
            left_tolerance = int(self.vars["left_tolerance"])
            right_tolerance = int(self.vars["right_tolerance"])
            arrow_tolerance = int(self.vars["arrow_tolerance"])
            fish_tolerance = int(self.vars["fish_tolerance"])
            friends_tolerance = int(self.vars["friends_tolerance"])
        except:
            left_tolerance = 8
            right_tolerance = 8
            arrow_tolerance = 8
            fish_tolerance = 4
            friends_tolerance = 5
        # Minigame Settings
        scale = get_scale_factor()
        bag_slot = str(self.vars["bag_slot"])
        bag_spam = self.vars["bag_spam"]
        lock_cursor = self.vars["lock_cursor"]
        restart_method = self.vars["restart_method"]
        bar_ratio_from_side = float(self.vars["bar_ratio_from_side"])
        restart_delay = float(self.vars["restart_delay"])
        self.scan_delay = float(self.vars["minigame_scan_delay"])
        kp = self._get_var_number("kp", 0.45)
        kd = self._get_var_number("kd", 0.35)
        # Cache Values
        last_capture_id = 0
        last_bar_size1 = 0
        last_bar_center1 = 0
        last_bar_size2 = 0
        last_bar_center2 = 0
        last_left_x1 = 0
        last_left_x2 = 0
        last_right_x1 = 0
        last_right_x2 = 0
        last_fish_x1 = 0
        last_fish_x2 = 0
        last_time = time.perf_counter()
        while self.macro_running:
            # Check If Dxcam Is Available
            if dxcam is not None:
                self.capture_frame = self.camera.get_latest_frame()
                self.capture_id = last_capture_id + 1
            # Get Image From Self.Capture_Frame
            if self.capture_id == last_capture_id:
                time.sleep(self.scan_delay)
                continue

            elif self.capture_frame is None:
                time.sleep(self.scan_delay)
                continue

            else:
                fish_img = self.capture_frame[fish_top:fish_bottom, fish_left:fish_right]
                fish_img2 = self.capture_frame[fish_top:fish_bottom, fish_left2:fish_right2]
                friend_img = self.capture_frame[friend_top:friend_bottom, friend_left:friend_right]
            # Fish Detection
            fish_x1, fish_y1 = self.pixel_search(fish_img, fish_color, fish_tolerance)
            fish_x2, fish_y2 = self.pixel_search(fish_img2, fish_color, fish_tolerance)
            fish_detected = True
            fish_detected2 = True
            if fish_x1 is None:
                fish_detected = False
            if fish_x2 is None:
                fish_detected2 = False
            # Left And Right Bar Detection
            left_x1, left_y1 = self.pixel_search(fish_img, left_color, left_tolerance)
            right_x1, right_y1 = self.pixel_search(fish_img, right_color, right_tolerance, 1)
            left_x2, left_y2 = self.pixel_search(fish_img2, left_color, left_tolerance)
            right_x2, right_y2 = self.pixel_search(fish_img2, right_color, right_tolerance, 1)
            bar_detected = True
            bar_detected2 = True
            if left_x1 is not None or right_x1 is not None:
                # Bar 1 Detected - Calculate Bar Center And Bar Size
                bar_size1 = abs(right_x1 - left_x1)
                bar_center1 = left_x1 + int(bar_size1 / 2)
            else:
                # Try Arrow For Left Bar
                arrow_x1, arrow_y1 = self.pixel_search(fish_img, arrow_color, arrow_tolerance)
                if arrow_x1 is not None:
                    arrow1_on_left_side = arrow_x1 < last_bar_center1
                    if arrow1_on_left_side:
                        left_x1 = arrow_x1
                        right_x1 = arrow_x1 + last_bar_size1
                    bar_size1 = abs(right_x1 - left_x1)
                    bar_center1 = left_x1 + int(bar_size1 / 2)
                else:
                    bar_detected = False
            if left_x2 is not None or right_x2 is not None:
                # Bar 2 Detected  Calculate Bar Center And Bar Size
                bar_size2 = abs(right_x1 - left_x1)
                bar_center2 = left_x1 + int(bar_size2 / 2)
            else:
                # Try Arrow For Right Bar
                arrow_x2, arrow_y2 = self.pixel_search(fish_img2, arrow_color, arrow_tolerance)
                if arrow_x2 is not None:
                    arrow2_on_left_side = arrow_x2 < last_bar_center2
                    if arrow2_on_left_side:
                        left_x2 = arrow_x2
                        right_x2 = arrow_x2 + last_bar_size2
                    bar_size2 = abs(right_x1 - left_x1)
                    bar_center2 = left_x1 + int(bar_size2 / 2)
                else:
                    bar_detected2 = False
            # Friend And Fish Restart
            if restart_method == "friend_area":
                friend_x, friend_y = self.pixel_search(friend_img, friends_color, friends_tolerance)
                if friend_x is not None and friend_y is not None:
                    self.interruptible_sleep(restart_delay)
                    return

            else:
                try:
                    if fish_x1 is None and fish_x2 is None:
                        self.interruptible_sleep(restart_delay)
                        return

                except:
                    time.sleep(self.scan_delay)
                    continue

            # print(f"bar_detected: {bar_detected}")
            # print(f"left_x: {left_x}, right_x: {right_x}")
            # print(f"bar_center: {bar_center}, bar_size: {bar_size}")
            # Bag Spam & Lock Cursor
            try:
                bag_spam_cycle += 1
            except:
                bag_spam_cycle = 0
            if bag_spam_cycle == 5:
                bag_spam_cycle = 0
                if bag_spam == "on":
                    self._send_key(bag_slot)
                if lock_cursor == "on":
                    mouse_controller.position = (int(shake_x / scale), int(shake_y / scale))
            # Restore From Cache
            self.fish_overlay.clear()
            if bar_detected == False:
                left_x1 = last_left_x1
                right_x1 = last_right_x1
                bar_center1 = last_bar_center1
                bar_size1 = last_bar_size1
            if fish_detected == False:
                fish_x1 = last_fish_x1
            if bar_detected2 == False:
                left_x2 = last_left_x2
                right_x2 = last_right_x2
                bar_center2 = last_bar_center2
                bar_size2 = last_bar_size2
            if fish_detected2 == False:
                fish_x2 = last_fish_x2
            # Edge Boundary For Left And Right Bar
            boundary1 = bar_size1 * bar_ratio_from_side
            boundary2 = bar_size2 * bar_ratio_from_side
            left_boundary1 = fish_left + boundary1
            right_boundary1 = fish_right - boundary1
            left_boundary2 = fish_left2 + boundary2
            right_boundary2 = fish_right2 - boundary2
            if fish_overlay == "on":
                self.fish_overlay.draw_box(
                    x1=left_x1, y1=fish_height*0.15, x2=right_x1, y2=fish_height*0.85,
                )
                if left_boundary1 is not None:
                    self.fish_overlay.draw_box(
                        x1=left_boundary1, y1=fish_height*0.15, x2=left_boundary1 + 15, y2=fish_height*0.85,
                    )
                if right_boundary1 is not None:
                    self.fish_overlay.draw_box(
                        x1=right_boundary1 - 15, y1=fish_height*0.15, x2=right_boundary1, y2=fish_height*0.85,
                    )
                if fish_x1 is not None:
                    self.fish_overlay.draw_box(
                        x1=fish_x1, y1=fish_height*0.15, x2=fish_x1 + 15, y2=fish_height*0.85,
                    )
                self.fish_overlay.draw_box(
                    x1=left_x2, y1=fish_height*0.15, x2=right_x2, y2=fish_height*0.85,
                )
                if left_boundary2 is not None:
                    self.fish_overlay.draw_box(
                        x1=left_boundary2, y1=fish_height*0.15, x2=left_boundary2 + 15, y2=fish_height*0.85,
                    )
                if right_boundary2 is not None:
                    self.fish_overlay.draw_box(
                        x1=right_boundary2 - 15, y1=fish_height*0.15, x2=right_boundary2, y2=fish_height*0.85,
                    )
                if fish_x2 is not None:
                    self.fish_overlay.draw_box(
                        x1=fish_x2, y1=fish_height*0.15, x2=fish_x2 + 15, y2=fish_height*0.85,
                    )
            current_time = time.perf_counter()
            time_delta = current_time - last_time
            error1 = fish_x1 - bar_center1
            p_term1 = error1 / time_delta * self.scan_delay
            d_term1 = (error1 - last_error1) / time_delta
            control_signal1 = p_term1 * kp + d_term1 * kd
            error2 = fish_x2 - bar_center2
            p_term2 = error2 / time_delta * self.scan_delay
            d_term2 = (error2 - last_error2) / time_delta
            control_signal2 = p_term2 * kp + d_term2 * kd
            if control_signal1 > 0:
                hold_mouse(False)
            else:
                release_mouse(False)
            if control_signal2 > 0:
                hold_mouse(True)
            else:
                release_mouse(True)
            if bar_detected == True:
                last_left_x1 = left_x1
                last_right_x1 = right_x1
                last_bar_center1 = bar_center1
                last_bar_size1 = bar_size1
            if bar_detected2 == True:
                last_left_x2 = left_x2
                last_right_x2 = right_x2
                last_bar_center2 = bar_center2
                last_bar_size2 = bar_size2
            if fish_detected == True:
                last_fish_x1 = fish_x1
            if fish_detected2 == True:
                last_fish_x2 = fish_x2
            last_error1 = error1
            last_error2 = error2
            last_time = current_time
    def enter_minigame_lullaby(self):
        # Helper Functions
        mouse_down = False
        def hold_mouse(mouse_state=False):
            "Hold mouse. False for left click, True for right click."
            nonlocal mouse_down
            if not mouse_down:
                self.hold_mouse(mouse_state)
                mouse_down = True
        def release_mouse(mouse_state=False):
            "Release mouse. False for left click, True for right click."
            nonlocal mouse_down
            if mouse_down:
                self.release_mouse(mouse_state)
                mouse_down = False
        # Areas
        lullaby_left, lullaby_top, lullaby_right, lullaby_bottom, lullaby_width, _ = self.get_areas("lullaby")
        fish_left, fish_top, fish_right, fish_bottom, fish_width, fish_height = self.get_areas("fish")
        friend_left, friend_top, friend_right, friend_bottom, _, _ = self.get_areas("friend")
        # Area Calculations
        fish_overlay = self.vars["fish_overlay"]
        if fish_overlay == "on":
            fish_center = int((lullaby_top + lullaby_bottom) / 2)
            if fish_center > HALF_HEIGHT:
                fish_top_overlay = lullaby_top - fish_height - fish_height
            else:
                fish_top_overlay = lullaby_top + fish_height + fish_height
            overlay_width = fish_right - fish_left
            overlay_height = int(fish_height / 1.5)
            self.fish_overlay.resize(
                lullaby_left,
                fish_top_overlay,
                lullaby_width,
                overlay_height,
            )
        # Colors
        left_color = self.vars["left_color"]
        right_color = self.vars["right_color"]
        arrow_color = self.vars["arrow_color"]
        fish_color = self.vars["fish_color"]
        friends_color = self.vars["friends_color"]
        # Convert Hex → Bgr Once (Capture Frames Are Bgr)
        left_bgr = np.array(self._hex_to_bgr(left_color), dtype=np.int16)
        right_bgr = np.array(self._hex_to_bgr(right_color), dtype=np.int16)
        # Tolerance
        try:
            left_tolerance = int(self.vars["left_tolerance"])
            right_tolerance = int(self.vars["right_tolerance"])
            arrow_tolerance = int(self.vars["arrow_tolerance"])
            fish_tolerance = int(self.vars["fish_tolerance"])
            friends_tolerance = int(self.vars["friends_tolerance"])
        except:
            left_tolerance = 8
            right_tolerance = 8
            arrow_tolerance = 8
            fish_tolerance = 4
            friends_tolerance = 5
        # Minigame Variables
        lullaby_metronome_padding = int(self.vars["lullaby_metronome_padding"])
        lullaby_mask_lost_ratio = float(self.vars["lullaby_mask_lost_ratio"])
        # Cache Variables
        is_initial_run = True
        last_capture_id = 0
        lullaby_area_x1 = None
        lullaby_area_x2 = None
        lullaby_area_y1 = None
        lullaby_area_y2 = None
        metronome_inside = False
        last_metronome_inside = False
        # Initial Color Masks
        initial_left_mask = None
        initial_right_mask = None
        # Baseline Mask Bounding Boxes
        initial_left_coords = None
        initial_right_coords = None
        while self.macro_running:
            # Check If Dxcam Is Available
            if dxcam is not None:
                self.capture_frame = self.camera.get_latest_frame()
                self.capture_id = last_capture_id + 1
            # Get Image From Self.Capture_Frame
            if self.capture_id == last_capture_id:
                time.sleep(self.scan_delay)
                continue

            elif self.capture_frame is None:
                time.sleep(self.scan_delay)
                continue

            # Initial Run
            # Find The Lullaby Area And Save The Initial Color Masks.
            if is_initial_run:
                lullaby_img = self.capture_frame[
                    lullaby_top:lullaby_bottom,
                    lullaby_left:lullaby_right
                ]
                # Current Frame As Int16 So Subtraction Cannot Overflow
                lullaby_pixels = lullaby_img.astype(np.int16)
                # Create Initial Masks (Colors Already Converted To Bgr Above)
                left_diff = np.abs(lullaby_pixels - left_bgr)
                right_diff = np.abs(lullaby_pixels - right_bgr)
                initial_left_mask = np.all(
                    left_diff <= left_tolerance,
                    axis=2
                )
                initial_right_mask = np.all(
                    right_diff <= right_tolerance,
                    axis=2
                )
                # Get Coordinates Of The Initial Masks
                left_y, left_x = np.where(initial_left_mask)
                right_y, right_x = np.where(initial_right_mask)
                # Make Sure Both Colors Were Found
                if (
                    len(left_x) == 0
                    or len(right_x) == 0
                ):
                    time.sleep(self.scan_delay)
                    last_capture_id = self.capture_id
                    continue

                # Save Initial Mask Coordinates
                initial_left_coords = (left_x, left_y)
                initial_right_coords = (right_x, right_y)
                # Calculate The Complete Initial Lullaby Area
                lullaby_area_x1 = min(
                    left_x.min(),
                    right_x.min()
                )
                lullaby_area_x2 = max(
                    left_x.max(),
                    right_x.max()
                )
                lullaby_area_y1 = min(
                    left_y.min(),
                    right_y.min()
                )
                lullaby_area_y2 = max(
                    left_y.max(),
                    right_y.max()
                )
                # Add Padding For The Metronome
                lullaby_area_x1 = max(
                    0,
                    lullaby_area_x1 - lullaby_metronome_padding
                )
                lullaby_area_x2 = min(
                    lullaby_img.shape[1],
                    lullaby_area_x2 + lullaby_metronome_padding
                )
                lullaby_area_y1 = max(
                    0,
                    lullaby_area_y1 - lullaby_metronome_padding
                )
                lullaby_area_y2 = min(
                    lullaby_img.shape[0],
                    lullaby_area_y2 + lullaby_metronome_padding
                )
                # Switch To The Smaller Region After Initialization.
                is_initial_run = False
            # Subsequent Runs
            # Only Capture/Process The Smaller Lullaby Region.
            else:
                lullaby_img2 = self.capture_frame[
                    lullaby_top + lullaby_area_y1:
                    lullaby_top + lullaby_area_y2,
                    lullaby_left + lullaby_area_x1:
                    lullaby_left + lullaby_area_x2
                ]
                # Create Current Color Masks Only Inside The Small Area
                current_pixels = lullaby_img2.astype(np.int16)
                current_left_mask = np.all(
                    np.abs(current_pixels - left_bgr) <= left_tolerance,
                    axis=2
                )
                current_right_mask = np.all(
                    np.abs(current_pixels - right_bgr) <= right_tolerance,
                    axis=2
                )
                # Compare Current Masks Against The Initial Masks.
                # The Initial Masks Are In Full Lullaby Coordinates,
                # So Crop Them To The Same Smaller Region First.
                initial_left_small = initial_left_mask[
                    lullaby_area_y1:lullaby_area_y2,
                    lullaby_area_x1:lullaby_area_x2
                ]
                initial_right_small = initial_right_mask[
                    lullaby_area_y1:lullaby_area_y2,
                    lullaby_area_x1:lullaby_area_x2
                ]
                # Pixels That Existed Initially But Disappeared Now
                left_missing_mask = (
                    initial_left_small &
                    ~current_left_mask
                )
                right_missing_mask = (
                    initial_right_small &
                    ~current_right_mask
                )
                # Calculate How Much Of The Original Mask Disappeared
                initial_left_count = np.count_nonzero(initial_left_small)
                initial_right_count = np.count_nonzero(initial_right_small)
                left_missing_count = np.count_nonzero(left_missing_mask)
                right_missing_count = np.count_nonzero(right_missing_mask)
                # Calculate The Total Mask Count
                initial_mask_count = initial_left_count + initial_right_count
                mask_missing_count = left_missing_count + right_missing_count
                self.status_overlay.set_line(1, "Initial Mask Count: ", initial_mask_count)
                self.status_overlay.set_line(2, "Current Mask Count: ", mask_missing_count)
                if left_missing_count + right_missing_count == 0:
                    continue # Invalid detection
                # Decide whether the metronome is inside or not
                metronome_ratio = mask_missing_count / initial_mask_count
                lullaby_mask_contain_ratio = 1 - lullaby_mask_lost_ratio
                if metronome_ratio < lullaby_mask_contain_ratio:
                    metronome_inside = True
                else:
                    metronome_inside = False
                self.status_overlay.set_line(3, "Metronome Ratio: ", round(metronome_ratio, 2))
                # Metronome Logic (Metronome_Inside = True)
                if not metronome_inside == False:
                    if last_metronome_inside != metronome_inside:
                        hold_mouse()
                        time.sleep(0.05)
                        release_mouse()
            last_metronome_inside = metronome_inside
            time.sleep(self.scan_delay)
            last_capture_id = self.capture_id
    def _enter_minigame(self):
        # Helper Functions
        mouse_down = False
        def hold_mouse(mouse_state=False):
            "Hold mouse. False for left click, True for right click."
            nonlocal mouse_down
            if not mouse_down:
                self.hold_mouse(mouse_state)
                mouse_down = True
        def release_mouse(mouse_state=False):
            "Release mouse. False for left click, True for right click."
            nonlocal mouse_down
            if mouse_down:
                self.release_mouse(mouse_state)
                mouse_down = False
        # Areas
        shake_left, shake_top, shake_right, shake_bottom, _, shake_height = self.get_areas("shake")
        fish_left, fish_top, fish_right, fish_bottom, fish_width, fish_height = self.get_areas("fish")
        friend_left, friend_top, friend_right, friend_bottom, _, _ = self.get_areas("friend")
        noiseform_left, noiseform_top, noiseform_right, noiseform_bottom, _, _ = self.get_areas("noiseform")
        # Area Calculations
        note_height = fish_bottom - shake_top
        shake_x = int((shake_left + shake_right) / 2)
        shake_y = int((shake_top + shake_bottom) / 2)
        fish_center_x_relative = fish_width / 2
        fish_center_x = fish_center_x_relative + fish_left
        fish_center_y = int((fish_top + fish_bottom) / 2)
        fish_overlay = self.vars["fish_overlay"]
        if fish_overlay == "on":
            # Position The Overlay Just Above Or Below The Fish Bar So It Does
            # Not Cover The Actual Minigame.  Show() Expects (Left, Top, Width,
            # Height) In Physical Pixels — Not Right/Bottom.
            if fish_center_y > HALF_HEIGHT:
                fish_top_overlay = fish_top + fish_height + fish_height
            else:
                fish_top_overlay = fish_top - fish_height - fish_height
            overlay_width = fish_right - fish_left
            overlay_height = int(fish_height / 1.5)
            self.fish_overlay.resize(
                fish_left,
                fish_top_overlay,
                overlay_width,
                overlay_height,
            )
        # Colors
        left_color = self.vars["left_color"]
        right_color = self.vars["right_color"]
        arrow_color = self.vars["arrow_color"]
        fish_color = self.vars["fish_color"]
        pinion_notes_color = self.vars["pinion_notes_color"]
        friends_color = self.vars["friends_color"]
        # Tolerance
        try:
            left_tolerance = int(self.vars["left_tolerance"])
            right_tolerance = int(self.vars["right_tolerance"])
            arrow_tolerance = int(self.vars["arrow_tolerance"])
            fish_tolerance = int(self.vars["fish_tolerance"])
            pinion_notes_tolerance = int(self.vars["pinion_notes_tolerance"])
            friends_tolerance = int(self.vars["friends_tolerance"])
        except:
            left_tolerance = 8
            right_tolerance = 8
            arrow_tolerance = 8
            fish_tolerance = 4
            pinion_notes_tolerance = 5
            friends_tolerance = 5
        # Minigame Settings
        scale = get_scale_factor()
        bag_slot = str(self.vars["bag_slot"])
        bag_spam = self.vars["bag_spam"]
        lock_cursor = self.vars["lock_cursor"]
        fishing_mode = self.vars["fishing_mode"].lower()
        fishing_profile = self.vars["fishing_profile"].lower()
        restart_method = self.vars["restart_method"]
        bar_ratio_from_side = float(self.vars["bar_ratio_from_side"])
        restart_delay = float(self.vars["restart_delay"])
        self.scan_delay = float(self.vars["minigame_scan_delay"])
        controller_mode = self.vars["controller_mode"].lower()
        kp = max(abs(float(self.vars["kp"])), 0.01)
        kd = max(abs(float(self.vars["kd"])), 0.01)
        stopping_distance = max(abs(float(self.vars["stopping_distance"])), 0.01)
        velocity_smoothing = min(max(abs(float(self.vars["velocity_smoothing"])), 0.01), 1.0)
        # Utility Settings
        pinion_note_ratio = float(self.vars["pinion_note_ratio"])
        # State Flags & Timers
        is_initial_run = True
        bar_detected = False
        self.catch_success = 0
        last_time = time.perf_counter()
        # Teleport Detection Variables  Prevent Sudden Jumps Unless Consistent
        # Use Percentage-Based Threshold: If Line Moves > 50% Of Screen Width, It'S Likely Detection Error
        # At 1032Px Width, 50%  ~516Px, Which Catches Major Detection Errors While Allowing Natural Movement
        TELEPORT_THRESHOLD_PERCENT = 0.50  # 50% of fish area width
        TELEPORT_THRESHOLD = int(fish_center_x_relative * TELEPORT_THRESHOLD_PERCENT)  # Convert to pixels
        TELEPORT_CONFIRM_TIME = 0.15  # Time in seconds to confirm a teleport (150ms)
        # Tracking For Potential Teleports
        potential_teleport_target_left = None
        potential_teleport_target_right = None
        potential_teleport_left_bar = None
        potential_teleport_right_bar = None
        teleport_first_detected_time = None
        initial_target_gap = None
        # Current Minigame Frame Tracking
        bar_size = 0
        bar_center = 0
        error = 0
        line_coords = []
        note_x = 0
        note_y_ratio = 0
        time_delta = 0
        mouse_delay_counter = 0
        # Failsafe & Previous Frame Tracking (History)
        last_capture_id = 0
        last_fish_x = fish_center_x_relative
        last_fish_x2 = None
        last_left_x = fish_center_x_relative - (fish_width * 0.15)
        last_right_x = fish_center_x_relative + (fish_width * 0.15)
        last_bar_center = fish_center_x_relative
        last_bar_size = 0
        last_error = 0
        last_bar_velocity = fish_width
        # Velocities & Mechanics
        right_bar_cycle = 0
        bag_spam_cycle = 0
        frame_interpolation_cycle = 0
        color_check_bar_velocity = 0.0
        color_check_target_velocity = 0.0
        time.sleep(0.1)
        self._reset_noiseform_warn_state()
        # Load Templates for Image Search
        try:
            if fishing_mode == "image":
                left_template = cv2.imread(os.path.join(CONFIGS_PATH, self.active_config, "left_bar.png"))
                right_template = cv2.imread(os.path.join(CONFIGS_PATH, self.active_config, "right_bar.png"))
                left_template2 = cv2.imread(os.path.join(CONFIGS_PATH, self.active_config, "left_bar2.png"))
                right_template2 = cv2.imread(os.path.join(CONFIGS_PATH, self.active_config, "right_bar2.png"))
                fish_template = cv2.imread(os.path.join(CONFIGS_PATH, self.active_config, "fish.png"))
        except:
            fishing_mode = "color" # Fallback
        # Loop
        while self.macro_running:
            current_time = time.perf_counter()
            # Check If Dxcam Is Available
            if dxcam is not None:
                self.capture_frame = self.camera.get_latest_frame()
                self.capture_id = last_capture_id + 1
            # Get Image From Self.Capture_Frame
            if self.capture_id == last_capture_id:
                time.sleep(self.scan_delay)
                continue
            elif self.capture_frame is None:
                time.sleep(self.scan_delay)
                continue

            else:
                shake_img = self.capture_frame[shake_top:fish_bottom, fish_left:fish_right]
                fish_img = self.capture_frame[fish_top:fish_bottom, fish_left:fish_right]
                friend_img = self.capture_frame[friend_top:friend_bottom, friend_left:friend_right]
                noiseform_img = self.capture_frame[noiseform_top:noiseform_bottom, noiseform_left:noiseform_right]
            # Reset Per-Frame Detection So A Failed Line Scan Cannot
            # Reuse Stale Coordinates From The Previous Iteration.
            left_x = None
            right_x = None
            fish_x = None
            fish_x2 = None
            # Fish Detection
            fish_x, fish_y = self.pixel_search(fish_img, fish_color, fish_tolerance)
            if fish_x is not None:
                fish_detected = True
            else:
                fish_detected = False
            # Bar Detection (Color Or Line)
            if fishing_mode == "color":
                left_x, left_y = self.pixel_search(fish_img, left_color, left_tolerance)
                # Only scan the bar size once every 10 times the scan delay
                right_bar_cycle += time_delta
                if right_bar_cycle > (self.scan_delay * 10):
                    right_bar_cycle = 0
                if right_bar_cycle == 0:
                    right_x, right_y = self.pixel_search(fish_img, right_color, right_tolerance, 1)
                else:
                    try:
                        right_x = left_x + last_bar_size
                    except:
                        right_x = last_right_x
                if left_x == None:
                    left_x, left_y = self.pixel_search(fish_img, right_color, right_tolerance)
                if right_x == None:
                    right_x, right_y = self.pixel_search(fish_img, left_color, left_tolerance, 1)
                # print(f"Raw coordinates: {left_x}, {right_x}, {fish_x}")
                # Check If We Should Scan For Arrows
                if left_x is not None and right_x is not None:
                    bar_detected = True
                    self.status_overlay.set_line(1, "Detection Source: ", "Bar")
                elif left_x is not None and (last_right_x is not None or last_bar_size):
                    # Only The Left Edge Was Found — Keep The Bar Live And
                    # Fill The Missing Right Edge From Last Size / Last Right.
                    if last_bar_size:
                        right_x = left_x + last_bar_size
                    elif last_right_x is not None:
                        right_x = last_right_x
                    bar_detected = True
                elif right_x is not None and (last_left_x is not None or last_bar_size):
                    # Only The Right Edge Was Found — Fill The Missing Left.
                    if last_bar_size:
                        left_x = right_x - last_bar_size
                    elif last_left_x is not None:
                        left_x = last_left_x
                    bar_detected = True
                else:
                    # Try Arrow
                    bar_detected = False
                    # Bars Not Found  Scan For Arrows
                    arrow_x, arrow_y = self.pixel_search(fish_img, arrow_color, arrow_tolerance)
                    # Reconstruct Missing Bar Edge From Previous Geometry Instead Of Mouse State
                    if arrow_x is not None:
                        # Treat 0 As Unknown To Match The Previous None Semantics
                        if last_left_x == 0:
                            last_left_x = None
                        if last_right_x == 0:
                            last_right_x = None
                        # If Exactly One Edge Is Missing, Reconstruct It Using The Last Known Bar Size
                        if last_left_x is None and last_right_x is not None:
                            last_left_x = last_right_x - last_bar_size
                        elif last_right_x is None and last_left_x is not None:
                            last_right_x = last_left_x + last_bar_size
                    if arrow_x is not None:
                        bar_detected = True
                        arrow_on_left_side = arrow_x < last_bar_center
                        dist_to_left = abs(arrow_x - last_left_x) if last_left_x is not None else fish_width
                        dist_to_right = abs(arrow_x - last_right_x) if last_right_x is not None else fish_width
                        proximity_threshold = int(last_bar_size / 4)
                        # Flip Decision If Wrong
                        if arrow_on_left_side:
                            if dist_to_right < dist_to_left and dist_to_right < proximity_threshold:
                                # Arrow Is Actually Closer To Right Bar  We Were Wrong!
                                arrow_on_left_side = False  # Flip the decision
                        else:
                            if dist_to_left < dist_to_right and dist_to_left < proximity_threshold:
                                # Arrow Is Actually Closer To Left Bar  We Were Wrong!
                                arrow_on_left_side = True  # Flip the decision
                        if arrow_on_left_side:
                            left_x = arrow_x
                            right_x = last_right_x
                            if right_x is None:
                                right_x = left_x + last_bar_size
                        else:
                            right_x = arrow_x
                            left_x = last_left_x
                            if left_x is None:
                                left_x = right_x - last_bar_size
                        self.status_overlay.set_line(1, "Detection Source: ", "Arrows")
                    else:
                        # Use Cache
                        bar_detected = False
                        self.status_overlay.set_line(1, "Detection Source: ", "Cache")
                try:
                    bar_center = int((left_x + right_x) / 2)
                    bar_size = right_x - left_x
                except:
                    bar_center = 0
                    bar_size = 0
            elif fishing_mode == "line":
                # Line Mode: Handle Cache Logic Inside The Branch
                line_coords = self._detect_lines_in_frame(fish_img)
                bar_detected = False
                fish_detected = False
                if len(line_coords) > 2:
                    if is_initial_run or initial_target_gap is None:
                        # Initial Run: Find 2 Closest Lines To Center As Target Lines
                        distance_coords = sorted([(abs(coord - fish_center_x_relative), coord) for coord in line_coords], key=lambda x: x[0])
                        target_pair = sorted([distance_coords[0][1], distance_coords[1][1]])
                        fish_x = target_pair[0]
                        fish_x2 = target_pair[1]
                        initial_target_gap = fish_x2 - fish_x
                        # Find Bars  Closest To Left Of Left Target, Closest To Right Of Right Target
                        left_candidates = [x for x in line_coords if x < fish_x]
                        right_candidates = [x for x in line_coords if x > fish_x2]
                        left_x = max(left_candidates) if left_candidates else fish_x
                        right_x = min(right_candidates) if right_candidates else fish_x2
                        if int(fish_width / 50) < (fish_x2 - fish_x):
                            fish_x2 = fish_x + int(fish_width / 50)
                            right_x = target_pair[1]
                        # Store For Next Run
                        last_fish_x = fish_x
                        last_fish_x2 = fish_x2
                        last_left_x = left_x
                        last_right_x = right_x
                        # print(f"📏 Initial: Target=({fish_x}, {fish_x2}), Gap={initial_target_gap}, Bars=({left_x}, {right_x})")
                        self.status_overlay.set_line(3, "Initial Positions: ", f"{fish_x}, {left_x}, {right_x}")
                        is_initial_run = False
                    else:
                        # Subsequent Runs: Simple Rules
                        # Rule 1: Find Pair With Gap Matching initial_target_gap
                        best_gap_diff = float('inf')
                        fish_x = last_fish_x
                        fish_x2 = last_fish_x2
                        for i in range(len(line_coords) - 1):
                            curr_left = line_coords[i]
                            curr_right = line_coords[i + 1]
                            curr_gap = curr_right - curr_left
                            gap_diff = abs(curr_gap - initial_target_gap)
                            if gap_diff < best_gap_diff:
                                best_gap_diff = gap_diff
                                fish_x = curr_left
                                fish_x2 = curr_right
                        # If Best Gap Is More Than 4X Initial Gap, Keep Old Positions
                        actual_gap = fish_x2 - fish_x
                        if actual_gap > initial_target_gap * 4:
                            fish_x = last_fish_x
                            fish_x2 = last_fish_x2
                        # Rule 2: Bars  Line Closest To Old Bar Position
                        # Critical: Exclude Target Lines From Bar Candidates
                        other_lines = [x for x in line_coords if x != fish_x and x != fish_x2]
                        if len(other_lines) >= 2:
                            # We Have At Least 2 Nontarget Lines - Pick Closest To Last Positions
                            if last_left_x is not None:
                                left_x = min(other_lines, key=lambda x: abs(x - last_left_x))
                            else:
                                left_x = other_lines[0]
                            # Find Closest To Last Right Bar (Excluding The One We Picked For Left)
                            remaining_lines = [x for x in other_lines if x != left_x]
                            if remaining_lines and last_right_x is not None:
                                right_x = min(remaining_lines, key=lambda x: abs(x - last_right_x))
                            elif remaining_lines:
                                right_x = remaining_lines[0]
                            else:
                                # Should Not Happen If Len(Other_Lines) > 2
                                right_x = last_right_x if last_right_x is not None else fish_x2
                        elif len(other_lines) == 1:
                            # Only 3 Total Lines (2 Target + 1 Other)
                            # Assign The Single Line To Closest Bar, Use Last Position For The Other
                            single_line = other_lines[0]
                            if last_left_x is not None and last_right_x is not None:
                                # Determine Which Bar This Line Is Closer To
                                dist_to_left = abs(single_line - last_left_x)
                                dist_to_right = abs(single_line - last_right_x)
                                if dist_to_left < dist_to_right:
                                    left_x = single_line
                                    right_x = last_right_x  # Use last position
                                else:
                                    right_x = single_line
                                    left_x = last_left_x  # Use last position
                            else:
                                # No Previous Positions - Just Assign To Left Bar
                                left_x = single_line
                                right_x = fish_x2  # Fallback
                        else:
                            # No Other Lines Besides Targets (Only 2 Total Lines)
                            # Use Last Known Bar Positions Only  Never Use Target Lines As Bars
                            left_x = last_left_x if last_left_x is not None else fish_x
                            right_x = last_right_x if last_right_x is not None else fish_x2
                    # Percentage-Based Anti-Teleport Validation
                    # Check If Lines Jumped More Than Threshold (Likely Detection Error Or Occlusion)
                    if last_fish_x is not None and last_fish_x2 is not None:
                        # Calculate Actual Jump Distances
                        target_left_jump = abs(fish_x - last_fish_x)
                        target_right_jump = abs(fish_x2 - last_fish_x2)
                        left_bar_jump = abs(left_x - last_left_x) if last_left_x is not None else 0
                        right_bar_jump = abs(right_x - last_right_x) if last_right_x is not None else 0
                        max_jump = max(target_left_jump, target_right_jump, left_bar_jump, right_bar_jump)
                        # If Movement Exceeds Threshold Percentage Of Screen Width, It Might Be A Teleport
                        if max_jump > TELEPORT_THRESHOLD:
                            # Potential Teleport - Check If It'S Consistent At This New Position
                            if (potential_teleport_target_left == fish_x and
                                potential_teleport_target_right == fish_x2 and
                                potential_teleport_left_bar == left_x and
                                potential_teleport_right_bar == right_x):
                                # Same Position Detected Again - Track Time
                                if teleport_first_detected_time is None:
                                    teleport_first_detected_time = current_time
                                # Check If Teleport Has Been Consistent Long Enough
                                time_since_first_detection = current_time - teleport_first_detected_time
                                if time_since_first_detection >= TELEPORT_CONFIRM_TIME:
                                    # Teleport Confirmed - Accept New Positions
                                    # print(f"⚠️ TELEPORT CONFIRMED after {time_since_first_detection:.3f}s - Accepting new positions (jump: {max_jump:.0f}px > {TELEPORT_THRESHOLD}px threshold)")
                                    self.status_overlay.set_line(3, "Teleport confirmed after: ", time_since_first_detection)
                                    last_fish_x = fish_x
                                    last_fish_x2 = fish_x2
                                    last_left_x = left_x
                                    last_right_x = right_x
                                    # Reset Teleport Tracking
                                    potential_teleport_target_left = None
                                    potential_teleport_target_right = None
                                    potential_teleport_left_bar = None
                                    potential_teleport_right_bar = None
                                    teleport_first_detected_time = None
                                else:
                                    # Still Confirming - Use Old Positions For Tracking
                                    self.status_overlay.set_line(3, "Potential Teleport: ", f"{max_jump:.0f}px > {TELEPORT_THRESHOLD}px")
                                    # print(f"⏳ Potential teleport (jump: {max_jump:.0f}px > {TELEPORT_THRESHOLD}px, confirming: {time_since_first_detection:.3f}s/{TELEPORT_CONFIRM_TIME}s) - Using last positions")
                                    fish_x = last_fish_x
                                    fish_x2 = last_fish_x2
                                    left_x = last_left_x
                                    right_x = last_right_x
                            else:
                                # New Potential Teleport Position - Start Tracking
                                potential_teleport_target_left = fish_x
                                potential_teleport_target_right = fish_x2
                                potential_teleport_left_bar = left_x
                                potential_teleport_right_bar = right_x
                                teleport_first_detected_time = current_time
                                # Use Old Positions While Confirming
                                self.status_overlay.set_line(3, "New Teleport: ", f"{max_jump:.0f}px > {TELEPORT_THRESHOLD}px")
                                # print(f"🔍 New teleport candidate detected (jump: {max_jump:.0f}px > {TELEPORT_THRESHOLD}px threshold) - Starting confirmation")
                                fish_x = last_fish_x
                                fish_x2 = last_fish_x2
                                left_x = last_left_x
                                right_x = last_right_x
                        else:
                            # Normal Movement - Accept Immediately And Reset Teleport Tracking
                            last_fish_x = fish_x
                            last_fish_x2 = fish_x2
                            last_left_x = left_x
                            last_right_x = right_x
                            potential_teleport_target_left = None
                            potential_teleport_target_right = None
                            potential_teleport_left_bar = None
                            potential_teleport_right_bar = None
                            teleport_first_detected_time = None
                    else:
                        # First Run - Just Accept Positions
                        last_fish_x = fish_x
                        last_fish_x2 = fish_x2
                        last_left_x = left_x
                        last_right_x = right_x
                # Line Mode Previously Never Set Bar_Detected / Bar_Center, So
                # The Overlay Could Move (Left_X/Right_X) While Predictive
                # Velocity Stayed At 0 (Bar_Center Frozen At Last_Bar_Center).
                if left_x is not None and right_x is not None:
                    bar_detected = True
                    bar_size = right_x - left_x
                    bar_center = (left_x + right_x) / 2.0
                if fish_x is not None:
                    fish_detected = True
            elif fishing_mode == "image":
                try:
                    left_x, left_y, left_confidence = self.image_search(fish_img, left_template)
                    right_x, right_y, right_confidence = self.image_search(fish_img, right_template)
                    if left_x is None:
                        left_x, left_y, left_confidence = self.image_search(fish_img, left_template2)
                    if right_x is None:
                        right_x, right_y, right_confidence = self.image_search(fish_img, right_template2)
                    fish_x, fish_y, fish_confidence = self.image_search(fish_img, fish_template)
                    bar_detected = True if left_x is not None and right_x is not None else False
                    fish_detected = True if fish_x is not None else False
                    print(left_x, right_x, fish_x)
                    try:
                        bar_center = int((left_x + right_x) / 2)
                        bar_size = right_x - left_x
                        print(f"Calculation success: {bar_center} and {bar_size}")
                    except:
                        bar_center = 0
                        bar_size = 0
                        print("Calculation failed: 0 and 0")
                except:
                    fishing_mode == "color"
            # Friend And Fish Restart
            if restart_method == "friend_area":
                friend_x, friend_y = self.pixel_search(friend_img, friends_color, friends_tolerance)
                if friend_x is not None and friend_y is not None:
                    self.interruptible_sleep(restart_delay)
                    return

            else:
                try:
                    if fish_x is None:
                        self.interruptible_sleep(restart_delay)
                        return

                except:
                    time.sleep(self.scan_delay)
                    continue

            # print(f"bar_detected: {bar_detected}")
            # print(f"left_x: {left_x}, right_x: {right_x}")
            # print(f"bar_center: {bar_center}, bar_size: {bar_size}")
            # Bag Spam & Lock Cursor
            bag_spam_cycle += 1
            if bag_spam_cycle == 5:
                bag_spam_cycle = 0
                if bag_spam == "on":
                    self._send_key(bag_slot)
                if lock_cursor == "on":
                    mouse_controller.position = (int(shake_x / scale), int(shake_y / scale))
            # Restore From Cache
            self.fish_overlay.clear()
            if bar_detected == False:
                left_x = last_left_x
                right_x = last_right_x
                bar_center = last_bar_center
                bar_size = last_bar_size
                bar_detected = True
            if fish_detected == False:
                fish_x = last_fish_x
                fish_detected = True
            # Set Status
            try:
                bar_velocity2 = round(bar_center - last_bar_center, 2)
                self.status_overlay.set_line(2, "Bar Velocity: ", bar_velocity2)
            except:
                bar_velocity2 = 0
                self.status_overlay.set_line(2, "", "")
            # Shapes Detection (Noiseform warn flash + bar-zone target)
            if fishing_profile == "shapes":
                noiseform_color, zone_x = self.detect_noiseform_target(noiseform_img, fish_img)
                if zone_x is not None:
                    fish_x = zone_x
                kind_label = noiseform_color or self._noise_zone_kind or "-"
                self.status_overlay.set_line(3, "Shape: ", kind_label if zone_x is None else f"{kind_label} @ {zone_x}")
            # Note Detection
            if fishing_profile == "notes":
                note_x, note_y = self.pixel_search(shake_img, pinion_notes_color, pinion_notes_tolerance)
                if note_x is not None and note_y is not None:
                    note_y_ratio = round(float(note_y / note_height), 2)
                    if note_y_ratio > pinion_note_ratio:
                        fish_x = note_x
                else:
                    note_y_ratio = 0.0
                self.status_overlay.set_line(3, "Note Position: ", note_y_ratio)
                # print("Note Ratio: ", note_y_ratio, " Pinion Ratio: ", pinion_note_ratio)
                # print("Fish: ", fish_x, " Note: ", note_x)
            else:
                # print("Note Tracking Disabled")
                note_y_ratio = 0.0
            if fishing_profile == "notes":
                # Catch Fails If The Note Ratio Becomes 1 And The Bar Can'T Catch It; Stays Success Only If Note Ratio Is Less Than 0.9
                if note_y_ratio > 0.9:
                    self.catch_success = 1
            else:
                # Catch Fails If The Fish Ever Leaves The Bar; Stays Success Only If Fish Stays Inside The Whole Time
                if left_x is not None and right_x is not None and fish_x is not None:
                    if not (left_x <= fish_x <= right_x):
                        self.catch_success = 1
            # Edge Boundary
            if bar_size is not None:
                boundary = bar_size * bar_ratio_from_side
                left_boundary = boundary
                right_boundary = fish_right - boundary - fish_left
            else:
                left_boundary = None
                right_boundary = fish_width
            # print("Boundary: ", left_boundary, right_boundary, " Fish: ", fish_x)
            # print("Last Cache: ", bar_center - last_bar_center)
            # Clamp Extreme Values
            if left_x is not None:
                left_x = min(abs(left_x), fish_width)
            if right_x is not None:
                right_x = min(abs(right_x), fish_width)
            if fish_x is not None:
                fish_x = min(abs(fish_x), fish_width)
            # Recompute Bar Geometry From The Same Edges The Overlay Draws
            # So Predictive Velocity Matches What The User Sees.
            if left_x is not None and right_x is not None:
                bar_size = right_x - left_x
                bar_center = (left_x + right_x) / 2.0
            # Fish Overlay
            if fish_overlay == "on":
                if fishing_mode == "color":
                    self.fish_overlay.draw_box(
                        x1=left_x, y1=overlay_height*0.15, x2=right_x, y2=overlay_height*0.85, color="green",
                        show_bar_center=True
                    )
                    if left_boundary is not None:
                        self.fish_overlay.draw_box(
                            x1=left_boundary, y1=overlay_height*0.15, x2=left_boundary + 15, y2=overlay_height*0.85, color="lightblue"
                        )
                    if right_boundary is not None:
                        self.fish_overlay.draw_box(
                            x1=right_boundary - 15, y1=overlay_height*0.15, x2=right_boundary, y2=overlay_height*0.85, color="lightblue"
                        )
                    if fish_x is not None:
                        self.fish_overlay.draw_box(
                            x1=fish_x, y1=overlay_height*0.15, x2=fish_x + 15, y2=overlay_height*0.85, color="red"
                        )
                else:
                    if bar_center > 0 and bar_size > 0 and fish_x > 0:
                        self.fish_overlay.draw_box(
                            x1=left_x, y1=overlay_height*0.15, x2=right_x, y2=overlay_height*0.85, color="green",
                            show_bar_center=True
                        )
                        self.fish_overlay.draw_box(
                            x1=fish_x, y1=overlay_height*0.15, x2=fish_x + 15, y2=overlay_height*0.85, color="red",
                        )
                    else:
                        for pos in range(len(line_coords)):
                            self.fish_overlay.draw_box(x1=line_coords[pos], y1=overlay_height*0.15, x2=line_coords[pos], y2=overlay_height*0.85, color="green")
            # Time Delta Is Measured Between Captured Frames.
            time_delta = current_time - last_time
            if time_delta < 0.001:
                time_delta = 0.001
            # Reset PID state after switched targets to note
            if fishing_profile == "notes":
                if fish_x == note_x:
                    if last_fish_x != note_x:
                        last_error = 0
            elif fishing_profile == "shapes":
                if fish_x == zone_x:
                    if last_fish_x != zone_x:
                        last_error = 0
            # print("(left_x - last_left_x) / time_delta:", (left_x - last_left_x) / self.scan_delay)
            if fish_x is not None:
                error = fish_x - bar_center
            else:
                error = 0
                fish_x = 0
            if (fish_x < left_boundary):
                control_signal = -30
            elif (fish_x > right_boundary):
                control_signal = 30
            else:
                if controller_mode == "normal":
                    # Normal: Traditional Pd Controller
                    if is_initial_run == True:
                        control_signal = 0
                        last_error = error
                    else:
                        p_term_multiplier = time_delta / self.scan_delay
                        p_term = int(error / p_term_multiplier) * kp
                        d_term = ((error - last_error) / time_delta) * kd
                        control_signal = p_term + d_term
                        # print("error - last_error: ", error - last_error)
                        # print("time_delta: ", time_delta)
                        # print("p_term: ", p_term)
                        # print("d_term: ", d_term)
                        last_error = error
                elif controller_mode == "steady":
                    # Steady: Asymmetric Pd Controller With Asymmetric Damping
                    if is_initial_run == True:
                        control_signal = 0
                        last_error = error
                    else:
                        p_term_multiplier = time_delta / self.scan_delay
                        p_term = int(error / p_term_multiplier) * kp
                        bar_velocity = bar_center - last_bar_center
                        error_magnitude_decreasing = abs(error) < abs(last_error)
                        bar_moving_toward_target = (
                            (bar_velocity > 0 and error > 0)
                            or (bar_velocity < 0 and error < 0)
                        )
                        if note_y_ratio > pinion_note_ratio:
                            steady_kd_multiplier = 0.5
                        elif error_magnitude_decreasing and bar_moving_toward_target:
                            steady_kd_multiplier = 5.0
                        else:
                            steady_kd_multiplier = 0.2
                        d_term = ((error - last_error) / time_delta) * kd * steady_kd_multiplier
                        control_signal = p_term + d_term
                        last_error = error
                elif controller_mode == "predictive":
                    # Predictive: Predictive Controller With Linear Stopping Distance And Counter-thrust
                    # Init Failsafe
                    if color_check_bar_velocity is None:
                        color_check_bar_velocity = 0.0
                    if color_check_target_velocity is None:
                        color_check_target_velocity = 0.0
                    # Missing Data Failsafe
                    if fish_x is None or bar_center is None:
                        control_signal = -30
                    # Calculate Velocities
                    if last_bar_center is not None and last_fish_x is not None:
                        if time_delta > 0:
                            raw_bar_velocity = (bar_center - last_bar_center) / time_delta
                            # If The Center Is Unchanged But The Overlay Edges Moved
                            # (Resize / One-Edge Fill), Use Average Edge Velocity.
                            if (
                                raw_bar_velocity == 0
                                and last_left_x is not None
                                and last_right_x is not None
                                and left_x is not None
                                and right_x is not None
                            ):
                                edge_velocity = (
                                    (left_x - last_left_x) + (right_x - last_right_x)
                                ) / (2.0 * time_delta)
                                if edge_velocity != 0:
                                    raw_bar_velocity = edge_velocity
                            raw_target_velocity = (fish_x - last_fish_x) / time_delta
                            color_check_bar_velocity = (velocity_smoothing * raw_bar_velocity + 
                                                        (1 - velocity_smoothing) * color_check_bar_velocity)
                            color_check_target_velocity = (velocity_smoothing * raw_target_velocity + 
                                                            (1 - velocity_smoothing) * color_check_target_velocity)
                    # Calculate Error And Relative Velocity First
                    try:
                        relative_velocity = float(color_check_bar_velocity - color_check_target_velocity)
                    except:
                        color_check_bar_velocity = 0
                        color_check_target_velocity = 0
                        control_signal = -30
                    # Nan Guard After Variables Are Defined
                    if not np.isfinite(relative_velocity):
                        control_signal = -30
                    # Calculate Stopping Distance Based On Relative Velocity
                    stopping_distance2 = abs(relative_velocity) * stopping_distance
                    # Debug
                    # print("raw_bar_velocity: ", round(raw_bar_velocity, 2), "raw_target_velocity: ", round(raw_target_velocity, 2))
                    # print("time_delta: ", round(time_delta, 2))
                    # print("color_check_bar_velocity: ", round(color_check_bar_velocity, 2))
                    # print("color_check_target_velocity: ", round(color_check_target_velocity, 2))
                    # print("relative_velocity: ", round(relative_velocity, 2))
                    # print("stopping_distance: ", round(stopping_distance2, 2))
                    if left_x <= fish_x <= right_x:
                        # On-bar: Use Stopping-distance / Counter-thrust Logic
                        if error > stopping_distance2:
                            # Bar Is Left Of Fish Beyond Stopping Distance → Hold To Move Right
                            self.status_overlay.set_line(3, "Tracking:", "> (Chase)")
                            control_signal = 30
                        elif error < -stopping_distance2:
                            # Bar Is Right Of Fish Beyond Stopping Distance → Release To Move Left
                            self.status_overlay.set_line(3, "Tracking:", "< (Chase)")
                            control_signal = -30
                        else:
                            # Within Stopping Distance — Counter-thrust Based On Relative Velocity
                            if relative_velocity > 0:
                                # Bar Moving Right Relative To Fish → Release (Apply Left Thrust)
                                self.status_overlay.set_line(3, "Tracking:", "< (Relative)")
                                control_signal = -30
                            else:
                                # Bar Moving Left Relative To Fish → Hold (Apply Right Thrust)
                                self.status_overlay.set_line(3, "Tracking:", "> (Relative)")
                                control_signal = 30
                    else:
                        control_signal = kp * error + kd * relative_velocity
                        self.status_overlay.set_line(3, "Tracking:", "> (PD)" if control_signal > 0 else "< (PD)")
                else:
                    control_signal = error
            # Mouse State
            # print(f"error: {error}")
            # print(f"control_signal: {control_signal}")
            if control_signal > 0:
                hold_mouse()
            else:
                release_mouse()
            # Update Cache
            try:
                last_bar_velocity = (bar_center - last_bar_center) / time_delta
            except:
                last_bar_velocity = fish_width
            if bar_detected == True:
                last_left_x = left_x
                last_right_x = right_x
                last_bar_center = bar_center
                last_bar_size = bar_size
            if fish_detected == True:
                if not fish_x == note_x:
                    last_fish_x = fish_x
            last_time = current_time
            # Cleanup
            is_initial_run = False
            last_capture_id = self.capture_id
            time.sleep(self.scan_delay)
        return

    def stop_macro(self, text="Macro Stopped"):
        self.macro_running = False
        try:
            self.fish_overlay.hide()
        except:
            pass
        try:
            self.status_overlay.hide()
        except:
            pass

        if (
            self.macro_thread
            and self.macro_thread.is_alive()
            and self.macro_thread is not threading.current_thread()
        ):
            self.macro_thread.join()
        if (
            self.capture_thread
            and self.capture_thread.is_alive()
            and self.capture_thread is not threading.current_thread()
        ):
            self.capture_thread.join()
        # Fully Release Dxcamera So A Later Dxcam.Create() Does Not Hit The
        # "instance already exists ... Delete the old object with `del obj`" warning.
        try:
            if self.camera is not None:
                try:
                    self.camera.stop()
                except Exception:
                    pass
                try:
                    del self.camera
                except Exception:
                    pass
                self.camera = None
        except Exception:
            pass
        if not text == "":
            self.set_status(text)
        try:
            window.show()
        except Exception:
            pass

def check_setup_guide():
    try:
        with open(os.path.join(UI_PATH, "index.html"), "r", encoding="utf-8-sig") as file:
            lines = file.readline().strip()
        with open(os.path.join(UI_PATH, "style.css"), "r", encoding="utf-8-sig") as file:
            lines = file.readline().strip()
        with open(os.path.join(UI_PATH, "app.js"), "r", encoding="utf-8-sig") as file:
            lines = file.readline().strip()
    except FileNotFoundError:
        open_folder_choice = messagebox.askyesno("Missing Files", """Your installation is missing the images or UI folder.
        Please report this bug in the Discord Server.\n
        Do you want to open the install folder?""")
        if open_folder_choice == True:
            open_folder(RESOURCE_PATH)
        return False

    try:
        with open(os.path.join(UI_PATH, "app.js"), "r", encoding="utf-8-sig") as file:
            # Read First Two Lines
            lines = [file.readline().strip() for _ in range(3)]
            # Parse First Line For App_Version
            first_line = lines[0]
            js_app_version = float(first_line.replace("const APP_VERSION = ", "").replace('"', "").replace(";", ""))
            # Parse Second Line For Beta_Version
            second_line = lines[1]
            js_beta_version = float(second_line.replace("const BETA_VERSION = ", "").replace('"', "").replace(";", ""))
            # Parse Third Line For Developer
            third_line = lines[2]
            js_developer = third_line.replace("const DEVELOPER = ", "").replace('"', "").replace(";", "")
        if js_app_version != APP_VERSION:
            messagebox.showerror("Version Mismatch", f"""
You are running version {APP_VERSION} but you're supposed to run version {js_app_version}.\nPlease report this bug in the Discord Server.
""")
            return False

        if js_beta_version != BETA_VERSION:
            if not BETA_VERSION == 0 or js_beta_version == 0:
                messagebox.showerror("Beta Version Mismatch", f"""
You are running beta {BETA_VERSION} but you're supposed to run beta {js_beta_version}.\nPlease report this bug in the Discord Server.
""")
                return False

        if js_developer != DEVELOPER:
            messagebox.showerror("Unofficial Build Detected", f"""
You tried to download an unauthorized version of Solar Fishing.\nPlease take actions against {js_developer} and download the official version.
""")
            return False

        return True

    except Exception as e:
        messagebox.showerror("Unknown Error", f"An unknown error prevented Solar Fishing from starting up:\n{e}")
    return False

setup_state = check_setup_guide()
if setup_state == False:
    sys.exit(0)
# Main Window
def on_closed():
    # Tear down child overlays so webview.start() can return. Overlay hide()
    # methods must not block the GUI thread (eyedropper schedules destroy).
    for closer in (
        api.fish_overlay.hide,
        api.status_overlay.hide,
        api.eyedropper.hide,
        api.area_selector.hide,
    ):
        try:
            closer()
        except Exception:
            pass
api = Api()
window = webview.create_window(
    f"Solar Fishing V{APP_VERSION}",
    os.path.join(UI_PATH, "index.html"),
    js_api=api,
    text_select=True,
    width=1000,
    height=700
)
window.events.closed += on_closed
webview.start()