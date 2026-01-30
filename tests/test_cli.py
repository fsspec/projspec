from projspec.__main__ import main


def test1(capsys):
    main(["projspec"], standalone_mode=False)
    assert "Project" in capsys.readouterr().out

    main(["projspec", "--json-out"], standalone_mode=False)
    assert capsys.readouterr().out.startswith("{")
