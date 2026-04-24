#!/usr/bin/env python3
"""
stripe_sync.py — create a Stripe Product + Price + Payment Link for every
available plate in index.html, then rewrite each <article> with a
data-stripe-url attribute so the modal "Acquire" button links to Stripe.

Idempotent: keeps a local .stripe_products.json keyed by image path. A plate
whose title and price are unchanged is skipped. Sold-out plates are never
pushed to Stripe.

Requires: Python 3.9+, stdlib only. A STRIPE_SECRET_KEY entry in .env.
"""
from __future__ import annotations

import base64
import html as html_lib
import json
import mimetypes
import os
import re
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path


def _ssl_context() -> ssl.SSLContext:
    """python.org's macOS installer ships without a CA bundle, so the
    default context fails on Stripe's cert. Try certifi; fall back to
    the system default and hand the user a clear remediation."""
    try:
        import certifi  # type: ignore
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()

ROOT = Path(__file__).parent.resolve()
ENV_FILE = ROOT / ".env"
HTML_FILE = ROOT / "index.html"
# STATE_FILE is assigned in main() once we know test vs. live mode.
STATE_FILE: Path = ROOT / ".stripe_products.json"

# Evocative per-image descriptions. Keyed by image path as it appears in the
# HTML. Edit freely — re-running with a changed description does NOT update
# Stripe (we only re-sync on title or price change). To force a refresh,
# delete that entry from .stripe_products.json.
DESCRIPTIONS = {
    "photos/DSC05224.jpg": (
        "Plate I · Kolonnade, 16 Uhr. Late afternoon light slipping between "
        "concrete pillars on the west colonnade; a single figure in passage, "
        "an orange bag held against the weight of the architecture. "
        "Silver gelatin print on matte baryta, framed in oiled oak with "
        "museum glass. 80 × 100 cm. Hand-numbered and signed. Edition of 7."
    ),
    "photos/DSC07948.jpg": (
        "Plate III · Die Apostel. A quiet congregation, each figure lit from "
        "within by a small square of light. A scene that arrives like a "
        "premonition — devotion, distance, the glow of something we cannot "
        "yet name. Silver gelatin print on Agfa Record Rapid, unframed. "
        "40 × 50 cm. Edition of 8."
    ),
    "photos/DSC07952-Edit.jpg": (
        "Plate IV · Das wache Kind. Among the sleeping, a single child "
        "remains awake, pulling the covers over her ears, refusing the "
        "chorus. Cibachrome, diasec-mounted. 90 × 120 cm. The final "
        "impression of an edition of three."
    ),
    "photos/DSCF3006.jpg": (
        "Plate V · Zwei Richtungen. Karl-Marx-Straße at first light: a "
        "traveller stooped over a suitcase, a runner crossing the sunlit "
        "glass of a shuttered storefront. Two bodies, two directions, one "
        "morning. Silver gelatin print on archival baryta. 30 × 40 cm. "
        "Edition of 10 — the earliest plate in the catalogue."
    ),
    "photos/DSCF5688.jpg": (
        "Plate VI · Ausgang. U-Bahnhof Rathaus Neukölln, Ausgang Süd. A "
        "figure at the threshold of the tunnel, a red bag held against the "
        "weight of daylight. Silver gelatin print on cotton rag, floated in "
        "black walnut. 50 × 70 cm. Edition of 6."
    ),
    "photos/DSCF7696.jpg": (
        "Plate VIII · Gischt. The figure stands steady as the sea arrives "
        "in scattered light around him. A study in salt, patience, and "
        "held ground. Silver gelatin print on baryta. 40 × 60 cm. "
        "Edition of 7."
    ),
    "photos/DSCF7911.jpg": (
        "Plate IX · Nur / Only. A lone figure crosses above a painted "
        "command: ONLY. A meditation on singular paths, direction, the "
        "public sentence. Cibachrome. 70 × 90 cm. Diptych with Plate V "
        "available on private request. Edition of 4."
    ),
    "photos/DSCF8869.jpg": (
        "Plate X · Überfahrt. A crossing in the morning light; a stranger "
        "meets the lens from among the pressed shoulders of strangers. "
        "Silver gelatin print. 50 × 60 cm. The closing plate of the "
        "current cycle. Edition of 5."
    ),
}


