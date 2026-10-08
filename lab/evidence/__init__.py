"""EV-1.0 evidence checker, with no model or network dependencies."""
from .checker import check_case, batch, evaluate

__all__ = ["check_case", "batch", "evaluate"]
