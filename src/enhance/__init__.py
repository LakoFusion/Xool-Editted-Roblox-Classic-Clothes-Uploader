import base64
import hashlib
import json
import os
import random
import re
import tempfile
import time

import requests
from PIL import Image, ImageChops, ImageDraw, ImageEnhance, ImageFilter

from . import uv_spec


REQUEST_TIMEOUT = 90
GEMINI_RETRY_DELAYS = (10, 30)
TEMP_IMAGE_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    "src", "assets", "temp",
)
OVERLAY_ROOT = os.path.join("src", "assets", "overlays")
SHADING_ROOT = os.path.join("src", "assets", "shading")
TEMPLATE_PATH = os.path.join("src", "assets", "template", "template.png")
ENHANCE_CACHE_ROOT = os.path.join("src", "assets", "enhance_cache")
ALLOWED_OVERLAY_EXTENSIONS = (".png", ".webp")
REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"
REPLICATE_MODELS_URL = "https://api.replicate.com/v1/models/{model}/predictions"
SD_POLL_INTERVAL_SECONDS = 3
SD_POLL_TIMEOUT_SECONDS = 180
SD_PROMPT_TEMPLATE = (
    "flat 2d roblox classic clothing texture sheet, {style} aesthetic, "
    "seamless fabric pattern, crisp contrast stitching, bold readable details, "
    "matching horizontal seams across all panels, rich charcoal shading instead "
    "of pure black, no text, no watermark, transparent background, top-down texture map"
)
CONFIG_PROVIDER = None
CONFIG_GEMINI_API_KEYS = []   # list of API keys for rotation
CONFIG_GEMINI_MODEL = None
CONFIG_GEMINI_COOKIE = None   # browser cookie for Gemini web
CONFIG_GEMINI_DOWNLOAD_COOKIE = None  # dedicated cookie for downloading generated images
CONFIG_GEMINI_COOKIE_OPTIONS = {}
CONFIG_MAX_NUDITY = 0.08
CONFIG_REPLICATE_API_TOKEN = None
CONFIG_SD_MODEL_VERSION = None
CONFIG_SD_PROMPT_STRENGTH = None
CONFIG_USE_CONTROLNET = True
_GEMINI_COOKIE_CLIENT = None  # cached XoolGeminiClient instance

STYLE_KEYWORDS = {
    # Specific 2026 styles precede the generic styles below so detect_style's
    # tie-break prefers their more specific signal (e.g. "cyberpunk" over "cargo")
    "y2k_dark": {"y2k_dark", "y2kdark", "darky2k"},
    "minimalist_og": {"minimalist_og", "minimalistog", "blocky"},
    "japanese_streetwear": {"japanese_streetwear", "japanesestreetwear", "noragi", "hakama"},
    "cyberpunk": {"cyberpunk", "cyber_punk", "neonpunk", "netrunner"},
    "scifi": {"scifi", "sci_fi", "spacecore", "mecha"},
    "scene": {"scene", "scenecore", "rawr", "crunkcore"},
    "cute": {"cute", "cutie", "kitty", "cat", "bunny", "heart", "sweet", "lovely"},
    "kawaii": {"kawaii", "sanrio", "chibi", "pastel", "pink", "softie"},
    "coquette": {"coquette", "bow", "ribbon", "lace", "pearl", "dollette", "ballet"},
    "y2k": {"y2k", "2000s", "mcbling", "chrome", "cyber", "star", "scene"},
    "emo": {"emo", "vamp", "scene", "black", "white", "sad", "gloomy"},
    "goth": {"goth", "gothic", "dark", "black", "vampire", "grave", "lace"},
    "horror": {"horror", "scary", "spooky", "haunted", "monster", "creepy"},
    "baddie": {"baddie", "igbaddie", "instabaddie", "halter", "tube", "corset", "lowrise", "strappy"},
    "cutout": {"cutout", "cutouts", "backless", "keyhole", "fishnet", "sheer", "mesh", "revealing"},
    "streetwear": {"streetwear", "baggy", "hoodie", "urban", "drip", "swag", "cargo"},
    "preppy": {"preppy", "school", "uniform", "plaid", "collar", "academy"},
    "soft": {"soft", "pastel", "cozy", "minimal", "basic", "clean"},
    "anime": {"anime", "manga", "japanese", "kawaii", "senpai", "otaku"},
    "grunge": {"grunge", "ripped", "washed", "distressed", "punk", "messy"},
    "clean": {"clean", "basic", "plain", "classic", "white", "simple", "minimal"},
    "acubi": {"acubi", "subversive", "mizuiro", "neutral", "utility", "asymmetric", "korean"},
    "weirdcore": {"weird", "weirdcore", "oddcore", "dreamcore", "liminal", "surreal"},
    "cyber": {"cyber", "techwear", "neon", "glow", "digital", "matrix"},
    "denim": {"denim", "jean", "jeans", "washed", "blue", "jacket"},
    "winter": {"winter", "snow", "cozy", "christmas", "xmas", "sweater"},
    "summer": {"summer", "beach", "sunny", "vacation", "tank", "crop"},
    "school": {"school", "uniform", "student", "academy", "preppy", "plaid"},
    "christmas": {"christmas", "xmas", "santa", "holiday", "festive", "winter"},
    "halloween": {"halloween", "spooky", "pumpkin", "witch", "ghost", "goth"},
}

OVERLAY_FOLDERS = {
    "cute": ["cute"],
    "kawaii": ["cute"],
    "coquette": ["coquette", "cute"],
    "y2k": ["y2k"],
    "emo": ["emo_goth", "y2k"],
    "goth": ["emo_goth"],
    "horror": ["emo_goth", "seasonal"],
    "baddie": ["y2k", "cute"],
    "cutout": ["coquette", "y2k"],
    "streetwear": ["streetwear"],
    "preppy": ["preppy"],
    "soft": ["cute", "preppy"],
    "anime": ["cute", "y2k"],
    "grunge": ["emo_goth", "streetwear"],
    "clean": ["preppy", "streetwear"],
    "acubi": ["streetwear", "preppy"],
    "weirdcore": ["weirdcore"],
    "cyber": ["y2k", "weirdcore"],
    "denim": ["streetwear"],
    "winter": ["seasonal"],
    "summer": ["cute", "streetwear"],
    "school": ["preppy"],
    "christmas": ["seasonal"],
    "halloween": ["seasonal", "emo_goth"],
    "y2k_dark": ["y2k", "emo_goth"],
    "minimalist_og": ["streetwear", "preppy"],
    "japanese_streetwear": ["streetwear", "preppy"],
    "cyberpunk": ["y2k", "weirdcore"],
    "scifi": ["weirdcore", "y2k"],
}

