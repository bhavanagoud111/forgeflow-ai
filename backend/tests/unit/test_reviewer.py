from forgeflow.agents.reviewer import parse_diff, static_findings
from forgeflow.schemas import ReviewReport

DIFF = (
    """diff --git a/app/run.py b/app/run.py
--- a/app/run.py
+++ b/app/run.py
@@ -1,2 +1,4 @@
 import subprocess
-x = 1
+subprocess.run(cmd, shell=True)
+TOKEN = "ghp_"""
    + "a" * 36
    + """"
+requests.get(url, verify=False)
diff --git a/.github/workflows/ci.yml b/.github/workflows/ci.yml
--- a/.github/workflows/ci.yml
+++ b/.github/workflows/ci.yml
@@ -1 +1 @@
-on: push
+on: pull_request
"""
)


def test_parse_diff_tracks_new_line_numbers():
    parsed = parse_diff(DIFF)
    added = [(n, t) for n, s, t in parsed["app/run.py"] if s == "+"]
    assert added[0] == (2, "subprocess.run(cmd, shell=True)")
    assert added[2][0] == 4


def test_static_findings_flag_dangerous_changes():
    changed = [
        {"path": "app/run.py", "status": "modified"},
        {"path": ".github/workflows/ci.yml", "status": "modified"},
        {"path": "tests/test_a.py", "status": "deleted"},
    ]
    findings = static_findings(DIFF, changed)
    titles = {f.title for f in findings}
    assert {
        "Shell invocation",
        "Credential committed",
        "TLS verification disabled",
        "CI configuration changed",
        "Test file deleted",
    } <= titles
    report = ReviewReport(summary="s", findings=findings)
    assert report.blocking  # the credential is critical


def test_secret_like_values_in_tests_are_not_flagged():
    diff = '--- /dev/null\n+++ b/tests/test_x.py\n@@ -0,0 +1 @@\n+SECRET = "test-secret-value"\n'
    assert not [
        f for f in static_findings(diff, [{"path": "tests/test_x.py", "status": "added"}]) if f.category == "security"
    ]
