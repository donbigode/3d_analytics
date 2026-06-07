from pydantic import BaseModel, EmailStr


class ClientCreate(BaseModel):
    name: str
    phone: str | None = None
    email: EmailStr | None = None
    notes: str | None = None


class ClientUpdate(BaseModel):
    name: str | None = None
    phone: str | None = None
    email: EmailStr | None = None
    notes: str | None = None


class ClientOut(BaseModel):
    id: str
    name: str
    phone: str | None
    email: EmailStr | None
    notes: str | None
