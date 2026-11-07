# Imports
# GUI (Primary And Fallback)
import webview
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
import warnings
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
import ctypes
if sys.platform == "win32":
    from ctypes import wintypes
    try:
        import pygetwindow as gw
    except ImportError:
        gw = None
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
APP_VERSION = "2026.11.1"
BETA_VERSION = 0
DEVELOPER = "Catman2608"

def _version_components(version):
    """Parse a dotted numeric version into comparable integer components."""
    parts = str(version).split(".")
    if not parts or any(not part.isdigit() for part in parts):
        raise ValueError(f"Invalid app version: {version}")
    return tuple(int(part) for part in parts)

def _compare_versions(left, right):
    left_parts = _version_components(left)
    right_parts = _version_components(right)
    width = max(len(left_parts), len(right_parts))
    left_parts += (0,) * (width - len(left_parts))
    right_parts += (0,) * (width - len(right_parts))
    return (left_parts > right_parts) - (left_parts < right_parts)

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
    _QUARTZ_SRGB_COLOR_SPACE = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceSRGB)
    # Cache display P3 color space (what MSS typically returns on modern Macs)
    _QUARTZ_P3_COLOR_SPACE = Quartz.CGColorSpaceCreateWithName(Quartz.kCGColorSpaceDisplayP3)
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
        Quartz.kCGImageAlphaPremultipliedFirst | Quartz.kCGBitmapByteOrder32Little,
        provider, None, False, Quartz.kCGRenderingIntentDefault
    )
    # 3. Draw into an sRGB context (CoreGraphics handles exact ColorSync transformation)
    out_raw = np.empty((height, width, 4), dtype=np.uint8)
    context = Quartz.CGBitmapContextCreate(out_raw, width, height, 8, bytes_per_row, _QUARTZ_SRGB_COLOR_SPACE, Quartz.kCGImageAlphaPremultipliedLast | Quartz.kCGBitmapByteOrder32Big)
    Quartz.CGContextDrawImage(context, Quartz.CGRectMake(0, 0, width, height), src_cg_image)
    # 4. Extract BGR uint8 result matching Quartz/MSS consumers
    return np.ascontiguousarray(out_raw[:, :, :3][:, :, ::-1])

def cgimage_to_srgb_numpy(image):
    if sys.platform == "darwin":
        width = Quartz.CGImageGetWidth(image)
        height = Quartz.CGImageGetHeight(image)
        bytes_per_row = width * 4
        raw = np.empty((height, width, 4), dtype=np.uint8)
        context = Quartz.CGBitmapContextCreate(raw, width, height, 8, bytes_per_row, _QUARTZ_SRGB_COLOR_SPACE, Quartz.kCGImageAlphaPremultipliedLast | Quartz.kCGBitmapByteOrder32Big)
        if context is None:
            return None

        Quartz.CGContextDrawImage(context, Quartz.CGRectMake(0, 0, width, height), image)
        return raw[:, :, :3][:, :, ::-1]

    return image

# Reload
def reload_page(skip=True):
    if skip == False:
        return

    if sys.platform == "win32":
        # Wrap in quotes to prevent compilation issues
        args = [sys.executable, f'"{sys.argv[0]}"'] + sys.argv[1:]
        os.execv(sys.executable, args)
    else:
        # os.execv does not use a shell, so do not wrap the script path in quotes.
        # Extra quotes become part of the filename and fail on macOS/Linux.
        args = [sys.executable] + list(sys.argv)
        os.execv(sys.executable, args)
