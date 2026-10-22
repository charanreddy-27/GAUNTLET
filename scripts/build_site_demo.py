#!/usr/bin/env python3
"""Regenerate web/demo/ — real reports for the showcase site.

Runs the seeded smoke flow twice (clean, then with a flake injected) through
the actual CLI into a throwaway runs dir, then renders the HTML report for
each run and the diff between them with the same code `gauntlet report
--html` uses. Logs are copied alongside so every "output.log" link works.

    python scripts/build_site_demo.py

Nothing here is hand-written: if the report renderer changes, re-run this and
the site shows the new output.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "web" / "demo"
sys.path.insert(0, str(ROOT))

from gauntlet.diff import diff_runs  # noqa: E402
from gauntlet.html_report import render_diff_html, render_html  # noqa: E402
from gauntlet.store import RunStore  # noqa: E402

BANNER = (
    '<section class="card card-b" style="display:flex;gap:12px;align-items:center;flex-wrap:wrap">'
    '<span class="tag crit">sample</span>'
    '<span style="flex:1;min-width:220px">{text}</span>'
    '<a class="btn ghost" href="/">← back to the GAUNTLET site</a></section>'
)


def run(env_extra: dict[str, str], runs_dir: Path) -> None:
    env = {**os.environ, "GAUNTLET_RUNS_DIR": str(runs_dir), "NO_COLOR": "1", "GAUNTLET_GIT_BRANCH": "main", **env_extra}
    subprocess.run(
        [sys.executable, "-m", "gauntlet.cli", "run", "flows/smoke.yaml", "--workers", "4", "--keep-going"],
        cwd=ROOT, env=env, check=False, stdout=subprocess.DEVNULL,
    )  # fmt: skip


def main() -> int:
    with tempfile.TemporaryDirectory() as tmp:
        runs_dir = Path(tmp) / "runs"
        run({"GAUNTLET_SEED": "7"}, runs_dir)
        run({"GAUNTLET_SEED": "7", "GAUNTLET_FLAKE": "0.3"}, runs_dir)
        with RunStore(runs_dir / "gauntlet.db") as store:
            clean, flaky = store.load("latest~1"), store.load("latest")

        if OUT.exists():
            shutil.rmtree(OUT)
        (OUT / "logs").mkdir(parents=True)

        def log_href_for(tag: str):
            def href(result):
                if not result.log_path:
                    return None
                name = f"{tag}-{result.step_id}.log"
                shutil.copyfile(result.log_path, OUT / "logs" / name)
                return f"logs/{name}"

            return href

        pages = {
            "report.html": (
                render_html(flaky, log_href_for("regression")),
                "This is a real report: <code>gauntlet report latest --html</code> after a seeded run "
                "with a flake injected. Click any node, filter the violations, open a log.",
            ),
            "report-clean.html": (
                render_html(clean, log_href_for("clean")),
                "The baseline run: same seed, no flake. <code>sim_unit</code> is WAIVED, not PASS — "
                "its known error has an owner.",
            ),
            "diff.html": (
                render_diff_html(diff_runs(clean, flaky), clean, flaky),
                "<code>gauntlet diff latest~1 latest --html</code>: the delta between the two runs. "
                "Exit code 1 is what trips a CI gate.",
            ),
        }
        for name, (html, note) in pages.items():
            if name == "diff.html":
                # In the standalone diff, run ids link to the two sample reports.
                html = html.replace(f'href="#{clean.run_id}"', 'href="report-clean.html"')
                html = html.replace(f'href="#{flaky.run_id}"', 'href="report.html"')
            html = html.replace("<main>\n", "<main>\n" + BANNER.format(text=note), 1)
            html = html.replace("<head>", '<head>\n<meta name="robots" content="noindex">', 1)
            (OUT / name).write_text(html, encoding="utf-8")
            print(f"wrote {OUT.relative_to(ROOT) / name}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
