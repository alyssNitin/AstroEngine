#!/usr/bin/env python3
"""
run_tests.py
============
NarayanAstroReader — Unit Test Runner with HTML Report
======================================================
Discovers and runs all test_*.py files, then generates a self-contained
HTML report saved to: tests/test_report.html

Usage:
  python tests/run_tests.py
  python tests/run_tests.py --verbose       # show test names
  python tests/run_tests.py --xml           # also write JUnit XML
"""
from __future__ import annotations
import sys, os, unittest, argparse, time, html as _html
from datetime import datetime
from pathlib import Path
from io import StringIO

# Ensure project root is on path
_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(_ROOT))

REPORT_PATH = _ROOT / "tests" / "test_report.html"


# ── Custom test result collector ──────────────────────────────────────────────

class _Result(unittest.TestResult):
    def __init__(self):
        super().__init__()
        self.records: list[dict] = []
        self.test_times: dict[str, float] = {}
        self._start_times: dict[str, float] = {}

    def startTest(self, test):
        super().startTest(test)
        self._start_times[str(test)] = time.monotonic()

    def _record(self, test, status: str, detail: str = ""):
        elapsed = time.monotonic() - self._start_times.get(str(test), 0)
        module  = test.__class__.__module__.replace("tests.", "")
        cls     = test.__class__.__name__
        method  = test._testMethodName
        doc     = (test._testMethodDoc or "").strip().split("\n")[0]
        self.records.append({
            "module": module, "class": cls, "method": method,
            "doc": doc, "status": status, "detail": detail,
            "elapsed": round(elapsed * 1000, 1),
        })

    def addSuccess(self, test):
        super().addSuccess(test)
        self._record(test, "PASS")

    def addFailure(self, test, err):
        super().addFailure(test, err)
        self._record(test, "FAIL", self._exc_info_to_string(err, test))

    def addError(self, test, err):
        super().addError(test, err)
        self._record(test, "ERROR", self._exc_info_to_string(err, test))

    def addSkip(self, test, reason):
        super().addSkip(test, reason)
        self._record(test, "SKIP", reason)

    def addExpectedFailure(self, test, err):
        super().addExpectedFailure(test, err)
        self._record(test, "XFAIL", self._exc_info_to_string(err, test))

    def addUnexpectedSuccess(self, test):
        super().addUnexpectedSuccess(test)
        self._record(test, "XPASS")


# ── HTML report generator ─────────────────────────────────────────────────────

def _e(s: str) -> str:
    return _html.escape(str(s))


