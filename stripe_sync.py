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
import tempfile
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
        "Pigment giclée on Hahnemühle Photo Rag Baryta, 315 gsm. "
        "53 × 70 cm. Hand-numbered, signed in graphite, shipped flat with a "
        "letterpress certificate of authenticity. Edition of 7."
    ),
    "photos/DSC07952-Edit.jpg": (
        "Plate III · Das wache Kind. Among the sleeping, a single child "
        "remains awake, pulling the covers over her ears, refusing the "
        "chorus. Pigment giclée on Hahnemühle Photo Rag Baryta, 315 gsm. "
        "70 × 47 cm. The final impression of an edition of three."
    ),
    "photos/DSCF3006.jpg": (
        "Plate IV · Zwei Richtungen. Karl-Marx-Straße at first light: a "
        "traveller stooped over a suitcase, a runner crossing the sunlit "
        "glass of a shuttered storefront. Two bodies, two directions, one "
        "morning. Pigment giclée on Hahnemühle Photo Rag Baryta, 315 gsm. "
        "70 × 39 cm. Edition of 10 — the earliest plate in the catalogue."
    ),
    "photos/DSCF5688.jpg": (
        "Plate V · Ausgang. U-Bahnhof Rathaus Neukölln, Ausgang Süd. A "
        "figure at the threshold of the tunnel, a red bag held against the "
        "weight of daylight. Pigment giclée on Hahnemühle Photo Rag Baryta, "
        "315 gsm. 70 × 47 cm. Edition of 6."
    ),
    "photos/DSCF7696.jpg": (
        "Plate VII · Gischt. The figure stands steady as the sea arrives "
        "in scattered light around him. A study in salt, patience, and "
        "held ground. Pigment giclée on Hahnemühle Photo Rag Baryta, "
        "315 gsm. 70 × 47 cm. Edition of 7."
    ),
    "photos/DSCF7911.jpg": (
        "Plate VIII · Nur / Only. A lone figure crosses above a painted "
        "command: ONLY. A meditation on singular paths, direction, the "
        "public sentence. Pigment giclée on Hahnemühle Photo Rag Baryta, "
        "315 gsm. 47 × 70 cm. Diptych with Plate V available on private "
        "request. Edition of 4."
    ),
    "photos/DSCF8869.jpg": (
        "Plate IX · Überfahrt. A crossing in the morning light; a stranger "
        "meets the lens from among the pressed shoulders of strangers. "
        "Pigment giclée on Hahnemühle Photo Rag Baryta, 315 gsm. "
        "70 × 39 cm. Edition of 5."
    ),
    "photos/R0001706.jpg": (
        "Plate X · Hinter Glas. A late-evening window in Neukölln; "
        "condensation between two conversations, lamplight bleeding through "
        "the glass. Pigment giclée on Hahnemühle Photo Rag Baryta, 315 gsm. "
        "53 × 70 cm. Edition of 7."
    ),
    "photos/DSC08417.jpg": (
        "Plate XI · Arkaden. A figure crossing the cloister, golden stone "
        "holding the last hour of light. Pigment giclée on Hahnemühle Photo "
        "Rag Baryta, 315 gsm. 47 × 70 cm. Edition of 7."
    ),
    "photos/DSCF9068.jpg": (
        "Plate XII · Vorbeigang. A figure in mid-stride against the long "
        "shadow of a classical façade; one of those afternoons when the city "
        "seems to step aside. Pigment giclée on Hahnemühle Photo Rag Baryta, "
        "315 gsm. 70 × 47 cm. Edition of 7."
    ),
    "photos/IMG_4217.jpg": (
        "Plate XIII · Fernsicht. A Berlin window in the rain; the "
        "Fernsehturm held just barely in the haze, a figure held just barely "
        "in the room. Pigment giclée on Hahnemühle Photo Rag Baryta, 315 gsm. "
        "52 × 70 cm. Edition of 7."
    ),
    "photos/IMG_8674.JPG": (
        "Plate XIV · Sonnenseite. A figure passing between two cars, the "
        "orange wall behind holding the last of the day. Pigment giclée on "
        "Hahnemühle Photo Rag Baryta, 315 gsm. 53 × 70 cm. Edition of 7."
    ),
    "photos/DSC09560.jpg": (
        "Plate XV · Finsternis. València, the sun closed to a ring above a "
        "row of upturned heads; a palm, a wire, a crowd gone silent in copper light. "
        "Pigment giclée on Hahnemühle Photo Rag Baryta, 315 gsm. "
        "70 × 47 cm. Edition of 7."
    ),
    "photos/DSC09593.jpg": (
        "Plate XVI · Sichel. València, minutes later: a crescent sun caught on the "
        "power lines, a man in a hat turning away from the spectacle. The "
        "closing plate of the current cycle. Pigment giclée on Hahnemühle "
        "Photo Rag Baryta, 315 gsm. 70 × 47 cm. Edition of 7."
    ),
}


# Shipping rate attached to every payment link. Created once in the Stripe
# dashboard; the same ID is used for both test and live ledgers. To swap
# the rate (or update the country allow-list), change the constants below
# and re-run — every existing payment link is deactivated and recreated on
# the next sync, and the new URLs are written back into index.html.
SOURCE_REPO = "schmidt-editions"
SHIPPING_RATE = "shr_1TYrViHnIwaKfOGFPX38u8GT"