POLISH_PRESETS = {
    "cute": (1.08, 0.98, 1.08, 1.04),
    "kawaii": (1.10, 0.98, 1.10, 1.03),
    "coquette": (1.07, 1.02, 1.06, 1.04),
    "y2k": (1.02, 1.12, 0.96, 1.08),
    "emo": (0.96, 1.16, 0.92, 1.08),
    "goth": (0.94, 1.18, 0.90, 1.08),
    "horror": (0.93, 1.18, 0.88, 1.07),
    "baddie": (1.03, 1.12, 1.04, 1.08),
    "cutout": (1.04, 1.10, 1.02, 1.08),
    "streetwear": (1.01, 1.10, 0.98, 1.08),
    "preppy": (1.06, 1.05, 1.04, 1.06),
    "soft": (1.08, 0.98, 1.03, 1.02),
    "anime": (1.08, 1.04, 1.10, 1.04),
    "grunge": (0.98, 1.18, 0.92, 1.10),
    "clean": (1.04, 1.04, 1.00, 1.06),
    "acubi": (1.02, 1.07, 0.95, 1.07),
    "weirdcore": (1.01, 1.12, 1.04, 1.08),
    "cyber": (1.02, 1.14, 1.02, 1.08),
    "denim": (1.01, 1.10, 0.98, 1.08),
    "winter": (1.07, 1.04, 0.98, 1.05),
    "summer": (1.10, 1.02, 1.08, 1.04),
    "school": (1.05, 1.04, 1.02, 1.06),
    "christmas": (1.06, 1.06, 1.03, 1.05),
    "halloween": (0.96, 1.15, 0.95, 1.07),
    "y2k_dark": (0.95, 1.18, 0.92, 1.09),
    "minimalist_og": (1.03, 1.06, 1.00, 1.08),
    "japanese_streetwear": (0.99, 1.12, 0.96, 1.08),
    "cyberpunk": (0.99, 1.16, 1.03, 1.10),
    "scifi": (1.01, 1.10, 1.03, 1.10),
}

