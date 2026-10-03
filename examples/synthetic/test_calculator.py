from calculator import add


def test_add_handles_negative_and_zero():
    assert add(-2, 2) == 0
    assert add(0, 7) == 7
