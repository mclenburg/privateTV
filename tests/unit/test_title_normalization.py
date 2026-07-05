from pathlib import Path

from privatetv.media.titles import is_dvd_standard_name, normalize_title, title_from_path


def test_normalize_title_replaces_underscores_and_splits_camel_case() -> None:
    assert normalize_title("PipiLangstrumpf_1") == "Pipi Langstrumpf 1"
    assert normalize_title("2_Himmelhunde_auf_dem_Weg_zur_Hoelle") == "2 Himmelhunde auf dem Weg zur Hoelle"
    assert normalize_title("grisu2") == "grisu 2"


def test_title_from_vts_file_uses_first_non_dvd_parent() -> None:
    assert (
        title_from_path(Path("/data/DVDs/PipiLangstrumpf_1/VTS_01_2.VOB"))
        == "Pipi Langstrumpf 1"
    )
    assert (
        title_from_path(Path("/data/DVDs/PipiLangstrumpf_1/VIDEO_TS/VTS_01_2.VOB"))
        == "Pipi Langstrumpf 1"
    )


def test_regular_file_title_still_uses_file_stem() -> None:
    assert (
        title_from_path(Path("/data/Filme/Buddy&Terence/2_Himmelhunde_auf_dem_Weg_zur_Hoelle.mp4"))
        == "2 Himmelhunde auf dem Weg zur Hoelle"
    )


def test_dvd_standard_name_detection() -> None:
    assert is_dvd_standard_name("VIDEO_TS")
    assert is_dvd_standard_name("VTS_01_2.VOB")
    assert not is_dvd_standard_name("PipiLangstrumpf_1")
