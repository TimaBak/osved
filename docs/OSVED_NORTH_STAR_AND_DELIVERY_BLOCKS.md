# ОСВЕД — North Star, продуктовая архитектура и поставка блоками

Статус: целевой договор продукта и критерии приёмки; не утверждение, что все пункты уже работают.
Дата: 2026-10-23. Актуальные код, production-логи, CI/CD всегда важнее старых handoff.

## 1. Северная звезда

**ОСВЕД — персональная информационно-аналитическая система, которая наблюдает за указанными пользователем источниками, выявляет значимые изменения, устанавливает факты, объясняет их на русском и сохраняет результат как накопленное знание.**

Не социальная лента, не пересказ каждого сообщения и не чат вместо навигации. Первая законченная продуктовая вертикаль — **OSVED News V1**, далее исследовательский интеллект, персональная память и медиалаб.

Главный пользовательский сценарий: подписался на канал / сайт / репозиторий → видит когда он проверен → видит поступившие сигналы → получает значимые подтверждённые новости в чистом читателе → может проверить источники → читает, сохраняет, настраивает интересы; Telegram служит доставкой того же объекта.

## 2. Канонический поток и объекты

```
Authorized account / Source registry
   -> collector run (status, cursor, latency, errors)
   -> immutable source item (URL, source, timestamps, source identity)
   -> normalized signal + dedup (reason, linked item ids)
   -> candidate event (why selected / why rejected / relevant to whom)
   -> bounded research (primary sources, independent evidence where possible)
   -> verified fact sheet (cited claims, caveats, no conjecture)
   -> editorial article (schema-based sections, source references, revision)
   -> shared publication (web card/reader, Telegram, saved, read and feedback)
   -> quality metrics and cost ledger
```

Source item ≠ signal ≠ candidate event ≠ verified news ≠ full research.
A new Telegram message MUST be discoverable as a source item or provide a specific collection failure reason, not be silently treated as a news article.
Deduplication must never silently delete original provenance.
Source states: never_checked / success_with_items / success_without_items / partial / failed / paused. Distinguish check time, last new item time, source's published time and ingestion time.
Each item/event must have traceable disposition: discovered, duplicate (linked event), ignored (reason), candidate, investigating, needs_evidence, published. Don't invent evidence to fill an empty feed.

## 3. Editorial contract

All articles share a stable, validated structure independent of HTML:
- identity/title, category, date, editorial status, source IDs;
- **Главное**: concise factual lead distinct from headline;
- **Что произошло**: event facts in small readable paragraphs;
- **Ключевые детали**: optional titled sections, each with supporting fact IDs;
- **Почему важно**: explicitly labeled grounded interpretation only if supported;
- **Что неизвестно / ограничения**: optional, accurately stated uncertainty;
- **Источники**: explicit original links and attribution.

No fake section headings or ungrounded implications. Store a structured schema and render two presentations: concise feed/Telegram and full web reader. Don't infer factual sections by brittle CSS or split citations indiscriminately. Cache model output, validate provenance, budget, and allow manual regenerate within limits.

## 4. User-facing information architecture

1. **Обзор** — concise personalized digest, service freshness, urgent items.
2. **Моя лента** — published and verified articles, read/save/hide/interests.
3. **Радар** — signals/candidates and visible dispositions, not conflated with verified news.
4. **Источники** — source/channel registry, per-source latest checked, latest item, error and manual bounded check; bulk import.
5. **Исследования** — event dossier, chronology, related sources and citations.
6. **Библиотека** — saved items, notes, history, topics, collections.
7. **Медиалаб** — transcripts and summaries from permitted media.
8. **Настройки** — model assignment per job, budgets, integrations/account authorizations, schedule and notifications.

Same backend SQLite/auth and semantics across site, Mini App and bot. The UI must be beautiful, responsive, accessible and information-dense, but visuals cannot substitute for true states.

## 5. Prioritized shipping blocks

