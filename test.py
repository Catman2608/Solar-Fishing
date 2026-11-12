import cv2, numpy as np
import threading
from collections import deque

# Noiseform logic (Ported from DeepFish BETA v1.1.7.ahk)
class GeometryDetector:
    """NoiseForm's bar is a see-through box, so its fill takes the colour of
    whatever is behind it and no bar colour can be matched. Like DeepFish,
    find it by shape instead: its two thin black borders and the black
    arrowheads just inside them. The fish is a dark green line with a
    bright green glow on both sides.
    """

    DARK = 16
    LINE_DARK = 50
    RELEARN_FRAMES = 3
    BAND_RECHECK = 6
    FORGET_AFTER = 1.5
    STILL_JITTER = 0.002
    INSET_RATIO = 0.111
    def __init__(self):
        self.reset()

    def reset(self):
        self.width = None
        self.inset = None
        self.center = None
        self.fish = None
        self.caps = None
        self.band = None
        self._misses = 0
        self._last_seen = None
        self._dt = None
        self._pending = None
        self._pending_count = 0
        self._shown_left = None
        self._shown_width = None

    @staticmethod
    def _runs(flags):
        padded = np.concatenate(([False], flags, [False])).astype(np.int8)
        step = np.diff(padded)
        return zip(np.flatnonzero(step == 1), np.flatnonzero(step == -1))

    @staticmethod
    def level(frame):
        """Brightest channel of each pixel (OpenCV: several times faster
        than numpy's max over the colour axis, which dominated detection)."""

        b, g, r = cv2.split(np.ascontiguousarray(frame[..., :3]))
        return cv2.max(cv2.max(b, g), r)

    @classmethod
    def dark(cls, frame):
        '''Pixels that are border black (see DARK and LINE_DARK).'''

        level = cls.level(frame).astype(np.int16)
        padded = np.pad(level, ((0, 0), (3, 3)), mode='edge')
        around = np.minimum(padded[:, :-6], padded[:, 6:])
        return (level <= cls.DARK) | (level <= cls.LINE_DARK) & (level * 2 <= around)

    def edges(self, frame):
        '''Centres of thin near-black columns, split into bar borders and
        arrowhead tips.

        The capture strip may sit anywhere over the track, so heights are
        compared with the tallest thin column rather than the frame: the
        borders are the tallest, the arrowheads clearly shorter.
        '''

        width = frame.shape[1]
        fill = self.dark(frame).mean(axis=0)
        thin = max(3, round(width * 0.008) + 2)
        runs = []
        for start, end in self._runs(fill >= 0.25):
            if start == 0 or end == width:
                continue
            if runs and start - runs[-1][1] <= 3:
                prev = runs.pop()
                start = prev[0]
            runs.append((start, end))
        runs = [(s_, e_, float(fill[s_:e_].max())) for s_, e_ in runs]
        tallest = max((f for s_, e_, f in runs if e_ - s_ <= thin), default=0.0)
        if tallest < 0.35:
            return [], []
        borders, arrows = [], []
        for start, end, height in runs:
            centre = (start + end - 1) / 2.0
            if end - start <= thin and height >= tallest * 0.94:
                borders.append(centre)
            else:
                if not end - start <= thin * 2.5:
                    continue
                if not height >= tallest * 0.25:
                    continue
                arrows.append(centre)
        return borders, arrows

    @staticmethod
    def track_band(frame):
        """Rows of the track, taken from the bar's black borders.

        The capture region can be much taller than the track, so find the
        thin column with the longest unbroken black run (a bar border or
        track end cap) and use the rows it spans.
        """

        dark = GeometryDetector.dark(frame)
        height, width = dark.shape
        run = np.zeros(width, np.int32)
        best = np.zeros(width, np.int32)
        bottom = np.zeros(width, np.int32)
        for y in range(height):
            run = np.where(dark[y], run + 1, 0)
            longer = run > best
            best = np.where(longer, run, best)
            bottom = np.where(longer, y + 1, bottom)
        thin = max(3, round(width * 0.008) + 2)
        padded = np.pad(best, thin)
        beside = np.maximum(padded[:width], padded[2 * thin:])
        score = np.where(beside * 2 <= best, best, 0)
        x = int(score.argmax())
        if score[x] < max(6, height * 0.2):
            return
        return int(bottom[x] - best[x]), int(bottom[x])

    @classmethod
    def _signatures(cls, borders, arrows, width, tol):
        '''(left, bar width, inset, arrowheads seen) for each border pair with
        an arrowhead at the usual distance inside one or both ends. The bar
        shrinks mid-catch and then shows only one arrowhead.'''

        found = []
        for i, left in enumerate(borders):
            for right in borders[i + 1:]:
                bar = right - left
                if not width * 0.12 <= bar <= width * 0.7:
                    continue
                expected = bar * cls.INSET_RATIO
                insets = [x - left for x in arrows if abs(x - left - expected) <= max(tol, bar * 0.04)]
                insets += [right - x for x in arrows if abs(right - x - expected) <= max(tol, bar * 0.04)]
                if insets:
                    found.append((left, bar, sum(insets) / len(insets), len(insets)))
        found.sort(key=(lambda s: -s[3]))
        return found

    def _fit(self, borders, arrows, tol):
        '''Best bar left for the learned shape, and how many edges agree.'''

        step = self.width * max(0.25, 3 * (self._dt or 0))
        roles = (0, borders), (self.inset, arrows), (self.width - self.inset, arrows), (self.width, borders)
        best = None
        for offset, pool in roles:
            for edge in pool:
                left = edge - offset
                matched = []
                for o, candidates in roles:
                    if candidates:
                        near = min(candidates, key=(lambda x: abs(x - (left + o))))
                        if abs(near - (left + o)) <= tol:
                            matched.append(near - o)
                left = sum(matched) / len(matched)
                drift = abs(left + self.width / 2.0 - self.center) if self.center is not None else 0
                key = len(matched) - drift / step, len(matched)
                if best is None or key > best[0]:
                    best = key, left, len(matched), drift
        if best is None:
            return (None, 0)
        _, left, votes, drift = best
        if votes < 4 and drift > step * 2:
            return (None, 0)
        return left, votes

    def _bar(self, frame):
        width = frame.shape[1]
        tol = max(3, round(width * 0.006))
        borders, arrows = self.edges(frame)
        if len(borders) >= 4 and borders[-1] - borders[0] > width * 0.75:
            self.caps = borders[0], borders[-1]
        if self.caps is not None:
            near = max(1.0, width * 0.002)
            borders = [b for b in borders if min((abs(b - c) for c in self.caps)) > near]
        signatures = self._signatures(borders, arrows, width, tol)
        if self.width is None:
            # Prefer a full signature (both arrowheads present).
            if signatures and signatures[0][3] == 2:
                left, self.width, self.inset = signatures[0][:3]
                self._pending, self._pending_count = None, 0
                return left
            # Otherwise learn width from plausible border pairs, but only
            # accept a pair whose implied inset matches an observed arrowhead
            # (or, when no arrowheads are visible this frame, whose width
            # agrees with the other candidate pairs).
            pairs = []
            for i, left_edge in enumerate(borders):
                for right_edge in borders[i + 1:]:
                    size = right_edge - left_edge
                    if not (width * 0.12 <= size <= width * 0.7):
                        continue
                    expected_inset = size * self.INSET_RATIO
                    arrow_tol = max(tol, size * 0.04)
                    arrow_ok = any(
                        abs(a - (left_edge + expected_inset)) <= arrow_tol
                        or abs(a - (right_edge - expected_inset)) <= arrow_tol
                        for a in arrows
                    )
                    pairs.append((left_edge, size, arrow_ok))
            if not pairs and not signatures:
                self._pending, self._pending_count = None, 0
                return
            if pairs:
                # Prefer a pair confirmed by arrowheads; otherwise take the
                # widest (bar borders are the tallest thin columns).
                confirmed = [p for p in pairs if p[2]]
                pool = confirmed or pairs
                left, size = max(pool, key=lambda p: p[1])[:2]
                if self._pending is not None and abs(size - self._pending) <= tol:
                    self._pending_count += 1
                else:
                    self._pending, self._pending_count = size, 1
                if self._pending_count < self.RELEARN_FRAMES:
                    return
                self.width, self.inset = size, size * self.INSET_RATIO
                self._pending, self._pending_count = None, 0
                return left
            return
        left, votes = self._fit(borders, arrows, tol)
        if votes >= 4:
            for s_left, s_width, s_inset, _ in signatures:
                if not abs(s_left - left) <= tol:
                    continue
                if not abs(s_width - self.width) <= tol:
                    continue
                self.width += (s_width - self.width) * 0.2
                self.inset += (s_inset - self.inset) * 0.2
                break
        if votes < 4 and signatures:
            other = [s for s in signatures if abs(s[1] - self.width) > tol]
            if other:
                if self.center is not None:
                    other.sort(key=(lambda s: (-s[3], abs(s[0] + s[1] / 2.0 - self.center))))
                size = other[0][1]
                if self._pending is not None and abs(size - self._pending) <= tol:
                    self._pending_count += 1
                else:
                    self._pending, self._pending_count = size, 1
                if self._pending_count >= self.RELEARN_FRAMES:
                    left, self.width, self.inset = other[0][:3]
                    self._pending, self._pending_count = None, 0
                    return left
                else:
                    self._pending, self._pending_count = None, 0
        if left is not None and (not -tol <= left or not left + self.width <= width + tol):
            return
        near_last = left is not None and self.center is not None and abs(left + self.width / 2.0 - self.center) <= self.width * 0.25
        if votes >= 2 or (votes == 1 and near_last):
            return left

    @staticmethod
    def _fish_candidates(frame, fish_colors, fish_tol, band=None):
        """(left, right, score) of columns where many track rows show the
        fish: a dark green core with bright green glow close by on both sides.

        Counting rows rather than taking a column median keeps the fish
        when a hazard zone or the red slash covers part of its height.
        Black arrowheads and grey hazard stripes fail the colour tests.
        The fish's capsule also sticks out above and below the track, which
        a hazard zone's edge never does, so rows there add to the score.
        """

        top, bottom = band if band is not None else (0, frame.shape[0])
        f = frame.astype(np.int16)
        blue, green, red = f[(..., 0)], f[(..., 1)], f[(..., 2)]
        core = (green >= 25) & (green <= 100) & (red <= 80) & (blue <= 100)
        for color in fish_colors or ():
            core |= (np.abs(blue - color[0]) <= fish_tol) & (np.abs(green - color[1]) <= fish_tol) & (np.abs(red - color[2]) <= fish_tol)
        glow = np.where((green >= 140) & (green - red >= 70), green, 0).astype(np.uint8)
        width = frame.shape[1]
        reach = max(4, round(width * 0.015))
        kernel = np.ones((1, reach + 1), np.uint8)
        # left_glow[y, x] = max(glow[y, x-reach .. x-1])
        right_padded = np.pad(glow, ((0, 0), (reach, 0)), mode='constant')
        left_glow = cv2.dilate(right_padded, kernel, anchor=(reach, 0))
        left_glow[:, :reach] = 0
        # right_glow[y, x] = max(glow[y, x+1 .. x+reach])
        left_padded = np.pad(glow, ((0, 0), (0, reach)), mode='constant')
        right_glow = cv2.dilate(left_padded, kernel, anchor=(0, 0))
        right_glow[:, -reach:] = 0
        fishy = core & (np.minimum(left_glow, right_glow) - green >= 80)
        share = fishy[top:bottom].mean(axis=0)
        reach_out = max(1, round((bottom - top) * 0.3))
        outside = np.vstack([fishy[max(0, top - reach_out):top], fishy[bottom:bottom + reach_out]])
        narrowest = max(2, round(width * 0.0025))
        widest = max(8, round(width * 0.028))
        if len(outside) >= 3:
            cap = outside.mean(axis=0)
            keep = (share >= 0.6) | (share >= 0.1) & (cap >= 0.8) | (share >= 0.3) & (cap >= 0.3)
        else:
            cap = np.zeros(width)
            keep = share >= 0.3
        found = []
        for start, end in GeometryDetector._runs(keep):
            if narrowest <= end - start <= widest:
                if not start > 0:
                    continue
            if end < width:
                found.append((start, end - 1, float(share[start:end].max() + cap[start:end].max())))
        return found

    def detect(self, frame, fish_colors=None, fish_tol=0, now=None):
        result = {'target_line_x': None, 'target_left_x': None, 'target_right_x': None, 'target_middle_x': None, 'bar_left_x': None, 'bar_right_x': None, 'source': 'noiseform'}
        if now is not None and self._last_seen is not None and now - self._last_seen > self.FORGET_AFTER:
            self.reset()
        self._dt = now - self._last_seen if now is not None and self._last_seen is not None else None
        band = self.band
        fresh = self.track_band(frame)
        if fresh is not None:
            if band is None or self._misses >= self.BAND_RECHECK:
                band = fresh
            else:
                overlap = min(fresh[1], band[1]) - max(fresh[0], band[0])
                # Require the new band to be *within* the old one (overlap ≥ 80%
                # of the new band's height) before replacing, so a drifting
                # wrong band cannot keep renewing itself.
                if overlap >= (fresh[1] - fresh[0]) * 0.8:
                    band = fresh
        if band is None:
            return result
        # Use the same dark threshold as _bar() so the sanity check and the
        # actual edge scan agree on what counts as border-black.
        edge_rows = self.dark(frame[max(0, band[0] - 3):band[1]]).astype(np.uint8)
        need = max(2, int(frame.shape[1] * 0.12))
        if not cv2.erode(edge_rows, np.ones((1, need), np.uint8), borderType=cv2.BORDER_CONSTANT, borderValue=0).any():
            self._misses += 1
            return result
        full = frame
        frame = frame[band[0]:band[1]]
        left = self._bar(frame)
        if left is not None:
            previous = self._shown_left
            if previous is not None and abs(left - previous) <= max(1.0, frame.shape[1] * self.STILL_JITTER) and self._shown_width == self.width:
                left = previous
            self._shown_left, self._shown_width = left, self.width
            result['bar_left_x'] = int(round(left))
            result['bar_right_x'] = int(round(left + self.width))
            self.center = left + self.width / 2.0
            self.band = band
            self._misses = 0
            if now is not None:
                self._last_seen = now
        else:
            self._misses += 1
        found = self._fish_candidates(full, fish_colors, fish_tol, band)
        if found:
            if left is not None:
                near = max(3, frame.shape[1] * 0.006)
                edges = left, left + self.width
                found = [f for f in found
                     if min((abs((f[0] + f[1]) / 2.0 - e) for e in edges)) > near]
        if found:
            width = frame.shape[1]
            last = self.fish
            pick = max(
                found,
                key=lambda f: f[2]
                - (abs((f[0] + f[1]) / 2.0 - last) / width * 6 if last is not None else 0),
            )
            middle = (pick[0] + pick[1]) // 2
            self.fish = middle
            result.update(target_left_x=int(pick[0]), target_right_x=int(pick[1]), target_middle_x=int(middle), target_line_x=int(middle))
        return result

