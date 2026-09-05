"""API 端点封装：与 react-desktop lib/api.ts 一一对应。"""
from __future__ import annotations

from typing import Any, Optional

from .http import http


# ============ Auth ============
def auth_login(email: str, password: str):
    return http.post("/auth/login", {"email": email, "password": password})


def auth_register(email: str, username: str, password: str):
    return http.post("/auth/register", {"email": email, "username": username, "password": password})


def auth_profile():
    return http.get("/auth/profile")


# ============ User ============
def user_me():
    return http.get("/users/me")


def user_update_me(dto: dict):
    return http.patch("/users/me", dto)


def user_settings():
    return http.get("/users/me/settings")


def user_update_settings(dto: dict):
    return http.put("/users/me/settings", dto)


# ============ Vision ============
def vision_list():
    return http.get("/visions")


def vision_create(dto: dict):
    return http.post("/visions", dto)


def vision_update(vid: str, dto: dict):
    return http.patch(f"/visions/{vid}", dto)


def vision_achieve(vid: str):
    return http.post(f"/visions/{vid}/achieve")


def vision_reset(vid: str):
    return http.post(f"/visions/{vid}/reset-status")


def vision_delete(vid: str):
    return http.delete(f"/visions/{vid}")


# ============ GoalGroup ============
def goal_group_tree(include_objectives: bool = False):
    return http.get("/goal-groups", params={"includeObjectives": include_objectives})


def goal_group_create(dto: dict):
    return http.post("/goal-groups", dto)


def goal_group_update(gid: str, dto: dict):
    return http.patch(f"/goal-groups/{gid}", dto)


def goal_group_delete(gid: str):
    return http.delete(f"/goal-groups/{gid}")


def goal_group_reorder(ids: list):
    return http.post("/goal-groups/reorder", {"ids": ids})


# ============ Objective ============
def objective_list(goal_group_id: Optional[str] = None, status: Optional[str] = None,
                   page: int = 1, page_size: int = 100):
    params: dict[str, Any] = {"page": page, "pageSize": page_size}
    if goal_group_id:
        params["goalGroupId"] = goal_group_id
    if status:
        params["status"] = status
    return http.get("/objectives", params=params)


def objective_get(oid: str):
    return http.get(f"/objectives/{oid}")


def objective_create(dto: dict):
    return http.post("/objectives", dto)


def objective_update(oid: str, dto: dict):
    return http.patch(f"/objectives/{oid}", dto)


def objective_delete(oid: str):
    return http.delete(f"/objectives/{oid}")


# ============ KeyResult ============
def kr_list_by_objective(oid: str):
    return http.get(f"/key-results/by-objective/{oid}")


def kr_create(dto: dict):
    return http.post("/key-results", dto)


def kr_update(kid: str, dto: dict):
    return http.patch(f"/key-results/{kid}", dto)


def kr_delete(kid: str):
    return http.delete(f"/key-results/{kid}")


# ============ Record ============
def record_trend(kid: str):
    return http.get(f"/records/trend/{kid}")


def record_create(dto: dict):
    return http.post("/records", dto)


def record_update(rid: str, dto: dict):
    return http.patch(f"/records/{rid}", dto)


def record_delete(rid: str):
    return http.delete(f"/records/{rid}")


# ============ Memo ============
def memo_list(owner_type: str, owner_id: str):
    return http.get("/memos", params={"ownerType": owner_type, "ownerId": owner_id})


def memo_create(dto: dict):
    return http.post("/memos", dto)


def memo_delete(mid: str):
    return http.delete(f"/memos/{mid}")


# ============ Task ============
def task_list(status: Optional[str] = None, date: Optional[str] = None):
    params: dict[str, Any] = {}
    if status:
        params["status"] = status
    if date:
        params["date"] = date
    return http.get("/tasks", params=params or None)


def task_create(dto: dict):
    return http.post("/tasks", dto)


def task_update(tid: str, dto: dict):
    return http.patch(f"/tasks/{tid}", dto)


def task_complete(tid: str, completed: bool):
    return http.post(f"/tasks/{tid}/complete", {"completed": completed})


def task_delete(tid: str):
    return http.delete(f"/tasks/{tid}")


def task_delete_overdue():
    return http.post("/tasks/delete-overdue")


def task_batch_delete(ids: list):
    return http.post("/tasks/batch-delete", {"ids": ids})


# ============ FocusCycle ============
def cycle_active():
    return http.get("/focus-cycles/active")


def cycle_create(dto: dict):
    return http.post("/focus-cycles", dto)


def cycle_update(cid: str, dto: dict):
    return http.patch(f"/focus-cycles/{cid}", dto)


def cycle_update_weight(cid: str, oid: str, weight: int):
    return http.patch(f"/focus-cycles/{cid}/objectives/{oid}/weight", {"weight": weight})


def cycle_end(cid: str):
    return http.post(f"/focus-cycles/{cid}/end")


# ============ Review ============
def review_list(type_: Optional[str] = None):
    return http.get("/reviews", params={"type": type_} if type_ else None)


def review_list_by_objective(oid: str):
    return http.get(f"/reviews/by-objective/{oid}")


def review_create(dto: dict):
    return http.post("/reviews", dto)


def review_update(rid: str, dto: dict):
    return http.patch(f"/reviews/{rid}", dto)


def review_delete(rid: str):
    return http.delete(f"/reviews/{rid}")


# ============ Summary / Gantt ============
def summary_get():
    return http.get("/summary")


def gantt_get(scope: Optional[str] = None, goal_group_id: Optional[str] = None):
    params: dict[str, Any] = {}
    if scope:
        params["scope"] = scope
    if goal_group_id:
        params["goalGroupId"] = goal_group_id
    return http.get("/gantt", params=params or None)


# ============ Data ============
def data_export():
    return http.get_raw("/data/export")


def data_import(payload: dict, conflict: str = "skip"):
    return http.post("/data/import", payload, params={"conflict": conflict})


# ============ Feedback ============
def feedback_create(dto: dict):
    return http.post("/feedback", dto)


# ============ AI ============
def ai_plan_goal(dto: dict):
    return http.post("/ai/plan-goal", dto)


def ai_plan_tasks(dto: dict):
    return http.post("/ai/plan-tasks", dto)


def ai_suggest_score(objective_id: str):
    return http.post("/ai/suggest-score", {"objectiveId": objective_id})


def ai_suggest_motivations(dto: dict):
    return http.post("/ai/suggest-motivations", dto)


def ai_weekly_report():
    return http.post("/ai/weekly-report")


def ai_conversations():
    return http.get("/ai/conversations")


def ai_usage():
    return http.get("/ai/usage")


# ============ Check-in ============
def checkin_status():
    return http.get("/checkins/status")


def checkin_upsert_this_week(note: Optional[str] = None):
    return http.put("/checkins/this-week", {"note": note, "tzOffsetMin": 480})


def checkin_history():
    return http.get("/checkins/history")


# ============ Notification ============
def notification_list():
    return http.get("/notifications")


def notification_mark_read(nid: str):
    return http.post(f"/notifications/{nid}/read")


def notification_mark_all_read():
    return http.post("/notifications/read-all")


def notification_delete(nid: str):
    return http.delete(f"/notifications/{nid}")


# ============ Recycle ============
def recycle_list():
    return http.get("/recycle")


def recycle_restore(entity_type: str, eid: str):
    return http.post("/recycle/restore", {"entityType": entity_type, "id": eid})


def recycle_destroy(entity_type: str, eid: str):
    return http.post("/recycle/destroy", {"entityType": entity_type, "id": eid})


def recycle_empty():
    return http.delete("/recycle/empty")