| Block | User outcome | Implementation scope | Acceptance gate |
|---|---|---|---|
| B0 Baseline and trust | Production works and user can read one real article | CI/deploy/browser, own login, provenance | Exact SHA, successful real news card and delivery, protected data |
| **B1 Fresh collection + source transparency** | Every followed source has honest freshness and new messages become traceable signals | schedule/cursors, source run receipts, collection diagnosis, dedup decisions, source visibility | Three successive controlled collection cycles; sample Telegram channel including «Не баг, а фича» reconciled against seen IDs with no silent missing items; errors visible |
| B2 Signal → event filtering | Radar has useful signal, not duplicates and routine noise | normalization, scoring, subject clustering, explainable rejection | Fixture and real sampling demonstrate provenance, dedup and categorization; manual override possible |
| B3 Verified editorial publication | Articles worth reading, genuinely structured | fact sheets, primary evidence, semantic article schema, paid bounded generation, Russian QA | Three different verified events published end-to-end; user checks readable headings, true source citations and Telegram parity |
| B4 Reliable news cadence | Predictable digest rather than a one-time pilot | throttled scheduler, budgets, idempotent delivery, dashboard health, kill switch | Three consecutive monitored live cycles with no duplicate delivery, overcharge or silent failure |
| B5 Personal intelligence | OSVED improves relevance from explicit feedback | topics/entities, mute/track, why recommended, note/read/save | Same interest and reading state across web/Telegram and verifiable preference explanations |
| B6 Deep intelligence | Long-lived understanding instead of article stream | event histories, timeline, company dossiers, source comparisons, research notebook | Answer can reproduce links and dated changes with provenance |
| B7 Media and artifacts | Transform approved media into useful outputs | transcription/subtitle support, bilingual summary, PDF, media assets | Real permitted sample with timestamps and rights checks |

**Work sequentially B1→B2→B3→B4 before expanding B5–B7.** B0's first real card was confirmed, but one successful pilot does not satisfy regular publication. UX bugs inside current block may be corrected without redefining the roadmap.

## 6. Honest current baseline

- One production pilot generated **one valid fact sheet, one dossier, one card, one sent Telegram delivery**; this proves a vertical slice, not continuous news service.
- A first candidate was rejected after research because its editorial hook lacked sufficient support; this rejection is an important quality safeguard.
- Past production diagnostics found 47 source items and 26 candidate events. These are snapshot counts and must not be used as current statistics.
- Scheduling was disabled on the most recently proven publication-readiness diagnostic. Don't imply automatic collection or daily publishing is enabled.
- Source collection was visibly uneven across platforms; root cause of missing recent posts, including «Не баг, а фича», is **not yet proven**.
- Reader CSS/layout and first source/status UI exist, but the separate semantic AI article schema is NOT implemented by merely adding section headings.
- A cancelled public Chromium smoke is not a passing visual regression test; separately confirm each new behavior when deployed.

## 7. Engineering quality gates

Each block moves through **contract → fixture/test → bounded real run → CI → reviewed PR → exact SHA deploy → read-only live diagnostics → desktop/mobile browser acceptance**. Collect per-step evidence in the PR or handoff. No silent paid model fallbacks or uncontrolled retries, no fake content, no weakening evidence validators, no SSH security bypass. Codex Sale is preferred; OpenRouter only explicitly permitted. Provider usage with unknown pricing must never be mislabeled as zero cost. Scheduler auto-enablement only after B1–B4 release gates.

## 8. Next immediate delivery: B1

- Audit collector scheduler disabled-state versus explicit manual collection, source registry, Telegram source cursors and recent run receipts.
- Instrument and expose transparent states: last check, last item, run outcome, item count, reason item did not become event.
- Inspect «Не баг, а фича» by its real registered identifier and real collection logs (don't infer an outcome from a channel name).
- Add targeted tests for stale sources, empty-but-successful checks, new post → item → signal, duplicate grouping and error messaging.
- Test one bounded live collection on Hermes through an approved operational path, then confirm UI truth. Don't claim success based on fixture content alone.

## 9. Product governance

At most one main product block in active development. Record: goal, customer observable demo, metric, blocker, exact PR/SHA, operational evidence and next action. Distinguish **implemented**, **CI passed**, **deployed**, **live tested** and **user accepted**. Never call an intermediate gate «fully done».
