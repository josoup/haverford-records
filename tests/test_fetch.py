from haverford_records.fetch import Fetched


def test_ok_requires_200_and_a_body():
    assert Fetched("u", 200, "<html/>", "abc").ok
    assert not Fetched("u", 200, "", "abc").ok
    assert not Fetched("u", 404, "<html/>", "abc").ok
