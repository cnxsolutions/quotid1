import json
from groq import Groq
from app.core.config import GROQ_API_KEY

_client = Groq(api_key=GROQ_API_KEY)

_SYSTEM = """Tu es un parser d'intentions pour un assistant personnel.
Analyse le message et retourne uniquement un objet JSON valide parmi ces formes :
- {"type":"expense","amount":<float>,"description":"<str>","account":"<str>|null","category":"<str>|null"}
- {"type":"income","amount":<float>,"description":"<str>","account":"<str>|null","category":"<str>|null","project":"<str>|null"}
- {"type":"task","description":"<str>"}
- {"type":"tasks_list"}
- {"type":"task_done","id":<int>}
- {"type":"cash"}
- {"type":"unknown"}

Règles :
- Montant + contexte achat/dépense = expense
- Revenu, salaire, mission, virement reçu = income
- Action à faire = task
- "mes tâches", "todo", "aujourd'hui" = tasks_list
- "fait le X", "terminé X", "done X" = task_done
- "solde", "tréso", "cash", "compte" = cash
- Si le message contient "compte:xxx", mettre "account":"xxx" (en minuscules), sinon null
- Si le message contient "cat:xxx", mettre "category":"xxx" parmi [Food,Transport,Logement,Business,Abonnement,Loisir,Santé,Autre], sinon null
- Si le message contient "projet:xxx", mettre "project":"xxx" (en majuscules), sinon null
Retourne uniquement le JSON brut, sans markdown, sans explication."""


def interpret(text: str) -> dict:
    from app.core.utils import normalize_category
    response = _client.chat.completions.create(
        model="llama-3.1-8b-instant",
        max_tokens=128,
        messages=[
            {"role": "system", "content": _SYSTEM},
            {"role": "user", "content": text},
        ],
    )
    raw = response.choices[0].message.content.strip()
    result = json.loads(raw)
    if "category" in result and result["category"]:
        result["category"] = normalize_category(result["category"])
    return result