STYLE_LEXICON = {
    "y2k": (
        "- Silhouette: fitted baby tee with a micro-pleated skirt or low-rise baggy cargo pants and "
        "oversized utility pockets.\n"
        "- Fabric: washed pastel or silver-sheen baby rib cotton, vintage distressed light-wash denim "
        "with subtle whiskering, and plush faux-fur trim.\n"
        "- Micro-details: bedazzled rhinestone hotfix starbursts, dark chrome cyber-tribal motifs, a "
        "chunky double-grommet belt, metal D-rings and contrast 2px white edge stitching.\n"
        "- Shading & Lighting: airbrushed pastel gradient wash, high-gloss specular shine on metallic "
        "hardware, crisp crease shadows and clean ambient occlusion under the waistband."
    ),
    "acubi": (
        "- Silhouette: deconstructed layered tank with a detached bolero shrug, thumbhole cuffs and "
        "asymmetrical cut-out panels.\n"
        "- Fabric: sheer layered power mesh over ribbed modal jersey with raw lettuce-edge hems.\n"
        "- Micro-details: exposed raw overlock seams, double-ended two-way zippers, safety-pin "
        "hardware, minimalist utility straps with mini metal buckles.\n"
        "- Shading & Lighting: muted grey and earth-tone palette, soft directional shading, clean "
        "contour folds with subtle seam shadowing."
    ),
    "emo": (
        "- Silhouette: layered long-sleeve striped under-shirt under a cropped dark graphic tee, with "
        "distressed laddered knit arm warmers.\n"
        "- Fabric: charcoal #1a1a1e fabric (never pure #000000), ripped fishnet mesh accents and "
        "faded slub jersey.\n"
        "- Micro-details: safety pins, double-row pyramid-stud belt, inverted stitched hearts, bleeding "
        "ink graphics, silver chains and stylized skull motifs.\n"
        "- Shading & Lighting: harsh contrast creases, deep black ambient occlusion, cold rim highlights."
    ),
    "goth": (
        "- Silhouette: fitted lace corset top with long layered sleeves.\n"
        "- Fabric: crushed velvet and black lace over sheer mesh.\n"
        "- Micro-details: spiderweb embroidery, corset lacing with metal eyelets, antique silver cross "
        "and pewter ornaments.\n"
        "- Shading & Lighting: candle-lit dramatic shadows, deep burgundy and violet ambient occlusion."
    ),
    "horror": (
        "- Silhouette: distressed tactical survival jacket or shredded asymmetrical medical shroud "
        "with jagged torn hems and detached sleeve wraps.\n"
        "- Fabric: weather-stained heavy canvas, frayed decayed gauze bandages, charred ribbed cotton "
        "and torn fishnet layering.\n"
        "- Micro-details: oxidized rust and coagulated crimson splatters, barbed-wire wraps, crude "
        "surgical thread repair stitches, safety pins and worn tourniquet buckles.\n"
        "- Shading & Lighting: atmospheric gritty soot wash, high-contrast chiaroscuro creasing, deep "
        "charcoal #141416 ambient occlusion and cold sickly green rim lighting."
    ),
    "baddie": (
        "- Silhouette: sculpted strappy corset bustier or ruched halter crop top with ultra low-rise "
        "flared bootcut trousers or a ruched mini skirt.\n"
        "- Fabric: double-layered sheer mesh over contour stretch jersey, semi-gloss faux crocodile "
        "leather and liquid satin with draped folds.\n"
        "- Micro-details: visible corset boning channels, multi-tiered crystal belly chain, delicate "
        "metallic O-ring connectors, side-ruching drawstrings and razor-sharp bound cutout borders.\n"
        "- Shading & Lighting: rich warm studio rim lighting, glossy wet-look specular highlights "
        "along contours and deep directional shadow creases accentuating garment depth."
    ),
    "cutout": (
        "- Silhouette: asymmetric top with clavicle keyhole, underbust teardrop and high-hip peekaboo "
        "panels, plus criss-cross halter ties.\n"
        "- Fabric: sheer power mesh layered over opaque stretch lining, with matte tubular knit "
        "binding.\n"
        "- Micro-details: lace-up back, O-ring hardware, strappy cross ties, reinforced seam tape and "
        "clean bound cut edges.\n"
        "- Shading & Lighting: crisp edge highlights along every cut, soft ambient occlusion and "
        "high-contrast fabric sheen."
    ),
    "streetwear": (
        "- Silhouette: oversized boxy drop-shoulder hoodie with baggy multi-pocket cargo pants.\n"
        "- Fabric: heavyweight French terry cotton and tactical ripstop nylon.\n"
        "- Micro-details: utility pockets, woven nylon straps, quick-release buckle clips, "
        "color-block panels.\n"
        "- Shading & Lighting: crisp deep fabric folds, urban studio directional rim light, "
        "defined seam shadows."
    ),
    "coquette": (
        "- Silhouette: fitted corset-waist top with a flared skirt or delicate cardigan.\n"
        "- Fabric: soft velvet, sheer lace and satin with fine ribbing.\n"
        "- Micro-details: corset boning, satin ribbon bows, scalloped lace trim, pearl shimmer.\n"
        "- Shading & Lighting: soft romantic lighting, delicate pastel ambient occlusion, "
        "glossy satin speculars."
    ),
    "cute": (
        "- Silhouette: oversized fluffy pastel cardigan layered over a pleated micro-skirt.\n"
        "- Fabric: soft fuzzy knit and smooth cotton with delicate lace trim.\n"
        "- Micro-details: ruffled frills, satin ribbon bows, heart-shaped buttons, pearl collar trim.\n"
        "- Shading & Lighting: clean cel-shading, flat color with soft pastel ambient occlusion "
        "and gentle blush highlights."
    ),
    "kawaii": (
        "- Silhouette: babydoll blouse with rounded sailor collar or puffy ruffled sleeves.\n"
        "- Fabric: soft velvet and chiffon accents in a candy pastel weave.\n"
        "- Micro-details: dainty bow ribbons, heart embroidery, scalloped lace edges.\n"
        "- Shading & Lighting: gentle pastel ambient occlusion, warm soft highlights, "
        "clean flat anime shading."
    ),
    "anime": (
        "- Silhouette: sharp cel-shaded silhouette with clean panel cuts and defined shoulders.\n"
        "- Fabric: smooth matte fabric with bold flat color blocking.\n"
        "- Micro-details: graphic motif shapes inspired by manga panels (abstract, no text or "
        "characters), crisp outline accents.\n"
        "- Shading & Lighting: hard cel-shading with two-tone shadow steps and saturated highlights."
    ),
    "preppy": (
        "- Silhouette: crisp academy blazer over a pleated skirt or tailored trousers.\n"
        "- Fabric: fine wool blend, starched cotton and soft tartan plaid.\n"
        "- Micro-details: ribbon tie, collar and cuff piping, neat double-stitching, abstract "
        "crest-inspired geometric emblem.\n"
        "- Shading & Lighting: bright clean daylight, soft uniform ambient occlusion, "
        "polished highlights."
    ),
    "grunge": (
        "- Silhouette: oversized slouchy thrift-fit flannel or distressed boxy tee with baggy bottoms.\n"
        "- Fabric: vintage washed cotton, acid-washed denim, worn frayed weave.\n"
        "- Micro-details: frayed raw fringes, safety pins, patchwork cloth stitches, faded grime wash.\n"
        "- Shading & Lighting: muted earthy shadows, desaturated gradients, low-contrast dusty creases."
    ),
    "cyber": (
        "- Silhouette: fitted techwear jacket with modular panel lines.\n"
        "- Fabric: matte technical fabric with reflective synthetic accents.\n"
        "- Micro-details: neon piping, holographic panels, reflective strips, tactical webbing.\n"
        "- Shading & Lighting: black base with electric cyan and magenta glow, hard rim highlights."
    ),
    "weirdcore": (
        "- Silhouette: familiar garment shape subtly warped for an uncanny look.\n"
        "- Fabric: low-fi textured cloth with digital static grain.\n"
        "- Micro-details: surreal dreamlike motifs, chromatic aberration shimmer, glitch artifact "
        "patterns.\n"
        "- Shading & Lighting: liminal nostalgic light, off-palette pastel against dark ground, "
        "eerie glow spots."
    ),
    "denim": (
        "- Silhouette: classic denim jacket over straight or relaxed-fit jeans.\n"
        "- Fabric: authentic denim twill with stonewashed gradients and whiskering fades.\n"
        "- Micro-details: contrast gold stitching, copper rivets, frayed hems, embossed pocket arcs.\n"
        "- Shading & Lighting: natural daylight wear, soft creases with subtle ambient occlusion."
    ),
    "soft": (
        "- Silhouette: relaxed cozy knit sweater with a gentle oversized drape.\n"
        "- Fabric: brushed fleece and ribbed knit with a fuzzy nap.\n"
        "- Micro-details: subtle tonal embroidery, soft rolled hems, tiny pastel buttons.\n"
        "- Shading & Lighting: muted pastel gradient, gentle diffused shadows, cozy rim glow."
    ),
    "clean": (
        "- Silhouette: classic straight-cut garment with balanced proportions.\n"
        "- Fabric: smooth combed cotton twill with a fine even weave.\n"
        "- Micro-details: subtle topstitching, tonal buttons, small blank woven tab detail.\n"
        "- Shading & Lighting: soft even studio light, gentle ambient occlusion, fresh neutral palette."
    ),
    "winter": (
        "- Silhouette: chunky cable-knit sweater or padded winter coat with a cozy cowl.\n"
        "- Fabric: wool knit, brushed flannel lining and soft sherpa accents.\n"
        "- Micro-details: snowflake and fairisle motifs, chunky ribbed cuffs, wooden toggle buttons.\n"
        "- Shading & Lighting: warm red, green and cream palette with soft cool shadow fill."
    ),
    "summer": (
        "- Silhouette: breezy flowy tank or short-sleeve shirt with airy drape.\n"
        "- Fabric: lightweight linen and crinkled cotton with an open weave.\n"
        "- Micro-details: tropical and sunny motif shapes, thin rolled hems, shell buttons.\n"
        "- Shading & Lighting: bright sunlight, airy translucent highlights, soft cast shadows."
    ),
    "school": (
        "- Silhouette: fitted academy uniform with a pleated skirt or tailored shorts.\n"
        "- Fabric: crisp cotton poplin and fine tartan plaid.\n"
        "- Micro-details: ribbon tie, blazer lapels, abstract geometric crest emblem.\n"
        "- Shading & Lighting: clean daylight, neat uniform ambient occlusion, polished bright accents."
    ),
    "christmas": (
        "- Silhouette: festive knit sweater with a cozy relaxed fit.\n"
        "- Fabric: chunky wool knit with fluffy faux-fur trim.\n"
        "- Micro-details: snowflake and reindeer-style motifs, jingle-bell accents, candy-cane stripes.\n"
        "- Shading & Lighting: warm red, green and gold palette with soft cosy glow."
    ),
    "halloween": (
        "- Silhouette: torn witchy layered dress or ragged oversized shirt.\n"
        "- Fabric: mottled woven fabric with distressed lace accents.\n"
        "- Micro-details: pumpkin, ghost and spider motifs, bat-wing lace edges, spooky mottled wash.\n"
        "- Shading & Lighting: orange, purple and black palette with eerie moonlight cast."
    ),
    "scene": (
        "- Silhouette: fitted graphic tee with layered arm-warmers or slim jeans.\n"
        "- Fabric: stretch cotton jersey with vivid printed panels.\n"
        "- Micro-details: bold color-blocked shapes, chunky layered highlights, star and lightning "
        "motifs.\n"
        "- Shading & Lighting: hot pink, electric blue and lime against black with punchy contrast."
    ),
    "y2k_dark": (
        "- Silhouette: low-slung tactical cargo pants with a cropped zip-up hoodie.\n"
        "- Fabric: washed charcoal #1a1a1e denim and dark ballistic nylon (never pure #000000).\n"
        "- Micro-details: dark chrome stars, cyber-tribal prints, spiderweb filigree, gunmetal "
        "grommets and chains.\n"
        "- Shading & Lighting: high-contrast dark creases with stark silver specular rim light."
    ),
    "minimalist_og": (
        "- Silhouette: blocky classic silhouette with timeless clean proportions.\n"
        "- Fabric: heavyweight combed cotton and crisp rigid denim twill.\n"
        "- Micro-details: ultra-clean color blocking, high-contrast seam separation, zero clutter.\n"
        "- Shading & Lighting: crisp vector-like edge highlights, minimal wrinkle noise, "
        "architectural shading."
    ),
    "japanese_streetwear": (
        "- Silhouette: loose kimono-cut jacket or noragi over wide-leg hakama-style trousers.\n"
        "- Fabric: structured heavy canvas and textured linen-cotton weave.\n"
        "- Micro-details: abstract brushwork patches, braided cord straps, wrapped waist ties.\n"
        "- Shading & Lighting: sharp cel-shaded creases with dramatic high-contrast street shadows."
    ),
    "cyberpunk": (
        "- Silhouette: technical armored bomber jacket with modular exoskeleton combat trousers.\n"
        "- Fabric: matte carbon-fiber panels over ballistic tech fabric.\n"
        "- Micro-details: mechanical armor plates, high-contrast neon emissive glowing trims in cyan, "
        "magenta and lime along dark seams.\n"
        "- Shading & Lighting: dark metallic reflections with vibrant specular neon bloom."
    ),
    "scifi": (
        "- Silhouette: aerodynamic fitted flight suit with streamlined composite plating.\n"
        "- Fabric: synthetic poly-mesh reinforced with ceramic composite panels.\n"
        "- Micro-details: glowing telemetry piping, modular hardpoint slots, magnetic latch lines, "
        "pressure seal rings.\n"
        "- Shading & Lighting: clean sterile ambient occlusion with high-tech emissive light strips."
    ),
}

