from scanner.scoring import recommendation_type


def test_recommendation_type_logic():
    assert recommendation_type(70, 0.2, 3.0, "DD", 0.7, 0.5) == "Possible squeeze"
    assert recommendation_type(70, 0.2, 1.2, "Earnings", 0.4, 0.2) == "Earnings chatter"
    assert recommendation_type(70, 0.2, 1.2, "DD", 0.7, 0.2) == "Momentum setup"
    assert recommendation_type(45, 0.2, 1.2, "Other", 0.2, 0.2) == "Watchlist"
    assert recommendation_type(50, 0.7, 3.0, "Meme", 0.2, 0.2) == "High-risk pump"
    assert recommendation_type(20, 0.2, 0.5, "Question", 0.1, 0.0) == "Avoid / too noisy"
