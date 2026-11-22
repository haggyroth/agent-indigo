"""RunLog directories: parallel runs must not share one."""
import json

from memory.run_log import RunLog


def test_two_runs_started_in_the_same_second_get_their_own_directories(tmp_path):
    a = RunLog(tmp_path, stamp="20261121-221209")
    b = RunLog(tmp_path, stamp="20261121-221209")
    c = RunLog(tmp_path, stamp="20261121-221209")
    assert len({a.dir, b.dir, c.dir}) == 3
    assert a.dir.name == "20261121-221209" and b.dir.name.endswith("-2") and c.dir.name.endswith("-3")
    a.event("tick", n=1)
    b.event("tick", n=2)
    for log in (a, b, c):
        log.close()
    assert [json.loads(line)["n"] for line in (a.dir / "run.jsonl").read_text().splitlines()] == [1]
    assert [json.loads(line)["n"] for line in (b.dir / "run.jsonl").read_text().splitlines()] == [2]