GENERIC_STYLE_DETAILS = (
    "- Silhouette: read the existing garment shape and keep its cut.\n"
    "- Fabric: enrich the weave and material feel appropriate to the theme.\n"
    "- Micro-details: add eye-catching ornaments and intricate trims with no text or logos.\n"
    "- Shading & Lighting: dramatic shading, ambient occlusion and crisp highlights that clearly "
    "read from far away."
)

PROVIDER_PROMPT = (
    "You are a senior virtual fashion designer specializing in Roblox 2D classic clothing UV templates "
    "(a flat 585x559 RGBA sprite sheet, top down, close up, flat texture, symmetrical).\n"
    "You are given an existing flat 2D clothing texture. Your mission is to completely UPGRADE, REDESIGN "
    "and POLISH it so it matches the trending {style} aesthetic.\n\n"
    "CRITICAL GEOMETRY RULES (DO NOT BREAK):\n"
    "- OUTPUT AN ORTHOGRAPHIC 2D UV UNWRAPPED TEXTURE ATLAS ONLY - a planar unfolded cube net with zero "
    "perspective distortion, zero camera depth of field and zero foreshortening. This is a texture map, "
    "NOT a photo. DO NOT draw human bodies, mannequins, faces, limbs, flesh, dolls, hangers, or "
    "background scenes.\n"
    "- Treat every garment section as an ISOLATED RECTANGULAR UV ISLAND: Front/Back torso (128x128), "
    "Side torso, sleeves and legs (64x128). Keep razor-sharp panel edges, zero edge bleed, zero "
    "overspray and no feathering across the empty gutters between islands.\n"
    "- DO NOT change the panel layout of the template. The background and all non-fabric negative space "
    "MUST stay completely empty and unpainted - never fill it in with white, gray, gradients, cast "
    "shadows, or a checkerboard transparency grid.\n"
    "- SEAM-SAFE ALIGNMENT: keep every horizontal cut (hem, belt, waistband, stripes, jacket zippers) "
    "perfectly level and aligned across the Front and Back torso panels (128x128) and the Side Torso "
    "panels (64x128), so the line wraps around the avatar without a break. Sleeve and leg panels "
    "(64x128) must continue seamlessly across every adjacent face - no offset, no gap, no stray white "
    "line at the seam.\n"
    "- DO NOT add any text, typography, letters, numbers, logos, brand names, or watermarks - "
    "copyrighted brand marks get rejected by moderation.\n"
    "- NO heavy blur, depth of field or color smearing: the texture is viewed at low resolution on a "
    "blocky avatar, so every detail must stay crisp and readable.\n"
    "- Maintain the exact original image dimensions.\n\n"
    "REVEALING / CUT-OUT CONSTRUCTION & SAFETY:\n"
    "- When the style calls for revealing cuts (tube tops, halter necks, low-rise waists, backless or "
    "side cut-outs, sheer mesh), express them only through garment construction: precisely bounded "
    "cutaway panels, hollow lattice negative space, open-back strap harnesses and translucent layered "
    "mesh. All exposed/non-fabric areas must remain completely empty and unpainted (no fill, no semi-"
    "transparent halo) exactly like the template background, so the avatar body shows through "
    "naturally in-game.\n"
    "- NEVER paint skin, flesh tones, body parts, nipples, cleavage or anatomical contours. Do NOT "
    "paint breast volume, underboob shadows, gluteal creases, belly buttons or push-up shading onto "
    "the fabric - garment shading is limited to fabric wrinkles, folds, seams and hardware.\n"
    "- TASTEFUL COVERAGE: keep every top substantial and fashion-forward; never design string micro-"
    "tops, thong cuts or lingerie-like silhouettes. All cut edges must be cleanly bound with crisp "
    "contrast stitching.\n"
    "- Keep every revealing detail tasteful, editorial and non-explicit so it passes Roblox "
    "moderation.\n\n"
    "FASHION DIRECTIVES - {style} AESTHETIC:\n"
    "{style_details}\n"
    "{nudity_rule}\n"
    "FABRIC & LIGHTING QUALITY (FAKE-3D UGC DEPTH):\n"
    "- 3D CYLINDRICAL ILLUSION: avatars are rigid blocks - fake 3D volume with consistent 45-degree "
    "overhead studio lighting, subtle darker gradient falloff near outer panel edges and soft vertical "
    "center highlights so sleeves and torso read as rounded, not flat.\n"
    "- FAKE NORMAL MAP & CAST SHADOWS: every seam, collar, pocket flap, strap and waistband needs "
    "tactile relief - a 1px bright micro-bevel on its top edge and a 1-2px deep contact cast shadow "
    "beneath it to fake layered fabric thickness.\n"
    "- MATERIAL SPECULAR HIERARCHY: hardware (zippers, chains, eyelets, buckles, O-rings) gets razor-"
    "sharp white specular gleams against dark reflections; leather/vinyl gets glossy highlight "
    "ribbons; denim and knit stay soft and diffuse.\n"
    "- ANATOMICAL TENSION FOLDS: paint fabric physics - diagonal tension wrinkles radiating from "
    "fastened buttons, zippers and seams, plus horizontal accordion compression folds at waistbands, "
    "armpits and cuffs.\n"
    "- MICRO-STITCHING: render ultra-crisp contrast stitching (about a 2px solid line with a 1px gap) "
    "along collar, hems, pocket edges and panel seams, with a 1px shadow offset for thread depth.\n"
    "- RICH DARKS & NO MUD: for dark or black garments use rich charcoal (about #1a1a1e) with silver "
    "highlight creases instead of pure #000000, so every fold and seam stays visible in-game.\n"
    "- Never leave flat solid colors: add realistic fabric weave (denim twill, ribbed knit, distressed "
    "seams, faded wash) appropriate to the style, and make colors pop with premium top-tier accents.\n\n"
    "Output ONLY the finalized, visually stunning flat clothing texture."
)


