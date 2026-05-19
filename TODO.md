# TODO

Two parallel workstreams. The un-fakify list (A) is about pulling fabricated
copy out of the catalogue; the compliance / premium list (B) is about making
the site legally watertight under DE/EU consumer law and credibly premium for
collectors. Items overlap where called out.

---

## A. Un-fakify the catalogue copy

Stepwise plan to strip fabricated details from the site and align it with the
reference at https://fine-art-nude.onrender.com/ (#craft in particular).

Cannot reach the reference from this sandbox (Render returns 403 to WebFetch,
egress allowlist blocks curl, no access to local `/Users/...`). The first step
must be done with the reference text in hand.

### A.1 Pull the reference copy

- Open https://fine-art-nude.onrender.com/#craft and lift the exact wording for:
  - paper / process / inks
  - signing / numbering / certificate
  - packaging + shipping
  - dimensions language
  - about/atelier blurb if it differs from ours
- Paste those blocks into the chat (or commit them to a scratch file) so the
  rewrite can mirror them rather than invent new copy.

### A.2 Strip residence / buyer references

Buyers are private — no city, no institution, no destinations. (Overlaps with
B's "Press / collections / exhibitions" — once these are scrubbed, the
institutional flourish elsewhere should also be softened.)

- `index.html:240` — "one held privately in Zürich" → remove the sentence.
- `index.html:342` — "one held institutionally" → remove the sentence.
- `journal.html:139` — "One impression has already found a wall in Antwerp" →
  remove or rewrite to omit destination.
- Audit any remaining `data-desc` attributes and the `DESCRIPTIONS` dict in
  `stripe_sync.py` for the same pattern.

### A.3 Remove framing language everywhere — prints ship unframed

- `index.html:223` (Pl. I) — "Framed in oiled oak, museum glass" → remove.
- `index.html:257` (Pl. III) — keep "Unframed" but rewrite to match reference.
- `index.html:274` (Pl. IV) — "Cibachrome, diasec mounted" → drop framing/mount.
- `index.html:308` (Pl. VI) — "Floated in black walnut" → remove.
- `index.html:466` (Conditions of sale) — "Framing available on request at
  additional cost" → remove; replace with reference's shipping/packaging
  language.
- Marquee ticker (`index.html:188-203`) — re-check the claims (Hahnemühle Photo
  Rag Baryta 315 g, certificate, Berlin) against the reference and rewrite.
- Mirror the same cleanup in `stripe_sync.py` `DESCRIPTIONS` (lines 50-102).

### A.4 Recompute dimensions from real aspect ratios at ~50×70 cm

For each photo in `photos/`, read the pixel dimensions, derive the aspect
ratio, then size so the long edge ≈ 70 cm (or 50 cm on the short edge,
whichever the orientation demands), rounded to whole cm. Apply to:

- `data-desc` on every `<article>` in `index.html`.
- `DESCRIPTIONS` in `stripe_sync.py`.
- Any size mentioned in the modal/about copy.

Method: `identify -format "%w %h\n" photos/<file>` (or Python+Pillow). The
current values (30×40, 40×50, 40×60, 50×60, 50×75, 60×75, 60×80, 70×90,
80×100, 90×120) are all fabricated and should be replaced.

Photos to size:
- Pl. I  DSC05224.jpg
- Pl. II DSC07168.jpg
- Pl. III DSC07948.jpg
- Pl. IV DSC07952-Edit.jpg
- Pl. V  DSCF3006.jpg
- Pl. VI DSCF5688.jpg
- Pl. VII DSCF7674.jpg
- Pl. VIII DSCF7696.jpg
- Pl. IX DSCF7911.jpg
- Pl. X  DSCF8869.jpg
- Hero  DSCF8869.jpg (same file, same size)

Also: the `aspect-[…]` Tailwind class on each `<figure>` should reflect the
real ratio so the grid layout is honest (`aspect-[5/4]`, `aspect-[4/5]`,
`aspect-[16/9]`, `aspect-[16/10]`, `aspect-[3/4]` are all set by hand right
now — verify against the real ratios and adjust).

### A.5 Replace the fake years (keep Roman-numeral framing)

