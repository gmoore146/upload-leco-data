import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src", "upload-leco-data"))

from main import get_relative_target  # noqa: E402


def test_routing():
    assert get_relative_target("sample_wn123_run.csv") == "WN123"
    assert get_relative_target("G400Plus-01.csv") == os.path.join("G400+", "G400+-01")
    assert get_relative_target("g400+-07.csv") == os.path.join("G400+", "G400+-07")
    assert get_relative_target("G+-42.txt") == os.path.join("G400+", "G400+-42")
    assert get_relative_target("random.csv") is None


if __name__ == "__main__":
    test_routing()
    print("ok")