ALLOWED_COUNTRIES = [
    # EU + EEA
    "AT", "BE", "BG", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GR",
    "HR", "HU", "IE", "IS", "IT", "LI", "LT", "LU", "LV", "MT", "NL", "NO",
    "PL", "PT", "RO", "SE", "SI", "SK",
    # UK + Switzerland
    "CH", "GB",
    # Americas
    "AR", "BR", "CA", "CL", "CO", "MX", "PE", "US", "UY",
    # Asia-Pacific
    "AU", "HK", "ID", "IN", "JP", "KR", "MY", "NZ", "PH", "SG", "TH", "TW",
    "VN",
    # Middle East
    "AE", "BH", "IL", "JO", "KW", "OM", "QA", "SA", "TR",
    # Africa
    "EG", "KE", "MA", "NG", "ZA",
]


def _payment_link_params(price_id: str, *, metadata: dict | None = None) -> dict:
    """Parameters for every payment_links create call — pinned to the shipping
    rate and country allow-list above."""
    params: dict = {
        "line_items": [{"price": price_id, "quantity": 1}],
        "shipping_options": [{"shipping_rate": SHIPPING_RATE}],
        "shipping_address_collection": {"allowed_countries": ALLOWED_COUNTRIES},
    }
    if metadata:
        params["metadata"] = metadata
    return params


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


def downscale_for_stripe(src: Path, max_bytes: int = 480_000) -> tuple[Path, bool]:
    """Stripe's business_logo upload purpose caps at 512 KB. Many catalogue
    JPEGs are 1-2 MB. Re-encode to a temp file ≤ max_bytes; return
    (path, was_downscaled). Caller is responsible for deleting the temp
    file after upload."""
    if src.stat().st_size <= max_bytes:
        return src, False
    try:
        from PIL import Image  # type: ignore
    except ImportError:
        sys.exit(
            "✗ Pillow not installed (required to resize images >512 KB for Stripe).\n"
            "   Install with:  pip3 install Pillow"
        )

    img = Image.open(src)
    if img.mode in ("RGBA", "P", "LA"):
        img = img.convert("RGB")

    tmp = Path(tempfile.mkdtemp(prefix="editions-stripe-")) / f"{src.stem}.jpg"
    max_side = 1800
    quality = 88
    last_size = -1
    while True:
        w, h = img.size
        scale = min(max_side / max(w, h), 1.0)
        if scale < 1.0:
            resized = img.resize((int(w * scale), int(h * scale)), Image.LANCZOS)
        else:
            resized = img
        resized.save(tmp, "JPEG", quality=quality, optimize=True, progressive=True)
        size = tmp.stat().st_size
        if size <= max_bytes:
            return tmp, True
        if size == last_size:  # not getting any smaller — give up gracefully
            return tmp, True
        last_size = size
        # Step down: shrink dimensions first (more impact), then quality.
        if max_side > 900:
            max_side = int(max_side * 0.82)
        else:
            quality = max(quality - 6, 55)
        if max_side < 600 and quality <= 55:
            return tmp, True


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

    upload_path, downscaled = downscale_for_stripe(path)
    note = (f" (downscaled {path.stat().st_size // 1024}"
            f"→{upload_path.stat().st_size // 1024}KB)") if downscaled else ""
    print(f"        uploading {img_rel}{note} …")
    try:
        f = stripe_upload_file(secret, upload_path)
    finally:
        if downscaled:
            try:
                upload_path.unlink()
                upload_path.parent.rmdir()
            except OSError:
                pass
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
            link = stripe_post(secret, "payment_links", _payment_link_params(
                price["id"], metadata={"source_repo": SOURCE_REPO, "plate": p["plate"]},
            ))
            state[key] = {**existing,
                "plate": p["plate"],
                "title": p["title"],
                "price_eur": p["price_eur"],
                "product_id": product["id"],
                "price_id": price["id"],
                "payment_link_id": link["id"],
                "url": link["url"],
                "status": "active",
                "shipping_rate": SHIPPING_RATE,
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

        # Decide whether the payment link can be reused. It can iff the price
        # is unchanged AND the link is still active AND the shipping rate
        # already matches.
        price_unchanged = existing.get("price_eur") == p["price_eur"]
        status_active = existing.get("status") == "active"
        shipping_ok = existing.get("shipping_rate") == SHIPPING_RATE

        if price_unchanged and status_active and shipping_ok:
            print(f"  keep  {label} — {existing.get('url', '?')}")
            existing.update(title=p["title"])
            state[key] = existing
            save()
            continue

        # Something changed → rotate the payment link, and the price too if
        # the EUR amount moved.
        if not price_unchanged:
            print(f"  repr. {label} — €{existing.get('price_eur')} → €{p['price_eur']}")
        elif not shipping_ok:
            print(f"  ship  {label} — attaching shipping rate")
        else:
            print(f"  reopen {label}")

        if existing.get("payment_link_id"):
            stripe_post(secret, f"payment_links/{existing['payment_link_id']}", {"active": "false"})

        if not price_unchanged:
            if existing.get("price_id"):
                stripe_post(secret, f"prices/{existing['price_id']}", {"active": "false"})
            price = stripe_post(secret, "prices", {
                "product": existing["product_id"],
                "unit_amount": p["price_eur"] * 100,
                "currency": "eur",
            })
            price_id = price["id"]
        else:
            price_id = existing["price_id"]

        link = stripe_post(secret, "payment_links", _payment_link_params(
            price_id, metadata={"source_repo": SOURCE_REPO, "plate": p["plate"]},
        ))
        existing.update(
            title=p["title"],
            price_eur=p["price_eur"],
            price_id=price_id,
            payment_link_id=link["id"],
            url=link["url"],
            status="active",
            shipping_rate=SHIPPING_RATE,
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
