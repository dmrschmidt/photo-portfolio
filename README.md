# Schmidt / Éditions

Static one-page catalogue + journal for the print editions of Dennis Schmidt.
Deployed at <https://editions.dmrschmidt.de/>.

## Layout

```
index.html        — single-page catalogue (10 plates + atelier + enquire)
journal.html      — studio notes
photos/           — plate masters (1500 px long edge)
dennis.jpg        — atelier portrait
stripe_sync.py    — pushes available plates to Stripe (Products → Prices →
                    Payment Links) and writes `data-stripe-url` back into
                    `index.html`
sitemap.xml
robots.txt
```

The catalogue is rendered entirely from `<article data-…>` attributes on each
plate; everything else (modal, hero, marquee, atelier panel) is static markup.

## Stripe sync

`stripe_sync.py` is the only build step. It is idempotent and ledger-backed.

```sh
echo 'STRIPE_SECRET_KEY=sk_test_…' > .env   # test keys are sk_test_…; live keys are sk_live_…
python3 stripe_sync.py
```

For each available plate it:

1. Uploads the image to Stripe Files (cached in the ledger).
2. Creates a Stripe Product + Price + Payment Link the first time it sees the
   plate, or rotates the Price + Link if the EUR amount changed.
3. Deactivates Price + Link when `data-remaining="0"` (sold-out).
4. Rewrites the matching `<article>` in `index.html` with the resulting
   `data-stripe-url`, so the modal's *Acquire* button deep-links to Stripe.

Ledgers are scoped per mode:

- `.stripe_products.test.json` — test keys
- `.stripe_products.live.json` — live keys (sync prompts for confirmation)

Both ledgers are gitignored. Deleting an entry forces that plate to be
re-created on the next run.

To change a plate's description in Stripe, edit `DESCRIPTIONS` in
`stripe_sync.py` and the matching `data-desc` in `index.html`, then re-run. To
force a Stripe-side refresh of a description that hasn't been picked up
(price unchanged path), delete the plate's entry from the ledger.

## Deployment

The repo is pure-static — any host that serves the directory works (Netlify,
Cloudflare Pages, GitHub Pages, S3+CloudFront, plain nginx). The only build
step is the Stripe sync above; commit the resulting `index.html` and the
static host will pick it up.

## Conventions

- Roman-numeral years on plate captions (`MMXXIV` for 2024). The modal
  renders them at runtime from `data-year="2024"` via a Roman-numeral helper.
- Print dimensions are written as `long × short` in cm and reflect the
  source image's actual aspect ratio at a 70 cm long edge.
- Buyer destinations and framing language are deliberately absent — prints
  ship flat, unframed, with a letterpress certificate.

## Known production gaps

See [`TODO.md`](TODO.md).
