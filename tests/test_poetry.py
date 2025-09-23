def test_legacy(proj):
    assert "poetry" in proj
    envs = proj.poetry.contents.environment
    assert envs["deep"].packages == ["unknown *"]
