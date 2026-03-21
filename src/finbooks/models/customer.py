from datetime import date
from enum import Enum

from pydantic import BaseModel, EmailStr, field_validator


class CustomerTier(str, Enum):
    RETAIL = "retail"
    PRIVATE = "private"


class Address(BaseModel):
    street: str
    city: str
    state: str  # 2-letter abbreviation
    zip_code: str
    country: str = "US"

    def __str__(self) -> str:
        return f"{self.street}, {self.city}, {self.state} {self.zip_code}"


class Customer(BaseModel):
    customer_id: str  # UUID string
    first_name: str
    last_name: str
    email: str
    phone: str
    address: Address
    tier: CustomerTier
    date_of_birth: date
    created_at: date

    @property
    def full_name(self) -> str:
        return f"{self.first_name} {self.last_name}"

    @property
    def display_id(self) -> str:
        """Formatted for statements: last 8 chars of UUID."""
        return self.customer_id[-8:].upper()
