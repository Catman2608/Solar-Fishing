import cv2
import numpy as np
import sys

def detect_shapes(image_path):
    """Detect triangle, circle, and square positions.
    
    Ignores a fish skeleton that may appear above the bar (larger, very low circularity).
    Works across different image heights / resolutions.
    """
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load image from {image_path}")
        return

    h, w = img.shape[:2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Threshold to isolate the bright white shapes
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    shapes = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area < 60:
            continue

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        circularity = 4 * np.pi * area / (peri ** 2) if peri > 0 else 0

        x, y, bw, bh = cv2.boundingRect(cnt)
        aspect = bw / float(bh) if bh > 0 else 0

        # Roughly square bounding box
        if not (0.7 < aspect < 1.4):
            continue

        # Icon size range that works for the tested resolutions
        # (rejects the larger fish skeleton above the bar)
        if not (12 < bh < 45 and 12 < bw < 45):
            continue

        # Reject very low-circularity blobs (fish skeleton)
        if circularity < 0.4:
            continue

        M = cv2.moments(cnt)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        else:
            cx = x + bw // 2
            cy = y + bh // 2

        shapes.append({
            'center': (cx, cy),
            'area': area,
            'vertices': len(approx),
            'circularity': circularity,
            'aspect': aspect,
            'bbox': (bw, bh)
        })

    if len(shapes) < 3:
        print(f"Warning: Found only {len(shapes)} candidate shapes (expected 3).")
        for s in shapes:
            print(s)
        return

    # If more than 3, keep the three with the most "icon-like" circularity
    if len(shapes) > 3:
        shapes = sorted(shapes, key=lambda s: s['circularity'], reverse=True)[:3]

    # Classification
    # Circle = highest circularity
    shapes_by_circ = sorted(shapes, key=lambda s: s['circularity'], reverse=True)
    circle = shapes_by_circ[0]

    remaining = [s for s in shapes if s['center'] != circle['center']]

    # Prefer a true 3-vertex contour for the triangle; otherwise lowest circularity
    tri_candidates = [s for s in remaining if s['vertices'] == 3]
    if tri_candidates:
        triangle = tri_candidates[0]
    else:
        remaining_by_circ = sorted(remaining, key=lambda s: s['circularity'])
        triangle = remaining_by_circ[0]

    square = [s for s in remaining if s['center'] != triangle['center']][0]

    print("Detected shape positions (x, y):")
    print(f"Triangle: {triangle['center']}")
    print(f"Circle:   {circle['center']}")
    print(f"Square:   {square['center']}")

    print("\nDetails:")
    print(f"  Triangle - vertices: {triangle['vertices']}, circularity: {triangle['circularity']:.2f}")
    print(f"  Circle   - vertices: {circle['vertices']}, circularity: {circle['circularity']:.2f}")
    print(f"  Square   - vertices: {square['vertices']}, circularity: {square['circularity']:.2f}")


if __name__ == "__main__":
    if len(sys.argv) > 1:
        image_path = sys.argv[1]
    else:
        image_path = "debug_fish.png"
    detect_shapes(image_path)
