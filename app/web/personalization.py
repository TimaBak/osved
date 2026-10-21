"""Deterministic and explainable owner-only preference engine for OSVED V1.

Preferences influence *ordering*, never source truth, verification status or
automatic publication. No external AI calls; signals are not called news.
Feedback is idempotent per material: flipping a choice replaces the prior one.
"""
from __future__ import annotations

from app.db.repository import Repository, utc_now
from app.web.folders import infer_reading_folder
from app.web.store import FOLDERS

TOPICS = {key: title for key, title in FOLDERS.items() if key != "all"}
ACTIONS = {
    "more": 2,
    "less": -2,
    "not_interested": -3,
    "already_known": -1,
    "deeper": 1,
    "follow": 3,
}
KINDS = {"news", "video", "radar"}


def initialize(repository: Repository) -> None:
    with repository.connection() as db:
        db.execute(
            """CREATE TABLE IF NOT EXISTS personal_topic_priorities (
                topic TEXT PRIMARY KEY, priority INTEGER NOT NULL,
                updated_at TEXT NOT NULL
            )"""
        )
        db.execute(
            """CREATE TABLE IF NOT EXISTS personal_content_feedback (
                kind TEXT NOT NULL, item_id INTEGER NOT NULL, topic TEXT NOT NULL,
                action TEXT NOT NULL, updated_at TEXT NOT NULL,
                PRIMARY KEY(kind,item_id)
            )"""
        )


def _valid_topic(topic: str) -> bool:
    return isinstance(topic, str) and topic in TOPICS


def set_priority(repository: Repository, topic: str, priority: int) -> None:
    if not _valid_topic(topic) or type(priority) is not int or not -3 <= priority <= 3:
        raise ValueError("invalid_topic_priority")
    with repository.connection() as db:
        if priority == 0:
            db.execute("DELETE FROM personal_topic_priorities WHERE topic=?", (topic,))
        else:
            db.execute(
                """INSERT INTO personal_topic_priorities(topic,priority,updated_at)
                   VALUES(?,?,?) ON CONFLICT(topic) DO UPDATE SET
                   priority=excluded.priority,updated_at=excluded.updated_at""",
                (topic, priority, utc_now()),
            )


def set_feedback(
    repository: Repository, kind: str, item_id: int, topic: str, action: str
) -> None:
    if (kind not in KINDS or type(item_id) is not int or item_id <= 0
            or not _valid_topic(topic)
            or action not in {*ACTIONS, "clear"}):
        raise ValueError("invalid_feedback")
    with repository.connection() as db:
        if action == "clear":
            db.execute(
                "DELETE FROM personal_content_feedback WHERE kind=? AND item_id=?",
                (kind, item_id),
            )
        else:
            db.execute(
                """INSERT INTO personal_content_feedback(kind,item_id,topic,action,updated_at)
                   VALUES(?,?,?,?,?) ON CONFLICT(kind,item_id) DO UPDATE SET
                   topic=excluded.topic,action=excluded.action,
                   updated_at=excluded.updated_at""",
                (kind, item_id, topic, action, utc_now()),
            )


def clear_preferences(repository: Repository) -> None:
    with repository.connection() as db:
        db.execute("DELETE FROM personal_content_feedback")
        db.execute("DELETE FROM personal_topic_priorities")


def snapshot(repository: Repository) -> dict:
    with repository.connection() as db:
        priorities = {
            row["topic"]: row["priority"]
            for row in db.execute(
                "SELECT topic,priority FROM personal_topic_priorities"
            ).fetchall()
            if row["topic"] in TOPICS
        }
        feedback = [
            dict(row) for row in db.execute(
                "SELECT kind,item_id,topic,action FROM personal_content_feedback"
            ).fetchall()
        ]
    return {
        "topics": [
            {"id": topic, "title": title, "priority": priorities.get(topic, 0)}
            for topic, title in TOPICS.items()
        ],
        "feedback": feedback,
    }


def material_topic(item: dict) -> str:
    folder = item.get("folder")
    if isinstance(folder, str) and folder in TOPICS:
        return folder
    inferred = infer_reading_folder({
        "headline": item.get("title") or "",
        "summary": item.get("summary") or "",
    })
    return inferred if inferred in TOPICS else "unclassified"


def personalize(items: list[dict], preferences: dict) -> list[dict]:
    """Give each item a transparent recommendation; return sorted copy.

    Original order is the stable tie-breaker, preserving prior recent-first
    ordering. Scores are heuristic ranks, not probabilities/LLM judgements.
    """
    weights = {entry["id"]: entry["priority"] for entry in preferences["topics"]}
    actions = {(r["kind"], r["item_id"]): r for r in preferences["feedback"]}
    topic_signal: dict[str, int] = {}
    for row in preferences["feedback"]:
        topic = row["topic"]
        topic_signal[topic] = topic_signal.get(topic, 0) + ACTIONS.get(row["action"], 0)
    # 5 votes already saturate one topic. Repeating endless reactions must
    # not drown out a deliberate manual priority or all unrelated topics.
    output = []
    for item in items:
        entry = dict(item)
        topic = material_topic(entry)
        manual = weights.get(topic, 0)
        learned = max(-6, min(6, topic_signal.get(topic, 0)))
        own_action = actions.get((entry.get("kind"), entry.get("id")), {}).get("action")
        own = ACTIONS.get(own_action, 0)
        score = manual * 10 + learned * 3 + own * 5
        explanation = []
        if manual:
            explanation.append(
                ("Вы вручную повысили приоритет" if manual > 0
                 else "Вы вручную снизили приоритет")+" темы «"+TOPICS[topic]+"»"
            )
        if learned:
            explanation.append(
                "Вы чаще выбирали похожие материалы" if learned > 0
                else "Вы реже выбирали похожие материалы"
            )
        if own_action:
            explanation.append("Ваша оценка именно этой публикации учтена")
        if not explanation:
            explanation.append("Свежий материал из подключённых источников; предпочтений пока нет")
        entry["recommendation"] = {
            "topic": topic,
            "topic_title": TOPICS[topic],
            "score": score,
            "reason": ". ".join(explanation)+".",
            "action": own_action,
            "basis": "heuristic_v1",
        }
        output.append(entry)
    return sorted(output, key=lambda value: value["recommendation"]["score"], reverse=True)
