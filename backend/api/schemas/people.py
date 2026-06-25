from pydantic import BaseModel


class PersonOut(BaseModel):
    id: str
    name: str
    active: bool
    sort_order: int


class PersonCreate(BaseModel):
    name: str


class PersonUpdate(BaseModel):
    name: str | None = None
    active: bool | None = None
    sort_order: int | None = None
