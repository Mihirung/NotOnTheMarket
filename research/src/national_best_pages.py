"""The best homes in England and Wales on several briefs at once, each one
drawn, on one page. Every house in the country is scored once on every
characteristic (its national percentile), then each brief is the average
of the percentiles it asks for, so a house must be good at all of them.

    python national_best_pages.py <out.html> <out.csv> [top]

The page and table name postcodes: they are for the owner of this research,
not for publishing.
"""
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).parent))
import find_best as FB  # noqa: E402
import national_house_view as NHV  # noqa: E402

BRIEFS = [
    ("The very best of everything", FB.ALL, {},
     "Every outlook, garden, light and landmark measure, with clean air, a GP and hospital, parks, woods and water "
     "nearby, sunshine, dry weather and mild winters."),
    ("The finest views", ["views", "far", "water", "hills"], {},
     "Long views across most of the horizon, the furthest sight-lines, water and hills."),
    ("By the sea, with the evening sun", ["sea", "evening_sun", "garden_sun", "views"], {},
     "The sea or an estuary in view upstairs, and a garden in the sun, morning to evening."),
    ("A private, sunny garden and a light house", ["quiet_garden", "garden_room", "garden_sun", "evening_sun", "light",
                                                   "winter_light"], {"houses_only": True},
     "Not overlooked, room in the garden, sun in it all day and all year, and sun on the windows. Houses only."),
    ("Quiet, green and healthy", ["clean_air", "near_park", "parkland", "near_woods", "near_gp", "near_hospital",
                                  "pubs_far", "few_takeaways", "quiet_garden"], {},
     "Clean air, parks and woods close by, a GP and hospital in reach, away from pubs and takeaways."),
    ("A village pub, a view and a sunny garden", ["pubs_near", "views", "garden_sun", "near_woods", "clean_air"], {}, None),
    ("Room to grow", ["extension_value", "extension_space", "garden_room", "light"], {"houses_only": True},
     "The most value and space that could be added without planning permission, with room in the garden and good light."),
    ("Sunny, dry and mild", ["sunny", "sunny_winters", "clear_skies", "dry", "few_downpours", "mild_winters",
                             "few_frosts", "garden_sun", "light"], {},
     "The most sunshine, winter included, the fewest grey skies, the least rain and the mildest winters, "
     "with sun in the garden and on the windows."),
    ("Ready for a warmer world", ["steady_climate", "few_heatwaves", "cool_summers", "summer_rain_kept",
                                  "winter_rain_steady", "open_outlook", "near_woods"], {},
     "Where the climate is changing least by the 2050s: the least warming, the fewest very hot days, "
     "summers keeping their rain and winters not much wetter, with shade from woods nearby."),
    ("A cathedral or abbey in sight", ["cathedral", "views", "light"], {}, None),
    ("A castle in sight", ["castle", "views", "light"], {}, None),
]


def pick(df, ranks, want, top, houses_only=False, region=None, per_postcode=True):
    score = np.zeros(len(df), np.float32); weakest = np.full(len(df), np.inf, np.float32)
    for w in want:
        score += ranks[w]; weakest = np.minimum(weakest, ranks[w])
    score /= len(want)
    ok = np.ones(len(df), bool)
    if houses_only:
        ok &= (df.n_uprn == 1).to_numpy()
    if region:
        ok &= np.isin(df["_area"].to_numpy(), FB.REGION_AREAS[region].split())
    s = np.where(ok, score + weakest / 1000, -1)
    cand = np.argpartition(-s, min(len(s) - 1, top * 60))[:top * 60]
    cand = cand[ok[cand]]                              # nothing from outside the region, however few are inside
    cand = cand[np.argsort(-s[cand])]
    out = df.iloc[cand].assign(score=score[cand].astype("float64").round(2), weakest=weakest[cand].astype("float64").round(1))
    if per_postcode:
        out = out.drop_duplicates("postcode")
    return out.head(top)


def main(out_html, out_csv, top=5):
    top = int(top)
    want_all = list(FB.CHAR)
    df = FB.load([FB.CHAR[w][0] for w in want_all])
    df["_row"] = np.arange(len(df))
    df, ranks, below = FB.score(df, want_all)
    cats = df.postcode.cat.categories.str.extract(r"^([A-Z]+)")[0].to_numpy()
    codes = df.postcode.cat.codes.to_numpy()
    df["_area"] = np.where(codes >= 0, cats[np.clip(codes, 0, None)], "")
    print(f"{len(df):,} houses scored on {len(want_all)} characteristics", flush=True)

    briefs = list(BRIEFS) + [(f"The best of everything in {r}", FB.ALL, {"region": r}, None) for r in FB.REGION_AREAS]
    items, rows = [], []
    for title, want, opts, blurb in briefs:
        n = top if "region" not in opts else 1
        t = pick(df, ranks, want, n, **opts).reset_index(drop=True)
        if not len(t):
            continue
        t = FB.describe(t, want, ranks, below)
        print(f"{title}: " + ", ".join(f"{r.postcode} ({r.score:.1f})" for r in t.itertuples()), flush=True)
        for k in range(len(t)):
            it = NHV.item(t.iloc[k], [(w, FB.CHAR[w][2]) for w in want])
            it["rank"] = k + 1
            if k == 0:
                it["section"] = title
                it["blurb"] = blurb or ""
            items.append(it)
            rows.append({"brief": title, "rank": k + 1, "postcode": t.postcode.iloc[k], "storeys": int(t.storeys.iloc[k]),
                         "score": t.score.iloc[k], "weakest": t.weakest.iloc[k],
                         **{f"pct_{w}": t[f"pct_{w}"].iloc[k] for w in want}})
    Path(out_html).write_text(NHV.page(items, "The best homes in England and Wales"))
    pd.DataFrame(rows).to_csv(out_csv, index=False)
    print("wrote", out_html, out_csv)


if __name__ == "__main__":
    main(*sys.argv[1:])
