"""Public reference data: states and districts (LGD codes) and the reporting languages.

The sign-in page, the landing page and the reporting site read these.
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Response
from pydantic import BaseModel

from raahat.application.voicecall import script
from raahat.config import Settings, get_settings
from raahat.security.jurisdiction import directory

router = APIRouter(tags=["reference"])


class DistrictItem(BaseModel):
    code: str
    name: str


class StateItem(BaseModel):
    code: str
    name: str
    kind: str
    districts: list[DistrictItem]


class Directory(BaseModel):
    source: str
    licence: str
    observed_on: str
    states: list[StateItem]


@router.get("/jurisdictions", response_model=Directory, summary="Every state and union territory with its districts")
def list_jurisdictions(response: Response) -> Directory:
    ref = directory()
    response.headers["Cache-Control"] = "public, max-age=86400"
    return Directory(
        source=ref.source,
        licence=ref.licence,
        observed_on=ref.observed_on,
        states=[
            StateItem(
                code=s.code, name=s.name, kind=s.kind,
                districts=[DistrictItem(code=d.code, name=d.name) for d in s.districts],
            )
            for s in ref.states
        ],
    )


class Language(BaseModel):
    code: str
    name: str
    question: str


class Reporting(BaseModel):
    public_reporting: bool
    default_language: str
    languages: list[Language]


@router.get("/reporting", response_model=Reporting, summary="Whether public reporting is open, and its languages")
def reporting(response: Response, settings: Settings = Depends(get_settings)) -> Reporting:
    response.headers["Cache-Control"] = "public, max-age=300"
    order = ["hi", "en", "bn", "mr", "te", "ta", "gu", "kn", "ml", "pa"]
    return Reporting(
        public_reporting=settings.public_intake_enabled,
        default_language=script.DEFAULT_LANGUAGE,
        languages=[
            Language(code=c, name=script.LANGUAGE_NAMES[c], question=script.line(c, "situation").text)
            for c in order if c in script.SUPPORTED
        ],
    )
