import json
import os
import re
import sys
import threading
import time
from pathlib import Path

import webview
from pynput.keyboard import Listener as KeyListener, Key

# Module-level only. Never store a pywebview Window on the js_api object —
# pywebview walks Window.native (WinForms / WebView2) and hits
# AccessibilityObject.Bounds.Empty... recursion plus COM UI-thread errors.
_main_window = None


def _schedule_webview_destroy(win, delay=0.05):
    """Destroy a pywebview window after the current JS/GUI call returns.

    Calling Window.destroy() from that window's js_api deadlocks pywebview
    (the bridge waits for destroy; destroy waits for the bridge). Tear the
    window down from a short-lived thread instead.
    """
    if win is None:
        return

    def _destroy():
        if delay:
            time.sleep(delay)
        try:
            win.destroy()
        except Exception:
            pass

    threading.Thread(target=_destroy, daemon=True).start()

APP_VERSION = 5.2

# Path Management (same layout as SolarFishingV5.py)
def get_base_path():
    # 1. Check if the application is bundled/frozen
    if getattr(sys, 'frozen', False):
        # Detect if it's a macOS application bundle (.app)
        # In macOS bundles, the executable runs inside Contents/MacOS/
        if sys.platform == 'darwin' and '.app/Contents/MacOS' in sys.executable:
            return Path(sys.executable).parent.resolve(), True

        # Detect if it's a Linux packaged environment (like AppImage)
        # Linux AppImages extract to a mount point, keeping assets inside the binary environment
        elif sys.platform.startswith('linux') and 'AppRun' in sys.executable:
            return Path(sys.executable).parent.resolve(), True

        # 2. Windows EXE (One-File) or standard local folder deployment
        # Returns the directory containing the actual .exe file, NOT the temporary _MEIPASS folder
        else:
            return Path(sys.executable).parent.resolve(), True

    # 3. Running from raw source code (.py file)
    else:
        return Path(__file__).parent.resolve(), False

# Establish the global base path for Solar Fishing V5
BASE_PATH, IS_COMPILED = get_base_path()
# Make sure base path exists
os.makedirs(BASE_PATH, exist_ok=True)
# Configs Path
LAST_CONFIG = os.path.join(BASE_PATH, "last_config.json")
CONFIGS_PATH = os.path.join(BASE_PATH, "configs")
IMAGES_PATH = os.path.join(BASE_PATH, "images")
UI_PATH = os.path.join(BASE_PATH, "ui")

