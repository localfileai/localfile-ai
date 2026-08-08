from app.extraction.service import select_analysis_text


def test_긴_문서는_앞_중간_뒤를_모두_포함한다():
    text = "HEAD-KEY " + "가" * 4000 + " MIDDLE-KEY " + "나" * 4000 + " TAIL-KEY"
    selected = select_analysis_text(text, 2000)

    assert len(selected) <= 2000
    assert "HEAD-KEY" in selected
    assert "MIDDLE-KEY" in selected
    assert "TAIL-KEY" in selected
    assert "[중간 생략]" in selected


def test_짧은_문서는_그대로_유지한다():
    text = "짧은 문서 전체"
    assert select_analysis_text(text, 2000) == text


def test_아주_작은_상한도_정확히_지킨다():
    assert select_analysis_text("abcdefghij", 1) == "a"