Plates are tagged MCMLXXXI–MCMLXXXV (1981-1985) but Dennis was born 1985
(`index.html:410`, `index.html:420`). Pick plausible recent years from the
real shoot dates and convert to Roman numerals. (Overlaps with B's "Artist
conceit math".)

- `data-year="…"` on each `<article>` in `index.html`.
- Hero subtitle "Editions I – X · MCMLXXXI – MCMLXXXV" (`index.html:156`) →
  update the range to the new earliest/latest year.
- Modal year map (`index.html:547`) — extend the `{'1981':'MCMLXXXI',…}` table
  to cover the new years, or replace it with a function that converts any
  4-digit year to Roman numerals.
- Footer "© MCMLXXXV" (`index.html:481`, `journal.html:193`) → current year.
- Journal entry dates already use MMXXV/MMXXVI — leave those.

Action: get the real shoot year for each plate (EXIF or memory), then map.
EXIF can be read with `identify -format "%[EXIF:DateTimeOriginal]\n" <file>`.

### A.6 Other fabricated copy to scrub

- `index.html:156` — "MCMLXXXI – MCMLXXXV" already covered above.
- `index.html:182` — pseudo-quote attributed "D.S., Studio note, winter".
  Decide: keep, rewrite, or drop.
- `index.html:172` — "52.48°N · Archival Baryta" geo-coord caption. Keep only
  if reference uses similar device; otherwise simplify.
- `index.html:229,246,263,…` — `Pl. I · MCMLXXXIV` style captions roll up into
  the year fix above.
- `journal.html:139` — "Pl. IV pulled in a run of three" contradicts
  `index.html:274` (`data-edition="3"` ✓ but `data-remaining="1"`, "Final
  impression"). Either rewrite the journal entry or align numbers.
- `stripe_sync.py` `DESCRIPTIONS` (50-102) — every entry references the fake
  process/size/framing; rewrite in lockstep with `index.html` so a re-sync
  doesn't push stale text to Stripe.
- `photos/stock-photo-bright-future-137318411.jpg` — an actual stock photo
  sitting in the photos folder. Not referenced from HTML; delete it.

### A.7 Verify

- Grep for lingering fake markers:
  `grep -nE 'silver gelatin|cibachrome|diasec|baryta|oak|walnut|museum glass|framed|Zürich|Antwerp|institutionally|MCMLXXX[I-V]' index.html journal.html stripe_sync.py`
- Open `index.html` in a browser, click each plate, confirm modal copy reads
  cleanly with new dimensions and no framing/buyer references.
- Re-run `python3 stripe_sync.py` only after the HTML is final (it rewrites
  `index.html` with `data-stripe-url` attrs and pushes descriptions to Stripe).

### A.8 Commit & push

- Commit on `claude/remove-fake-data-bldgO`, push with
  `git push -u origin claude/remove-fake-data-bldgO`.
- Do **not** open a PR unless asked.

---

## B. Compliance & premium

Punch list to take this from "shipped" to fully compliant under DE/EU consumer
law and credibly premium for collectors. Ordered roughly by impact / risk.

### B.1 Legal — required for B2C sales from Germany

- [x] **PAngV price labels** — each plate card and the modal must show "incl. VAT · shipping at checkout" (or the §25a margin-scheme equivalent) next to the price, not only on the Stripe page. Visible legal exposure.
- [x] **ODR notice in footer** — link to `https://ec.europa.eu/consumers/odr` and one-line VSBG statement (Art. 14 EU 524/2013). Currently absent.
- [x] **AGB / Terms of Sale page** — full consumer contract terms: scope, conclusion of contract, prices, payment, delivery, passing of risk, retention of title, warranty, jurisdiction, applicable law. Replace the single `<details>` paragraph.
- [x] **Widerrufsbelehrung + Muster-Widerrufsformular** — the formal cancellation notice text and the standard withdrawal form (HTML or PDF). Mentioning "14 days" is not enough under §312g BGB.
- [x] **Shipping & delivery page** — lead times by region, carriers, insurance, customs handling for international buyers. Buyer must know shipping cost before clicking through to Stripe.
- [ ] **Privacy coverage** — `dmrschmidt.de/privacy.html` must specifically name `editions.dmrschmidt.de`, Bunny Fonts, Stripe, and (until B.1.7 lands) the jsdelivr CDN.
- [ ] **Self-host Tailwind build** — replace the in-browser JIT script (loaded from US-based jsdelivr; leaks visitor IP each page view) with a minified static CSS file. Kills the third-country transfer and removes ~50 KB of runtime JS.

### B.2 Accessibility — BFSG (German Accessibility Act, in force since June 2025)

- [ ] **Modal a11y** — `role="dialog"`, `aria-modal="true"`, `aria-labelledby`, focus trap, return focus on close, ESC handler already exists.
- [ ] **Keyboard activation on plate cards** — currently click-only; add `role="button"`, `tabindex="0"`, Enter/Space handler.
- [ ] **Skip-to-content link** for keyboard / screen-reader users.
- [ ] **`prefers-reduced-motion`** — pause the marquee, disable the lift/scale transitions and entrance reveal.
- [ ] **Color contrast audit** — `text-mute` (#7a746a) on ink is borderline at small sizes.

### B.3 Premium — what paying buyers notice

- [ ] **Schema.org JSON-LD** — `Product` per plate (price, availability, image), `Person` for the artist, `WebSite`. Drives rich results.
- [ ] **Image pipeline** — generate AVIF/WebP responsive variants with `srcset`/`sizes`, `fetchpriority="high"` on the hero. Current full JPEGs are slow on mobile and anti-luxury.
- [ ] **Designed OG share card** — 1200×630 with the wordmark, not a reused photo.
- [ ] **Certificate of authenticity sample** — image or PDF a buyer can see before committing €900.
- [ ] **Press / collections / exhibitions** — once A.2 is done this should also soften any remaining institutional flourish. If there is nothing real to credit yet, remove the language entirely.
- [ ] **Styled 404 page**.
- [ ] **Artist conceit math** — see A.5; one framing sentence (family archive, after Berlin, etc.) or a date adjustment.

### B.4 Lower priority

- [ ] `twitter:site` / `twitter:creator` handles in the social meta.
- [ ] Stripe success / cancel pages styled in the atelier voice.
- [ ] Multi-currency display for non-EU buyers (USD/GBP indicative).
