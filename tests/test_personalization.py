"""Personal interest controls never publish, fetch or buy content."""
from __future__ import annotations

import asyncio
import time
from aiohttp.test_utils import TestClient, TestServer
from pydantic import SecretStr

from app.web.login_codes import issue_login_code
from app.web.personalization import (
    clear_preferences, initialize, material_topic, personalize,
    set_feedback, set_priority, snapshot,
)
from app.web.portal import COOKIE, create_portal
from tests.test_portal import BOT_TOKEN
from tests.test_web_api import fixture


def test_idempotent_feedback_ranking_and_reset(tmp_path):
    _, repo, _ = fixture(tmp_path)
    initialize(repo)
    sample = [
        {"kind":"radar","id":1,"title":"AI agents in enterprise","summary":""},
        {"kind":"radar","id":2,"title":"Новости космоса и ракет","summary":""},
        {"kind":"radar","id":3,"title":"Непонятное событие","summary":""},
    ]
    assert material_topic(sample[0]) == "ai_software"
    assert material_topic(sample[1]) == "space"
    assert material_topic(sample[2]) == "unclassified"
    assert [x["id"] for x in personalize(sample,snapshot(repo))] == [1,2,3]
    set_priority(repo,"space",3)
    ranked=personalize(sample,snapshot(repo))
    assert ranked[0]["id"] == 2
    assert "вручную повысили" in ranked[0]["recommendation"]["reason"]
    set_feedback(repo,"radar",1,"ai_software","more")
    set_feedback(repo,"radar",1,"ai_software","more")
    assert len(snapshot(repo)["feedback"]) == 1
    set_feedback(repo,"radar",1,"ai_software","not_interested")
    assert snapshot(repo)["feedback"][0]["action"] == "not_interested"
    assert personalize(sample,snapshot(repo))[-1]["id"] == 1
    set_feedback(repo,"radar",1,"ai_software","clear")
    assert snapshot(repo)["feedback"] == []
    clear_preferences(repo)
    assert all(x["priority"]==0 for x in snapshot(repo)["topics"])


def test_invalid_topics_and_feedback_rejected(tmp_path):
    _, repo, _ = fixture(tmp_path)
    initialize(repo)
    for topic,priority in (("invalid",3),("space",4),("space",True)):
        try:
            set_priority(repo,topic,priority)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe preference accepted")
    for kind,item,topic,action in (
        ("radar",-1,"space","more"),("evil",1,"space","more"),
        ("radar",1,"anything","more"),("radar",1,"space","hack"),
    ):
        try:
            set_feedback(repo,kind,item,topic,action)
        except ValueError:
            pass
        else:
            raise AssertionError("Unsafe feedback accepted")


def test_owner_only_feedback_and_manual_topic_priority(tmp_path):
    async def scenario():
        settings, repo, delivery = fixture(tmp_path)
        settings.telegram_bot_token=SecretStr(BOT_TOKEN)
        with repo.connection() as db:
            db.execute("UPDATE events SET status='candidate',headline='Открытия в космосе' WHERE id=?",
                       (delivery["event_id"],))
        client=TestClient(TestServer(create_portal(settings,repo)))
        await client.start_server()
        try:
            endpoint="/api/personalization/topic"
            assert (await client.post(endpoint,json={"topic":"space","priority":2})).status==401
            code=issue_login_code(repo,token=BOT_TOKEN,owner_id=123,now=int(time.time()))
            login=await client.post("/api/code-login",json={"code":code})
            assert login.status==200
            csrf=(await login.json())["csrf"]
            cookie={"Cookie":f"{COOKIE}={login.cookies[COOKIE].value}"}
            assert (await client.post(endpoint,json={"topic":"space","priority":2},
                                      headers=cookie)).status==403
            good={**cookie,"X-CSRF-Token":csrf}
            assert (await client.post(endpoint,json={"topic":"space","priority":2},
                                      headers=good)).status==200
            assert (await client.post(endpoint,json={"topic":"fake","priority":2},
                                      headers=good)).status==400
            path="/api/personalization/feedback"
            event=delivery["event_id"]
            action={"kind":"radar","id":event,"action":"follow"}
            assert (await client.post(path,json=action,headers=good)).status==200
            assert (await client.post(path,json={**action,"id":999999},headers=good)).status==404
            response=await client.get("/api/overview",headers=cookie)
            assert response.status==200
            overview=await response.json()
            assert overview["personalization"]["algorithm"]=="heuristic_v1"
            assert overview["personalization"]["feedback_count"]==1
            radar=[x for x in overview["radar"] if x["id"]==event][0]
            assert radar["recommendation"]["topic"]=="space"
            assert radar["recommendation"]["action"]=="follow"
            assert "почему" not in radar["recommendation"]["basis"]
            assert radar["verified"] is False
            assert (await client.post("/api/personalization/reset",
                json={"confirm":False},headers=good)).status==400
            assert (await client.post("/api/personalization/reset",
                json={"confirm":True},headers=good)).status==200
            assert snapshot(repo)["feedback"]==[]
        finally:
            await client.close()
    asyncio.run(scenario())
