import webview
import os
def _schedule_webview_destroy():
    pass
def get_scale_factor():
    return 1
UI_PATH = 0
SCREEN_WIDTH = 0
SCREEN_HEIGHT = 0
class TermsOfServiceDialogue:
    # Prevent Pywebview From Walking This Object When The Main Api Is Js_Api
    # (Window.Native.Accessibilityobject.Bounds Recursion / Webview2 Com).
    _serializable = False
    HTML_FILE = os.path.join(UI_PATH, "terms_of_service.html")
    def __init__(self, parent_app):
        self.parent_app = parent_app
        self._tos_dialogue = None
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
        if self._open and self._tos_dialogue:
            # If Already Open, Shift/Resize It Instead Of Duplicating
            self.resize(left, top, width, height, already_logical=True)
            return

        self.left = left
        self.top = top
        self.width = width
        self.height = height
        self._tos_dialogue = webview.create_window(
            "Fish Overlay",
            url=self.HTML_FILE,
            transparent=False,
            frameless=True,
            easy_drag=False,
            on_top=True,
            resizable=False,
            focus=False,
            width=self.width,
            height=self.height,
            x=self.left,
            y=self.top,
            background_color="#ffffff",
            min_size=(0.03 * SCREEN_WIDTH, 0.05 * SCREEN_HEIGHT),
        )
        self._open = True
        self._visible = True
        self._tos_dialogue.events.closed += self._on_closed
    def hide(self):
        """Destroys the current window instance completely.
        Clear _open BEFORE destroy so concurrent minigame threads that still
        call clear()/draw_box()/_eval skip the disposed WebView2 and avoid
        ObjectDisposedException (logged by pywebview as 'Error occurred in script').
        Destroy is scheduled off the caller thread so a stop/hotkey/shutdown
        path cannot deadlock pywebview the way Eyedropper/AreaSelector did.
        """
        win = self._tos_dialogue
        if not win or not self._open:
            self._open = False
            self._visible = False
            return

        self._open = False
        self._visible = False
        self._tos_dialogue = None
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
        if self._tos_dialogue and self._open:
            try:
                self._tos_dialogue.move(self.left, self.top)
                self._tos_dialogue.resize(self.width, self.height)
            except Exception:
                # Window May Already Be Disposed (Race With Stop_Macro / Hide)
                self._open = False
                self._tos_dialogue = None
    def _on_closed(self):
        """Internal callback cleaning lifecycle states upon execution exit."""
        self._tos_dialogue = None
        self._open = False
        self._visible = False