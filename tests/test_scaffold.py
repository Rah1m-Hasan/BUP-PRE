def test_app_module_imports():
    import app.main

    assert hasattr(app.main, "app")
