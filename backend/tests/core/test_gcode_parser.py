from backend.core.gcode.parser import parse_gcode_metadata, GcodeMeta

SAMPLE = """;TIME:1720.57
;Filament used:4.98355m
;Material Type:PLA
;Machine Name:K2 Plus
M104 S210
"""


def test_parse_extracts_known_fields(tmp_path):
    f = tmp_path / "x.gcode"
    f.write_text(SAMPLE)
    meta = parse_gcode_metadata(f)
    assert isinstance(meta, GcodeMeta)
    assert meta.time_s == 1720.57
    assert meta.filament_m == 4.98355
    assert meta.material == "PLA"
    assert meta.machine == "K2 Plus"
