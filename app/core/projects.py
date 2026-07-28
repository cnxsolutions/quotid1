from app.core.database import supabase


def get_project_id(name: str) -> int | None:
    result = supabase.table("projects").select("id").ilike("name", name).limit(1).execute()
    return result.data[0]["id"] if result.data else None


def insert_project(name: str) -> None:
    supabase.table("projects").insert({"name": name}).execute()


def get_projects() -> list:
    result = supabase.table("projects").select("id, name").order("name").execute()
    return result.data


def get_projects_with_summary() -> list:
    """Liste des projets avec total/nombre de revenus, en 2 requêtes au lieu de 2N+1."""
    projects = get_projects()
    if not projects:
        return []
    ids = [p["id"] for p in projects]
    incomes = supabase.table("incomes").select("project_id, amount").in_("project_id", ids).execute().data
    totals: dict[int, dict] = {}
    for r in incomes:
        agg = totals.setdefault(r["project_id"], {"total": 0.0, "count": 0})
        agg["total"] += float(r["amount"])
        agg["count"] += 1
    return [
        {
            "name": p["name"],
            "total": totals.get(p["id"], {}).get("total", 0.0),
            "count": totals.get(p["id"], {}).get("count", 0),
        }
        for p in projects
    ]
