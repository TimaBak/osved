"""Cross-language editorial hook must be grounded in an existing cited fact."""

from app.research.facts import (
    ResearchFact,
    derive_editorial_hook,
    editorial_hook_errors,
)


def test_cloudflare_verified_bots_hook_from_russian_fact() -> None:
    fact = ResearchFact(
        text=(
            "Cloudflare объявила о системе для оценки и информирования об отклонениях "
            "поведения Verified bots от правила не допускать злоупотреблений."
        ),
        kind="release",
        document_ids=[101],
        evidence_quotes=[],
    )
    documents = {101: {"id": 101, "source_class": "primary"}}
    hook = derive_editorial_hook(
        [fact],
        documents,
        event_type="company_event",
        event_headline="Continuous accountability for Verified bots",
    )
    assert hook is not None
    assert hook.hook_fact == fact.text
    assert hook.document_ids == [101]
    assert editorial_hook_errors(
        hook, [fact], documents, event_type="company_event"
    ) == []


def test_unrelated_fact_is_not_promoted_to_editorial_hook() -> None:
    fact = ResearchFact(
        text="Поставщик разработал новую систему управления корпоративными лицензиями.",
        kind="release",
        document_ids=[101],
        evidence_quotes=[],
    )
    hook = derive_editorial_hook(
        [fact],
        {101: {"id": 101, "source_class": "primary"}},
        event_type="company_event",
        event_headline="Continuous accountability for Verified bots",
    )
    assert hook is None
