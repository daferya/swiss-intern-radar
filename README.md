# Swiss AI Internship Radar

A free, self-hosted job radar for **AI, machine-learning and data internships in Switzerland**.
Every morning it reads the public job boards of ~55 employers (AI labs, big tech, Swiss AI
start-ups, pharma, industry), keeps the internships that are in Switzerland and about AI/ML/data,
and publishes them on your own website. When something new fits your profile, GitHub opens an
issue and emails you.

It costs nothing to run: no paid APIs, no LLM, no server. Scraping runs on GitHub Actions and the
site is a static page on GitHub Pages (both free for public repositories).

## What you get

- **A departure board of new postings.** The site opens with what appeared this week, then a full
  list you can filter: length fits 6 months, start in Aug–Sep 2027 (or flexible), hide roles that
  need German, hide PhD-only roles, city, topic (ML/AI, vision, NLP/LLM, robotics…), employer type.
- **Facts pulled out of the ad text** (English, French, German, Italian), with plain rules:
  internship length ("6–12 Monate", "durée : 6 mois", "13–17 weeks"), start date ("dès septembre
  2027", "Eintritt nach Vereinbarung", "ASAP"), pay when it is stated, and required languages.
  Three lamps on each row show whether length, start and language fit.
- **Your own tracker.** Save, mark as applied, or hide postings; download your list as CSV.
  Marks stay in your browser.
- **Alerts.** A GitHub issue (with an email) each morning that new matching internships appear.
  Optional phone push through ntfy.

## Put it online (about 5 minutes)

1. Create a new **public** repository on GitHub, for example `swiss-intern-radar`.
   (GitHub Pages is free for public repos. Private repos need GitHub Pro, which students get for
   free with the GitHub Student Developer Pack.)
2. Push this folder with git (dragging files into the browser can drop the hidden `.github` folder):
   ```bash
   cd swiss-intern-radar
   git init -b main && git add -A && git commit -m "Internship radar"
   git remote add origin https://github.com/<you>/swiss-intern-radar.git
   git push -u origin main
   ```
3. On GitHub: **Settings → Pages → Build and deployment → Source: GitHub Actions**.
4. **Actions** tab → enable workflows if asked → **radar** → **Run workflow**.
5. A few minutes later your radar is at `https://<you>.github.io/swiss-intern-radar/`.
   From then on it refreshes every day at about 06:15 Swiss time.

With the [GitHub CLI](https://cli.github.com) installed, `bash scripts/setup_github.sh` does
steps 1–4 for you.

## Run it on your laptop

```bash
python3 -m venv .venv && source .venv/bin/activate      # Python 3.10+. Windows: .venv\Scripts\activate
pip install -r requirements.txt
python -m internradar scrape     # ~1–3 minutes; prints which sources worked
python -m internradar serve      # opens the site on http://localhost:8000
python -m internradar list       # or read your matches in the terminal
```

Google, Apple, Meta, Microsoft and IBM only render their career pages with JavaScript. To include
them, also run `pip install -r requirements-browser.txt && python -m playwright install chromium`.
(The GitHub workflow does this automatically.)

## Make it yours

**`config.yaml`** holds your profile: target start months, internship length, languages to hide,
minimum stated pay, words to exclude from titles (quant/trading roles are excluded by default),
and how broad "AI/ML/data" should be (`min_relevance`). The website opens with these filters and
the alerts only announce postings that fit them.

**`companies.yaml`** lists where to look. To add an employer, find its job board:

```bash
python -m internradar discover "Lakera" "Gravis Robotics" "Picterra"
```

It probes Greenhouse, Lever, Ashby, Workable, Recruitee, Personio and SmartRecruiters and prints
a snippet to paste. For Workday employers (Roche, Novartis, NVIDIA…), copy the host and site name
from any job URL on their career site: `https://novartis.wd3.myworkdayjobs.com/en-US/Novartis_Careers/job/...`
gives `host: novartis.wd3.myworkdayjobs.com` and `site: Novartis_Careers`. Companies marked
`ats: auto` are probed automatically and the result is remembered.

After each run, the **Sources** table at the bottom of the site (or `python -m internradar check`)
shows every employer's status. Some entries in `companies.yaml` are educated guesses; if one shows
as failing, run `discover` on it and fix the line.

## Alerts

- **Email:** when new matching internships appear, the workflow opens an issue assigned to you.
  Check that GitHub emails you about issues (Settings → Notifications).
- **Phone push (optional):** install the free [ntfy](https://ntfy.sh) app, subscribe to a long,
  random topic name, and save that name as the repository secret `NTFY_TOPIC`
  (Settings → Secrets and variables → Actions).
- **More coverage (optional):** a free [Adzuna](https://developer.adzuna.com) API key adds
  internships from companies that are not in your list. Save `ADZUNA_APP_ID` and `ADZUNA_APP_KEY`
  as repository secrets.

## How it works

| Job board | Public endpoint used (no key) |
|---|---|
| Greenhouse | `boards-api.greenhouse.io/v1/boards/{slug}/jobs?content=true` (US and EU hosts) |
| Lever | `api.lever.co/v0/postings/{slug}?mode=json` (and `api.eu.lever.co`) |
| Ashby | `api.ashbyhq.com/posting-api/job-board/{slug}` |
| Workable | `apply.workable.com/api/v1/widget/accounts/{slug}?details=true` |
| Recruitee | `{slug}.recruitee.com/api/offers/` |
| Personio | `{slug}.jobs.personio.de/xml` |
| SmartRecruiters | `api.smartrecruiters.com/v1/companies/{id}/postings` |
| Workday | `{tenant}.wdN.myworkdayjobs.com/wday/cxs/{tenant}/{site}/jobs`, filtered with the site's own "Switzerland" facet |
| Other career sites | the listing page, then the schema.org `JobPosting` data on each job page |

Each posting is checked for: a Swiss location, internship / thesis / working-student wording
(`intern`, `Praktikum`, `stage`, `stagiaire`, `tirocinio`, `Werkstudent`, `Masterarbeit`…), and an
AI/ML/data relevance score from the title and description. Everything is rule-based and runs in a
few seconds; the slow part is being polite to the job boards (at most 2 parallel requests per site,
once a day).

`docs/data/jobs.json` is committed after every run, so the radar remembers when it first saw each
posting. A source that fails for a day keeps its last postings (marked on the site) instead of
dropping them.

## Costs and limits

- **Free:** GitHub Actions is free on public repositories and a daily run takes 2–4 minutes;
  GitHub Pages is free; every API used is public. A custom domain is the only thing that would
  cost money, and you don't need one.
- **Coverage:** only employers in `companies.yaml` (plus Adzuna if you add a key). Companies with
  custom career sites (for example Swisscom, UBS, Nestlé) need an `html` or `browser` entry.
- **Parsing:** length, start date, pay and languages are read from free text. Check them on the
  posting before you apply.
- **Big-tech pages** scraped with the headless browser can break when those sites are redesigned;
  the Sources table tells you when.
- **Be a good citizen:** don't add LinkedIn, Indeed or jobs.ch scraping; their terms forbid it.
- **Schedules:** GitHub pauses scheduled workflows in public repos after 60 days without activity.
  The daily data commit normally keeps it active; if the Actions tab ever shows the workflow as
  disabled, click **Enable workflow**.

## Development

```bash
pip install -r requirements.txt -r requirements-dev.txt
python -m pytest -q
```

`internradar/sources/` has one small adapter per job board, `classify.py` the parsing rules,
`location.py` the Swiss-location check, `pipeline.py` the run/merge logic, and `docs/index.html`
the whole website (no build step). The Archivo font is bundled under the SIL Open Font License.

Inspired by [swissaijob.ch](https://swissaijob.ch).