def _resize_filter():
    return getattr(Image, "Resampling", Image).LANCZOS


def _format_cookie_entries(entries):
    parts = [
        f"{entry['name']}={entry['value']}"
        for entry in entries
        if isinstance(entry, dict) and entry.get("name") and entry.get("value")
    ]
    return "; ".join(parts) or None


def _normalize_cookie(raw):
    """Convert cookie from various formats to a header string.

    Accepts:
      - Plain header string: "name1=value1; name2=value2"
      - JSON array string:   '[{"name":"SID","value":"..."},...]'
      - Python list of dicts: [{"name":"SID","value":"..."},...]
    Returns header string or None.
    """
    if not raw:
        return None

    if isinstance(raw, list):
        return _format_cookie_entries(raw)

    raw = str(raw).strip()
    if not raw:
        return None

    if raw.startswith("["):
        try:
            cookie_list = json.loads(raw)
        except (json.JSONDecodeError, TypeError, KeyError):
            return raw
        if isinstance(cookie_list, list):
            return _format_cookie_entries(cookie_list)

    return raw


def _build_prompt(style):
    nudity_rule = ""
    if CONFIG_MAX_NUDITY:
        nudity_rule = (
            "- IMPORTANT: The design will be scanned by a moderation bot. "
            f"It MUST pass a safety score (max_nudity_value <= {CONFIG_MAX_NUDITY}). "
            "Be as creative and gorgeous as possible without triggering the automated nudity filter."
        )
    style_details = STYLE_LEXICON.get(style, GENERIC_STYLE_DETAILS)
    return PROVIDER_PROMPT.format(
        style=style,
        style_details=style_details,
        nudity_rule=nudity_rule,
    )


def configure(provider=None, gemini_api_key=None, gemini_api_keys=None,
              gemini_model=None, gemini_cookie=None,
              gemini_cookie_min_delay_seconds=None,
              gemini_cookie_cooldown_seconds=None,
              gemini_cookie_max_strategies=None,
              gemini_download_cookie=None,
              max_nudity_value=0.08,
              replicate_api_token=None, sd_model_version=None,
              sd_prompt_strength=None, use_controlnet=None):
    """Configure the enhance module.

    Args:
        provider: "gemini_cookie", "gemini", "openai", "photoroom", "replicate_sd"
        gemini_api_key: single API key (backward compat)
        gemini_api_keys: list of API keys for rotation
        gemini_model: Gemini model name for API key provider
        gemini_cookie: browser cookie string for Gemini web provider
        gemini_download_cookie: optional dedicated cookie for downloading generated images
        replicate_api_token: Replicate API token for the "replicate_sd" provider
        sd_model_version: Replicate model reference — "owner/model",
            "owner/model:version" or a bare version hash
        sd_prompt_strength: optional img2img strength (0-1) forwarded to the
            Replicate model as "prompt_strength"
        use_controlnet: attach the current texture as "image" input so a
            ControlNet-conditioned SD model locks the UV layout (default True)
    """
    global CONFIG_PROVIDER, CONFIG_GEMINI_API_KEYS, CONFIG_GEMINI_MODEL
    global CONFIG_GEMINI_COOKIE, CONFIG_GEMINI_DOWNLOAD_COOKIE, CONFIG_GEMINI_COOKIE_OPTIONS
    global _GEMINI_COOKIE_CLIENT, CONFIG_MAX_NUDITY
    global CONFIG_REPLICATE_API_TOKEN, CONFIG_SD_MODEL_VERSION, CONFIG_USE_CONTROLNET
    global CONFIG_SD_PROMPT_STRENGTH
    CONFIG_PROVIDER = provider or None
    CONFIG_GEMINI_MODEL = gemini_model or None
    CONFIG_MAX_NUDITY = max_nudity_value
    CONFIG_REPLICATE_API_TOKEN = (str(replicate_api_token).strip()
                                  if replicate_api_token else None) or None
    CONFIG_SD_MODEL_VERSION = (str(sd_model_version).strip()
                               if sd_model_version else None) or None
    if use_controlnet is not None:
        CONFIG_USE_CONTROLNET = bool(use_controlnet)
    if sd_prompt_strength is not None:
        try:
            CONFIG_SD_PROMPT_STRENGTH = float(sd_prompt_strength)
        except (TypeError, ValueError):
            CONFIG_SD_PROMPT_STRENGTH = None

    # Normalize API keys: merge single + list, strip, remove empty, dedupe
    raw_keys = []
    if isinstance(gemini_api_keys, list):
        raw_keys.extend(gemini_api_keys)
    if gemini_api_key and isinstance(gemini_api_key, str):
        raw_keys.append(gemini_api_key)
    seen = set()
    clean_keys = []
    for k in raw_keys:
        k = str(k).strip()
        if k and k not in seen:
            seen.add(k)
            clean_keys.append(k)
    CONFIG_GEMINI_API_KEYS = clean_keys

    # Gemini cookie — accept both header string and JSON array format
    CONFIG_GEMINI_COOKIE = _normalize_cookie(gemini_cookie)
    CONFIG_GEMINI_DOWNLOAD_COOKIE = _normalize_cookie(gemini_download_cookie)
    CONFIG_GEMINI_COOKIE_OPTIONS = {
        "min_stream_interval": gemini_cookie_min_delay_seconds,
        "rate_limit_cooldown": gemini_cookie_cooldown_seconds,
        "max_attachment_strategies": gemini_cookie_max_strategies,
    }
    _GEMINI_COOKIE_CLIENT = None  # reset cached client
    if CONFIG_PROVIDER:
        print(f"[config] enhance provider={CONFIG_PROVIDER}")
    if CONFIG_GEMINI_COOKIE:
        print(f"[config] gemini cookie loaded ({len(CONFIG_GEMINI_COOKIE)} chars)")


def _tokens(*parts):
    text = " ".join(str(part or "") for part in parts).lower()
    return set(re.findall(r"\w+", text))


def detect_style(item_name, search_tags):
    text = re.sub(r"[\W_]+", " ", f"{item_name} {search_tags}".lower())
    words = set(text.split())
    scores = {}
    for style, keywords in STYLE_KEYWORDS.items():
        score = 0
        for keyword in keywords:
            normalized = re.sub(r"[\W_]+", " ", str(keyword).lower()).strip()
            if not normalized:
                continue
            if " " in normalized:
                if normalized in text:
                    score += 2
            elif normalized in words:
                score += 1
        scores[style] = score
    best_style, best_score = max(scores.items(), key=lambda item: item[1])
    return best_style if best_score else "clean"


def _polish_image(image, style):
    brightness, contrast, color, sharpness = POLISH_PRESETS.get(style, POLISH_PRESETS["clean"])
    image = ImageEnhance.Brightness(image).enhance(brightness)
    image = ImageEnhance.Contrast(image).enhance(contrast)
    image = ImageEnhance.Color(image).enhance(color)
    image = ImageEnhance.Sharpness(image).enhance(sharpness)
    return image.filter(ImageFilter.SMOOTH_MORE if style in {"cute", "kawaii", "soft"} else ImageFilter.SHARPEN)


