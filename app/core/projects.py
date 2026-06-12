from app.core.database import supabase


def get_project_id(name: str) -> int | None:
    result = supabase.table("projects").select("id").ilike("name", name).limit(1).execute()
    return result.data[0]["id"] if result.data else None


def insert_project(name: str) -> None:
    supabase.table("projects").insert({"name": name}).execute()


def get_projects() -> list:
    result = supabase.table("projects").select("id, name").order("name").execute()
    return result.data


def get_project_summary(name: str) -> dict:
    project_id = get_project_id(name)
    if project_id is None:
        return {"name": name, "total": 0.0, "count": 0}
    result = supabase.table("incomes").select("amount").eq("project_id", project_id).execute()
    total = sum(float(r["amount"]) for r in result.data)
    return {"name": name, "total": total, "count": len(result.data)}
