from backend.app.realtime_envelope import RealtimeEnvelope


def test_realtime_envelope_adds_ack_and_monotonic_seq():
    envelope = RealtimeEnvelope(session_id="s1", trace_id="trace_test", message_id="m1")

    ack = envelope.ack()
    event = envelope.wrap({"type": "text_delta", "message_id": "m1", "text": "hi"})
    done = envelope.wrap({"type": "done", "message_id": "m1"})

    assert ack["type"] == "ack"
    assert ack["seq"] == 0
    assert event["seq"] == 1
    assert done["seq"] == 2
    assert event["trace_id"] == "trace_test"
    assert event["session_id"] == "s1"
    assert "timestamp" in event