def _overlay_candidates(style):
    candidates = []
    for folder in OVERLAY_FOLDERS.get(style, ["preppy"]):
        folder_path = os.path.join(OVERLAY_ROOT, folder)
        if not os.path.isdir(folder_path):
            continue
        for filename in os.listdir(folder_path):
            if filename.lower().endswith(ALLOWED_OVERLAY_EXTENSIONS):
                candidates.append(os.path.join(folder_path, filename))
    return candidates


def _apply_overlay(image, overlay_path, opacity=0.32):
    overlay = Image.open(overlay_path).convert("RGBA").resize(image.size, _resize_filter())
    alpha = overlay.getchannel("A").point(lambda value: int(value * opacity))
    # Never paint outside the garment: mask the overlay with the image alpha so
    # transparent template areas stay transparent.
    alpha = ImageChops.multiply(alpha, image.getchannel("A"))
    overlay.putalpha(alpha)
    return Image.alpha_composite(image, overlay)


# Roblox classic shirt (585x559) torso rectangles measured from src/assets/template/template.png:
# side/hip panels x 165..228 and 359..424, back panel x 427..554, all spanning y 74..201.
CC_SIDE_PANEL_BOXES = ((165, 74, 228, 201), (359, 74, 424, 201))
CC_BACK_PANEL_BOXES = ((427, 74, 554, 201),)
CC_SIDE_DARKEN_ALPHA = 20  # ~-7.8% brightness on the hips/side panels
CC_BACK_DARKEN_ALPHA = 13  # ~-5.1% brightness on the back panel
CC_SEAM_HIGHLIGHT_STRENGTH = 0.05  # ~+5% white along the inner seam edge


def _apply_fabric_depth(image, strength=0.45):
    """Inner shadow, block color-coding and a seam highlight so panels read as 3D on avatars."""
    alpha = image.getchannel("A")
    if alpha.getextrema()[1] == 0:
        return image

    eroded = alpha.filter(ImageFilter.MinFilter(5))
    inner = ImageChops.subtract(alpha, eroded).point(lambda value: int(value * strength))
    shade = Image.new("RGBA", image.size, (0, 0, 0, 0))
    shade.putalpha(inner)
    image = Image.alpha_composite(image, shade)

    scale_x = image.size[0] / 585.0
    scale_y = image.size[1] / 559.0

    def scaled(box):
        return (
            int(box[0] * scale_x), int(box[1] * scale_y),
            int(box[2] * scale_x), int(box[3] * scale_y),
        )

    color_coding = Image.new("RGBA", image.size, (0, 0, 0, 0))
    coding_draw = ImageDraw.Draw(color_coding)
    for box in CC_SIDE_PANEL_BOXES:
        coding_draw.rectangle(scaled(box), fill=(0, 0, 0, CC_SIDE_DARKEN_ALPHA))
    for box in CC_BACK_PANEL_BOXES:
        coding_draw.rectangle(scaled(box), fill=(0, 0, 0, CC_BACK_DARKEN_ALPHA))
    color_coding.putalpha(ImageChops.multiply(color_coding.getchannel("A"), alpha))
    image = Image.alpha_composite(image, color_coding)

    eroded_tight = alpha.filter(ImageFilter.MinFilter(3))
    seam = ImageChops.subtract(alpha, eroded_tight).point(
        lambda value: int(value * CC_SEAM_HIGHLIGHT_STRENGTH))
    seam = ImageChops.multiply(seam, alpha)
    highlight = Image.new("RGBA", image.size, (255, 255, 255, 0))
    highlight.putalpha(seam)
    return Image.alpha_composite(image, highlight)


def _apply_template(image):
    if not os.path.exists(TEMPLATE_PATH):
        return image
    template = Image.open(TEMPLATE_PATH).convert("RGBA").resize(image.size, _resize_filter())
    image = image.copy()
    image.paste(template, (0, 0), mask=template)
    return image


def _difference_score(before, after):
    diff = ImageChops.difference(before.convert("RGB"), after.convert("RGB"))
    histogram = diff.histogram()
    total = sum(value * (index % 256) for index, value in enumerate(histogram))
    pixels = before.size[0] * before.size[1] * 3
    rgb_score = total / float(max(pixels, 1))
    alpha_diff = ImageChops.difference(before.getchannel("A"), after.getchannel("A"))
    alpha_histogram = alpha_diff.histogram()
    alpha_total = sum(value * (index % 256) for index, value in enumerate(alpha_histogram))
    alpha_pixels = before.size[0] * before.size[1]
    alpha_score = alpha_total / float(max(alpha_pixels, 1))
    return (rgb_score + alpha_score) / 2.0


def _valid_output(original, candidate):
    if candidate.size != original.size:
        return False
    if candidate.mode != "RGBA":
        return False
    score = _difference_score(original, candidate)
    return 0.2 <= score <= 45


def _cleanup_stale_temp_files(max_age_seconds=3600):
    if not os.path.isdir(TEMP_IMAGE_DIR):
        return
    now = time.time()
    for filename in os.listdir(TEMP_IMAGE_DIR):
        file_path = os.path.join(TEMP_IMAGE_DIR, filename)
        try:
            if os.path.isfile(file_path) and now - os.path.getmtime(file_path) > max_age_seconds:
                os.remove(file_path)
        except OSError:
            pass


def _save_bytes_to_temp(image_bytes):
    os.makedirs(TEMP_IMAGE_DIR, exist_ok=True)
    fd, path = tempfile.mkstemp(prefix="enhance_", suffix=".png", dir=TEMP_IMAGE_DIR)
    os.close(fd)
    with open(path, "wb") as output_file:
        output_file.write(image_bytes)
    return path


def _download_image(url):
    response = requests.get(url, timeout=REQUEST_TIMEOUT)
    response.raise_for_status()
    return response.content


def _image_cache_key(path, style):
    hasher = hashlib.sha256()
    with open(path, "rb") as image_file:
        for chunk in iter(lambda: image_file.read(1024 * 1024), b""):
            hasher.update(chunk)
    provider = (CONFIG_PROVIDER or os.environ.get("XOOL_ENHANCE_PROVIDER", "local")).strip().lower() or "local"
    return hashlib.sha256(f"v3:{provider}:{style}:{hasher.hexdigest()}".encode("utf-8")).hexdigest()


def _cache_path(cache_key):
    return os.path.join(ENHANCE_CACHE_ROOT, f"{cache_key}.png")


def _load_cached_image(path, original, cache_key):
    cached_path = _cache_path(cache_key)
    if not os.path.exists(cached_path):
        return False
    try:
        cached = Image.open(cached_path).convert("RGBA")
        cached = _apply_template(cached)
        if not _valid_output(original, cached):
            return False
        cached.save(path)
        print("enhanced asset mode=cache")
        return True
    except Exception as error:
        print(f"enhance cache rejected: {error}")
        return False


def _save_cached_image(image, cache_key):
    os.makedirs(ENHANCE_CACHE_ROOT, exist_ok=True)
    image.save(_cache_path(cache_key))


