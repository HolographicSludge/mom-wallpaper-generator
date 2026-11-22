"""Wallpaper generator. Runs on GitHub Actions (Linux), NOT on mom's laptop.

Usage:  python generate.py OUTPUT_DIR

OUTPUT_DIR holds one folder per period, e.g. OUTPUT_DIR/21/00.jpg ... 09.jpg
For the current period AND the next one, any missing set gets generated.
Folders for periods that are already over get deleted.

ai model i'm using: https://huggingface.co/black-forest-labs/FLUX.2-klein-4B
run on Cloudflare Workers AI's GPUs (free daily allowance), because it was WAY too slow on GitHub's CPU-only runner
needs two env variables (GitHub secrets): CLOUDFLARE_ACCOUNT_ID and CLOUDFLARE_API_TOKEN
"""

import base64, io, os, random, shutil, sys, time
from datetime import datetime as dt, timezone
from pathlib import Path

# constants
NUM_IMAGES = 10       # MUST match NUM_IMAGES in Set_New_Wallpapers.py
JPEG_QUALITY = 92     # jpg instead of png: ~10x smaller files, keeps the repo small
MODEL = "@cf/black-forest-labs/flux-2-klein-4b"   # Cloudflare's name for FLUX.2 klein 4B (Apache 2.0)
MAX_TRIES = 5         # per image, in case Cloudflare is busy or rejects a prompt


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


def getTheme(current):
    HORROR_MOVIES = ["Nightmare on Elm Street", "the movie Friday the 13th", "the movie Scream", "The Shining", "The Exorcist", "the movie It", "the movie Halloween", "Stranger Things"]
    SPACE_SHIT = ["outer space", "planets", "astronauts"]
    WINTER = ["a snowy cabin at night", "a frozen lake with skaters", "a snowy village street", "a snowy forest", "a snow hare", "a snowman", "several snowflake patterns"]
    THANKSGIVING = ["thanksgiving", "an autumn forest", "a pattern of autumn leaves"]
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
        "an orchard",           rand(THANKSGIVING),
        rand(WINTER),           "christmas"
    ]
    return THEMES[current % 24]

def getStyle():
    STYLES = ["painting", "watercolor", "pixel art", "cartoon", "vector art", "arts-and-crafts"]
    return rand(STYLES)

# takes the period now, so generating NEXT period's images uses NEXT period's theme
def prompt(current):
    theme = getTheme(current)
    style = getStyle()
    # no "desktop"/"wallpaper" in the prompt, the model drew laptops, taskbars and watermarks because of those words
    # this model has no negative prompt, but its text encoder is a full language model (Qwen3), so it understands "no X" better than older models did
    final = f"A wide, detailed scene themed around {theme}" + (f" in a {style} style" if random.randint(1, 3)<3 else "") + ". There is no text, lettering, logo or watermark anywhere in the image."
    return final


# asks Cloudflare to make one image, returns it as a Pillow Image.
# tries again (with a freshly picked prompt) if Cloudflare is busy or refuses the prompt
def generate(current):
    import requests
    from PIL import Image

    url = f"https://api.cloudflare.com/client/v4/accounts/{os.environ['CLOUDFLARE_ACCOUNT_ID']}/ai/run/{MODEL}"
    headers = {"Authorization": f"Bearer {os.environ['CLOUDFLARE_API_TOKEN']}"}

    for attempt in range(1, MAX_TRIES + 1):
        text = prompt(current)
        print(f"  prompt: {text!r}", flush=True)
        # this model wants "multipart form data". (None, value) is how requests sends a plain form field
        formFields = {"prompt": (None, text), "width": (None, "1920"), "height": (None, "1080")}
        try:
            response = requests.post(url, headers=headers, files=formFields, timeout=180)
            if response.headers.get("content-type", "").startswith("image/"):
                imageBytes = response.content                       # raw image back
            else:
                body = response.json()
                if not response.ok or not body.get("success", True):
                    raise RuntimeError(f"HTTP {response.status_code}: {body.get('errors')}")
                imageBytes = base64.b64decode(body["result"]["image"])   # base64 image inside JSON
            image = Image.open(io.BytesIO(imageBytes)).convert("RGB")
            # should already be 1920x1080, this is just a safety net
            if image.size != (1920, 1080):
                image = image.resize((1920, 1080), Image.LANCZOS)
            return image
        except Exception as e:
            print(f"  attempt {attempt}/{MAX_TRIES} failed: {e}", flush=True)
            if attempt == MAX_TRIES:
                raise
            time.sleep(10 * attempt)   # wait a bit longer each time


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

    todo = [periodNum for periodNum in wanted if not isComplete(out / str(periodNum))]
    if not todo:
        print(f"periods {wanted} already have images, nothing to do")
        return

    for periodNum in todo:
        print(f"generating period {periodNum} (theme slot {periodNum % 24})", flush=True)
        # build in a temp folder and rename at the end, so a half-finished set
        # (e.g. the job timed out) never looks finished to mom's laptop
        tmp = out / f"_tmp_{periodNum}"
        shutil.rmtree(tmp, ignore_errors=True)
        tmp.mkdir()
        for i in range(NUM_IMAGES):
            start = time.time()
            generate(periodNum).save(tmp / f"{i:02d}.jpg", quality=JPEG_QUALITY)
            print(f"  image {i+1}/{NUM_IMAGES} done in {time.time() - start:.0f}s", flush=True)
        final = out / str(periodNum)
        shutil.rmtree(final, ignore_errors=True)
        tmp.rename(final)


if __name__ == "__main__":
    main()
