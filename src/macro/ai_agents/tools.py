"""The bounded arithmetic tool available equally to every judge."""
import math
from typing import Literal


def calculate(operation: Literal["sum", "divide", "subtract"], values: list[float]) -> dict:
    """Perform bounded arithmetic on supplied numbers; never access cases, files or labels."""
    if not values or len(values) > 100 or any(not math.isfinite(v) or abs(v) > 1e12 for v in values):
        return {"error": "supply 1 to 100 finite bounded numbers"}
    if operation == "sum":
        return {"value": sum(values)}
    if len(values) != 2:
        return {"error": "divide/subtract require exactly two values"}
    if operation == "divide":
        return {"error": "division by zero"} if values[1] == 0 else {"value": values[0] / values[1]}
    if operation == "subtract":
        return {"value": values[0] - values[1]}
    return {"error": "unsupported operation"}


