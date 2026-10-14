#!/usr/bin/env python3
"""
GPU rental prices, from GetDeploying's open dataset (CC BY 4.0, attribution required).

    https://getdeploying.com/dataset   weekly on-demand $/GPU-hour across ~90 clouds

Writes data/gpu_rental.json: one weekly series per GPU we chart, plus its specs.
The dataset updates weekly, so most runs change nothing; the file carries no fetch
timestamp, which keeps git quiet until a new week actually lands.

Never fails the job: if the source is down, the last committed file stays in use.
"""
import csv, io, json, pathlib, sys, urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "gpu_rental.json"
PRICES = "https://getdeploying.com/dataset/gpu-prices/weekly.csv"
MODELS = "https://getdeploying.com/dataset/gpu-models/gpu-models.csv"
UA = "artificialacceleration.com data job (+https://artificialacceleration.com)"

# the GPUs worth a line: datacenter generations, and the cards people put in a home lab
TRACK = {
    "nvidia-a100": "datacenter", "nvidia-h100": "datacenter", "nvidia-h200": "datacenter",
    "nvidia-b200": "datacenter", "nvidia-b300": "datacenter", "amd-mi300x": "datacenter",
    "amd-mi325x": "datacenter", "amd-mi355x": "datacenter", "intel-gaudi2": "datacenter",
    "nvidia-rtx-3090": "home", "nvidia-rtx-4090": "home", "nvidia-rtx-5090": "home",
    "nvidia-rtx-pro-6000": "home",
}


def get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def main():
    try:
        prices = list(csv.DictReader(io.StringIO(get(PRICES))))
        models = {m["gpu_slug"]: m for m in csv.DictReader(io.StringIO(get(MODELS)))}
    except Exception as e:                       # network, HTTP, decode: keep the old file
        print(f"gpu rental: fetch failed ({type(e).__name__}); keeping {OUT.name}")
        return 0
    series = {}
    for slug, kind in TRACK.items():
        pts = sorted((r["date"], round(float(r["median_price"]), 4), round(float(r["min_price"]), 4), int(r["provider_count"]))
                     for r in prices if r["gpu_slug"] == slug and r["billing_type"] == "ON_DEMAND")
        if not pts:
            continue
        m = models.get(slug, {})
        series[slug] = {
            "name": m.get("name", slug).replace("Nvidia ", ""),
            "kind": kind,
            "released": m.get("release_date") or None,
            "vram_gb": float(m["vram_gb"]) if m.get("vram_gb") else None,
            "bandwidth_gbps": float(m["mem_bandwidth_gbps"]) if m.get("mem_bandwidth_gbps") else None,
            "points": [list(p) for p in pts],    # [week, median $/hr, lowest $/hr, providers]
        }
    if len(series) < 4:
        print(f"gpu rental: only {len(series)} series parsed; keeping {OUT.name}")
        return 0
    payload = {"source": "GetDeploying open dataset", "url": "https://getdeploying.com/dataset",
               "license": "CC BY 4.0", "billing": "on-demand, per GPU-hour, median across providers",
               "as_of": max(p[0] for s in series.values() for p in s["points"]), "series": series}
    OUT.write_text(json.dumps(payload, indent=1) + "\n")
    print(f"gpu rental: {len(series)} GPUs through {payload['as_of']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
