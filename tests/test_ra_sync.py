"""tools/ra_sync.py (#358): the read-only comparison of the account's real unlocks with the local evaluation — pure, no network."""
import io
import urllib.error
from pathlib import Path

import pytest

from knowledge.ra_set import ACHIEVEMENTS
from tools import ra_sync

KEY = "SECRETKEY0123456789abcdef"


def _data(earned=(), hardcore=()):
    return {"Achievements": {str(a[0]): {"ID": a[0], "Title": a[1], "DateEarned": "2026-01-01 00:00:00" if a[0] in earned or a[0] in hardcore else None,
                                          "DateEarnedHardcore": "2026-01-01 00:00:00" if a[0] in hardcore else None} for a in ACHIEVEMENTS}}


def test_unlocked_ids_reads_softcore_and_hardcore():
    out = ra_sync.unlocked_ids(_data(earned={34776}, hardcore={541899}))
    assert out == {34776: "softcore", 541899: "hardcore"}
    assert ra_sync.unlocked_ids({}) == {} and ra_sync.unlocked_ids({"Achievements": None}) == {}


def test_compare_sorts_every_achievement_into_one_bucket():
    ids = [a[0] for a in ACHIEVEMENTS]
    states = {i: "no" for i in ids}
    a, b, c, d, e, f = ids[:6]
    states[a], states[b], states[c], states[d] = "yes", "probably", "unknown", "no"
    unlocked = {a: "softcore", b: "softcore", c: "hardcore", d: "softcore", e: "softcore"}       # e: earned, local 'no'; f: yes locally but locked on the account
    states[e], states[f] = "no", "yes"
    diff = ra_sync.compare(unlocked, states)
    assert diff["probably_hit"] == [b] and diff["untracked"] == [c]
    assert sorted(diff["account_only"]) == sorted([d, e]) and diff["local_only"] == [f]
    assert a in diff["agree"]
    assert sum(len(v) for v in diff.values()) == len(ids)                    # nothing counted twice or lost


def test_summary_and_report_without_and_with_a_local_state():
    unlocked = {34776: "hardcore", 541899: "softcore"}
    assert ra_sync.summary(unlocked).startswith("2/128 earned (2/781 pts), 1 in hardcore")
    plain = ra_sync.report(unlocked, None)
    assert plain.startswith("Account: 2/128") and "Still locked (126)" in plain
    states = {a[0]: ("yes" if a[0] == 34776 else "no") for a in ACHIEVEMENTS}
    both = ra_sync.report(unlocked, states)
    assert "Local: 1 yes" in both and "On the account but NOT here" in both and "(1): Now the Adventure Can Start" in both


def test_an_http_failure_is_reported_by_status_alone_never_with_the_url_or_the_key(monkeypatch, capsys):
    def boom(req, timeout=0):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, io.BytesIO(b""))
    monkeypatch.setattr(ra_sync.urllib.request, "urlopen", boom)
    with pytest.raises(SystemExit) as e:
        ra_sync.fetch_progress("someone", KEY, "someone")
    assert str(e.value) == "RetroAchievements answered HTTP 401" and KEY not in str(e.value)
    assert KEY not in capsys.readouterr().out + capsys.readouterr().err

    def offline(req, timeout=0):
        raise urllib.error.URLError("no route to " + req.full_url)               # a URLError's reason can carry the URL: only its type may be shown
    monkeypatch.setattr(ra_sync.urllib.request, "urlopen", offline)
    with pytest.raises(SystemExit) as e2:
        ra_sync.fetch_progress("someone", KEY, "someone")
    assert str(e2.value) == "could not read the progress (URLError)" and KEY not in str(e2.value)


def test_the_request_goes_to_retroachievements_with_the_game_and_target(monkeypatch):
    seen = {}

    def fake(req, timeout=0):
        seen["url"] = req.full_url
        return io.BytesIO(b'{"Achievements": {}}')
    monkeypatch.setattr(ra_sync.urllib.request, "urlopen", fake)
    assert ra_sync.fetch_progress("me", KEY, "them") == {"Achievements": {}}
    assert seen["url"].startswith("https://retroachievements.org/API/API_GetGameInfoAndUserProgress.php?") and "g=788" in seen["url"] and "u=them" in seen["url"]


def test_the_tool_never_writes_the_key_or_the_progress_to_disk():
    src = Path(ra_sync.__file__).read_text()
    import re
    assert not re.search(r"(?<![A-Za-z_.])open\(", src) and "write_text" not in src and "json.dump(" not in src          # urlopen( is the network read; no file is opened or written


def test_consistency_warns_when_the_response_count_and_the_parsed_dates_disagree():
    unlocked = ra_sync.unlocked_ids(_data(earned={34776}))
    assert ra_sync.consistency({"NumAwardedToUser": 1}, unlocked) == ""
    assert ra_sync.consistency({"NumAwardedToUser": 0}, {}) == ""
    warning = ra_sync.consistency({"NumAwardedToUser": 5}, {})
    assert warning.startswith("WARNING") and "5 earned" in warning and "0 were read" in warning
    assert ra_sync.consistency({}, {}) == ""                                   # a response without the field: nothing to compare
