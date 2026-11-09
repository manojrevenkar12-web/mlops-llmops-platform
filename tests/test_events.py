import sqlite3

from paved.events import EventLog


def test_a_step_is_recorded_once(tmp_path):
    log = EventLog(tmp_path / "e.sqlite")
    a = log.append("r1", "canary_0", "canary", {"share": 0.05})
    b = log.append("r1", "canary_0", "canary", {"share": 0.99})
    assert a == b and b.payload["share"] == 0.05
    assert len(log.events("r1")) == 1


def test_the_chain_detects_an_edited_history(tmp_path):
    p = tmp_path / "e.sqlite"
    log = EventLog(p)
    for i in range(3):
        log.append("r1", f"s{i}", "gate", {"passed": True})
    assert log.verify()
    db = sqlite3.connect(p)
    db.execute("UPDATE events SET payload='{\"passed\": false}' WHERE step='s1'")
    db.commit()
    assert not EventLog(p).verify()
