"""Directive models — interpretation entries and structured adjustment shapes."""

from typing import Literal, Optional, Union
from pydantic import BaseModel, Field, ConfigDict

DirectiveType = Literal[
    "solar_reduction",
    "minimum_battery_reserve",
    "no_charge_window",
    "no_discharge_window",
    "max_grid_window",
    "no_op",
]

BatteryAction = Literal["charge", "discharge", "idle"]


class SolarReductionAdj(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hours: list[int] = Field(min_length=1, max_length=24)
    factor: float = Field(ge=0.0, le=1.0)


class MinReserveAdj(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hours: list[int] = Field(min_length=1, max_length=24)
    minimum_energy_kwh: float = Field(ge=0.0)


class HoursOnlyAdj(BaseModel):
    """Adjustment shape for no_charge_window / no_discharge_window."""

    model_config = ConfigDict(extra="forbid")
    hours: list[int] = Field(min_length=1, max_length=24)


class MaxGridAdj(BaseModel):
    model_config = ConfigDict(extra="forbid")
    hours: list[int] = Field(min_length=1, max_length=24)
    max_grid_kwh: float = Field(ge=0.0)


StructuredAdjustment = Union[
    SolarReductionAdj,
    MinReserveAdj,
    HoursOnlyAdj,
    MaxGridAdj,
    dict,
    None,
]


class DirectiveInterpretation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    note_index: int = Field(ge=0, le=10)
    applies: bool
    directive_type: DirectiveType
    structured_adjustment: Optional[dict] = None
    explanation: str = Field(min_length=1, max_length=500)