def _generate_html(result: _Result, elapsed_total: float, suite_name: str) -> str:
    records   = result.records
    total     = len(records)
    passed    = sum(1 for r in records if r["status"] == "PASS")
    failed    = sum(1 for r in records if r["status"] == "FAIL")
    errors    = sum(1 for r in records if r["status"] == "ERROR")
    skipped   = sum(1 for r in records if r["status"] == "SKIP")
    pct       = round(passed / max(total, 1) * 100, 1)
    now       = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    overall   = "PASSED" if (failed + errors) == 0 else "FAILED"
    ov_color  = "#059669" if overall == "PASSED" else "#DC2626"

    STATUS_STYLE = {
        "PASS":  ("✅", "#059669", "#F0FDF4", "#86EFAC"),
        "FAIL":  ("❌", "#DC2626", "#FEF2F2", "#FCA5A5"),
        "ERROR": ("💥", "#B45309", "#FFFBEB", "#FCD34D"),
        "SKIP":  ("⏭️",  "#6B7280", "#F9FAFB", "#D1D5DB"),
        "XFAIL": ("⚠️",  "#7C3AED", "#F5F3FF", "#C4B5FD"),
        "XPASS": ("🎉", "#0369A1", "#EFF6FF", "#93C5FD"),
    }

    # Group by module→class
    groups: dict[str, dict[str, list]] = {}
    for r in records:
        groups.setdefault(r["module"], {}).setdefault(r["class"], []).append(r)

    rows_html = []
    for mod, classes in groups.items():
        rows_html.append(
            f'<tr><td colspan="6" style="background:#F3F4F6;font-weight:700;'
            f'font-size:.78rem;color:#6B7280;text-transform:uppercase;'
            f'letter-spacing:.5px;padding:8px 14px">{_e(mod)}</td></tr>'
        )
        for cls, tests in classes.items():
            rows_html.append(
                f'<tr><td colspan="6" style="background:#FAFAFA;font-weight:600;'
                f'font-size:.82rem;color:#374151;padding:6px 22px">{_e(cls)}</td></tr>'
            )
            for t in tests:
                icon, fg, bg, border = STATUS_STYLE.get(t["status"], ("❓","#000","#fff","#ccc"))
                detail_html = ""
                if t["detail"]:
                    escaped = _e(t["detail"])
                    detail_html = (
                        f'<details><summary style="cursor:pointer;font-size:.75rem;'
                        f'color:#6B7280;margin-top:4px">Show detail</summary>'
                        f'<pre style="font-size:.72rem;overflow-x:auto;'
                        f'background:#1F2937;color:#F9FAFB;padding:10px;border-radius:6px;'
                        f'margin-top:6px">{escaped}</pre></details>'
                    )
                rows_html.append(f"""
<tr style="background:{bg};border-left:3px solid {border}">
  <td style="padding:10px 14px;font-size:.85rem;font-weight:600;color:{fg};
             white-space:nowrap">{icon} {_e(t['status'])}</td>
  <td style="padding:10px 14px;font-size:.82rem;font-family:monospace;color:#1F2937">
    {_e(t['method'])}
    {('<div style="font-size:.74rem;color:#6B7280;margin-top:2px">'+_e(t['doc'])+'</div>') if t['doc'] else ''}
    {detail_html}
  </td>
  <td style="padding:10px 14px;font-size:.78rem;color:#6B7280;
             white-space:nowrap;text-align:right">{t['elapsed']} ms</td>
</tr>""")

    rows = "\n".join(rows_html)

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>NarayanAstroReader — Test Report</title>
<style>
  body{{font-family:'Segoe UI',system-ui,sans-serif;background:#F9FAFB;color:#111827;margin:0;padding:0}}
  header{{background:linear-gradient(120deg,#E8610A,#8B1A8B,#5B3DC8);padding:20px 28px;color:#fff}}
  header h1{{font-size:1.4rem;margin:0 0 4px}}
  header p{{font-size:.82rem;opacity:.85;margin:0}}
  main{{max-width:1100px;margin:0 auto;padding:24px 16px}}
  .stat-row{{display:grid;grid-template-columns:repeat(auto-fit,minmax(130px,1fr));gap:12px;margin-bottom:24px}}
  .stat{{background:#fff;border:1.5px solid #E5E7EB;border-radius:12px;padding:16px 18px;text-align:center}}
  .stat .num{{font-size:2rem;font-weight:700}}
  .stat .lbl{{font-size:.75rem;color:#6B7280;font-weight:600;text-transform:uppercase}}
  .overall{{display:inline-block;padding:4px 16px;border-radius:20px;font-weight:700;
            font-size:.9rem;background:{ov_color};color:#fff;margin-bottom:16px}}
  table{{width:100%;border-collapse:collapse;background:#fff;border-radius:12px;
         overflow:hidden;border:1.5px solid #E5E7EB;box-shadow:0 2px 8px rgba(0,0,0,.06)}}
  th{{background:#F3F4F6;font-size:.78rem;font-weight:700;color:#374151;
      text-transform:uppercase;letter-spacing:.5px;padding:10px 14px;text-align:left}}
  tr:not(:last-child){{border-bottom:1px solid #F3F4F6}}
  .footer{{margin-top:24px;font-size:.76rem;color:#9CA3AF;text-align:center}}
</style>
</head>
<body>
<header>
  <h1>🪐 NarayanAstroReader — Unit Test Report</h1>
  <p>{_e(suite_name)} · Generated {_e(now)} · Total time {elapsed_total:.2f}s</p>
</header>
<main>
  <div class="overall">{overall} — {pct}% passed</div>
  <div class="stat-row">
    <div class="stat"><div class="num" style="color:#059669">{passed}</div><div class="lbl">Passed</div></div>
    <div class="stat"><div class="num" style="color:#DC2626">{failed}</div><div class="lbl">Failed</div></div>
    <div class="stat"><div class="num" style="color:#B45309">{errors}</div><div class="lbl">Errors</div></div>
    <div class="stat"><div class="num" style="color:#6B7280">{skipped}</div><div class="lbl">Skipped</div></div>
    <div class="stat"><div class="num" style="color:#1F2937">{total}</div><div class="lbl">Total</div></div>
  </div>

  <table>
    <thead>
      <tr>
        <th style="width:90px">Status</th>
        <th>Test</th>
        <th style="width:90px;text-align:right">Time</th>
      </tr>
    </thead>
    <tbody>
      {rows}
    </tbody>
  </table>

  <div class="footer">NarayanAstroReader v1.0 · PyJHora + Claude AI · Phase 1: AI Core &amp; Credit System</div>
</main>
</body>
</html>"""


# ── Runner ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="NarayanAstroReader test runner")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose test names")
    parser.add_argument("--xml", action="store_true", help="Also write JUnit XML")
    parser.add_argument("--pattern", default="test_*.py", help="File pattern (default: test_*.py)")
    args = parser.parse_args()

    tests_dir = Path(__file__).parent
    loader    = unittest.TestLoader()

    print(f"\n🪐 NarayanAstroReader Test Runner")
    print(f"   Discovering tests in: {tests_dir}")
    print("=" * 60)

    suite = loader.discover(str(tests_dir), pattern=args.pattern, top_level_dir=str(_ROOT))

    result  = _Result()
    t_start = time.monotonic()

    # Stream names to console if verbose
    if args.verbose:
        for test_group in suite:
            for sub_group in test_group:
                for test in sub_group:
                    print(f"  ▸ {test.id()}")

    suite.run(result)
    elapsed = time.monotonic() - t_start

    # Console summary
    total  = result.testsRun
    passed = sum(1 for r in result.records if r["status"] == "PASS")
    failed = len(result.failures)
    errors = len(result.errors)
    print(f"\nResults: {passed}/{total} passed | {failed} failed | {errors} errors | {elapsed:.2f}s")

    # HTML report
    report_html = _generate_html(result, elapsed, "All Tests")
    REPORT_PATH.write_text(report_html, encoding="utf-8")
    print(f"\n📄 HTML report: {REPORT_PATH}")

    # JUnit XML (optional)
    if args.xml:
        try:
            import xml.etree.ElementTree as ET
            ts = ET.Element("testsuite", {
                "name": "NarayanAstroReader", "tests": str(total),
                "failures": str(failed), "errors": str(errors),
                "time": str(round(elapsed, 3)),
            })
            for r in result.records:
                tc = ET.SubElement(ts, "testcase", {
                    "classname": f"{r['module']}.{r['class']}",
                    "name": r["method"],
                    "time": str(r["elapsed"] / 1000),
                })
                if r["status"] == "FAIL":
                    ET.SubElement(tc, "failure", {"message": r["detail"][:200]})
                elif r["status"] == "ERROR":
                    ET.SubElement(tc, "error", {"message": r["detail"][:200]})
                elif r["status"] == "SKIP":
                    ET.SubElement(tc, "skipped", {"message": r["detail"]})
            xml_path = REPORT_PATH.with_suffix(".xml")
            ET.ElementTree(ts).write(str(xml_path), encoding="utf-8", xml_declaration=True)
            print(f"📋 JUnit XML: {xml_path}")
        except Exception as ex:
            print(f"⚠️  XML write failed: {ex}")

    # Exit code
    overall_ok = (failed + errors) == 0
    print(f"\n{'✅ ALL TESTS PASSED' if overall_ok else '❌ SOME TESTS FAILED'}\n")
    sys.exit(0 if overall_ok else 1)


if __name__ == "__main__":
    main()
