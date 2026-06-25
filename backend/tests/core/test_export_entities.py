from backend.core.export.entities import EXPORT_ENTITIES, columns_for


def test_people_entities_exported():
    names = {name for name, _m, _ex in EXPORT_ENTITIES}
    assert "people" in names
    assert "quote_people" in names


def test_secrets_excluded_and_users_has_no_hash():
    names = {name for name, _model, _ex in EXPORT_ENTITIES}
    assert "settings" not in names
    assert "export_config" not in names
    assert "quotes" in names and "sales" in names and "users" in names
    users = next(e for e in EXPORT_ENTITIES if e[0] == "users")
    assert "password_hash" not in columns_for(users)
    assert "email" in columns_for(users)
