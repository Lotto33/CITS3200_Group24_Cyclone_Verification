"""The BoM code lookup tables."""

from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.api.deps import DbSession
from app.models.codes import CodeDomain
from app.schemas.codes import CodeDomainRead

router = APIRouter()


@router.get("", response_model=list[CodeDomainRead])
def list_domains(db: DbSession) -> list[CodeDomainRead]:
    """Every domain with its values, as transcribed from the 2011 spec.

    These are reference data, not constraints: the shipped best-track CSV
    carries codes the spec does not define, so an observation may hold a value
    absent from here. Unknown codes are reported in `ingest_run.stats`.
    """
    rows = db.execute(
        select(CodeDomain)
        .options(selectinload(CodeDomain.values))
        .order_by(CodeDomain.code)
    ).scalars()
    return [CodeDomainRead.model_validate(r) for r in rows]


@router.get("/{domain}", response_model=CodeDomainRead)
def get_domain(db: DbSession, domain: str) -> CodeDomainRead:
    row = db.execute(
        select(CodeDomain)
        .options(selectinload(CodeDomain.values))
        .where(CodeDomain.code == domain)
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(status_code=404, detail=f"no code domain {domain!r}")
    return CodeDomainRead.model_validate(row)
