"""Kelly Criterion position sizing for binary prediction market contracts.

Calculates optimal bet size based on the edge between model probability and
market price. Uses fractional Kelly (default 0.25×) for variance reduction.

For a Kalshi YES contract costing C cents that pays $1 if the event happens:
    Edge = model_prob * 100 - C
    Kelly fraction f* = (model_prob * 100 - C) / (100 - C)

For NO side (costing 100-C cents):
    Kelly fraction f* = ((1-model_prob) * 100 - (100 - C)) / C

Kalshi charges a 15% fee on profits, which reduces the effective payout.
Fee-adjusted Kelly accounts for this by reducing the win amount.

Safety caps (in priority order):
    1. Negative edge → 0 contracts (never bet against yourself)
    2. max_contracts_per_trade cap
    3. max_bankroll_pct_per_trade cap
    4. max_trade_size_cents cap (from risk manager settings)
    5. Floor at 1 contract minimum (if edge is positive)

Usage:
    from backend.trading.kelly import calculate_kelly_size, KellyResult

    result = calculate_kelly_size(
        model_prob=0.35,
        price_cents=22,
        side="yes",
        bankroll_cents=50000,
        settings=kelly_settings,
    )
    # result.optimal_quantity -> recommended number of contracts
"""

from __future__ import annotations

from dataclasses import dataclass, field

from backend.common.logging import get_logger

logger = get_logger("TRADING")

# Kalshi fee: 15% of profit on winning contracts, minimum 1 cent
KALSHI_FEE_RATE = 0.15
MIN_FEE_CENTS = 1


@dataclass
class KellySettings:
    """Configuration for Kelly Criterion position sizing.

    Attributes:
        use_kelly_sizing: Enable Kelly sizing (False = always 1 contract).
        kelly_fraction: Fractional Kelly multiplier (0.25 = quarter Kelly).
        max_bankroll_pct_per_trade: Max % of bankroll per single trade.
        max_contracts_per_trade: Hard cap on contracts per trade.
    """

    use_kelly_sizing: bool = False
    kelly_fraction: float = 0.25
    max_bankroll_pct_per_trade: float = 0.05  # 5% of bankroll
    max_contracts_per_trade: int = 10


@dataclass
class KellyResult:
    """Result of Kelly Criterion calculation with full diagnostics.

    Attributes:
        raw_kelly_fraction: Uncapped Kelly fraction (can be negative).
        adjusted_kelly_fraction: After applying fractional multiplier.
        optimal_quantity: Final recommended number of contracts.
        cost_cents: Total cost in cents for the recommended quantity.
        edge_cents: Edge per contract in cents (model EV - cost).
        reasons: List of reasons for any adjustments made.
    """

    raw_kelly_fraction: float = 0.0
    adjusted_kelly_fraction: float = 0.0
    optimal_quantity: int = 1
    cost_cents: int = 0
    edge_cents: float = 0.0
    reasons: list[str] = field(default_factory=list)


def calculate_kelly_fraction(
    model_prob: float,
    price_cents: int,
    side: str,
    fee_rate: float = KALSHI_FEE_RATE,
) -> float:
    """Calculate the raw Kelly fraction for a binary contract.

    For YES side:
        cost = price_cents
        profit_if_win = 100 - price_cents
        fee_if_win = max(1, int(profit_if_win * fee_rate))
        net_profit_if_win = profit_if_win - fee_if_win

        f* = (model_prob * net_profit_if_win - (1 - model_prob) * cost)
             / net_profit_if_win

    For NO side:
        cost = 100 - price_cents
        profit_if_win = price_cents
        fee_if_win = max(1, int(profit_if_win * fee_rate))
        net_profit_if_win = profit_if_win - fee_if_win

        prob_win = 1 - model_prob (probability bracket does NOT hit)
        f* = (prob_win * net_profit_if_win - (1 - prob_win) * cost)
             / net_profit_if_win

    Args:
        model_prob: Model probability for the bracket (0.0-1.0).
        price_cents: Market YES price in cents (1-99).
        side: "yes" or "no".
        fee_rate: Kalshi fee rate on profits (default 0.15).

    Returns:
        Raw Kelly fraction (can be negative = no edge).

    Raises:
        ValueError: If inputs are out of valid range.
    """
    if not (0.0 <= model_prob <= 1.0):
        msg = f"model_prob must be 0.0-1.0, got {model_prob}"
        raise ValueError(msg)
    if not (1 <= price_cents <= 99):
        msg = f"price_cents must be 1-99, got {price_cents}"
        raise ValueError(msg)
    if side not in ("yes", "no"):
        msg = f"side must be 'yes' or 'no', got {side!r}"
        raise ValueError(msg)

    if side == "yes":
        cost = price_cents
        profit_if_win = 100 - price_cents
        prob_win = model_prob
    else:
        cost = 100 - price_cents
        profit_if_win = price_cents
        prob_win = 1.0 - model_prob

    # Fee-adjusted profit
    fee_if_win = max(MIN_FEE_CENTS, int(profit_if_win * fee_rate))
    net_profit = profit_if_win - fee_if_win

    # Avoid division by zero (net_profit = 0 means no profit possible)
    if net_profit <= 0:
        return 0.0

    # Kelly formula: f* = (p * b - q) / b
    # where p = prob_win, q = 1 - p, b = net_profit / cost (odds)
    # Simplified: f* = (p * net_profit - q * cost) / net_profit
    q = 1.0 - prob_win
    kelly = (prob_win * net_profit - q * cost) / net_profit

    return kelly


