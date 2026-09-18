"""Pydantic request models for POST /optimize-energy."""

from pydantic import BaseModel, Field, ConfigDict, field_validator, model_validator
from typing import List


class HourEntry(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hour: int = Field(ge=0, le=23)
    demand_kwh: float = Field(ge=0)
    solar_kwh: float = Field(ge=0)
    tariff_bdt_per_kwh: float = Field(ge=0)


class Battery(BaseModel):
    model_config = ConfigDict(extra="forbid")
    capacity_kwh: float = Field(gt=0)
    initial_energy_kwh: float = Field(ge=0)
    minimum_energy_kwh: float = Field(ge=0)
    max_charge_kwh_per_hour: float = Field(ge=0)
    max_discharge_kwh_per_hour: float = Field(ge=0)

    @model_validator(mode="after")
    def _physical(self):
        if self.initial_energy_kwh > self.capacity_kwh:
            raise ValueError("initial_energy_kwh cannot exceed capacity_kwh")
        if self.minimum_energy_kwh > self.capacity_kwh:
            raise ValueError("minimum_energy_kwh cannot exceed capacity_kwh")
        if self.max_charge_kwh_per_hour > self.capacity_kwh:
            raise ValueError("max_charge_kwh_per_hour cannot exceed capacity_kwh")
        if self.max_discharge_kwh_per_hour > self.capacity_kwh:
            raise ValueError("max_discharge_kwh_per_hour cannot exceed capacity_kwh")
        return self


class OptimizeEnergyRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: str = Field(min_length=1, max_length=200)
    operator_notes: List[str] = Field(min_length=1, max_length=3)
    hours: List[HourEntry]
    battery: Battery

    @field_validator("operator_notes")
    @classmethod
    def _notes_nonempty(cls, v: List[str]):
        for i, n in enumerate(v):
            if not isinstance(n, str) or not n.strip():
                raise ValueError(f"operator_notes[{i}] must be a non-empty string")
        return v

    @model_validator(mode="after")
    def _hours_ok(self):
        if len(self.hours) != 24:
            raise ValueError(
                f"hours must contain exactly 24 entries, got {len(self.hours)}"
            )
        seen = set()
        for h in self.hours:
            if h.hour in seen:
                raise ValueError(f"duplicate hour {h.hour}")
            seen.add(h.hour)
        if seen != set(range(24)):
            raise ValueError("hours must cover exactly hours 0..23")
        return self
