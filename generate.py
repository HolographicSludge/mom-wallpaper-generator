"""Wallpaper generator. Runs on GitHub Actions (Linux), NOT on mom's laptop.

Usage:  python generate.py OUTPUT_DIR

OUTPUT_DIR holds one folder per period, e.g. OUTPUT_DIR/21/00.jpg ... 09.jpg
For the current period AND the next one, any missing set gets generated.
Folders for periods that are already over get deleted.

ai model i'm using: https://huggingface.co/Photoroom/prx-1024-t2i-beta
"""

import random, shutil, sys, time
from datetime import datetime as dt, timezone
from pathlib import Path

# constants
NUM_IMAGES = 10       # MUST match NUM_IMAGES in Set_New_Wallpapers.py
JPEG_QUALITY = 92     # jpg instead of png: ~10x smaller files, keeps the repo small


# helper function - select a random item from a list
def rand(list):
    return list[random.randint(0, len(list)-1)]


# NOTE: no "date = dt.now()" default here on purpose. Python evaluates defaults
# once at startup, so pass the date in (or leave it None) instead.
def period(date=None):
    if date is None:
        date = dt.now(timezone.utc)
    y = date.year - 2026
    m = date.month
    halfm = 0 if date.day<=15 else 1
    return (y*12 + m-1) * 2 + halfm


def getTheme(p):
    HORROR_MOVIES = ["Nightmare on Elm Street", "the movie Friday the 13th", "the movie Scream", "The Shining", "The Exorcist", "the movie It", "the movie Halloween", "Stranger Things"]
    SPACE_SHIT = ["outer space", "planets", "astronauts"]
    THEMES = [
        "new years",            "the northern lights",
        "valentine's day",      "mardi gras",
        "st patrick's day",     "easter",
        "florals",              "forests",         # forests is for earth day without it being literally just text that says "earth day" in a cool font or smth
        "mother's day",         "summer treats",   # summer treats is for end-of-school
        "LGBTQ pride",          "the beach/sea",
        "fourth of july",       "lisa frank",
        "back-to-school",       "science",
        "harry potter",         rand(SPACE_SHIT),
        rand(HORROR_MOVIES),    "halloween",
        "an orchard",           "thanksgiving",
        "a winter wonderland",  "christmas"
    ]
    return THEMES[p % 24]

def getStyle():
    STYLES = ["painting", "watercolor", "pixel art", "cartoon", "vector art"]
    return rand(STYLES)

# takes the period now, so generating NEXT period's images uses NEXT period's theme
def prompt(p):
    theme = getTheme(p)
    style = getStyle()
    final = f"A desktop wallpaper themed around {theme}" + (f" in a {style} style" if random.randint(1, 3)<3 else "")
    return final


def generate(pipe, p):
    import torch
    from PIL import Image

    text = prompt(p)
    seed = random.randint(0, 2**31 - 1)
    print(f"  prompt: {text!r}  seed: {seed}", flush=True)

    image = pipe(
            text,
            width = 1280, height = 720,                          # model is trained around 1024px, so do 720p then upscale
            num_inference_steps = 28,                            # value from the model card; fewer = faster but worse
            guidance_scale = 5.0,                                # value from the model card
            generator = torch.Generator("cpu").manual_seed(seed),
        ).images[0]

    # upscale 1.5x: 1280x720 -> 1920x1080
    return image.resize((1920, 1080), Image.LANCZOS).convert("RGB")


def isComplete(folder):
    return all((folder / f"{i:02d}.jpg").is_file() for i in range(NUM_IMAGES))


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python generate.py OUTPUT_DIR")
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)

    current = period()
    wanted = [current, current + 1]

    # delete sets for periods that are already over
    for folder in out.iterdir():
        if folder.is_dir() and folder.name.isdigit() and int(folder.name) < current:
            print(f"deleting old period {folder.name}")
            shutil.rmtree(folder)

    todo = [p for p in wanted if not isComplete(out / str(p))]
    if not todo:
        print(f"periods {wanted} already have images, nothing to do")
        return

    # load the model only if there's actually something to make (it's a big download)
    import torch
    from diffusers.pipelines.prx import PRXPipeline
    print("loading model...", flush=True)
    pipe = PRXPipeline.from_pretrained("Photoroom/prx-1024-t2i-beta", torch_dtype=torch.bfloat16)

    for p in todo:
        print(f"generating period {p} (theme slot {p % 24})", flush=True)
        # build in a temp folder and rename at the end, so a half-finished set
        # (e.g. the job timed out) never looks finished to mom's laptop
        tmp = out / f"_tmp_{p}"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir()
        for i in range(NUM_IMAGES):
            start = time.time()
            generate(pipe, p).save(tmp / f"{i:02d}.jpg", quality=JPEG_QUALITY)
            print(f"  image {i+1}/{NUM_IMAGES} done in {time.time() - start:.0f}s", flush=True)
        final = out / str(p)
        shutil.rmtree(final, ignore_errors=True)
        tmp.rename(final)


if __name__ == "__main__":
    main()
