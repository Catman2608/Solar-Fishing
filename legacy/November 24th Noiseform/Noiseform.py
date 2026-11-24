import cv2
import numpy as np


def classify_shape(contour):
    area = cv2.contourArea(contour)
    peri = cv2.arcLength(contour, True)
    if peri == 0 or area < 20:
        return None, 0.0

    # Polygon approximation
    approx = cv2.approxPolyDP(contour, 0.04 * peri, True)
    vertices = len(approx)

    # Bounding box & NumPy geometry metrics
    x, y, w, h = cv2.boundingRect(contour)
    bbox_area = float(w * h)
    extent = area / bbox_area if bbox_area > 0 else 0.0
    aspect_ratio = w / float(h) if h > 0 else 0.0
    circularity = (4.0 * np.pi * area) / (peri * peri)

    # 1. Triangle check
    if vertices == 3:
        return "triangle", circularity

    # 2. Square check (4 corners, ~1:1 aspect ratio, fills bounding box well)
    if vertices == 4 and 0.75 <= aspect_ratio <= 1.35 and extent > 0.65:
        return "square", circularity

    # 3. Circle check (high circularity, near-square bounding box)
    if circularity > 0.72 and 0.75 <= aspect_ratio <= 1.35:
        return "circle", circularity

    # Fallback using extent if vertices are slightly noisy
    if extent > 0.75 and 0.75 <= aspect_ratio <= 1.35:
        return "square", circularity
    if 0.42 <= extent <= 0.58 and circularity < 0.72:
        return "triangle", circularity

    return "unknown", circularity


def detect_white_shapes(image_path, output_path="detected_shapes.png"):
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Could not load image: {image_path}")

    # Upscale 3x to give small icons cleaner geometry
    scale = 3
    up = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)

    # Convert to HSV and isolate bright/low-saturation (white) regions
    hsv = cv2.cvtColor(up, cv2.COLOR_BGR2HSV)
    _, s, v = cv2.split(hsv)

    # Tune V (brightness) and S (saturation) depending on lighting/compression
    white_mask = cv2.inRange(v, 175, 255) & cv2.inRange(s, 0, 90)

    # Fill inner cutouts (like the '!') and smooth jagged edges
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
    closed = cv2.morphologyEx(white_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    contours, _ = cv2.findContours(
        closed, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    # Fill each outer contour on a clean mask so interior holes don't distort area
    filled_mask = np.zeros_like(closed)
    valid_contours = []
    for cnt in contours:
        if cv2.contourArea(cnt) >= 80:  # filter out tiny noise speckles (scaled up)
            cv2.drawContours(filled_mask, [cnt], -1, 255, thickness=cv2.FILLED)
            valid_contours.append(cnt)

    # Re-find contours on filled shapes for clean geometry
    clean_contours, _ = cv2.findContours(
        filled_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE
    )

    # Sort left-to-right using NumPy / bounding box x-coordinate
    clean_contours = sorted(
        clean_contours, key=lambda c: cv2.boundingRect(c)[0]
    )

    vis = up.copy()
    detections = []

    for cnt in clean_contours:
        shape, circ = classify_shape(cnt)
        if shape is None:
            continue

        x, y, w, h = cv2.boundingRect(cnt)
        # Convert coordinates back to original image scale
        orig_box = (x // scale, y // scale, w // scale, h // scale)
        detections.append((shape, orig_box, round(float(circ), 3)))

        color = (0, 255, 255)
        cv2.rectangle(vis, (x, y), (x + w, y + h), color, 2)
        cv2.putText(
            vis,
            f"{shape} ({circ:.2f})",
            (x, max(15, y - 6)),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.55,
            color,
            2,
        )

    cv2.imwrite(output_path, vis)
    return detections


if __name__ == "__main__":
    results = detect_white_shapes("debug_fish.png")
    for label, box, circ in results:
        print(f"Detected {label:8s} | bbox(x,y,w,h)={box} | circularity={circ}")
