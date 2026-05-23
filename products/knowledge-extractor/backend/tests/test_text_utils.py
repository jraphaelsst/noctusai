"""text_utils — title sanitizing + code-fence stripping."""
from app.services.text_utils import clean_lesson_title, strip_code_fence


def test_clean_lesson_title_strips_brand_and_timestamp():
    raw = "3 Estruturas validadas - CORE Educação - Google Chrome 2026-05-21 11-54-47"
    assert clean_lesson_title(raw) == "3 Estruturas validadas"


def test_clean_lesson_title_strips_chrome_timestamp_without_brand():
    raw = "1 O que é o Núcleo - Google Chrome 2026-05-21 12-47-23"
    assert clean_lesson_title(raw) == "1 O que é o Núcleo"


def test_clean_lesson_title_leaves_clean_titles_untouched():
    assert clean_lesson_title("3 Os três pilares do método") == "3 Os três pilares do método"


def test_strip_code_fence_removes_wrapping_markdown_fence():
    assert strip_code_fence("```markdown\n# Title\nbody\n```") == "# Title\nbody"
    assert strip_code_fence("# Title\nbody") == "# Title\nbody"
