from backend.app.semantic_layer import rule_semantic_frame
from backend.app.models import ChatRequest


def test_capability_question_is_small_talk():
    for text in ["你能帮我做些什么", "你能做什么", "你是干嘛的", "你有什么功能"]:
        req = ChatRequest(type="user_message", session_id="s1", message=text)
        frame = rule_semantic_frame(req)
        assert frame.intent == "small_talk", text