# ──────────────────────── .env + Stripe helpers ──────────────────────────────

def load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip('"').strip("'")
    return env


def _flatten(obj, prefix: str = "") -> list[tuple[str, str]]:
    """Flatten nested dict/list into Stripe's form-encoded key notation."""
    out: list[tuple[str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            key = f"{prefix}[{k}]" if prefix else k
            out.extend(_flatten(v, key))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(_flatten(v, f"{prefix}[{i}]"))
    else:
        out.append((prefix, str(obj)))
    return out


def stripe_post(secret: str, path: str, params: dict, *, host: str = "api.stripe.com") -> dict:
    url = f"https://{host}/v1/{path}"
    data = urllib.parse.urlencode(_flatten(params)).encode()
    req = urllib.request.Request(url, data=data, method="POST")
    token = base64.b64encode(f"{secret}:".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    try:
        with urllib.request.urlopen(req, context=_ssl_context()) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        raise SystemExit(f"✗ Stripe API error {e.code} on {path}: {body}")
    except urllib.error.URLError as e:
        if "CERTIFICATE_VERIFY_FAILED" in str(e):
            raise SystemExit(
                "✗ SSL cert verification failed. Fix with either:\n"
                "   1) /Applications/Python\\ 3.12/Install\\ Certificates.command\n"
                "   2) pip3 install certifi\n"
                f"   (raw error: {e})"
            )
        raise


def stripe_upload_file(secret: str, file_path: Path) -> dict:
    """POST multipart/form-data to files.stripe.com to upload a local image.
    Returns the File object (dict with 'id'). Uses purpose=business_logo,
    which Stripe accepts for arbitrary hosted assets referenceable via
    file_links."""
    mime = mimetypes.guess_type(file_path.name)[0] or "application/octet-stream"
    boundary = f"----stripe-sync-{uuid.uuid4().hex}"
    crlf = b"\r\n"
    parts: list[bytes] = []

    def add_field(name: str, value: str) -> None:
        parts.extend([
            f"--{boundary}".encode(), crlf,
            f'Content-Disposition: form-data; name="{name}"'.encode(), crlf, crlf,
            value.encode(), crlf,
        ])

    add_field("purpose", "business_logo")
    parts.extend([
        f"--{boundary}".encode(), crlf,
        f'Content-Disposition: form-data; name="file"; filename="{file_path.name}"'.encode(), crlf,
        f"Content-Type: {mime}".encode(), crlf, crlf,
        file_path.read_bytes(), crlf,
        f"--{boundary}--".encode(), crlf,
    ])
    body = b"".join(parts)

    req = urllib.request.Request(
        "https://files.stripe.com/v1/files", data=body, method="POST")
    token = base64.b64encode(f"{secret}:".encode()).decode()
    req.add_header("Authorization", f"Basic {token}")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    try:
        with urllib.request.urlopen(req, context=_ssl_context()) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        raise SystemExit(f"✗ Stripe file upload failed {e.code}: {e.read().decode()}")


def ensure_image_url(secret: str, state: dict, img_rel: str) -> str | None:
    """Upload the image once and create a public file link. Cache both in
    state[img_rel] so reruns are free. Returns the public URL, or None if
    the file is missing locally."""
    cached = state.get(img_rel, {})
    if cached.get("image_url"):
        return cached["image_url"]

    path = ROOT / img_rel
    if not path.exists():
        print(f"        ⚠ {img_rel} not found on disk — skipping image")
        return None

    print(f"        uploading {img_rel} …")
    f = stripe_upload_file(secret, path)
    link = stripe_post(secret, "file_links", {"file": f["id"]})

    entry = state.setdefault(img_rel, {})
    entry["file_id"] = f["id"]
    entry["file_link_id"] = link["id"]
    entry["image_url"] = link["url"]
    STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))
    return link["url"]


# ──────────────────────── HTML parse + rewrite ───────────────────────────────

ARTICLE_RE = re.compile(r'<article\b[^>]*>', re.DOTALL)
ATTR_RE = re.compile(r'data-([a-z-]+)="([^"]*)"')

def parse_pieces(html: str) -> list[dict]:
    pieces: list[dict] = []
    for m in ARTICLE_RE.finditer(html):
        tag = m.group(0)
        attrs = dict(ATTR_RE.findall(tag))
        if "plate" not in attrs or "price" not in attrs:
            continue
        pieces.append({
            "plate": attrs["plate"],
            "title": html_lib.unescape(attrs.get("title", "")),
            "img": attrs.get("img", ""),
            "year": attrs.get("year", ""),
            "edition": int(attrs.get("edition", "0") or 0),
            "remaining": int(attrs.get("remaining", "0") or 0),
            "price_eur": int(attrs.get("price", "0") or 0),
            "desc": html_lib.unescape(attrs.get("desc", "")),
        })
    return pieces


def inject_stripe_url(html: str, plate: str, url: str | None) -> str:
    """Insert, replace, or remove a data-stripe-url attribute on the
    article tag for the given plate. Passing url=None strips it."""
    def repl(m: re.Match) -> str:
        tag = m.group(0)
        if 'data-plate="' + plate + '"' not in tag:
            return tag
        if url is None:
            return re.sub(r'\s*data-stripe-url="[^"]*"', "", tag)
        if "data-stripe-url=" in tag:
            return re.sub(r'data-stripe-url="[^"]*"', f'data-stripe-url="{url}"', tag)
        return tag[:-1] + f' data-stripe-url="{url}">'
    return ARTICLE_RE.sub(repl, html)


# ──────────────────────── main ───────────────────────────────────────────────

def main() -> int:
    env = load_env(ENV_FILE)
    secret = env.get("STRIPE_SECRET_KEY") or os.environ.get("STRIPE_SECRET_KEY")
    if not secret:
        sys.exit("✗ STRIPE_SECRET_KEY missing (check .env)")

    is_live = secret.startswith("sk_live_")
    mode = "LIVE" if is_live else "TEST"
    print(f"Stripe mode: {mode}")

    # Separate ledger per mode — IDs are not portable across modes.
    global STATE_FILE
    STATE_FILE = ROOT / (".stripe_products.live.json" if is_live else ".stripe_products.test.json")

    # One-time migration: if a legacy unscoped file exists, treat it as test.
    legacy = ROOT / ".stripe_products.json"
    if legacy.exists() and not STATE_FILE.exists() and not is_live:
        legacy.rename(STATE_FILE)
        print(f"↳ migrated legacy ledger → {STATE_FILE.name}")

    if is_live:
        print("⚠  LIVE mode — this will create real, chargeable products.")
        if input("   type 'yes' to continue: ").strip().lower() != "yes":
            sys.exit("aborted")

    html = HTML_FILE.read_text(encoding="utf-8")
    pieces = parse_pieces(html)
    print(f"Found {len(pieces)} plates in index.html")

    state: dict = json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}

    def save() -> None:
        STATE_FILE.write_text(json.dumps(state, indent=2, ensure_ascii=False))

    for p in pieces:
        key = p["img"]
        label = f"Pl. {p['plate']:>4} — {p['title']}"
        existing = state.get(key) or {}
        description = DESCRIPTIONS.get(key, p["desc"])[:5000]

        # Plate is sold out ──────────────────────────────────────────────
        if p["remaining"] <= 0:
            if existing.get("payment_link_id") and existing.get("status") != "sold_out":
                print(f"  close {label} — deactivating price + payment link")
                stripe_post(secret, f"payment_links/{existing['payment_link_id']}", {"active": "false"})
                if existing.get("price_id"):
                    stripe_post(secret, f"prices/{existing['price_id']}", {"active": "false"})
                existing["status"] = "sold_out"
                existing.pop("url", None)
                state[key] = existing
                save()
            else:
                print(f"  skip  {label} — sold out")
            continue

        # Plate is available ─────────────────────────────────────────────
        image_url = ensure_image_url(secret, state, p["img"])
        product_name = f"Pl. {p['plate']} — {p['title']}"

        # Fresh: no product yet in the ledger.
        if not existing.get("product_id"):
            print(f"  new   {label} …")
            product_params: dict = {
                "name": product_name,
                "description": description,
                "metadata": {
                    "plate": p["plate"],
                    "image": p["img"],
                    "year": p["year"],
                    "edition_size": str(p["edition"]),
                },
            }
            if image_url:
                product_params["images"] = [image_url]
            product = stripe_post(secret, "products", product_params)
            price = stripe_post(secret, "prices", {
                "product": product["id"],
                "unit_amount": p["price_eur"] * 100,
                "currency": "eur",
            })
            link = stripe_post(secret, "payment_links", {
                "line_items": [{"price": price["id"], "quantity": 1}],
            })
            state[key] = {**existing,
                "plate": p["plate"],
                "title": p["title"],
                "price_eur": p["price_eur"],
                "product_id": product["id"],
                "price_id": price["id"],
                "payment_link_id": link["id"],
                "url": link["url"],
                "status": "active",
            }
            save()
            print(f"        → {link['url']}")
            continue

        # Already exists — patch product (name/desc/images are mutable).
        product_patch: dict = {
            "name": product_name,
            "description": description,
            "metadata": {
                "plate": p["plate"],
                "image": p["img"],
                "year": p["year"],
                "edition_size": str(p["edition"]),
            },
        }
        if image_url:
            product_patch["images"] = [image_url]
        stripe_post(secret, f"products/{existing['product_id']}", product_patch)

        # Price unchanged → nothing further to create.
        if existing.get("price_eur") == p["price_eur"] and existing.get("status") == "active":
            print(f"  keep  {label} — {existing.get('url', '?')}")
            existing.update(title=p["title"])
            state[key] = existing
            save()
            continue

        # Price changed (or plate is being re-opened) → rotate price + link.
        if existing.get("price_eur") != p["price_eur"]:
            print(f"  repr. {label} — €{existing.get('price_eur')} → €{p['price_eur']}")
        else:
            print(f"  reopen {label}")

        if existing.get("payment_link_id"):
            stripe_post(secret, f"payment_links/{existing['payment_link_id']}", {"active": "false"})
        if existing.get("price_id"):
            stripe_post(secret, f"prices/{existing['price_id']}", {"active": "false"})
        price = stripe_post(secret, "prices", {
            "product": existing["product_id"],
            "unit_amount": p["price_eur"] * 100,
            "currency": "eur",
        })
        link = stripe_post(secret, "payment_links", {
            "line_items": [{"price": price["id"], "quantity": 1}],
        })
        existing.update(
            title=p["title"],
            price_eur=p["price_eur"],
            price_id=price["id"],
            payment_link_id=link["id"],
            url=link["url"],
            status="active",
        )
        state[key] = existing
        save()
        print(f"        → {link['url']}")

    # Rewrite index.html with data-stripe-url attrs.
    updated = html
    for p in pieces:
        entry = state.get(p["img"])
        # Strip URL for sold-out plates (falls back to mailto enquiry).
        if p["remaining"] <= 0 or not entry or not entry.get("url"):
            updated = inject_stripe_url(updated, p["plate"], None)
        else:
            updated = inject_stripe_url(updated, p["plate"], entry["url"])

    if updated != html:
        HTML_FILE.write_text(updated, encoding="utf-8")
        print("✓ index.html updated with payment links")
    else:
        print("✓ index.html already up to date")

    return 0


if __name__ == "__main__":
    sys.exit(main())
