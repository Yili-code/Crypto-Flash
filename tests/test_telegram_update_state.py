import pytest

import telegram_update_state as state


def test_update_receipt_round_trip(tmp_path, monkeypatch):
    monkeypatch.setattr(state, "UPDATE_STATE_FILE", tmp_path / "updates.json")
    assert state.load_last_update_id() is None
    state.save_last_update_id(42)
    assert state.load_last_update_id() == 42
    assert not state.UPDATE_STATE_FILE.with_suffix(".json.tmp").exists()


@pytest.mark.parametrize("payload", ["broken", "[]", '{"last_update_id": -1}'])
def test_invalid_update_receipt_fails_closed(tmp_path, monkeypatch, payload):
    monkeypatch.setattr(state, "UPDATE_STATE_FILE", tmp_path / "updates.json")
    state.UPDATE_STATE_FILE.write_text(payload, encoding="utf-8")
    with pytest.raises(state.UpdateStateError):
        state.load_last_update_id()
    assert state.UPDATE_STATE_FILE.read_text(encoding="utf-8") == payload
