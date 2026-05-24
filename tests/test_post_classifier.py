from scanner.post_classifier import classify_post, dominant_post_type, post_type_weight


def test_classifies_post_types_with_keyword_rules():
    assert classify_post("Deep dive DD on NVDA valuation") == "DD"
    assert classify_post("Breaking news: company announces approval") == "News"
    assert classify_post("Earnings guidance and EPS discussion") == "Earnings"
    assert classify_post("Buying calls and LEAPS") == "Options"
    assert classify_post("YOLO all in") == "YOLO"
    assert classify_post("Rocket moon meme 🚀") == "Meme"
    assert classify_post("Should I buy TSLA?") == "Question"
    assert classify_post("Regular watchlist update") == "Other"


def test_post_type_weights_and_dominant_type():
    assert post_type_weight("DD") == 1.5
    assert post_type_weight("Question") == 0.3
    assert dominant_post_type(["Meme", "DD", "DD"]) == "DD"
