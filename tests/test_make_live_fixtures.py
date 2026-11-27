"""tools/make_live_fixtures.py (#279): the recipe table and the CLI's no-emulator paths."""
from tools import make_live_fixtures as mk


def test_every_recipe_is_a_function_with_a_description():
    assert set(mk.RECIPES) >= {"threemon", "vermilion", "league_door"}
    assert all(callable(fn) and doc for fn, doc in mk.RECIPES.values())


def test_list_reports_existing_and_missing_fixtures(tmp_path, capsys):
    (tmp_path / "vermilion.ss1").write_bytes(b"x")
    assert mk.main_cli(["--list", "--out", str(tmp_path)]) == 0
    lines = {line.split()[0]: line.split()[1] for line in capsys.readouterr().out.splitlines()}
    assert lines["vermilion"] == "exists" and lines["threemon"] == "missing"


def test_unknown_recipes_and_up_to_date_folders_never_touch_the_emulator(tmp_path, capsys):
    assert mk.main_cli(["--only", "nope", "--out", str(tmp_path)]) == 2
    for name in mk.RECIPES:
        (tmp_path / f"{name}.ss1").write_bytes(b"x")
    assert mk.main_cli(["--out", str(tmp_path)]) == 0 and "nothing to do" in capsys.readouterr().out
