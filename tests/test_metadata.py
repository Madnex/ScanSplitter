import pytest

from scansplitter.metadata import metadata_defaults, normalize_metadata_patch


def test_normalizes_partial_metadata_and_people():
    result = normalize_metadata_patch(
        {"date": "1975-06-01", "date_precision": "season", "people": [" Ada ", "ada", "Bob", ""]}
    )
    assert result["date"] == "1975-06-01"
    assert result["people"] == ["Ada", "Bob"]
    assert result["caption"] is None


def test_partial_update_preserves_values_and_null_clears():
    current = metadata_defaults()
    current.update({"caption": "At the beach", "album": "Roll 4"})
    result = normalize_metadata_patch({"caption": None}, current)
    assert result["caption"] is None
    assert result["album"] == "Roll 4"


@pytest.mark.parametrize(
    "patch",
    [
        {"date": "1975"},
        {"date": "1975-02-30"},
        {"date_precision": "week"},
        {"latitude": 51.2},
        {"latitude": 91, "longitude": 4},
        {"latitude": 51, "longitude": 181},
        {"caption": "x" * 2001},
    ],
)
def test_rejects_invalid_metadata(patch):
    with pytest.raises(ValueError):
        normalize_metadata_patch(patch)