def calculate_kelly_size(
    model_prob: float,
    price_cents: int,
    side: str,
    bankroll_cents: int,
    settings: KellySettings | None = None,
    max_trade_size_cents: int = 100,
) -> KellyResult:
    """Calculate optimal position size using fractional Kelly Criterion.

    Combines the raw Kelly fraction with safety caps to produce a
    recommended number of contracts.

    Args:
        model_prob: Model probability for the bracket (0.0-1.0).
        price_cents: Market YES price in cents (1-99).
        side: "yes" or "no".
        bankroll_cents: Total bankroll in cents.
        settings: Kelly configuration. Uses defaults if None.
        max_trade_size_cents: Max cost per trade from risk manager.

    Returns:
        KellyResult with optimal_quantity and diagnostics.
    """
    if settings is None:
        settings = KellySettings()

    result = KellyResult()

    # If Kelly sizing is disabled, return 1 contract
    if not settings.use_kelly_sizing:
        cost_per_contract = price_cents if side == "yes" else 100 - price_cents
        result.optimal_quantity = 1
        result.cost_cents = cost_per_contract
        result.reasons.append("Kelly sizing disabled — using 1 contract")
        return result

    # Calculate raw Kelly fraction
    raw_kelly = calculate_kelly_fraction(model_prob, price_cents, side)
    result.raw_kelly_fraction = round(raw_kelly, 6)

    # Safety cap 1: Negative edge → 0 contracts
    if raw_kelly <= 0:
        result.optimal_quantity = 0
        result.cost_cents = 0
        result.edge_cents = 0.0
        result.reasons.append(f"Negative edge (Kelly={raw_kelly:.4f}) — no bet")
        return result

    # Apply fractional Kelly
    adjusted = raw_kelly * settings.kelly_fraction
    result.adjusted_kelly_fraction = round(adjusted, 6)

    # Calculate optimal bet amount in cents
    optimal_bet_cents = adjusted * bankroll_cents
    cost_per_contract = price_cents if side == "yes" else 100 - price_cents

    # Edge per contract (expected profit per contract in cents)
    fee_cents = max(MIN_FEE_CENTS, int((100 - cost_per_contract) * KALSHI_FEE_RATE))
    net_payout = 100 - fee_cents
    if side == "yes":
        result.edge_cents = round(model_prob * net_payout - cost_per_contract, 2)
    else:
        result.edge_cents = round((1 - model_prob) * net_payout - cost_per_contract, 2)

    # Convert bet amount to contract count
    if cost_per_contract <= 0:
        result.optimal_quantity = 0
        result.reasons.append("Zero cost per contract")
        return result

    quantity = int(optimal_bet_cents / cost_per_contract)
    reasons = []

    # Safety cap 2: max contracts per trade
    if quantity > settings.max_contracts_per_trade:
        reasons.append(
            f"Capped from {quantity} to {settings.max_contracts_per_trade} "
            f"(max_contracts_per_trade)"
        )
        quantity = settings.max_contracts_per_trade

    # Safety cap 3: max bankroll percentage per trade
    max_from_bankroll = int(
        (bankroll_cents * settings.max_bankroll_pct_per_trade) / cost_per_contract
    )
    if quantity > max_from_bankroll:
        reasons.append(
            f"Capped from {quantity} to {max_from_bankroll} "
            f"({settings.max_bankroll_pct_per_trade:.0%} bankroll cap)"
        )
        quantity = max_from_bankroll

    # Safety cap 4: max trade size from risk manager
    max_from_risk = int(max_trade_size_cents / cost_per_contract)
    if quantity > max_from_risk:
        reasons.append(
            f"Capped from {quantity} to {max_from_risk} "
            f"(max_trade_size_cents={max_trade_size_cents})"
        )
        quantity = max_from_risk

    # Safety cap 5: Floor at 1 contract minimum (edge is positive)
    if quantity < 1:
        quantity = 1
        reasons.append("Floored to 1 contract (positive edge, small bankroll)")

    result.optimal_quantity = quantity
    result.cost_cents = quantity * cost_per_contract
    result.reasons = reasons

    logger.debug(
        "Kelly sizing calculated",
        extra={
            "data": {
                "raw_kelly": result.raw_kelly_fraction,
                "adjusted_kelly": result.adjusted_kelly_fraction,
                "quantity": result.optimal_quantity,
                "cost_cents": result.cost_cents,
                "edge_cents": result.edge_cents,
            }
        },
    )

    return result
