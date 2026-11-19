

def test_start_fresh_backs_the_journal_up_and_resets_it(tmp_path):
    from memory.long_term import DEFAULTS, LongTermMemory
    path = tmp_path / "progress.json"
    ltm = LongTermMemory(path=str(path))
    ltm.data["milestones"] = ["delivered_oaks_parcel", "beat_brock"]
    ltm.data["badges_earned"] = 1
    ltm.save()
    backup = ltm.start_fresh()
    assert backup is not None and backup.exists() and "delivered_oaks_parcel" in backup.read_text()
    assert ltm.data["milestones"] == DEFAULTS["milestones"] and ltm.data["badges_earned"] == 0
    assert LongTermMemory(path=str(path)).data["milestones"] == DEFAULTS["milestones"]                 # and what is on disk is the blank journal
    assert LongTermMemory(path=str(tmp_path / "none.json")).start_fresh() is None                      # nothing to back up
