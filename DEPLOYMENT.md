# DEPLOYMENT — ship the GAUNTLET site to Vercel

The showcase site in [`web/`](web/) is **fully static** — hand-written
HTML/CSS/JS, no build step, no framework, no server code. That makes deploying
it about as easy as it gets. This guide covers the exact Vercel settings plus a
checklist of the things only you can do.

---

## What's already wired up

- **[`vercel.json`](vercel.json)** at the repo root tells Vercel to serve the
  `web/` folder as static output, with:
  - `outputDirectory: "web"` — the site root
  - `buildCommand: null` — nothing to build
  - `cleanUrls: true` — `/about` serves `web/about.html` (no `.html` needed)
  - long-lived caching for `styles.css`, `main.js`, `favicon.svg`, `og.png`
  - sensible security headers (`X-Content-Type-Options`, `X-Frame-Options`,
    `Referrer-Policy`)
- **No environment variables are required.** The contact form uses a `mailto:`
  handoff (no backend, no secrets).

---

## Option A — Deploy from the Vercel dashboard (recommended)

1. Push this repo to GitHub (see the manual checklist below if you haven't yet).
2. Go to **vercel.com → Add New… → Project** and **Import** the GitHub repo.
3. On the configure screen:
   - **Framework Preset:** `Other`
   - **Root Directory:** leave as the repo root (`./`) — `vercel.json` points
     Vercel at `web/`.
   - **Build Command:** leave empty (overridden to none by `vercel.json`).
   - **Output Directory:** leave as detected (`vercel.json` sets `web`).
4. Click **Deploy**. In ~20 seconds you'll get a `*.vercel.app` URL.

> If Vercel ever ignores `vercel.json` for a static import, set **Root
> Directory** to `web` in the dashboard and clear the Build/Output overrides —
> that deploys the folder directly.

## Option B — Deploy from the CLI

```bash
npm i -g vercel
cd <repo root>
vercel            # first run links/creates the project; follow the prompts
vercel --prod     # promote to production
```

Accept the defaults; `vercel.json` supplies the rest.

---

## Custom domain (optional)

To serve it at something like `gauntlet.charanreddy.dev`:

1. Vercel project → **Settings → Domains → Add**.
2. Enter the domain/subdomain.
3. At your DNS provider, add the record Vercel shows you:
   - subdomain (`gauntlet.charanreddy.dev`) → **CNAME** → `cname.vercel-dns.com`
   - apex/root domain → **A** → the IP Vercel provides
4. Wait for propagation + automatic SSL (usually minutes).

---

## ✅ Manual checklist — the things only you can do

These are the steps GAUNTLET can't do for you. None take long.

1. **Create the GitHub repo & push.** If this isn't a git repo yet:
   ```bash
   git init && git add -A && git commit -m "GAUNTLET: platform + showcase site + docs"
   git branch -M main
   git remote add origin https://github.com/charanreddy-27/GAUNTLET.git
   git push -u origin main
   ```
2. **Deploy to Vercel** using Option A or B above.
3. **Update the canonical URLs** once you know the live URL. In
   `web/index.html`, `web/about.html`, `web/project.html`, replace the
   `og:image` / `og:url` values with the absolute deployed URL
   (e.g. `https://gauntlet.charanreddy.dev/og.png`) so link previews render on
   LinkedIn/Twitter/Slack. Also update the **Live site** link in `README.md`.
4. **Drop in real screenshots.** The README hero currently uses `web/og.png`.
   If you want in-app screenshots, add them under a `screenshots/` (or
   `web/assets/`) folder and reference them in `README.md`. A short GIF of
   `gauntlet run` + `diff` is the single highest-leverage asset here.
5. **Add the LinkedIn post link.** Once you post about the project, put the URL
   in the `project.html` CTA ("Read the LinkedIn post") and the README.
6. **Validate the social card.** Paste the live URL into
   [LinkedIn Post Inspector](https://www.linkedin.com/post-inspector/) and
   [opengraph.xyz](https://www.opengraph.xyz) to confirm the OG image renders.
7. **Sanity-check the contact form.** It opens a `mailto:` to
   `charanreddychanda@gmail.com`. Confirm that's the address you want (note:
   the "who this is" block also lists `charanreddychanda@gmail.com`; the CLAUDE
   profile lists `charanreddychanda27@gmail.com` — pick one and make it
   consistent).
8. **(Optional) Run the Python demo in CI or locally** and capture the terminal
   output / HTML report (`gauntlet report <run> --html out.html`) as an artifact
   to link from the site.

---

## The Python package (not part of the web deploy)

The `gauntlet` CLI is a separate artifact from the website — Vercel only serves
`web/`. If you want the tool installable:

- **PyPI (optional):** `python -m build && twine upload dist/*` (the project is
  already `pip install -e .`-ready via `pyproject.toml`).
- **CI:** [`.github/workflows/gauntlet.yml`](.github/workflows/gauntlet.yml)
  already installs the package, runs the test suite and the seeded smoke flow,
  and uploads `runs/` as a build artifact on every push.

---

## Troubleshooting

| Symptom | Fix |
|---|---|
| Vercel builds nothing / 404 at root | Ensure `vercel.json` is at the **repo root**, or set Root Directory to `web` in the dashboard. |
| `/about` 404s but `/about.html` works | `cleanUrls` isn't applied — confirm `vercel.json` deployed; redeploy. |
| OG image doesn't show in previews | `og:image` must be an **absolute** URL (see checklist #3); re-scrape with the LinkedIn/Twitter inspector. |
| Fonts don't load | The site uses Google Fonts over HTTPS; check the network tab / any content blocker. Everything else is self-hosted. |
| Dark/light toggle "forgets" | It persists to `localStorage` per browser; that's expected, not a bug. |
