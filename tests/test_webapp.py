import projspec


def test_webapp_kwargs(tmpdir):
    proj = projspec.Project(str(tmpdir))
    proj2 = proj.create("flask")
    art = proj2.flask.artifacts["server"]["flask-app"]
    art.make()
    # defaults for flask
    assert art._port == 5000
    assert art._address == "127.0.0.1"
    art.clean()

    art.make(port=9999, address="0.0.0.0")
    assert art._port == 9999
    assert art._address == "0.0.0.0"
