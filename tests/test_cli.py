from projspec.__main__ import main


def test1(preserve_argv, capsys):
    main(["projspec"], standalone_mode=False)
    assert "Project" in capsys.readouterr().out
