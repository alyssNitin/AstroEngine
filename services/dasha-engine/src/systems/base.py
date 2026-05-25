"""
systems/base.py
===============
Abstract base class for all Dasha system implementations.

Every Dasha system (Vimshottari, Yogini, Chara, etc.) must inherit from
AbstractDashaSystem and implement the two core methods:
  - calculate(): Build the full timeline for a date range
  - get_current(): Return the active period at today's date

This pluggable interface allows new dasha systems to be added without
modifying any other part of the codebase. Simply create a new module in
this package, subclass AbstractDashaSystem, and register in __init__.py.
"""
from __future__ import annotations
from abc import ABC, abstractmethod
from datetime import date


class AbstractDashaSystem(ABC):
    """
    Pluggable interface for a Vedic Dasha system.

    Attributes:
        name (str): Machine-readable system identifier (e.g. "vimshottari")
        display_name (str): Human-readable name for UI display
        total_years (int): Full cycle duration in years (e.g. 120 for Vimshottari)
        description (str): Brief description of the system
    """

    name: str
    display_name: str
    total_years: int
    description: str = ""

    @abstractmethod
    def calculate(
        self,
        birth_chart: dict,
        from_date: str,
        to_date: str,
        depth: int = 2,
    ) -> dict:
        """
        Build a nested Dasha timeline for the given date range.

        Args:
            birth_chart: Full kundli dict from kundli-engine
            from_date: ISO date string "YYYY-MM-DD"
            to_date: ISO date string "YYYY-MM-DD"
            depth: Nesting level:
                   1 = Mahadasha only
                   2 = Mahadasha + Antardasha
                   3 = + Pratyantar dasha
                   4 = + Sookshma dasha
                   5 = + Prana dasha

        Returns:
            dict with keys:
                system (str): dasha system name
                timeline (list): nested period objects
                total_years (int): cycle length
        """
        ...

    @abstractmethod
    def get_current(self, birth_chart: dict) -> dict:
        """
        Return the active Dasha period(s) at today's date.

        Args:
            birth_chart: Full kundli dict from kundli-engine

        Returns:
            dict with keys:
                mahadasha (str): active Mahadasha planet/sign
                antardasha (str): active Antardasha (if depth ≥ 2)
                started (str): ISO date when current period began
                ends (str): ISO date when current period ends
                days_remaining (int): days until Antardasha changes
        """
        ...

    def list_periods(self) -> list[str]:
        """
        Return the ordered list of dasha periods (planet/sign names).
        Subclasses may override for non-standard sequences.
        """
        return []

    def __repr__(self) -> str:
        return f"<{self.__class__.__name__} name={self.name!r} years={self.total_years}>"
