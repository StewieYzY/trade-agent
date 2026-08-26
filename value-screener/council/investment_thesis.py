"""Minimal G2 3.3 InvestmentThesis integration facade.

The complete stable InvestmentThesis contract remains a later G2 child. This
module only exposes the dossier-bound valuation expectation projection.
"""

from council.growth_expectation_integration import build_investment_thesis

__all__ = ["build_investment_thesis"]