def _enhance_with_openai(path, style):
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        return None

    with open(path, "rb") as image_file:
        response = requests.post(
            "https://api.openai.com/v1/images/edits",
            headers={"Authorization": f"Bearer {api_key}"},
            data={
                "model": os.environ.get("XOOL_OPENAI_IMAGE_MODEL", "gpt-image-1"),
                "prompt": _build_prompt(style),
                "n": "1",
                "background": "transparent",
            },
            files={"image": (os.path.basename(path), image_file, "image/png")},
            timeout=REQUEST_TIMEOUT,
        )
    response.raise_for_status()
    data = response.json()["data"][0]
    if data.get("b64_json"):
        return _save_bytes_to_temp(base64.b64decode(data["b64_json"]))
    if data.get("url"):
        return _save_bytes_to_temp(_download_image(data["url"]))
    return None


def _enhance_with_photoroom(path, style):
    api_key = os.environ.get("PHOTOROOM_API_KEY")
    if not api_key:
        return None

    with open(path, "rb") as image_file:
        response = requests.post(
            "https://image-api.photoroom.com/v2/edit",
            headers={"x-api-key": api_key},
            data={
                "removeBackground": "false",
                "beautify.mode": "ai.auto",
                "lighting.mode": "ai.auto",
                "editWithAI.mode": "ai.auto",
                "editWithAI.prompt": _build_prompt(style),
                "export.format": "png",
            },
            files={"imageFile": image_file},
            timeout=REQUEST_TIMEOUT,
        )
    response.raise_for_status()
    return _save_bytes_to_temp(response.content)


def _enhance_with_gemini_cookie(path, style):
    """Enhance clothing via Gemini web using browser cookie."""
    global _GEMINI_COOKIE_CLIENT

    cookie = CONFIG_GEMINI_COOKIE or os.environ.get("GEMINI_COOKIE")
    if not cookie:
        print("[gemini] no cookie configured (gemini_cookie is empty)")
        return None

    try:
        from src.enhance.gemini_client import GeminiFatalResponseError, XoolGeminiClient
    except ImportError as e:
        print(f"[gemini] client import failed: {e}")
        return None

    # Re-use cached client or create a new one
    if _GEMINI_COOKIE_CLIENT is None:
        try:
            _GEMINI_COOKIE_CLIENT = XoolGeminiClient(
                cookie,
                download_cookie=CONFIG_GEMINI_DOWNLOAD_COOKIE,
                **CONFIG_GEMINI_COOKIE_OPTIONS,
            )
            print("[gemini] client initialized OK")
        except Exception as e:
            print(f"[gemini] client init FAILED: {e}")
            return None

    prompt = _build_prompt(style)

    for attempt in range(2):
        try:
            result_path = _GEMINI_COOKIE_CLIENT.enhance_image(path, prompt)
            return result_path
        except GeminiFatalResponseError as e:
            print(f"[gemini] fatal Gemini web error, resetting client: {e}")
            _GEMINI_COOKIE_CLIENT = None
            return None
        except Exception as e:
            if attempt == 0:
                print(f"[gemini] attempt 1 failed, retrying in 15s: {e}")
                time.sleep(15)
                _GEMINI_COOKIE_CLIENT = None
                try:
                    _GEMINI_COOKIE_CLIENT = XoolGeminiClient(
                        cookie,
                        download_cookie=CONFIG_GEMINI_DOWNLOAD_COOKIE,
                        **CONFIG_GEMINI_COOKIE_OPTIONS,
                    )
                except Exception:
                    pass
            else:
                print(f"[gemini] attempt 2 failed, giving up: {e}")
    return None


def _gemini_post_with_retries(url, headers, payload, key_label):
    """POST to Gemini, retrying rate limits and network errors.

    Returns (response, exhausted). exhausted=True means this key cannot be
    used (auth error or retries spent) and the caller should try the next key.
    """
    for attempt in range(len(GEMINI_RETRY_DELAYS) + 1):
        try:
            response = requests.post(url, headers=headers, json=payload, timeout=REQUEST_TIMEOUT)
        except (requests.Timeout, requests.ConnectionError):
            if attempt < len(GEMINI_RETRY_DELAYS):
                wait = GEMINI_RETRY_DELAYS[attempt]
                print(f"gemini api {key_label} request failed; retrying in {wait}s")
                time.sleep(wait)
                continue
            return None, True

        if response.status_code in (429, 503):
            if attempt < len(GEMINI_RETRY_DELAYS):
                wait = GEMINI_RETRY_DELAYS[attempt]
                print(f"gemini api {key_label} rate limited; retrying in {wait}s")
                time.sleep(wait)
                continue
            return None, True
        if response.status_code in (401, 403):
            print(f"gemini api {key_label} auth error {response.status_code}")
            return None, True
        return response, False

    return None, True


