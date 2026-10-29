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

