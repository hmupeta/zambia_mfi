"""
Crop the Nimbus logo PNG to keep only the icon (top portion),
removing the "NIMBUS" and "INVESTMENT Ltd." text underneath.

Opens a preview, then saves the cropped icon as nimbus-mark.png.
Run:  python crop_logo.py
"""
from pathlib import Path
from PIL import Image

SRC = Path(r'C:\Users\Howardm\Documents\django\zambia_mfi\frontend\static\images\nimbus-logo.png')
DST = SRC.with_name('nimbus-mark.png')

if not SRC.exists():
    raise SystemExit(f'Not found: {SRC}')

img = Image.open(SRC).convert('RGBA')
w, h = img.size
print(f'Original size: {w} x {h}')

# The icon occupies roughly the top 55% of the image.
# Tune the ratio below if you want a tighter/looser crop.
ICON_RATIO = 0.58
crop_h = int(h * ICON_RATIO)

# Optional: shrink width to just the icon by finding content bounds
cropped = img.crop((0, 0, w, crop_h))

# Auto-tight crop: strip transparent/white borders
bbox = cropped.getbbox()
if bbox:
    cropped = cropped.crop(bbox)

# Optional: pad slightly so the icon isn't edge-touching
pad = 8
cw, ch = cropped.size
canvas = Image.new('RGBA', (cw + pad * 2, ch + pad * 2), (0, 0, 0, 0))
canvas.paste(cropped, (pad, pad))

canvas.save(DST)
print(f'✅ Saved: {DST}')
print(f'New size: {canvas.size[0]} x {canvas.size[1]}')