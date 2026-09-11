"""api/routers/templates.py — Templates de workflows préconfigurés."""
from typing import List
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()


class TemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    category: str
    yaml_content: str


_TEMPLATES = [
    TemplateResponse(
        id="csv_to_csv",
        name="CSV → CSV",
        description="Lit un fichier CSV, applique une transformation, écrit un CSV.",
        category="ETL",
        yaml_content="""version: "1.0"
workflow:
  name: csv_to_csv
  trigger:
    type: manual
  steps:
    - name: extract_csv
      type: job
      job: ./jobs/extract
    - name: load_csv
      type: job
      job: ./jobs/load
      depends_on: [extract_csv]
""",
    ),
    TemplateResponse(
        id="api_to_db",
        name="API → Database",
        description="Récupère des données depuis une API REST et les charge en base.",
        category="ETL",
        yaml_content="""version: "1.0"
workflow:
  name: api_to_db
  trigger:
    type: schedule
    cron: "0 8 * * *"
  steps:
    - name: fetch_api
      type: job
      job: ./jobs/fetch
    - name: load_db
      type: job
      job: ./jobs/load
      depends_on: [fetch_api]
    - name: notify
      type: action
      action: webhook
      params:
        url: "{{ env.WEBHOOK_URL }}"
      depends_on: [load_db]
      on_failure: skip
""",
    ),
    TemplateResponse(
        id="parallel_etl",
        name="ETL Parallèle",
        description="Deux extractions en parallèle, merge, puis chargement.",
        category="ETL",
        yaml_content="""version: "1.0"
workflow:
  name: parallel_etl
  trigger:
    type: manual
  steps:
    - name: extract_a
      type: job
      job: ./jobs/extract_a
    - name: extract_b
      type: job
      job: ./jobs/extract_b
    - name: load
      type: job
      job: ./jobs/load
      depends_on: [extract_a, extract_b]
""",
    ),
]


@router.get("", response_model=List[TemplateResponse])
def list_templates():
    """Liste les templates de workflows disponibles."""
    return _TEMPLATES


@router.get("/{template_id}", response_model=TemplateResponse)
def get_template(template_id: str):
    from fastapi import HTTPException
    tpl = next((t for t in _TEMPLATES if t.id == template_id), None)
    if not tpl:
        raise HTTPException(404, detail=f"Template '{template_id}' not found")
    return tpl
