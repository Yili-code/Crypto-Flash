import json
import struct

import jin10_monitor as jm


def test_pack_and_unpack_str_round_trip():
    buffer = memoryview(jm.pack_str("金十数据") + jm.pack_str("tail"))
    first, offset = jm.unpack_str(buffer, 0)
    second, offset = jm.unpack_str(buffer, offset)
    assert (first, second) == ("金十数据", "tail")
    assert offset == len(buffer)


def test_xor_payload_is_its_own_inverse():
    payload = bytes(range(256))
    key = "12345.67890"
    assert jm.xor_payload(jm.xor_payload(payload, key), key) == payload


def test_xor_payload_passes_empty_input_through():
    assert jm.xor_payload(b"", "key") == b""
    assert jm.xor_payload(b"abc", "") == b"abc"


def test_build_ws_login_round_trips_through_the_cipher():
    key = "111.222"
    decoded = jm.xor_payload(jm.build_ws_login(key, last_id="42"), key)
    assert struct.unpack_from("<h", decoded, 0)[0] == 4002
    assert decoded.endswith(jm.pack_str("42"))


def test_parse_ws_packet_reads_a_json_frame():
    packet = struct.pack("<h", 1000) + jm.pack_str(json.dumps({"id": "1", "action": 1}))
    code, data = jm.parse_ws_packet(packet)
    assert code == 1000
    assert data == {"id": "1", "action": 1}


def test_parse_ws_packet_reverses_a_history_batch():
    # The wire order is newest-first; the parser flips it so pushes go out chronologically.
    payloads = [json.dumps({"id": str(i)}) for i in range(3)]
    packet = (
        struct.pack("<h", 1200)
        + struct.pack("<i", len(payloads))
        + b"".join(jm.pack_str(p) for p in payloads)
    )
    code, data = jm.parse_ws_packet(packet)
    assert code == 1200
    assert [entry["id"] for entry in data] == ["2", "1", "0"]


def test_parse_ws_packet_ignores_unknown_codes():
    assert jm.parse_ws_packet(struct.pack("<h", 9999)) == (9999, None)


def test_ws_connect_kwargs_use_a_header_keyword_the_library_understands():
    import inspect

    import websockets

    kwargs = jm.get_ws_connect_kwargs()
    supported = inspect.signature(websockets.connect).parameters
    header_kw = "additional_headers" if "additional_headers" in supported else "extra_headers"
    assert header_kw in kwargs
    assert "User-Agent" in kwargs[header_kw]
