# TODO

The un-fakify pass — paper/process, dimensions, residence/buyer references,
framing language, the impossible MCMLXXXI–MCMLXXXV catalogue years (now
plausible-recent placeholders MMXX–MMXXIV, flagged below), the MCMLXXXV
copyright (now MMXXVI), and the stock photo in `photos/` — is done. See
commit `e7354eb`.

What remains is the compliance / premium punch list to take the site from
"clean" to "production". Ordered roughly by impact / risk.

## 1. Legal — required for B2C sales from Germany

- [x] **PAngV price labels** — each plate card and the modal must show "incl. VAT · shipping at checkout" (or the §25a margin-scheme equivalent) next to the price, not only on the Stripe page. Visible legal exposure.
- [x] **ODR notice in footer** — link to `https://ec.europa.eu/consumers/odr` and one-line VSBG statement (Art. 14 EU 524/2013). Currently absent.
- [x] **AGB / Terms of Sale page** — full consumer contract terms: scope, conclusion of contract, prices, payment, delivery, passing of risk, retention of title, warranty, jurisdiction, applicable law. Replace the single `<details>` paragraph.
- [x] **Widerrufsbelehrung + Muster-Widerrufsformular** — the formal cancellation notice text and the standard withdrawal form (HTML or PDF). Mentioning "14 days" is not enough under §312g BGB.
- [x] **Shipping & delivery page** — lead times by region, carriers, insurance, customs handling for international buyers. Buyer must know shipping cost before clicking through to Stripe.
- [x] **Privacy coverage** — site now serves its own `privacy.html`, naming Bunny Fonts, jsDelivr, and Stripe specifically. One placeholder remains: the hoster needs to be filled in under §4 once confirmed.
- [ ] **Self-host Tailwind build** — replace the in-browser JIT script (loaded from US-based jsdelivr; leaks visitor IP each page view) with a minified static CSS file. Kills the third-country transfer, removes ~50 KB of runtime JS, and eliminates the brief FOUC on every load. Cheapest path: `npx @tailwindcss/cli -i input.css -o styles.css --minify`, commit `styles.css`, swap the `<script>` tag for a `<link rel="stylesheet">`. No Node runtime at deploy time — only at build.

## 2. Accessibility — BFSG (German Accessibility Act, in force since June 2025)

- [ ] **Modal a11y** — `role="dialog"`, `aria-modal="true"`, `aria-labelledby` are now set; ESC handler already exists. Still missing: move focus into the dialog on open, return it to the triggering `<article>` on close, and trap Tab inside the dialog while it's open.
- [ ] **Keyboard activation on plate cards** — currently click-only; add `role="button"`, `tabindex="0"`, Enter/Space handler.
- [ ] **Skip-to-content link** for keyboard / screen-reader users.
- [ ] **`prefers-reduced-motion`** — pause the marquee, disable the lift/scale transitions and entrance reveal.
- [ ] **Color contrast audit** — `text-mute` (#7a746a) on ink is borderline at small sizes.

## 3. Premium — what paying buyers notice

- [ ] **Schema.org JSON-LD** — `Product` per plate (price, availability, image), `Person` for the artist, `WebSite`. Drives rich results.
- [ ] **Image pipeline** — generate AVIF/WebP responsive variants with `srcset`/`sizes`, `fetchpriority="high"` on the hero. Current full JPEGs are slow on mobile and anti-luxury. The Tailwind `aspect-[…]` classes already pin layout, so adding `width`/`height` attributes here would also eliminate the residual CLS.
- [ ] **Designed OG share card** — 1200×630 with the wordmark, not a reused photo.
- [ ] **Certificate of authenticity sample** — image or PDF a buyer can see before committing €900.
- [ ] **Press / collections / exhibitions** — institutional flourish elsewhere should be softened. If there is nothing real to credit yet, remove the language entirely.
- [ ] **Styled 404 page**.
- [ ] **Replace placeholder shoot years with real ones** — EXIF was stripped from the web copies in `photos/`, so the current `data-year` values (MMXX–MMXXIV) are plausible-recent placeholders. Overwrite each one with the real year from memory or from the source RAW/JPG. The hero subtitle (`Editions I – X · MMXX – MMXXIV`) and any "earliest plate in the catalogue" callouts derive from the earliest/latest plate year — adjust after the per-plate years are set.
- [ ] **Maybachufer 40 sanity check** — `index.html` (Atelier and Enquire panels) and `journal.html` (entry №III location chip) all cite "Maybachufer 40, Neukölln". If this is a real address, ignore. If not, correct or remove — it's the only piece of ground-truth claim left.

## 4. Lower priority

- [ ] `twitter:site` / `twitter:creator` handles in the social meta.
- [ ] Stripe success / cancel pages styled in the atelier voice. Includes wiring `after_completion[type]=redirect` + `after_completion[redirect][url]` into the `payment_links` call in `stripe_sync.py` so buyers actually land on them.
- [ ] Multi-currency display for non-EU buyers (USD/GBP indicative).