# MSS screen dimensions and attribute checking
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

    # Define the RECT structure used by Windows API
    class RECT(ctypes.Structure):
        _fields_ = [
            ("left", ctypes.c_long),
            ("top", ctypes.c_long),
            ("right", ctypes.c_long),
            ("bottom", ctypes.c_long)
        ]
    def get_taskbar_height():
        # Find the window handle for the taskbar
        hwnd = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
        if hwnd:
            rect = RECT()
            # Get the bounding rectangle coordinates
            if ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                taskbar_height = rect.bottom - rect.top
                return int(taskbar_height)

            else:
                return "Failed to get taskbar dimensions."

        else:
            return "Could not find the Windows Taskbar window."

    # Windows Api Related Functions
    def get_scale_factor():
        return 1

    def _get_hwnd(window):
        """Return a Windows HWND int from a pywebview window/native object."""
        native = getattr(window, "native", window)
        candidates = (
            native,
            getattr(native, "Handle", None),  # WinForms BrowserForm -> System.IntPtr
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

# macOS (Keyboard, Scale Factor, Mouse Button, ScreenCaptureKit)
elif sys.platform == "darwin":
    # ScreenCaptureKit (preferred capture backend on macOS 12.3+)
    try:
        import ScreenCaptureKit as _SCK
        from collections import OrderedDict
        try:
            from Foundation import NSRunLoop
        except:
            NSRunLoop = None
        from ScreenCaptureKit import (SCShareableContent, SCContentFilter, SCStreamConfiguration, SCStream, SCStreamOutputType, SCStreamOutputTypeScreen)
        from Foundation import NSDate, NSObject
        import objc
        _SCK_AVAILABLE = True
        # PyObjC exposes the enum as a NewType. Cases are module constants
        # (SCStreamOutputTypeScreen == 0), not attributes of the NewType.
        _SCK_OUTPUT_SCREEN = SCStreamOutputTypeScreen
    except Exception as e:
        _SCK = None
        SCShareableContent = None
        SCContentFilter = None
        SCStreamConfiguration = None
        SCStream = None
        SCStreamOutputType = None
        NSDate = None
        NSObject = None
        objc = None
        _SCK_AVAILABLE = False
        _SCK_OUTPUT_SCREEN = 0
    _scale_cache = None
    MAC_KEY_MAP = {
        "a": 0, "s": 1, "d": 2, "f": 3, "h": 4, "g": 5, "z": 6, "x": 7, "c": 8, "v": 9,
        "b": 11, "q": 12, "w": 13, "e": 14, "r": 15, "y": 16, "t": 17, "1": 18, "2": 19, "3": 20,
        "4": 21, "6": 22, "5": 23, "equal": 24, "9": 25, "7": 26, "minus": 27, "-": 27, "8": 28, "0": 29, "o": 31,
        "u": 32, "i": 34, "p": 35, "l": 37, "j": 38, "'": 39, "quote": 39, "apostrophe": 39, "k": 40, "semicolon": 41, "comma": 43, "slash": 44, "n": 45,
        "m": 46, "period": 47, "space": 49, "return": 36, "enter": 76, "tab": 48, "backspace": 51, "delete": 51, "escape": 53,
        "command": 55, "cmd": 55, "shift": 56, "option": 58, "alt": 58, "control": 59, "ctrl": 59,
    }
    _QUARTZ_KEY_SOURCE = None
    def get_taskbar_height():
        return 0

    def _get_quartz_key_source():
        # Private Source So Posted Keys Do Not Inherit Hardware Command/Fn/Globe State
        global _QUARTZ_KEY_SOURCE
        if _QUARTZ_KEY_SOURCE is None:
            _QUARTZ_KEY_SOURCE = Quartz.CGEventSourceCreate(Quartz.kCGEventSourceStatePrivate)
            try:
                Quartz.CGEventSourceSetLocalEventsSuppressionInterval(_QUARTZ_KEY_SOURCE, 0.0)
            except Exception:
                pass

        return _QUARTZ_KEY_SOURCE

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
    def _warp_mouse(x, y):
        """
        Instantly warps the mouse cursor to the given (x, y) coordinates
        without generating mouse-motion events.
        """
        # Define the target point
        point = Quartz.CGPointMake(float(x), float(y))
        event = Quartz.CGEventCreateMouseEvent(None, Quartz.kCGEventMouseMoved, point, Quartz.kCGMouseButtonLeft)
        # Warp the cursor
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
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
        event = Quartz.CGEventCreateMouseEvent(None, event_type, Quartz.CGPointMake(float(x), float(y)), btn)
        Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
    def send_key(key, delay=0.05, click_type=0, flags=0):
        """
        Send a keyboard event.
        click_type:
            0 = click (press + release)   [default]
            1 = hold (press only)
            2 = release (release only)
        flags: Quartz modifier mask. Default 0 so Globe/Fn is never inherited.
        """
        keycode = MAC_KEY_MAP.get(str(key).lower())
        if keycode is None:
            return

        source = _get_quartz_key_source()
        def _post_key(down):
            event = Quartz.CGEventCreateKeyboardEvent(source, keycode, down)
            if event is None:
                return

            # Explicit Flags Only. A Null Source Inherits Combined Session Flags,
            # Often Including Globe/Fn. Two Letters Then Look Like A Double
            # Globe Tap And macOS Opens Siri / Type To Siri / Dictation.
            Quartz.CGEventSetFlags(event, flags or 0)
            Quartz.CGEventPost(Quartz.kCGHIDEventTap, event)
        if click_type == 1:           # Hold (press only)
            _post_key(True)
        elif click_type == 2:         # Release only
            _post_key(False)
        else:                         # Click (press + release)
            _post_key(True)
            time.sleep(delay)
            _post_key(False)
    def send_hotkey(modifier, key, delay=0.05):
        """Modifier Down, Key Click With That Flag, Modifier Up."""
        flag_map = {
            "command": Quartz.kCGEventFlagMaskCommand,
            "cmd": Quartz.kCGEventFlagMaskCommand,
            "shift": Quartz.kCGEventFlagMaskShift,
            "option": Quartz.kCGEventFlagMaskAlternate,
            "alt": Quartz.kCGEventFlagMaskAlternate,
            "control": Quartz.kCGEventFlagMaskControl,
            "ctrl": Quartz.kCGEventFlagMaskControl,
        }
        flag = flag_map.get(str(modifier).lower(), 0)
        send_key(modifier, click_type=1, flags=flag)
        time.sleep(0.02)
        send_key(key, delay=delay, flags=flag)
        time.sleep(0.02)
        send_key(modifier, click_type=2, flags=0)
# Linux (Mouse Positions And Xdisplay)
elif sys.platform.startswith("linux"):
    _xdisplay = None
    def get_taskbar_height():
        return 0

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
        xtest.fake_input(d, X.ButtonPress if press else X.ButtonRelease, btn)
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
# Config Management
def get_base_path():
    # 1. Check If The Application Is Bundled/Frozen
    if getattr(sys, 'frozen', False):
        # Detect If It'S A macOS Application Bundle (.App)
        if sys.platform == 'darwin':
            if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
                #   Windows/Linux onedir →  <app>/_internal
                #   macOS .app           →  <app>.app/Contents/Frameworks
                #   onefile              →  temp extract dir
                return Path(sys._MEIPASS).resolve(), True

        # Detect If It'S A Linux Packaged Environment (Like Appimage)
        # Linux Appimages Extract To A Mount Point, Keeping Assets Inside The Binary Environment
        elif sys.platform == "linux":
            if 'AppRun' in sys.executable:
                return Path(sys.executable).parent.resolve(), True

        # 2. Windows Exe (Onefile) Or Standard Local Folder Deployment
        # Returns The Directory Containing The Actual .Exe File, Not The Temporary _Meipass Folder
        else:
            return Path(sys.executable).parent.resolve(), True

    # 3. Running From Raw Source Code (.Py File)
    else:
        return Path(__file__).parent.resolve(), False

# Get Read Only Path
def get_resource_path():
    """
    Packaged assets (ui/, images/, bundled default configs/).
    Compiled macOS/Linux: PyInstaller onedir --add-data folder (sys._MEIPASS, typically <app>/_internal or .app/Contents/Frameworks).
    Compiled Windows: directory next to the .exe (unchanged).
    Dev: project directory.
    """
    if getattr(sys, 'frozen', False):
        if sys.platform == "win32":
            return Path(sys.executable).parent.resolve()

        if hasattr(sys, "_MEIPASS"):
            return Path(sys._MEIPASS).resolve()

        return Path(sys.executable).parent.resolve()

    return Path(__file__).parent.resolve()
# Establish The Global Base Path For Solar Fishing V5
EDITABLE_PATH, IS_COMPILED = get_base_path()
READ_ONLY_PATH = get_resource_path()
# Make Sure Base Path Exists
os.makedirs(EDITABLE_PATH, exist_ok=True)
os.makedirs(READ_ONLY_PATH, exist_ok=True)
# Configs Path
LAST_CONFIG = os.path.join(EDITABLE_PATH, "last_config.json")
data = load_misc_settings(LAST_CONFIG)
CONFIGS_PATH = os.path.join(EDITABLE_PATH, "configs")
IMAGES_PATH = os.path.join(READ_ONLY_PATH, "images")
UI_PATH = os.path.join(READ_ONLY_PATH, "ui")
# File Management
def open_base_folder(folder=EDITABLE_PATH):
    if sys.platform == "win32":
        os.startfile(folder)
    elif sys.platform == "darwin":  # Macos
        subprocess.run(["open", folder])
    else:  # Linux
        subprocess.run(["xdg-open", folder])
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
class PointSelect:
    """
    Fullscreen overlay for selecting a screen point as normalized ratios (0-1).
    Captures a frozen screenshot (menu bar cropped so it matches the frameless window), renders it in the canvas, and returns the picked ratios.
    """
    # Prevent Pywebview From Walking This Object When The Main Api Is Js_Api
    # (Window.Native.Accessibilityobject.Bounds Recursion / Webview2 Com).
    _serializable = False
    HTML_FILE = os.path.join(UI_PATH, "point_select.html")
    def __init__(self, parent_app):
        self.parent = parent_app
        self.overlay_window = None
        self._open = False
        self._visible = False
        self.last_picked = None
        self._cancelled = False
        self._field_id = None
        self._scale = 1.0
        self._screen_capture = None
        self._screenshot_b64 = None
        self.roblox_bounds = {}
        self.left = 0
        self.top = 0
        self.width = 0
        self.height = 0
    def is_open(self):
        return self._open and self.overlay_window is not None

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
            ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
            if not ok:
                return None

            b64 = base64.b64encode(buf.tobytes()).decode("ascii")
            return "data:image/jpeg;base64," + b64

        except Exception:
            return None

    def show(self, field_id=None, roblox_bounds={}):
        """Open the point selector overlay. Optional field_id is the settings
        field that should receive the picked ratios (e.g. 'mirror_ratio').
        Thin js_api object — only exposes the methods the HTML page calls.
        Do NOT pass `self` (or any object that holds a reference to the pywebview Window): on macOS Cocoa that triggers infinite recursion
        via AccessibilityObject.Bounds.
        """
        try:
            self.roblox_bounds = roblox_bounds
        except:
            self.roblox_bounds = {}
        if self._open and self.overlay_window:
            return

        outer = self
        class _PointSelectApi:
            def window_ready(self, win_x, win_y, width=None, height=None):
                return outer.window_ready(win_x, win_y, width, height)

            def get_screenshot_data(self):
                return outer.get_screenshot_data()

            def get_geometry(self):
                return outer.get_geometry()

            def pick_point(self, ratio_x, ratio_y):
                return outer.pick_point(ratio_x, ratio_y)

            def close_point_select(self):
                return outer.close_point_select()

        self.last_picked = None
        self._cancelled = False
        self._field_id = field_id
        self._screen_capture = self._capture_and_crop()
        self._screenshot_b64 = self._encode_screenshot(self._screen_capture)
        menu_offset = get_macos_menu_offset()
        win_h = max(1, SCREEN_HEIGHT - menu_offset)
        self.left = SCREEN_LEFT
        self.top = SCREEN_TOP + int(round(menu_offset))
        self.width = SCREEN_WIDTH
        self.height = win_h
        self.overlay_window = webview.create_window("Point Select", self.HTML_FILE, js_api=_PointSelectApi(), transparent=False, frameless=True, easy_drag=False, on_top=True, resizable=False, focus=True, width=self.width, height=self.height, x=self.left, y=self.top, background_color="#000000")
        self._open = True
        self._visible = True
        self.overlay_window.events.closed += self._on_closed
        if sys.platform == "win32":
            def maximize_point_select():
                try:
                    hwnd = _get_hwnd(self.overlay_window)
                    if hwnd:
                        user32.ShowWindow(wintypes.HWND(hwnd), SW_MAXIMIZE)
                except Exception:
                    pass

            self.overlay_window.events.shown += maximize_point_select
    def hide(self):
        """Destroys the current window instance completely.
        Destroy is scheduled off the JS-API thread to avoid pywebview deadlock.
        """
        win = self.overlay_window
        if not win or not self._open:
            self._open = False
            self._visible = False
            return

        self._open = False
        self._visible = False
        self.overlay_window = None
        _schedule_webview_destroy(win, after=self._on_closed)
    def window_ready(self, win_x, win_y, width=None, height=None):
        """JS signals the page is ready — push screenshot."""
        if self._screenshot_b64 and self.overlay_window and self._open:
            try:
                self.overlay_window.evaluate_js("window.__applyScreenshot && window.__applyScreenshot()")
            except Exception:
                pass

        return None

    def get_screenshot_data(self):
        """Return the data-URL of the frozen (menu-bar-cropped) screenshot."""
        return self._screenshot_b64 or ""

    def get_geometry(self):
        """Return logical screen geometry so JS can compute full-screen ratios.
        menu_offset is the height of the cropped menu bar (logical pixels).
        screen_w / screen_h are the full logical screen dimensions.
        """
        menu_offset = get_macos_menu_offset()
        return {

            "menu_offset": float(menu_offset),
            "screen_w": float(SCREEN_WIDTH),
            "screen_h": float(SCREEN_HEIGHT),
        }
    def pick_point(self, ratio_x, ratio_y):
        """Called by JS when the user clicks.
        ratio_x / ratio_y are already normalized 0-1 relative to the overlay
        viewport (computed in JS from clientX/Y ÷ innerWidth/Height)."""
        if not self.is_open():
            return None

        try:
            rx = max(0.0, min(1.0, float(ratio_x)))
            ry = max(0.0, min(1.0, float(ratio_y)))
        except (TypeError, ValueError):
            return None

        self.last_picked = (rx, ry)
        self._cancelled = False
        label = f"{rx:.3f}, {ry:.3f}"
        # Write into settings vars when a target key was provided
        field_id = self._field_id
        if field_id:
            try:
                self.parent.vars[field_id] = label
            except Exception:
                pass

        # Notify the main webview so the input updates
        self._notify_main_ui(label, field_id)
        try:
            self.parent.set_status(f"Selected point: {label}")
        except Exception:
            pass

        self.hide()
        return label

    def close_point_select(self):
        """Called by JS on Escape — cancel without picking."""
        if not self.is_open():
            return

        self._cancelled = True
        self.last_picked = None
        try:
            self.parent.set_status("Point select cancelled")
        except Exception:
            pass

        self.hide()
    def _notify_main_ui(self, label, field_id=None):
        """Push the picked ratios into the main pywebview window."""
        try:
            safe = str(label).replace("\\", "\\\\").replace("'", "\\'")
            key_js = "null"
            if field_id:
                key_js = "'" + str(field_id).replace("\\", "\\\\").replace("'", "\\'") + "'"
            script = (
                f"(function(){{"
                f"var v='{safe}',k={key_js};"
                f"if(window.onPointPicked)window.onPointPicked(v,k);"
                f"if(k){{var el=document.getElementById(k)||document.querySelector('[data-point-key=\"'+k+'\"]')"
                f"||document.querySelector('input[name=\"'+k+'\"]');"
                f"if(el){{el.value=v;el.dispatchEvent(new Event('input',{{bubbles:true}}));"
                f"el.dispatchEvent(new Event('change',{{bubbles:true}}));}}"
                f"}}"
                f"}})()"
            )
            if webview.windows:
                webview.windows[0].evaluate_js(script)
        except Exception:
            pass

    def _on_closed(self, *args):
        """Lifecycle cleanup when the overlay is destroyed."""
        self.overlay_window = None
        self._open = False
        self._visible = False
        self._screenshot_b64 = None