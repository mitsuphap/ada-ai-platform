"""Unit tests for the scraper pipeline. All AI/network calls are mocked."""
import types

import pytest


# ----- query_generator (Gemini mocked) -------------------------------------

class _FakeResp:
    def __init__(self, text):
        self.text = text


class _FakeModel:
    def __init__(self, *args, **kwargs):
        pass

    def generate_content(self, prompt):
        return _FakeResp('["cheap gyms vancouver", "24h fitness vancouver price"]')


def test_generate_queries_parses_json(monkeypatch):
    import query_generator

    monkeypatch.setattr(query_generator.genai, "GenerativeModel", _FakeModel)
    queries = query_generator.generate_queries_with_gemini("cheap gyms in Vancouver", n=2)

    assert queries == ["cheap gyms vancouver", "24h fitness vancouver price"]


def test_generate_queries_falls_back_on_bad_json(monkeypatch):
    import query_generator

    class _BadModel(_FakeModel):
        def generate_content(self, prompt):
            return _FakeResp("not json at all")

    monkeypatch.setattr(query_generator.genai, "GenerativeModel", _BadModel)
    queries = query_generator.generate_queries_with_gemini("find me poetry presses", n=3)

    # Defensive fallback: reuse the user text as a single query.
    assert queries == ["find me poetry presses"]


# ----- llm_scrape_from_seeds pure helpers -----------------------------------

def test_is_valid_phone_accepts_real_rejects_years():
    import llm_scrape_from_seeds as s

    assert s.is_valid_phone("(604) 555-1234") is True
    assert s.is_valid_phone("2012-2014") is False
    assert s.is_valid_phone("2024") is False


def test_is_generic_email():
    import llm_scrape_from_seeds as s

    assert s.is_generic_email("info@example.com") is True
    assert s.is_generic_email("jane.doe@example.com") is False


def test_find_best_email_prefers_person_specific():
    import llm_scrape_from_seeds as s

    candidates = ["info@acme.com", "jdoe@acme.com"]
    assert s.find_best_email_for_person(candidates, "Jane Doe") == "jdoe@acme.com"


def test_normalize_name_strips_titles():
    import llm_scrape_from_seeds as s

    assert s.normalize_name("Dr. Jane Doe") == "jane doe"
    assert s.normalize_name("Jane Doe PhD") == "jane doe"
    assert s.normalize_name("  Prof.  John   Smith ") == "john smith"


def test_merge_records_prefers_person_email_over_generic():
    import llm_scrape_from_seeds as s

    records = [
        {"url": "https://a.com", "llm_payload": {"name": "Jane Doe", "contact_email": "info@a.com"}},
        {"url": "https://b.com", "llm_payload": {"name": "Jane Doe", "contact_email": "jane@a.com"}},
    ]
    merged = s.merge_records(records)
    assert merged["llm_payload"]["contact_email"] == "jane@a.com"


# ----- classify_search_results (Gemini mocked) ------------------------------

def test_classify_batch_parses_pipe_format(monkeypatch):
    import classify_search_results as c

    fake_text = (
        "https://x.com|||highly_relevant|||0.97|||official site\n"
        "https://y.com|||irrelevant|||0.20|||blog post"
    )
    fake_model = types.SimpleNamespace(generate_content=lambda prompt: _FakeResp(fake_text))
    monkeypatch.setattr(c, "model", fake_model)

    batch = [
        {"title": "X", "url": "https://x.com", "snippet": "", "query": "q", "rank": 1},
        {"title": "Y", "url": "https://y.com", "snippet": "", "query": "q", "rank": 2},
    ]
    results = c.classify_batch(batch, c.DOMAIN_DESCRIPTION, c.LABELS, user_request="find official sites")

    by_url = {r["url"]: r for r in results}
    assert by_url["https://x.com"]["label"] == "highly_relevant"
    assert by_url["https://x.com"]["confidence"] == pytest.approx(0.97)
    assert by_url["https://y.com"]["label"] == "irrelevant"
