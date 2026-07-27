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
  - `framework: null`, plus explicit no-op `buildCommand` and `installCommand`
    — see [Why these are set explicitly](#why-framework-and-the-commands-are-set-explicitly)
  - `cleanUrls: true` — `/about` serves `web/about.html` (no `.html` needed)
  - revalidating cache headers on the assets (they have no content hash in the
    filename, so `immutable` would pin stale CSS/JS for a year)
  - security headers: `X-Content-Type-Options`, `X-Frame-Options`,
    `Referrer-Policy`, `Permissions-Policy`, and a `Content-Security-Policy`
    scoped to what the site actually loads (self + Google Fonts)
- **[`.vercelignore`](.vercelignore)** keeps the Python platform, tests and docs
  out of the deployment entirely — only `web/` ships.
- **No environment variables are required.** The contact form uses a `mailto:`
  handoff (no backend, no secrets).

### Why `framework` and the commands are set explicitly

Vercel's zero-config detection runs whenever `framework`, `buildCommand` or
`installCommand` is `null`. Because `pyproject.toml` sits at the repo root, that
detection classified GAUNTLET as a **Python backend** and every build failed
before it started:

```
Error: No python entrypoint found. Set "tool.vercel.entrypoint" in pyproject.toml
or define an entrypoint in one of: app.py, index.py, server.py, main.py, ...
```

The project's stored Framework Preset was `python` for the same reason. Setting
all three keys to explicit values in `vercel.json` overrides the stored preset
and skips detection, so the build is just "copy `web/`". `.vercelignore` removes
`pyproject.toml` from the deployment as a second line of defence.

**If you ever add a real Python API to this project**, don't revert these keys —
add an `api/` directory (Vercel Functions) instead, and give the function its
own entrypoint.

### The Production Branch must be `main`

This one is a **dashboard setting** — nothing in this repo can set it, so it is
worth knowing about.

Vercel pins a project's Production Branch to whatever branch it was **first
imported from**. This project was imported from `claude/gauntlet-ip-regression-me6p5p`,
so that became the production branch. The symptom is confusing, because nothing
looks broken:

- merges to `main` build successfully, but land as **preview** deployments
  (`target: null`) instead of production;
- `gauntlet-charanreddy-27s-projects.vercel.app` keeps serving whatever the last
  real production deployment was — and serves **nothing at all** if that
  deployment is deleted;
- the Deployments list is full of green builds while the live URL is stale or
  blank.

Fix it once, in **Project → Settings → Git → Production Branch → `main` → Save**,
then promote the newest `main` deployment (**Deployments → ⋯ → Promote to
Production**). After that every merge to `main` publishes to production
automatically.

A deployment's `target` field is the thing to check: `"production"` means it is
live on the production domain, `null` means it is only a preview.

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
3. **Set the Production Branch to `main`** — Project → Settings → Git. See
   [The Production Branch must be `main`](#the-production-branch-must-be-main).
   Until this is right, merges to `main` only ever produce preview deployments
   and the live URL never updates.
4. **Only if you add a custom domain:** the canonical/OG URLs in
   `web/index.html`, `web/about.html`, `web/project.html`, plus
   `web/robots.txt`, `web/sitemap.xml` and the **Live site** link in
   `README.md`, are currently pinned to the production Vercel URL
   `https://gauntlet-charanreddy-27s-projects.vercel.app`. Search-and-replace
   that one string with the new domain — they must stay **absolute** or link
   previews break on LinkedIn/Twitter/Slack.
5. **Drop in real screenshots.** The README hero currently uses `web/og.png`.
   If you want in-app screenshots, add them under a `screenshots/` (or
   `web/assets/`) folder and reference them in `README.md`. A short GIF of
   `gauntlet run` + `diff` is the single highest-leverage asset here.
6. **Add the LinkedIn post link.** Once you post about the project, put the URL
   in the `project.html` CTA ("Read the LinkedIn post") and the README.
7. **Validate the social card.** Paste the live URL into
   [LinkedIn Post Inspector](https://www.linkedin.com/post-inspector/) and
   [opengraph.xyz](https://www.opengraph.xyz) to confirm the OG image renders.
8. **Sanity-check the contact address.** The site was inconsistent between
   `charanreddychanda@gmail.com` and `charanreddychanda27@gmail.com`; it is now
   consistently **`charanreddychanda27@gmail.com`** (the address on the GitHub
   and Vercel accounts) in `web/about.html` and `web/main.js`. If you'd rather
   use the other one, change it in both files.
9. **(Optional) Run the Python demo in CI or locally** and capture the terminal
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
| `Error: No python entrypoint found` | `framework`/`buildCommand`/`installCommand` fell back to auto-detection and `pyproject.toml` made Vercel think this is a Python backend. Keep all three set explicitly in `vercel.json` (see above). |
| Builds are green but the live URL is stale or blank | The deployments are landing as previews. Check the Production Branch is `main` (see above), then promote the latest `main` deployment. |
| Vercel builds nothing / 404 at root | Ensure `vercel.json` is at the **repo root**, or set Root Directory to `web` in the dashboard. |
| Site shows stale CSS/JS after a deploy | Assets are cached for an hour with `stale-while-revalidate`; hard-reload, or wait it out. Don't reintroduce `immutable` — the filenames carry no content hash. |
| `/about` 404s but `/about.html` works | `cleanUrls` isn't applied — confirm `vercel.json` deployed; redeploy. |
| OG image doesn't show in previews | `og:image` must be an **absolute** URL (see checklist #3); re-scrape with the LinkedIn/Twitter inspector. |
| Fonts don't load | The site uses Google Fonts over HTTPS; check the network tab / any content blocker. Everything else is self-hosted. |
| Dark/light toggle "forgets" | It persists to `localStorage` per browser; that's expected, not a bug. |
