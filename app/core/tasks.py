from app.core.database import supabase


def insert_task(description: str, due_date=None, project_id: int | None = None) -> None:
    row = {"description": description, "done": False}
    if due_date is not None:
        row["due_date"] = due_date.isoformat()
    if project_id is not None:
        row["project_id"] = project_id
    supabase.table("tasks").insert(row).execute()


def get_pending_tasks() -> list:
    result = (
        supabase.table("tasks")
        .select("id, description, due_date, project_id, projects(name)")
        .eq("done", False)
        .order("due_date", nullsfirst=False)
        .order("id")
        .execute()
    )
    tasks = []
    for r in result.data:
        project_name = None
        if r.get("projects"):
            project_name = r["projects"]["name"]
        tasks.append({
            "id": r["id"],
            "description": r["description"],
            "due_date": r["due_date"],
            "project_name": project_name,
        })
    return tasks


def get_tasks_due_tomorrow() -> list:
    return get_tasks_due_in_days(1)


def get_tasks_due_in_days(days: int) -> list:
    from datetime import date, timedelta
    target = (date.today() + timedelta(days=days)).isoformat()
    result = (
        supabase.table("tasks")
        .select("id, description, due_date, projects(name)")
        .eq("done", False)
        .eq("due_date", target)
        .execute()
    )
    tasks = []
    for r in result.data:
        project_name = r["projects"]["name"] if r.get("projects") else None
        tasks.append({"id": r["id"], "description": r["description"], "due_date": r["due_date"], "project_name": project_name})
    return tasks


def mark_done(task_id: int) -> bool:
    result = supabase.table("tasks").update({"done": True}).eq("id", task_id).eq("done", False).execute()
    return len(result.data) > 0
