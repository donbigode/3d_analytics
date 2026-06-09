from backend.core.library.parsers import (
    AUXILIARY_FORMATS,
    PRINTABLE_FORMATS,
    detect_format,
    is_printable,
    parse_meta_for_format,
)


def test_detect_lowercases_extension():
    assert detect_format("Model.STL") == "stl"
    assert detect_format("MyPart.GCODE") == "gcode"


def test_detect_returns_last_extension():
    # Bambu/Orca emit ".gcode.3mf" — the underlying file is a 3MF.
    assert detect_format("part.gcode.3mf") == "3mf"


def test_detect_accepts_alternate_gcode_extensions():
    assert detect_format("part.gco") == "gco"
    assert detect_format("part.g") == "g"
    assert detect_format("part.bgcode") == "bgcode"


def test_detect_accepts_auxiliary_formats():
    for ext in ("pdf", "docx", "txt", "png", "jpg", "csv", "xlsx", "zip"):
        assert detect_format(f"notes.{ext}") == ext, ext


def test_detect_rejects_unknown():
    assert detect_format("evil.exe") is None
    assert detect_format("noext") is None
    assert detect_format("") is None


def test_is_printable_partitions_formats():
    assert all(is_printable(f) for f in PRINTABLE_FORMATS)
    assert not any(is_printable(f) for f in AUXILIARY_FORMATS)


def test_parse_meta_skips_auxiliary():
    # Auxiliary files never trigger parsers; the bytes can be garbage.
    assert parse_meta_for_format(b"\x89PNG\r\n\x1a\n...", "png") == {}
    assert parse_meta_for_format(b"PDF junk", "pdf") == {}


def test_parse_meta_zero_values_for_unparseable_gcode():
    # Unparseable gcode no longer raises — the fuzzy parser yields zeros.
    out = parse_meta_for_format(b"nothing useful here", "gcode")
    assert out.get("time_s") == 0.0
    assert out.get("filament_m") == 0.0
