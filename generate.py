"""Wallpaper generator. Runs on GitHub Actions (Linux), NOT on mom's laptop.

Usage:  python generate.py OUTPUT_DIR

OUTPUT_DIR holds one folder per period, e.g. OUTPUT_DIR/21/00.jpg ... 09.jpg
For the current period AND the next one, any missing set gets generated.
Folders for periods that are already over get deleted.

ai model i'm using: https://huggingface.co/black-forest-labs/FLUX.2-klein-4B
"""

import random, shutil, sys, time
from datetime import datetime as dt, timezone
from pathlib import Path

# constants
NUM_IMAGES = 10       # MUST match NUM_IMAGES in Set_New_Wallpapers.py
JPEG_QUALITY = 92     # jpg instead of png: ~10x smaller files, keeps the repo small
MODEL = "black-forest-labs/FLUX.2-klein-4B"   # Apache 2.0, step-distilled (only needs 4 steps)


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


def getTheme(period):
    HORROR_MOVIES = ["Nightmare on Elm Street", "the movie Friday the 13th", "the movie Scream", "The Shining", "The Exorcist", "the movie It", "the movie Halloween", "Stranger Things"]
    SPACE_SHIT = ["outer space", "planets", "astronauts"]
    WINTER = ["a snowy cabin at night", "a frozen lake with skaters", "a snowy village street", "a snowy forest", "a snow hare"]
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
        rand(WINTER),           "christmas"
    ]
    return THEMES[period % 24]

def getStyle():
    STYLES = ["painting", "watercolor", "pixel art", "cartoon", "vector art"]
    return rand(STYLES)

# takes the period now, so generating NEXT period's images uses NEXT period's theme
def prompt(period):
    theme = getTheme(period)
    style = getStyle()
    # no "desktop"/"wallpaper" in the prompt, the model drew laptops, taskbars and watermarks because of those words
    # this model has no negative prompt, but its text encoder is a full language model (Qwen3), so it understands "no X" better than older models did
    final = f"A wide, detailed scene themed around {theme}" + (f" in a {style} style" if random.randint(1, 3)<3 else "") + ". There is no text, lettering, logo or watermark anywhere in the image."
    return final


# turns prompt text into the numbers the image model actually uses.
# done for ALL images first, so the text encoder (~8 GB) can be deleted from RAM before the image model (~8 GB) is loaded. both at once wouldn't fit in 16 GB.
def encodePrompts(texts):
    import gc, torch
    from diffusers import Flux2KleinPipeline
    print("loading text encoder...", flush=True)
    enc = Flux2KleinPipeline.from_pretrained(MODEL, transformer=None, vae=None, dtype=torch.bfloat16)
    embeds = []
    with torch.no_grad():
        for text in texts:
            embeds.append(enc.encode_prompt(prompt=text)[0])
    del enc
    gc.collect()
    return embeds


def generate(pipe, embeds):
    import torch
    from PIL import Image

    seed = random.randint(0, 2**31 - 1)
    image = pipe(
            prompt_embeds = embeds,
            width = 1280, height = 720,                          # model isn't trained for 1080p, so do 720p then upscale
            num_inference_steps = 4,                             # klein is step-distilled: 4 steps is what it's made for
            generator = torch.Generator("cpu").manual_seed(seed),
        ).images[0]

    # upscale to 1080p
    return image.resize((1920, 1080), Image.LANCZOS).convert("RGB")


def isComplete(folder):
    return all((folder / f"{i:02d}.jpg").is_file() for i in range(NUM_IMAGES))


def main():
    if len(sys.argv) != 2:
        sys.exit("usage: python generate.py OUTPUT_DIR")
    out = Path(sys.argv[1])
    out.mkdir(parents=True, exist_ok=True)

    current = period()
    wanted = [current, current+1]

    # delete sets for periods that are already over
    for folder in out.iterdir():
        if folder.is_dir() and folder.name.isdigit() and int(folder.name) < current:
            print(f"deleting old period {folder.name}")
            shutil.rmtree(folder)

    todo = [period for period in wanted if not isComplete(out / str(period))]
    if not todo:
        print(f"periods {wanted} already have images, nothing to do")
        return

    # decide every prompt up front, then turn them all into embeddings in one go
    jobs = []   # (period, image number, prompt text)
    for period in todo:
        for i in range(NUM_IMAGES):
            jobs.append((period, i, prompt(period)))
    allEmbeds = encodePrompts([text for _, _, text in jobs])

    import torch
    from diffusers import Flux2KleinPipeline
    print("loading image model...", flush=True)
    pipe = Flux2KleinPipeline.from_pretrained(MODEL, text_encoder=None, tokenizer=None, dtype=torch.bfloat16)

    for period in todo:
        print(f"generating period {period} (theme slot {period % 24})", flush=True)
        # build in a temp folder and rename at the end, so a half-finished set
        # (e.g. the job timed out) never looks finished to mom's laptop
        tmp = out / f"_tmp_{period}"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir()
        for (jp, i, text), embeds in zip(jobs, allEmbeds):
            if jp != period:
                continue
            print(f"  prompt: {text!r}", flush=True)
            start = time.time()
            generate(pipe, embeds).save(tmp / f"{i:02d}.jpg", quality=JPEG_QUALITY)
            print(f"  image {i+1}/{NUM_IMAGES} done in {time.time() - start:.0f}s", flush=True)
        final = out / str(period)
        shutil.rmtree(final, ignore_errors=True)
        tmp.rename(final)


if __name__ == "__main__":
    main()
