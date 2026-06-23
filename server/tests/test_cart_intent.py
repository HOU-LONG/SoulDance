from backend.app import agent as agent_module
from backend.app import cart_intent


def test_agent_reuses_cart_intent_helpers():
    assert agent_module._detect_cart_action is cart_intent._detect_cart_action
    assert agent_module._normalize_cart_action is cart_intent._normalize_cart_action
    assert agent_module._detect_quantity is cart_intent._detect_quantity
    assert agent_module._cart_product_display_name is cart_intent._cart_product_display_name
    assert agent_module._cart_message is cart_intent._cart_message


def test_detect_cart_action_uses_canonical_mappings():
    assert cart_intent._detect_cart_action("我要下单") == "checkout"
    assert cart_intent._detect_cart_action("清空购物车") == "clear_cart"
    assert cart_intent._detect_cart_action("购物车里的全部删掉") == "clear_cart"
    assert cart_intent._detect_cart_action("把它删掉") == "remove"
    assert cart_intent._detect_cart_action("数量改成2") == "update_quantity"
    assert cart_intent._detect_cart_action("加到购物车") == "add_to_cart"


def test_normalize_cart_action_accepts_clear_cart_aliases():
    assert cart_intent._normalize_cart_action("clear") == "clear_cart"
    assert cart_intent._normalize_cart_action("empty_cart") == "clear_cart"


def test_detect_quantity_extracts_numeric_and_chinese_values():
    assert cart_intent._detect_quantity("数量改成2") == 2
    assert cart_intent._detect_quantity("我要两件") == 2
    assert cart_intent._detect_quantity("来一杯咖啡") == 1
    assert cart_intent._detect_quantity("加两杯咖啡") == 2
    assert cart_intent._detect_quantity("买三盒") == 3


def test_detect_quantity_ignores_model_numbers_without_quantity_units():
    assert cart_intent._detect_quantity("将小米17ultra加入购物车") is None
    assert cart_intent._detect_quantity("把OPPO Reno16加入购物车") is None
    assert cart_intent._detect_quantity("iPhone17 Pro加入购物车") is None


def test_cart_message_for_remove_action():
    assert cart_intent._cart_message("remove", "苹果手机") == "已从购物车移除 苹果手机。"


def test_cart_messages_stay_plain_text():
    message = cart_intent._cart_message("add_to_cart", "清爽防晒")

    assert message == "已把 清爽防晒 加入购物车。"
    assert "**" not in message
    assert "\n\n" not in message
