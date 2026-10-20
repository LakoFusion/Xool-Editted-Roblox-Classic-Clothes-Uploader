"""Roblox classic clothing UV geometry and seam-continuity helpers.

Panel boxes are measured from ``src/assets/template/template.png`` with the same
coordinates used by the ``CC_*`` constants in ``src/enhance/__init__.py``
(torso band y 74..201, verified by ``measure_template.py``).

``align_horizontal_seams`` only equalizes the paired edge columns of the torso
strip (the four panels that wrap around the avatar). It never invents content:
rows where either edge pixel is transparent are left untouched.
"""

from PIL import Image


CANVAS_SIZE = (585, 559)

# Left-to-right flat order of the torso strip; the wrap-around closes back -> side_a.
TORSO_PANELS = {
    "side_a": (165, 74, 228, 201),   # 64x128 hip/side panel
    "front":  (231, 74, 358, 201),   # 128x128 front torso
    "side_b": (359, 74, 424, 201),   # 64x128 hip/side panel
    "back":   (427, 74, 554, 201),   # 128x128 back torso
}
TORSO_ORDER = ("side_a", "front", "side_b", "back")


def panel_boundaries():
    """Return the boundary pairs of the torso strip, including the wrap closure."""
    boundaries = []
    for index in range(len(TORSO_ORDER)):
        left = TORSO_ORDER[index]
        right = TORSO_ORDER[(index + 1) % len(TORSO_ORDER)]
        boundaries.append((left, right))
    return boundaries


def _scaled(box, size):
    scale_x = size[0] / float(CANVAS_SIZE[0])
    scale_y = size[1] / float(CANVAS_SIZE[1])
    return (
        int(box[0] * scale_x), int(box[1] * scale_y),
        int(box[2] * scale_x), int(box[3] * scale_y),
    )


def _edge_columns(left_name, right_name, size):
    left_box = _scaled(TORSO_PANELS[left_name], size)
    right_box = _scaled(TORSO_PANELS[right_name], size)
    y0 = max(left_box[1], right_box[1])
    y1 = min(left_box[3], right_box[3])
    return left_box[2], right_box[0], y0, y1


def align_horizontal_seams(image):
    """Sync RGB of paired torso edge columns so wrapped seams stop breaking.

    For every boundary pair (side_a->front, front->side_b, side_b->back and the
    wrap closure back->side_a) the two facing edge columns are replaced by their
    per-pixel average, but only on rows where both pixels are opaque. Each
    column keeps its own alpha, and everything else in the image is untouched.
    """
    if not isinstance(image, Image.Image) or image.mode != "RGBA":
        return image
    aligned = image.copy()
    pixels = aligned.load()
    for left_name, right_name in panel_boundaries():
        x_left, x_right, y0, y1 = _edge_columns(left_name, right_name, aligned.size)
        if x_left == x_right:
            continue
        for y in range(y0, y1 + 1):
            left_pixel = pixels[x_left, y]
            right_pixel = pixels[x_right, y]
            if left_pixel[3] == 0 or right_pixel[3] == 0:
                continue
            average = tuple((left_pixel[c] + right_pixel[c]) // 2 for c in range(3))
            pixels[x_left, y] = average + (left_pixel[3],)
            pixels[x_right, y] = average + (right_pixel[3],)
    return aligned


def seam_mismatch(image):
    """Max per-channel RGB difference across each paired edge column, opaque rows only."""
    if not isinstance(image, Image.Image) or image.mode != "RGBA":
        return {}
    pixels = image.load()
    mismatches = {}
    for left_name, right_name in panel_boundaries():
        x_left, x_right, y0, y1 = _edge_columns(left_name, right_name, image.size)
        worst = 0
        if x_left != x_right:
            for y in range(y0, y1 + 1):
                left_pixel = pixels[x_left, y]
                right_pixel = pixels[x_right, y]
                if left_pixel[3] == 0 or right_pixel[3] == 0:
                    continue
                worst = max(worst, max(
                    abs(left_pixel[c] - right_pixel[c]) for c in range(3)))
        mismatches[f"{left_name}->{right_name}"] = worst
    return mismatches