def _enhance_with_gemini(path, style):
    """Enhance clothing via official Gemini API with key rotation."""
    # Build key list: config keys + env key
    keys = list(CONFIG_GEMINI_API_KEYS)
    env_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if env_key and env_key not in keys:
        keys.append(env_key)
    if not keys:
        return None

    model = CONFIG_GEMINI_MODEL or os.environ.get("XOOL_GEMINI_MODEL", "gemini-3.1-flash-image")
    if "image" not in model.lower():
        print(f"gemini api: model {model} may not return image data; use gemini-3.1-flash-image")
    with open(path, "rb") as image_file:
        image_data = base64.b64encode(image_file.read()).decode("utf-8")

    payload = {
        "contents": [{
            "parts": [
                {
                    "text": _build_prompt(style)
                },
                {
                    "inlineData": {
                        "mimeType": "image/png",
                        "data": image_data,
                    }
                },
            ]
        }],
        "generationConfig": {
            "responseModalities": ["TEXT", "IMAGE"]
        }
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    for key_index, api_key in enumerate(keys):
        key_label = f"key {key_index + 1}/{len(keys)}"
        headers = {
            "x-goog-api-key": api_key,
            "Content-Type": "application/json",
        }

        response, exhausted = _gemini_post_with_retries(url, headers, payload, key_label)
        if exhausted:
            print(f"gemini api {key_label} exhausted, trying next key")
            continue

        response.raise_for_status()

        text_samples = []
        for candidate in response.json().get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline_data = part.get("inlineData") or part.get("inline_data")
                if inline_data and inline_data.get("data"):
                    return _save_bytes_to_temp(base64.b64decode(inline_data["data"]))
                if part.get("text"):
                    text_samples.append(str(part["text"]).replace("\n", " ")[:160])
        if text_samples:
            print(f"gemini api {key_label} returned text, not an image: {text_samples[0]}")
        else:
            print(f"gemini api {key_label} returned no image data with model {model}")
        continue

    # All keys exhausted
    print("gemini api: all keys exhausted, falling back to local")
    return None


def _build_sd_prompt(style):
    return SD_PROMPT_TEMPLATE.format(style=style)


def _enhance_with_sd_replicate(path, style):
    """Enhance clothing via a Replicate-hosted SD model (e.g. a Roblox-shirt LoRA).

    Requires `replicate_api_token` plus `sd_model_version` (configured in
    ai_settings.json / configure()). `sd_model_version` accepts three forms:
    "owner/model" (fetched via the model endpoint, e.g. black-forest-labs/flux-dev),
    "owner/model:version" or a bare version hash (both sent to the predictions
    endpoint as-is, per Replicate's accepted version syntax). With `use_controlnet`
    (default true) the current texture is attached as the "image" input so the
    model refines the existing design instead of inventing a new one, and the
    optional `sd_prompt_strength` is forwarded as "prompt_strength" for img2img
    models. Any failure returns None so the caller falls back to the local
    pipeline.
    """
    token = CONFIG_REPLICATE_API_TOKEN or os.environ.get("REPLICATE_API_TOKEN", "").strip()
    version = CONFIG_SD_MODEL_VERSION or os.environ.get("XOOL_SD_MODEL_VERSION", "").strip()
    if not token:
        print("[sd] no replicate_api_token configured")
        return None
    if not version:
        print("[sd] sd_model_version not configured (Replicate owner/model, owner/model:version or hash)")
        return None

    sd_input = {"prompt": _build_sd_prompt(style)}
    if CONFIG_USE_CONTROLNET:
        with open(path, "rb") as image_file:
            encoded = base64.b64encode(image_file.read()).decode("ascii")
        sd_input["image"] = f"data:image/png;base64,{encoded}"
    if CONFIG_SD_PROMPT_STRENGTH is not None:
        sd_input["prompt_strength"] = CONFIG_SD_PROMPT_STRENGTH
    if "/" in version and ":" not in version:
        endpoint = REPLICATE_MODELS_URL.format(model=version)
        body = {"input": sd_input}
    else:
        endpoint = REPLICATE_API_URL
        body = {"version": version, "input": sd_input}
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(endpoint, headers=headers,
                                 json=body,
                                 timeout=REQUEST_TIMEOUT)
        response.raise_for_status()
        prediction = response.json()
    except Exception as error:
        print(f"[sd] replicate request failed: {error}")
        return None

    get_url = (prediction.get("urls") or {}).get("get")
    deadline = time.time() + SD_POLL_TIMEOUT_SECONDS
    while prediction.get("status") in ("starting", "processing") and get_url:
        if time.time() >= deadline:
            print("[sd] replicate prediction timed out")
            return None
        time.sleep(SD_POLL_INTERVAL_SECONDS)
        try:
            response = requests.get(get_url, headers=headers, timeout=REQUEST_TIMEOUT)
            response.raise_for_status()
            prediction = response.json()
        except Exception as error:
            print(f"[sd] replicate poll failed: {error}")
            return None

    status = prediction.get("status")
    output = prediction.get("output")
    if status != "succeeded" or not output:
        print(f"[sd] replicate prediction status={status}")
        return None
    url = output[0] if isinstance(output, list) and output else output
    if not isinstance(url, str) or not url.startswith("http"):
        print("[sd] replicate returned no usable output url")
        return None
    try:
        return _save_bytes_to_temp(_download_image(url))
    except Exception as error:
        print(f"[sd] replicate download failed: {error}")
        return None


def _provider_result(path, style):
    provider = (CONFIG_PROVIDER or os.environ.get("XOOL_ENHANCE_PROVIDER", "")).strip().lower()
    handlers = {
        "gemini_cookie": _enhance_with_gemini_cookie,
        "openai": _enhance_with_openai,
        "photoroom": _enhance_with_photoroom,
        "gemini": _enhance_with_gemini,
        "replicate_sd": _enhance_with_sd_replicate,
    }
    handler = handlers.get(provider)
    if handler is None:
        return None
    try:
        return handler(path, style)
    except Exception as error:
        print(f"enhance provider failed, using local polish: {error}")
    return None


def _garment_type(path):
    parts = [part.lower() for part in re.split(r"[\\/]+", str(path))]
    return "pants" if "pants" in parts else "shirt"


def _apply_shading_map(image, garment_type="shirt", opacity=0.4):
    """Multiply the pre-baked AO map into the garment, alpha-masked and neutral outside."""
    filename = "pants_ao_template.png" if garment_type == "pants" else "shirt_ao_template.png"
    shading_path = os.path.join(SHADING_ROOT, filename)
    if not os.path.exists(shading_path):
        return image
    shading = Image.open(shading_path).convert("L").resize(image.size, _resize_filter())
    alpha = image.getchannel("A")
    scaled = shading.point(lambda value: 255 - int((255 - value) * opacity))
    factor = Image.composite(scaled, Image.new("L", image.size, 255), alpha)
    r, g, b, a = image.split()
    r = ImageChops.multiply(r, factor)
    g = ImageChops.multiply(g, factor)
    b = ImageChops.multiply(b, factor)
    return Image.merge("RGBA", (r, g, b, a))


def _local_enhance(original, style, rng, garment_type="shirt"):
    enhanced = _polish_image(original.copy(), style)
    overlays = _overlay_candidates(style)
    if overlays:
        rng.shuffle(overlays)
        for overlay_path in overlays[:2]:
            enhanced = _apply_overlay(enhanced, overlay_path)
    enhanced = _apply_shading_map(enhanced, garment_type)
    enhanced = uv_spec.align_horizontal_seams(enhanced)
    return _apply_template(_apply_fabric_depth(enhanced))


def enhance_clothing(path, item_name="", search_tags=""):
    _cleanup_stale_temp_files()
    try:
        style = detect_style(item_name, search_tags)
        original = Image.open(path).convert("RGBA")
        rng = random.Random(f"{path}:{style}:{item_name}:{search_tags}")
        cache_key = _image_cache_key(path, style)

        if _load_cached_image(path, original, cache_key):
            return style

        provider_path = _provider_result(path, style)
        if provider_path:
            try:
                provider_image = Image.open(provider_path).convert("RGBA")
                if provider_image.size != original.size:
                    provider_image = provider_image.resize(original.size, _resize_filter())
                garment = _garment_type(path)
                provider_image = _apply_shading_map(provider_image, garment)
                provider_image = uv_spec.align_horizontal_seams(provider_image)
                provider_image = _apply_template(_apply_fabric_depth(provider_image))
                if _valid_output(original, provider_image):
                    provider_image.save(path)
                    _save_cached_image(provider_image, cache_key)
                    print(f"enhanced asset style={style} mode=provider")
                    return style
            except Exception as error:
                print(f"enhance provider output rejected: {error}")
            finally:
                try:
                    os.remove(provider_path)
                except OSError:
                    pass

        local_image = _local_enhance(original, style, rng, _garment_type(path))
        if not _valid_output(original, local_image):
            local_image = _apply_template(_polish_image(original.copy(), "clean"))
        local_image.save(path)
        provider = (CONFIG_PROVIDER or os.environ.get("XOOL_ENHANCE_PROVIDER", "")).strip().lower()
        if not provider or provider == "local":
            _save_cached_image(local_image, cache_key)
        print(f"enhanced asset style={style} mode=local")
        return style
    except Exception as error:
        print(f"enhance failed for {path}: {error}")
        return "clean"
