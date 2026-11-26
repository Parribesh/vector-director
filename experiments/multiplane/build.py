"""One outline scene -> a multiplane set: the builder's plan, then each layer painted.
    python experiments/multiplane/build.py ../sadhu 3 vault
Writes to <sadhu>/lab/out/<name>/. A picture already there isn't painted again."""
import base64
import json
import os
import sys
import urllib.request

from PIL import Image

from vector_director.director import llm as LLM
from vector_director.director.pipeline import arr, en, obj, N, S

STYLE = "Hand-painted look for a polished modern cartoon series: flat clean colour shapes with soft simple shading, thin dark ink outlines, slightly stylised believable shapes. No text, no people."


def paint(path, prompt, size, clear):
    if os.path.exists(path):
        return 0
    body = {"model": "gpt-image-1.5", "prompt": f"{prompt}\n\n{STYLE}", "size": size, "quality": "medium", "n": 1, **({"background": "transparent", "output_format": "png"} if clear else {})}
    r = urllib.request.Request("https://api.openai.com/v1/images/generations", data=json.dumps(body).encode(), headers={"content-type": "application/json", "authorization": "Bearer " + os.environ["OPENAI_API_KEY"]})
    d = json.load(urllib.request.urlopen(r, timeout=280))
    with open(path, "wb") as f:
        f.write(base64.b64decode(d["data"][0]["b64_json"]))
    return 1


def main(sadhu, number, name):
    sc = json.load(open(f"{sadhu}/bible/series/cris-and-baba/ep01.json"))["outline"][int(number) - 1]
    out = f"{sadhu}/lab/out/{name}"
    os.makedirs(out, exist_ok=True)
    schema = obj({"backdrop": S, "ground": obj({"color": S, "material": S}), "light": obj({"kind": en("warm", "cold", "neutral"), "mood": S}),
                  "pieces": arr(obj({"name": S, "prompt": S, "height_m": N, "x": N, "z": N})), "marks": arr(obj({"name": S, "x": N, "z": N}))})
    got = LLM.run("set_layers", {"series": "Cris and Baba", "count": "3", "scene": json.dumps({k: sc[k] for k in ("place", "time", "summary", "things")}, ensure_ascii=False, indent=1)}, schema, f"multiplane-{name}")
    plan = got["data"]
    print(got["provider"], got["model"], got["usage"], "cached" if got["cached"] else "")
    made = paint(f"{out}/backdrop.png", plan["backdrop"], "1536x1024", False)
    for i, p in enumerate(plan["pieces"]):
        p["file"] = f"piece{i}.png"
        made += paint(f"{out}/{p['file']}", p["prompt"], "1024x1024", True)
        img = Image.open(f"{out}/{p['file']}").convert("RGBA")
        img = img.crop(img.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox())         # the object's own edges, so that its base stands on the ground
        img.save(f"{out}/{p['file']}")
        p["aspect"] = img.width / img.height
    back = Image.open(f"{out}/backdrop.png").convert("RGB")
    plan["groundSample"] = "#%02x%02x%02x" % back.resize((1, 1), box=(0, back.height - 12, back.width, back.height)).getpixel((0, 0))     # the wall's foot, so the floor meets it without a seam
    json.dump(plan, open(f"{out}/plan.json", "w"), ensure_ascii=False, indent=1)
    print("painted", made)
    print(json.dumps(plan, ensure_ascii=False, indent=1))


main(*sys.argv[1:])
