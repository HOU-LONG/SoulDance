from backend.app.models import DisplayMessage, DisplayMessageProduct, SessionContext


def test_display_message_defaults():
    msg = DisplayMessage(role="user", text="hello")
    assert msg.role == "user"
    assert msg.text == "hello"
    assert msg.products == []
    assert msg.quick_actions == []


def test_session_context_has_display_messages():
    ctx = SessionContext(session_id="s1")
    assert ctx.display_messages == []
    assert ctx.schema_version == 3


def test_session_context_round_trip_json():
    ctx = SessionContext(session_id="s1")
    ctx.display_messages.append(
        DisplayMessage(
            role="assistant",
            text="hi",
            products=[DisplayMessageProduct(product_id="p1", name="Phone", price=2999.0)],
        )
    )
    data = ctx.model_dump_json()
    loaded = SessionContext.model_validate_json(data)
    assert loaded.display_messages[0].role == "assistant"
    assert loaded.display_messages[0].products[0].product_id == "p1"
