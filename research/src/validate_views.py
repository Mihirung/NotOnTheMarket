"""Sanity-check computed outlooks against places anyone from Exeter knows.

Expectations, stated before looking:
  Topsham (EX3 0)        estuary-side town: water views common upstairs
  Pennsylvania (EX4 4/5) hill north of the centre: long views, Haldon visible
  City centre (EX1 1)    terraces/flats: enclosed, low long-view share
  St Leonard's (EX2 4)   leafy villas: trees dominate the horizon
  Exwick (EX4 2)         valley-side estate: mixed
Usage: python validate_views.py <views_postcode.parquet>
"""
import sys
import pandas as pd

df = pd.read_parquet(sys.argv[1])
df["sector"] = df.postcode.str.rsplit(" ", n=1).str[0] + " " + df.postcode.str.rsplit(" ", n=1).str[1].str[0]
cols = ["g_median_horizon_deg", "g_overlooked_share", "u_long_view_share",
        "u_longest_view_km", "u_water_share", "u_sea_share", "u_hills_share",
        "sees_Exe estuary", "sees_Haldon Hills", "sees_Dartmoor (Haytor)"]
probe = {"EX3 0": "Topsham", "EX4 4": "Pennsylvania/St James", "EX4 5": "Pennsylvania N",
         "EX1 1": "City centre", "EX2 4": "St Leonard's", "EX4 2": "Exwick",
         "EX2 9": "Alphington/Ide", "EX4 8": "Pinhoe"}
rows = []
for sec, name in probe.items():
    s = df[df.sector == sec]
    if len(s) == 0:
        continue
    rows.append({"place": name, "sector": sec, "n": len(s),
                 "horizon°": s.g_median_horizon_deg.median(),
                 "overlooked": s.g_overlooked_share.mean(),
                 "long views": s.u_long_view_share.mean(),
                 "longest km": s.u_longest_view_km.median(),
                 "water": s.u_water_share.mean(),
                 "sees estuary": s["sees_Exe estuary"].mean(),
                 "sees Haldon": s["sees_Haldon Hills"].mean(),
                 "sees Dartmoor": s["sees_Dartmoor (Haytor)"].mean()})
out = pd.DataFrame(rows).set_index("place")
pd.set_option("display.width", 160)
print(out.round(2).to_string())
