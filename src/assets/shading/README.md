# Shading maps (pre-baked AO for classic clothing)

L-mode 585x559 PNG multiply maps consumed by `_apply_shading_map()` in
`src/enhance/__init__.py`:

- `shirt_ao_template.png` — neckline/collar shadow, hem shadow and soft
  cylinder shading on the hip panels.
- `pants_ao_template.png` — waistband shadow, knee crease band and ankle/hem
  shadow.

Conventions:

- `255` = neutral (pixel unchanged); lower values darken the garment.
- The map is resized to the target image, blended with `opacity` (default
  `0.4`) and **masked by the garment alpha**, so transparent pixels stay
  byte-identical.
- The shifted/darkened panels are the measured Roblox classic torso boxes
  (`y 74..201`, see `src/enhance/uv_spec.py`), the same geometry used by the
  `CC_*` color-coding constants.

The maps are procedurally generated; regenerate them (e.g. after a template
change) with the `gen_shading_maps.py` helper kept alongside the other
verification scripts in the `opencode` temp folder.