class _NoiseformGimmick:
    """NoiseForm's danger-zone event.

    A shape flashes three times above the track: a green circle, a white
    square or a black triangle. Three zones then appear on the track, each
    marked with one of those shapes, and about 2.2 s later a smite beam hits
    them. The bar must be touching the zone whose shape flashed.

    The flash is found by its shape inside the shake region: a filled green
    blob that is round, a white one that is square, or a black one that is
    a triangle, about 0.37 track lengths wide and centred over the track.
    Colour alone is not enough (a pale sun or a dark shadow can fill the
    screen), but those are never the right size, shape and position.
    Zones are found by their white icon; the zone's own fill (green
    stripes, grey stripes or near-black) around the icon says which one it
    is.
    """

    KINDS = ('GREEN', 'WHITE', 'BLACK')
    FLASH_RISE = 0.46
    FLASH_HALF_WIDTH = 0.3
    FLASH_HALF_HEIGHT = 0.3
    SHAPE_WIDTH = 0.37
    SHAPE_PIXELS = 110
    ZONE_WIDTH = 0.114
    FLASH_MEMORY = 4.5
    ZONE_GRACE = 0.45
    ZONE_DELAY = 0.55
    ZONE_OVERLAP = 0.35
    def __init__(self):
        self._lock = threading.Lock()
        self.flash_ring = deque(maxlen=90)
        self.reset()

    def reset(self):
        self.box = None
        self.flash_request = None
        self._flash_background = None
        self._last_frame_kind = None
        self._pulses = []
        self.zones = {}
        self._zones_seen = None
        self._zones_first = None

    @classmethod
    def flash_box(cls, region, band, track_length=None):
        '''Screen box (in points) to watch for the flash, from the minigame
        region and the track rows found inside it.'''

        length = track_length or region['width']
        centre_x = region['left'] + region['width'] / 2.0
        track_y = region['top'] + (band[0] + band[1]) / 2.0
        centre_y = track_y - cls.FLASH_RISE * length
        half_w = cls.FLASH_HALF_WIDTH * length
        half_h = cls.FLASH_HALF_HEIGHT * length
        top = max(0, int(round(centre_y - half_h)))
        return {'left': int(round(centre_x - half_w)), 'top': top, 'width': int(round(2 * half_w)), 'height': int(round(2 * half_h))}

    @classmethod
    def _shrink(cls, img, shape_width):
        img = img[..., :3]
        scale = min(1.0, cls.SHAPE_PIXELS / max(1.0, shape_width))
        if scale < 1.0:
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_AREA)
        return img, scale

    @classmethod
    def find_flash(cls, img, shape_width, centre_x=None, background=None):
        """Kind of the flash shape in a BGR(A) picture, or None.

        shape_width is the expected shape width in pixels of this picture;
        centre_x, when known, is where the track's centre falls in it.
        background, when given, is the brightness of this (shrunk) picture
        before the flash; the black triangle is then also found as the area
        that got darker, which is what shows it against a night sky.
        """

        small, scale = cls._shrink(img, shape_width)
        return cls._find_shrunk(small, scale, shape_width, centre_x, background)

    @classmethod
    def _find_shrunk(cls, img, scale, shape_width, centre_x, background):
        expect = shape_width * scale
        centre = None if centre_x is None else centre_x * scale
        pix = img.astype(np.int16)
        blue, green, red = pix[(..., 0)], pix[(..., 1)], pix[(..., 2)]
        lum = (blue + green + red) / 3.0
        spread = pix.max(axis=2) - pix.min(axis=2)
        masks = [
            ('BLACK', lum < 45, False),
            ('BLACK', (lum < 85) & (spread < 28), False),
            ('WHITE', (lum > 215) & (spread < 20), False),
            ('WHITE', (lum > 185) & (spread < 32), False),
            ('GREEN', (green > red + 70) & (green > blue + 40) & (green > 150), False),
        ]
        if background is not None and background.shape[:2] == lum.shape:
            if background.ndim == 3:
                bg = background.astype(np.int16)
                bg_lum = bg.mean(axis=2)
                bg_spread = bg.max(axis=2) - bg.min(axis=2)
                bg_green = bg[(..., 1)] - np.maximum(bg[(..., 0)], bg[(..., 2)])
            else:
                bg_lum, bg_spread, bg_green = background, None, None
            masks.append(('BLACK', (bg_lum - lum > 10) & (lum < 90), True))
            if bg_spread is not None:
                masks.append(('WHITE', (lum - bg_lum > 12) & (bg_spread - spread > 12) & (lum > 150), True))
                greenness = green - np.maximum(blue, red)
                masks.append(('GREEN', (greenness - bg_green > 40) & (green > 120), True))
        close = np.ones((5, 5), np.uint8)
        thin = np.ones((3, 3), np.uint8)
        cut = np.ones((7, 7), np.uint8)
        best = None
        for kind, mask, relative in masks:
            mask = mask.astype(np.uint8) * 255
            if relative:
                mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, thin)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, close)
            contours = list(cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])
            contours += list(cv2.findContours(cv2.morphologyEx(mask, cv2.MORPH_OPEN, cut), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)[0])
            for contour in contours:
                x, y, w, h = cv2.boundingRect(contour)
                # Size filter: width near expected shape size and roughly square.
                if not (expect * 0.75 <= w <= expect * 1.3):
                    continue
                if not (0.7 <= w / max(h, 1) <= 1.45):
                    continue
                # Centre filter when a track centre is known.
                if centre is not None:
                    if abs(x + w / 2.0 - centre) > expect * 0.35:
                        continue
                area = cv2.contourArea(contour)
                fill = area / float(w * h)
                solidity = area / max(cv2.contourArea(cv2.convexHull(contour)), 1.0)
                perimeter = cv2.arcLength(contour, True)
                roundness = 4 * np.pi * area / max(perimeter * perimeter, 1.0)
                if kind == 'BLACK':
                    ok = 0.38 <= fill <= 0.65 and solidity > 0.85
                elif kind == 'WHITE':
                    ok = fill >= 0.85 and solidity > 0.92
                else:
                    ok = 0.68 <= fill <= 0.86 and roundness > 0.75 and solidity > 0.92
                if not ok:
                    continue
                if best is not None and not area > best[1]:
                    continue
                best = kind, area
        if best is None and cls._green_circle(img, green, expect, centre):
            return 'GREEN'
        return best and best[0]


    @staticmethod
    def _green_circle(img, green, expect, centre):
        '''The green circle found by its round outline, for when green
        scenery behind it (a grass strip, foliage) merges with its fill so
        the blob has no circle shape left.'''

        if img.shape[0] < 8 or img.shape[1] < 8:
            return False
        green_mask = (green > img[(..., 2)].astype(np.int16) + 70) & (green > img[(..., 0)].astype(np.int16) + 40) & (green > 150)
        blurred = cv2.GaussianBlur(np.ascontiguousarray(img[(..., 1)]), (5, 5), 0)
        circles = cv2.HoughCircles(
            blurred, cv2.HOUGH_GRADIENT, dp=1,
            minDist=max(1, int(expect * 0.8)),
            param1=80, param2=22,
            minRadius=max(2, int(expect * 0.38)),
            maxRadius=max(3, int(expect * 0.62)),
        )
        if circles is None:
            return False
        rows, cols = np.ogrid[:img.shape[0], :img.shape[1]]
        for x, y, radius in circles[0]:
            if centre is not None:
                if abs(x - centre) > expect * 0.35:
                    continue
            disk = (cols - x) ** 2 + (rows - y) ** 2 <= (radius * 0.8) ** 2
            if not disk.any():
                continue
            if green_mask[disk].mean() >= 0.6:
                return True
        return False

    def observe_flash(self, img, now, shape_width, centre_x=None):
        small, scale = self._shrink(img, shape_width)
        colour = small.astype(np.float32)
        background = self._flash_background
        kind = self._find_shrunk(small, scale, shape_width, centre_x, background)
        self.flash_ring.append((now, small, kind))
        if kind is None:
            if background is None or background.shape != colour.shape:
                self._flash_background = colour
            else:
                self._flash_background = background + (colour - background) * 0.15
        with self._lock:
            if kind is not None and kind != self._last_frame_kind:
                self._pulses.append((kind, now))
            self._last_frame_kind = kind
            self._pulses = [(k, t) for k, t in self._pulses if now - t <= self.FLASH_MEMORY]

    def flashed(self, now):
        '''The shape that flashed most in the last few seconds, if any.'''

        with self._lock:
            recent = [(k, t) for k, t in self._pulses if now - t <= self.FLASH_MEMORY]
        if not recent:
            return
        counts = {k: sum((1 for kk, _ in recent if kk == k)) for k in self.KINDS}
        best = max(counts.values())
        return next((k for k, t in reversed(recent) if counts[k] == best))

    @classmethod
    def find_zones(cls, band_frame, track_length=None):
        '''{kind: centre x} for zones visible in the track rows.'''

        img = band_frame[..., :3].astype(np.int16)
        width = img.shape[1]
        length = track_length or width
        zone = cls.ZONE_WIDTH * length
        blue, green, red = img[(..., 0)], img[(..., 1)], img[(..., 2)]
        lum = (blue + green + red) / 3.0
        spread = img.max(axis=2) - img.min(axis=2)
        icon_rows = ((lum > 185) & (spread < 50)).sum(axis=0)
        found = []
        for start, end in GeometryDetector._runs(icon_rows >= 3):
            if not length * 0.008 <= end - start <= length * 0.035:
                continue
            centre = (start + end - 1) / 2.0
            inner, outer = zone * 0.16, zone * 0.45
            cols = np.r_[max(0, int(centre - outer)):max(0, int(centre - inner)), min(width, int(centre + inner)):min(width, int(centre + outer))]
            if not len(cols):
                continue
            fill = img[:, cols]
            f_lum = float(np.median(fill.mean(axis=2)))
            f_green = float(np.median(fill[(..., 1)] - np.maximum(fill[(..., 0)], fill[(..., 2)])))
            if f_green >= 35 and 35 <= f_lum <= 105:
                found.append(('GREEN', centre))
            elif f_green < 30 and f_lum <= 50:
                found.append(('BLACK', centre))
            elif f_green < 30 and 65 <= f_lum <= 125:
                found.append(('WHITE', centre))
            # else: unclassifiable fill, skip
        zones = {}
        for kind, centre in found:
            zones.setdefault(kind, []).append(centre)
        # Each kind must appear at most once (ambiguous zones are unusable).
        if any(len(v) != 1 for v in zones.values()):
            return {}
        centres = sorted(v[0] for v in zones.values())
        if any(b - a < zone * 0.8 for a, b in zip(centres, centres[1:])):
            return {}
        return {k: v[0] for k, v in zones.items()}

    def observe_zones(self, band_frame, now, track_length=None):
        zones = self.find_zones(band_frame, track_length)
        if zones:
            known = [v for v in self.zones.values()]
            half = self.ZONE_WIDTH * (track_length or band_frame.shape[1]) / 2.0
            agree = all((abs(zones[k] - self.zones[k]) <= half for k in zones if k in self.zones))
            clash = any((abs(v - x) <= half for k, v in zones.items() if k not in self.zones for x in known))
            if self.zones and (not agree or clash):
                return
            if self._zones_seen is None or now - self._zones_seen > self.ZONE_GRACE:
                self._zones_first = now
            self.zones.update(zones)
            self._zones_seen = now
            return
        if self._zones_seen is not None:
            if now - self._zones_seen > self.ZONE_GRACE:
                self.zones = {}
                self._zones_seen = None
                with self._lock:
                    self._pulses = []

    def correct_zone(self, now):
        '''(kind, zone centre) of the zone the flash picked, once both are
        known, else None.'''

        if not self.zones:
            return
        kind = self.flashed(now)
        if kind is None or kind not in self.zones:
            return
        return kind, self.zones[kind]

    def target(self, now, fish_x=None, bar_width=None, track_length=None):
        """(bar centre target x, kind) while the bar must hold the flashed
        zone, else None, from ZONE_DELAY after the zones appeared.

        Only part of the bar has to be in the zone, so the bar stays as close
        to the fish as it can: its centre follows the fish, but no further
        than the point where its near edge still reaches ZONE_OVERLAP of the
        zone's width into the zone. With a fish already inside that range the
        bar simply keeps tracking it. Without a fish or bar width, the zone's
        centre.
        """

        zone = self.correct_zone(now)
        if zone is None or self._zones_first is None or now - self._zones_first < self.ZONE_DELAY:
            return
        kind, centre = zone
        if fish_x is None or not bar_width or not track_length:
            return centre, kind
        half_zone = self.ZONE_WIDTH * track_length / 2.0
        overlap = self.ZONE_OVERLAP * 2 * half_zone
        half_bar = bar_width / 2.0
        lowest = centre - half_zone + overlap - half_bar
        highest = centre + half_zone - overlap + half_bar
        if lowest > highest:
            return centre, kind
        return min(max(float(fish_x), lowest), highest), kind