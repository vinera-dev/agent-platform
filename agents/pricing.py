from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

TOKENS_PER_UNIT = Decimal(1_000_000)
PRECISION = Decimal("0.000001")


def estimate_cost(model: str, prompt_tokens: int, completion_tokens: int) -> Decimal:
    rates = settings.MODEL_PRICING.get(model)
    if rates is None:
        return Decimal(0).quantize(PRECISION)
    input_rate = Decimal(str(rates["input"]))
    output_rate = Decimal(str(rates["output"]))
    total = (prompt_tokens * input_rate + completion_tokens * output_rate) / TOKENS_PER_UNIT
    return total.quantize(PRECISION, rounding=ROUND_HALF_UP)
