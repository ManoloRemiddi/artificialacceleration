# -*- coding: utf-8 -*-
"""World map paths for the hardware page, computed at build time.

Decodes the Natural Earth TopoJSON (build/geo/countries-110m.json) and projects it with
Equal Earth, an equal-area projection (country sizes stay honest, which matters for a map
that colours countries by price). Output: {ISO numeric code: SVG path}, plus the view size.
"""
import json, math, pathlib

GEO = pathlib.Path(__file__).resolve().parent / "geo" / "countries-110m.json"
A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
M = math.sqrt(3) / 2


def equal_earth(lon, lat):
    lam, phi = math.radians(lon), math.radians(lat)
    th = math.asin(M * math.sin(phi))
    t2, t6 = th * th, th ** 6
    x = 2 * math.sqrt(3) * lam * math.cos(th) / (3 * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)))
    y = th * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))
    return x, y


def _arcs(topo):
    sx, sy = topo["transform"]["scale"]
    tx, ty = topo["transform"]["translate"]
    out = []
    for arc in topo["arcs"]:
        x = y = 0
        pts = []
        for dx, dy in arc:
            x += dx
            y += dy
            pts.append((x * sx + tx, y * sy + ty))
        out.append(pts)
    return out


def _ring(arcs, idx):
    pts = []
    for i in idx:
        seg = arcs[i] if i >= 0 else list(reversed(arcs[~i]))
        pts.extend(seg if not pts else seg[1:])
    return pts


def paths(width=960, skip=("010",), points=None):
    """Country paths scaled to `width`; Antarctica dropped (no market, half the map).
    `points` {key: (lon, lat)} are projected too (label anchors, and markers for countries
    too small for this scale, such as Singapore)."""
    topo = json.loads(GEO.read_text())
    arcs = _arcs(topo)
    xmax, _ = equal_earth(180, 0)
    _, ymax = equal_earth(0, 90)
    k = width / (2 * xmax)
    crop = 0.24                      # trim the empty polar band left by dropping Antarctica
    top, bottom = ymax * 0.93, -ymax * (1 - crop)
    height = (top - bottom) * k
    proj = lambda lon, lat: ((equal_earth(lon, lat)[0] + xmax) * k, (top - equal_earth(lon, lat)[1]) * k)
    out = {}
    for g in topo["objects"]["countries"]["geometries"]:
        cid = g.get("id")
        if not cid or cid in skip or g["type"] not in ("Polygon", "MultiPolygon"):
            continue
        polys = [g["arcs"]] if g["type"] == "Polygon" else g["arcs"]
        d = []
        for poly in polys:
            for ring in poly:
                ll = _ring(arcs, ring)
                lons = [lon for lon, _ in ll]
                # a ring that crosses the 180th meridian (Russia's far east, Fiji) would be drawn
                # the long way round the globe as a streak: move its western points east of 180
                # instead; anything past the edge is simply clipped by the view box
                if max(lons) - min(lons) > 180:
                    ll = [(lon + 360 if lon < 0 else lon, lat) for lon, lat in ll]
                pts = [proj(lon, lat) for lon, lat in ll]
                if len(pts) > 2:
                    d.append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in pts) + "Z")
        out[cid] = {"d": "".join(d), "name": g.get("properties", {}).get("name", "")}
    pts = {k: [round(v, 1) for v in proj(lon, lat)] for k, (lon, lat) in (points or {}).items()}
    return {"width": width, "height": round(height, 1), "countries": out, "points": pts}


if __name__ == "__main__":
    m = paths()
    print(len(m["countries"]), "countries,", m["width"], "x", m["height"], ",", sum(len(c["d"]) for c in m["countries"].values()), "path chars")
