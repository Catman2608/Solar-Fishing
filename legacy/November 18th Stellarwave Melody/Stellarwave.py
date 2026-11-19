import cv2
import numpy as np

# 1. Load the image
img = cv2.imread("test.png")

def color_mask(image, hex_bgr, tolerance=20):
    target_bgr = np.array(hex_bgr, dtype=np.int32)
    lower = np.clip(target_bgr - tolerance, 0, 255).astype(np.uint8)
    upper = np.clip(target_bgr + tolerance, 0, 255).astype(np.uint8)
    return cv2.inRange(image, lower, upper)

# 2. Mask for color #b1daef (BGR: EF DA B1)
mask1 = color_mask(img, [0xDA, 0xA5, 0xBC])
mask2 = color_mask(img, [0xCB, 0xA0, 0xB3])

# 4. Combine both masks (union)
mask = cv2.bitwise_or(mask1, mask2)
# equivalent: mask = np.maximum(mask1, mask2)

# 5. Save
cv2.imwrite("result.png", mask)