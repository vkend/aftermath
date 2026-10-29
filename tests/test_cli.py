import re

import pytest

from aftermath import main


def test_version(capsys):
    with pytest.raises(SystemExit) as exit_info:
        main(["--version"])
    assert exit_info.value.code == 0
    assert capsys.readouterr().out.startswith("aftermath 0.1.0")


def test_no_arguments_prints_help(capsys):
    main([])
    assert "usage: aftermath" in capsys.readouterr().out


def test_door_reports_distance_band_advice_and_limits(tmp_path, capsys, monkeypatch):
    from test_door import FakeSam, door_photo

    photo, mask = door_photo(tmp_path / "IMG_0001.jpg", 14)
    monkeypatch.setattr("aftermath.segment.LocalSam31", lambda cache: FakeSam(mask))
    main(["door", str(photo), "--truth-ft", "14", "--language", "es", "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert "IMG_0001.jpg: 14.0 ft, range 13.2–14.9 ft: too close" in out
    assert re.search(r"Tape 14 ft: [+-]0\.\d%", out)
    assert "Está demasiado cerca" in out and "1 of 1 within ±10% of the tape: PASS" in out
    assert "dentro de un 6%" in out and "¿Es una puerta normal" in out
    assert (tmp_path / "out" / "IMG_0001-door.jpg").exists()


def test_door_speaks_hindi_too(tmp_path, capsys, monkeypatch):
    from test_door import FakeSam, door_photo

    photo, mask = door_photo(tmp_path / "IMG_0002.jpg", 26)
    monkeypatch.setattr("aftermath.segment.LocalSam31", lambda cache: FakeSam(mask))
    main(["door", str(photo), "--language", "hi", "--out", str(tmp_path / "out")])
    out = capsys.readouterr().out
    assert "सीडीसी की सलाह के मुताबिक" in out and "क्या यह आम दरवाज़ा है" in out
