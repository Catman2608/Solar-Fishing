import cv2
import numpy as np

def detect_shapes(image_path):
    # Load the image
    img = cv2.imread(image_path)
    if img is None:
        print(f"Error: Could not load image from {image_path}")
        return

    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Threshold to isolate the white shapes
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)

    # Find external contours
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    shapes = []
    for cnt in contours:
        area = cv2.contourArea(cnt)
        # Filter by reasonable area for the icons
        if not (90 < area < 300):
            continue

        peri = cv2.arcLength(cnt, True)
        approx = cv2.approxPolyDP(cnt, 0.04 * peri, True)
        circularity = 4 * np.pi * area / (peri ** 2) if peri > 0 else 0

        x, y, w, h = cv2.boundingRect(cnt)
        aspect = w / float(h) if h > 0 else 0
        # Filter by aspect ratio close to 1 (roughly square bounding boxes)
        if not (0.8 < aspect < 1.3):
            continue

        # Compute centroid
        M = cv2.moments(cnt)
        if M["m00"] != 0:
            cx = int(M["m10"] / M["m00"])
            cy = int(M["m01"] / M["m00"])
        else:
            cx = x + w // 2
            cy = y + h // 2

        shapes.append({
            'center': (cx, cy),
            'area': area,
            'vertices': len(approx),
            'circularity': circularity,
            'aspect': aspect
        })

    if len(shapes) < 3:
        print(f"Warning: Found only {len(shapes)} candidate shapes (expected 3).")
        for s in shapes:
            print(s)
        return

    # Classify shapes
    # Circle has the highest circularity
    shapes_by_circ = sorted(shapes, key=lambda s: s['circularity'], reverse=True)
    circle = shapes_by_circ[0]

    remaining = [s for s in shapes if s['center'] != circle['center']]
    # Triangle has the lowest circularity among the remaining
    remaining_by_circ = sorted(remaining, key=lambda s: s['circularity'])
    triangle = remaining_by_circ[0]
    square = remaining_by_circ[1]

    # Print results
    print("Detected shape positions (x, y):")
    print(f"Triangle: {triangle['center']}")
    print(f"Circle:   {circle['center']}")
    print(f"Square:   {square['center']}")

    # Optional: print additional debug info
    print("\nDetails:")
    print(f"  Triangle - vertices: {triangle['vertices']}, circularity: {triangle['circularity']:.2f}")
    print(f"  Circle   - vertices: {circle['vertices']}, circularity: {circle['circularity']:.2f}")
    print(f"  Square   - vertices: {square['vertices']}, circularity: {square['circularity']:.2f}")

if __name__ == "__main__":
    # Path to the image (place debug_fish.png in the same directory or adjust the path)
    image_path = "debug_fish.png"
    detect_shapes(image_path)