class Api:
    def __init__(self):
        # Start Hotkey Listener
        try:
            self.key_listener = KeyListener(on_press=self.on_key_press)
            self.key_listener.daemon = True
            self.key_listener.start()
        except Exception as e:
            self.set_status(f"Key Listener error: {e}")
        self._ensure_default_config()
    def _html_attr(self, attrs, name):
        match = re.search(
            r"""\b""" + re.escape(name) + r"""\s*=\s*(?:['"]([^'"]*)['"]|([^\s>]+))""",
            attrs,
            re.IGNORECASE,
        )
        if not match:
            return None
        return (match.group(1) if match.group(1) is not None else match.group(2) or "").strip()


    def _get_prompt_defaults(self):
        """Defaults from index.html placeholders, value attributes, and first options."""
        global _PROMPT_DEFAULTS
        if _PROMPT_DEFAULTS is not None:
            return dict(_PROMPT_DEFAULTS)

        defaults = {}
        try:
            with open(UI_PATH / "index.html", "r", encoding="utf-8") as file:
                html = file.read()
        except Exception:
            _PROMPT_DEFAULTS = {}
            return {}

        try:
            for attrs in re.findall(r"<input\b([^>]*)>", html, flags=re.IGNORECASE):
                field_id = self._html_attr(attrs, "id")
                if not field_id or field_id == "config_list" or field_id.startswith("_"):
                    continue
                input_type = (self._html_attr(attrs, "type") or "text").lower()
                if input_type == "checkbox":
                    defaults[field_id] = bool(re.search(r"\bchecked\b", attrs, re.IGNORECASE))
                    continue
                if input_type in ("button", "submit", "file", "image", "hidden"):
                    continue
                value = self._html_attr(attrs, "value")
                placeholder = self._html_attr(attrs, "placeholder")
                if value is not None and value != "":
                    defaults[field_id] = value
                elif placeholder is not None and placeholder != "":
                    defaults[field_id] = placeholder
        except Exception:
            pass

        try:
            select_pattern = re.compile(
                r"<select\b([^>]*)>(.*?)</select>",
                re.IGNORECASE | re.DOTALL,
            )
            option_pattern = re.compile(
                r"<option\b([^>]*)>",
                re.IGNORECASE,
            )
            for attrs, body in select_pattern.findall(html):
                field_id = self._html_attr(attrs, "id")
                if not field_id or field_id == "config_list" or field_id.startswith("_"):
                    continue
                chosen = None
                first = None
                for option_attrs in option_pattern.findall(body):
                    option_value = self._html_attr(option_attrs, "value")
                    if option_value is None:
                        continue
                    if first is None:
                        first = option_value
                    if re.search(r"\bselected\b", option_attrs, re.IGNORECASE):
                        chosen = option_value
                        break
                defaults[field_id] = chosen if chosen is not None else (first or "")
        except Exception:
            pass

        _PROMPT_DEFAULTS = defaults
        return dict(defaults)


    def _get_saved_default_config(self):
        default_path = os.path.join(CONFIGS_PATH, "Default", "config.json")
        try:
            with open(default_path, "r", encoding="utf-8") as file:
                data = json.load(file)
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}


    def _get_config_defaults(self):
        defaults = self._get_saved_default_config()
        defaults.update(self._get_prompt_defaults())
        return defaults


    def _is_blank_setting(self, value):
        if value is None:
            return True
        if isinstance(value, str) and value.strip() == "":
            return True
        return False


    def _fill_blank_settings(self, settings):
        """Fill missing or empty keys from Default config + HTML placeholders.

        A single bad key is skipped so one corrupt value cannot wipe the rest.
        """
        filled = {}
        try:
            defaults = self._get_config_defaults()
        except Exception:
            defaults = {}

        try:
            for key, value in defaults.items():
                try:
                    if key and not str(key).startswith("_") and key != "config_list":
                        filled[key] = value
                except Exception:
                    continue
        except Exception:
            pass

        try:
            incoming = settings if isinstance(settings, dict) else {}
            for key, value in incoming.items():
                try:
                    if not key or str(key).startswith("_") or key == "config_list":
                        continue
                    if self._is_blank_setting(value):
                        continue
                    filled[key] = value
                except Exception:
                    continue
        except Exception:
            pass

        return filled


    def _safe_config_name(self, name):
        name = str(name or "").strip()
        name = os.path.basename(name)
        if name.lower().endswith(".json"):
            name = name[:-5]
        name = name.replace("\\", "").replace("/", "").strip()
        return name


    def _config_folder(self, config_name):
        return os.path.join(CONFIGS_PATH, config_name)


    def _config_file(self, config_name):
        return os.path.join(self._config_folder(config_name), "config.json")


    def _ensure_default_config(self):
        os.makedirs(CONFIGS_PATH, exist_ok=True)
        names = [
            folder
            for folder in os.listdir(CONFIGS_PATH)
            if os.path.isdir(os.path.join(CONFIGS_PATH, folder))
        ]
        if names:
            return

        folder = self._config_folder("Default")
        os.makedirs(folder, exist_ok=True)
        path = self._config_file("Default")
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as file:
                json.dump({}, file, indent=4)

    # Stop pywebview from walking this object when it is used as js_api
    # (Window.native.AccessibilityObject.Bounds recursion / WebView2 COM).
    _serializable = False

    def close_window(self):
        win = _main_window
        if win is None and webview.windows:
            win = webview.windows[0]
        _schedule_webview_destroy(win)

    def minimize_window(self):
        win = _main_window
        if win is None and webview.windows:
            win = webview.windows[0]
        if win is None:
            return
        try:
            win.minimize()
        except Exception:
            pass

    def rebind_hotkeys(self):
        self.hotkey_state = 1

    def list_configs(self):
        try:
            self._ensure_default_config()
            configs = sorted(
                [
                    folder
                    for folder in os.listdir(CONFIGS_PATH)
                    if os.path.isdir(os.path.join(CONFIGS_PATH, folder))
                ]
            )
            return configs
        except Exception:
            return []

    def get_last_config(self):
        try:
            if os.path.exists(LAST_CONFIG):
                with open(LAST_CONFIG, "r", encoding="utf-8") as file:
                    data = json.load(file)
                if isinstance(data, dict):
                    return data.get("last_config", "") or ""
        except Exception:
            pass
        return ""

    def save_last_config(self, config_name):
        config_name = self._safe_config_name(config_name)
        if not config_name:
            return False
        try:
            data = {}
            if os.path.exists(LAST_CONFIG):
                try:
                    with open(LAST_CONFIG, "r", encoding="utf-8") as file:
                        loaded = json.load(file)
                    if isinstance(loaded, dict):
                        data = loaded
                except Exception:
                    data = {}
            data["last_config"] = config_name
            os.makedirs(BASE_PATH, exist_ok=True)
            with open(LAST_CONFIG, "w", encoding="utf-8") as file:
                json.dump(data, file, indent=4)
            return True
        except Exception:
            return False

    def resolve_config_name(self, config_name):
        configs = self.list_configs()
        wanted = self._safe_config_name(config_name)
        if wanted in configs:
            return wanted
        for name in configs:
            if name.lower() == wanted.lower():
                return name
        last = self._safe_config_name(self.get_last_config())
        if last in configs:
            return last
        return configs[0] if configs else ""

    def save_settings(self, file_name, settings=None):
        try:
            # JS may call save_settings(settings) with a single dict.
            if settings is None and isinstance(file_name, dict):
                settings = file_name
                file_name = self.get_last_config() or "Default"

            if not isinstance(settings, dict):
                return {"success": False, "error": "Settings must be an object."}

            config_name = self.resolve_config_name(file_name) or self._safe_config_name(file_name)
            if not config_name:
                return {"success": False, "error": "No config selected."}

            folder = self._config_folder(config_name)
            os.makedirs(folder, exist_ok=True)
            settings = self._fill_blank_settings(settings)
            config_path = self._config_file(config_name)
            with open(config_path, "w", encoding="utf-8") as file:
                json.dump(settings, file, indent=4)
            self.save_last_config(config_name)
            return {"success": True, "config_name": config_name}
        except Exception as exc:
            return {"success": False, "error": str(exc)}

    def load_settings(self, config_name=None):
        settings = {}
        name = ""
        try:
            name = self.resolve_config_name(config_name)
        except Exception:
            name = ""

        if name:
            config_path = self._config_file(name)
            try:
                if os.path.exists(config_path):
                    with open(config_path, "r", encoding="utf-8") as file:
                        loaded = json.load(file)
                    if isinstance(loaded, dict):
                        settings = loaded
            except Exception:
                settings = {}

        settings = self._fill_blank_settings(settings)

        if name:
            try:
                self.save_last_config(name)
            except Exception:
                pass
            try:
                os.makedirs(self._config_folder(name), exist_ok=True)
                with open(self._config_file(name), "w", encoding="utf-8") as file:
                    json.dump(settings, file, indent=4)
            except Exception:
                pass

        result = dict(settings)
        if name:
            result["_config_name"] = name
        result["_success"] = True
        return result

    def on_key_press(self, key):
        print(key)

python_api = Api()
_main_window = webview.create_window(
    f"Solar Fishing V{APP_VERSION}",
    os.path.join(UI_PATH, "index.html"),
    js_api=python_api,
    width=800,
    height=600,
    frameless=True,
    easy_drag=False,
)
webview.start()
