from backend.core.production.suggestions import failure_event_text


class _Ev:
    def __init__(self, desc, ctx):
        self.failure_description = desc
        self.context = ctx


def test_failure_event_text_composes_material_and_description():
    ev = _Ev("descolou da mesa", [
        {"material_type": "PETG", "color": "Transparente", "manufacturer": "3D Lab",
         "filament_m": 12.5, "time_s": 7200, "is_multi_color": False},
    ])
    text = failure_event_text(ev)
    assert "PETG" in text
    assert "Transparente" in text
    assert "descolou da mesa" in text
