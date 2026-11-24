import faberon


def test_package_importable():
    """The package imports and exposes a version."""
    assert faberon.__version__
