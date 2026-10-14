# -*- coding: utf-8 -*-
"""site/hardware/index.html: the full hardware tracker.

Every price is converted to US dollars here, at the exchange rate of its own date, and
handed to the page as JSON; the page only draws and filters.
"""
import calendar, json, pathlib
from datetime import date

import hwdata
import hardware_section as HS

R = pathlib.Path(__file__).resolve().parent.parent
CN_VENDORS = ["Huawei", "Cambricon", "Hygon", "Moore Threads", "MetaX", "Biren", "Kunlunxin", "Lisuan",
              "Alibaba T-Head", "Enflame", "Iluvatar", "Iluvatar CoreX"]
VENDOR_ORDER = ["NVIDIA", "AMD", "Intel", "Apple"]


def short(name):
    return (name.replace("GeForce ", "").replace("Framework Desktop (Ryzen AI Max+ 395, 128 GB)", "Framework Desktop 395")
            .replace(" Blackwell", ""))


def payload(hw, rental, as_of):
    rates = hwdata.Rates()
    regions = hw["regions"]
    products = []
    for p in hw["products"]:
        pts = []
        for pt in sorted(p.get("prices", []), key=lambda q: q["date"]):
            u = hwdata.usd(pt, rates, regions)
            ux = hwdata.usd(pt, rates, regions, ex_tax=True)
            if u is None:
                continue
            row = {"d": pt["date"], "r": pt["region"], "cur": pt["currency"], "amt": pt["amount"], "tax": pt.get("tax", "excl"),
                   "basis": pt.get("basis", ""), "src": pt.get("src"), "usd": round(u, 2), "usd_ex": round(ux, 2)}
            if pt.get("high"):
                row["high_usd"] = round(rates.to_usd(pt["high"], pt["currency"], pt["date"] if len(pt["date"]) > 7 else pt["date"] + "-15"), 2)
            pts.append(row)
        products.append({"id": p["id"], "name": p["name"], "short": short(p["name"]), "vendor": p["vendor"],
                         "segment": p["segment"], "mem_gb": p.get("mem_gb"), "bw_gbps": p.get("bw_gbps"), "note": p.get("note"),
                         "regions": len({q["r"] for q in pts}), "points": pts})
    S = rental.get("series", {})
    accels = []
    for a in hw["accelerators"]:
        b = HS.latest_buy(a)
        row = {k: a.get(k) for k in ("id", "name", "vendor", "country", "segment", "launch", "mem_gb", "bw_gbps",
                                      "fp16_tflops", "fp8_tflops", "notes", "what")}
        if b and b.get("low") is not None:
            d = b["date"] if len(b["date"]) > 7 else b["date"] + "-15"
            row.update(buy_lo=round(rates.to_usd(b["low"], b["currency"], d) or 0),
                       buy_hi=round(rates.to_usd(b.get("high") or b["low"], b["currency"], d) or 0),
                       buy_src=b.get("src"), buy_date=b["date"])
        s = S.get(a.get("rental_slug") or "")
        if s:
            row["rent_now"] = s["points"][-1][1]
            ch, _ = HS.yoy(s["points"])
            row["rent_yoy"] = ch
        elif a.get("rent"):
            r = sorted(a["rent"], key=lambda q: q["date"])[-1]
            usd = rates.to_usd(r["price"], r["currency"], r["date"] if len(r["date"]) > 7 else r["date"] + "-15")
            row["rent_note"] = "%s %s/hr (%s, %s)" % (r["currency"], format(r["price"], "g"), r.get("provider", ""), r["date"])
            if usd:
                row["rent_now"] = round(usd, 2)
        accels.append(row)
    order = {v: i for i, v in enumerate(VENDOR_ORDER)}
    accels.sort(key=lambda a: (a["country"] != "US", order.get(a["vendor"], 9), a["vendor"], a["segment"] == "rack", a.get("launch") or ""))
    vendors = sorted({p["vendor"] for p in products} | {a["vendor"] for a in accels},
                     key=lambda v: (v in CN_VENDORS, order.get(v, 9), v))
    return {"as_of": as_of.isoformat(), "as_of_ms": calendar.timegm(as_of.timetuple()) * 1000,
            "checked": hw["checked"], "regions": regions, "vendors": vendors, "cn_vendors": CN_VENDORS,
            "products": products, "accelerators": accels}


def write(site, as_of=None):
    as_of = as_of or date.today()
    hw = hwdata.load()
    rp = R / "data" / "gpu_rental.json"
    rental = json.loads(rp.read_text()) if rp.exists() else {"series": {}}
    S = rental.get("series", {})
    rent_html = ('<div class="hwgrid" style="display:grid;grid-template-columns:repeat(auto-fit,minmax(420px,1fr));gap:14px">'
                 + HS.rental_chart(S, ["nvidia-a100", "nvidia-h100", "nvidia-h200", "nvidia-b200", "nvidia-b300",
                                       "amd-mi300x", "amd-mi325x", "amd-mi355x", "intel-gaudi2"],
                                   "Datacenter GPUs · median on-demand $/GPU-hour",
                                   "Weekly median rental price per GPU-hour for NVIDIA, AMD and Intel datacenter GPUs")
                 + HS.rental_chart(S, ["nvidia-rtx-3090", "nvidia-rtx-4090", "nvidia-rtx-5090", "nvidia-rtx-pro-6000"],
                                   "Home-lab cards, rented in the cloud · median $/GPU-hour",
                                   "Weekly median rental price per GPU-hour for consumer and workstation GPUs")
                 + '</div><p class="note">Solid: NVIDIA; dashed: AMD; dotted: Intel. Median on-demand price across every provider '
                 'listing the GPU that week; the year-on-year change appears only where at least 3 providers list it. '
                 'Data through %s. Chinese accelerators are not in an open rental dataset; their reported cloud prices are in the table above.</p>'
                 % (rental.get("as_of") or "—"))
    tpl = (R / "build" / "hardware_template.html").read_text()
    out = tpl.replace("__RENTAL__", rent_html).replace("__DATA__", json.dumps(payload(hw, rental, as_of), ensure_ascii=False))
    d = site / "hardware"
    d.mkdir(parents=True, exist_ok=True)
    (d / "index.html").write_text(out)
    print(f"hardware page: {len(hw['products'])} products, {len(hw['accelerators'])} accelerators")
