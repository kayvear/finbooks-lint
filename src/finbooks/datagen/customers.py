from __future__ import annotations

import uuid
from datetime import date

import pandas as pd
from faker import Faker

from finbooks.models.customer import Address, Customer, CustomerTier
from finbooks.settings import settings

# 90% retail, 10% private
_TIER_WEIGHTS = [0.90, 0.10]
_TIERS = [CustomerTier.RETAIL, CustomerTier.PRIVATE]


class CustomerGenerator:
    """Generates synthetic customers using Faker with a fixed seed."""

    def __init__(self) -> None:
        self._fake = Faker("en_US")
        Faker.seed(settings.random_seed)

    def generate(self, n: int | None = None) -> list[Customer]:
        count = n or settings.num_customers
        customers: list[Customer] = []

        import random
        rng = random.Random(settings.random_seed)

        for i in range(count):
            tier = rng.choices(_TIERS, weights=_TIER_WEIGHTS, k=1)[0]
            cid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"finbooks-customer-{i}"))

            # Deterministic DOB: ages 25–75
            birth_year = 1950 + (i * 7 % 50)
            birth_month = (i % 12) + 1
            birth_day = (i % 28) + 1
            dob = date(birth_year, birth_month, birth_day)

            # Deterministic opened date: 2015–2023
            opened_year = 2015 + (i % 9)
            opened = date(opened_year, (i % 12) + 1, (i % 28) + 1)

            customers.append(Customer(
                customer_id=cid,
                first_name=self._fake.first_name(),
                last_name=self._fake.last_name(),
                email=self._fake.email(),
                phone=self._fake.phone_number(),
                address=Address(
                    street=self._fake.street_address(),
                    city=self._fake.city(),
                    state=self._fake.state_abbr(),
                    zip_code=self._fake.zipcode(),
                ),
                tier=tier,
                date_of_birth=dob,
                created_at=opened,
            ))

        return customers

    def to_dataframe(self, customers: list[Customer]) -> pd.DataFrame:
        records = []
        for c in customers:
            records.append({
                "customer_id": c.customer_id,
                "first_name": c.first_name,
                "last_name": c.last_name,
                "email": c.email,
                "phone": c.phone,
                "street": c.address.street,
                "city": c.address.city,
                "state": c.address.state,
                "zip_code": c.address.zip_code,
                "tier": c.tier.value,
                "date_of_birth": c.date_of_birth,
                "created_at": c.created_at,
            })
        return pd.DataFrame(records)
