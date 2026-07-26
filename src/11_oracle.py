#%%
"""
Blockchain 101 -- Toy Example #15: The Oracle Problem.

Compares a NAIVE smart contract trusting a single price oracle against
a ROBUST one requiring multiple independent oracles + median -- then
shows the robust version's actual limit: it can't detect a lie that
every honest oracle unknowingly agrees on.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Oracle:
    """An independent, named source reporting a real-world price."""
    name: str
    reported_price: float


def naive_liquidation_check(
    collateral_eth: float, debt_usd: float, oracle: Oracle, threshold: float = 1.5
) -> bool:
    """Trusts ONE oracle. If it lies, the contract faithfully acts on the lie."""
    ratio = (collateral_eth * oracle.reported_price) / debt_usd
    return ratio < threshold  # True = liquidate


def robust_liquidation_check(
    collateral_eth: float, debt_usd: float, oracles: list[Oracle], threshold: float = 1.5
) -> bool:
    """Requires MULTIPLE independent oracles, uses the MEDIAN -- the same
    'many independent parties must agree' principle as PoW verification,
    PoS endorsement, and Fabric's endorsement policy, aimed at price
    data instead of transaction integrity."""
    prices = sorted(o.reported_price for o in oracles)
    median_price = prices[len(prices) // 2]
    ratio = (collateral_eth * median_price) / debt_usd
    return ratio < threshold

#%%
if __name__ == "__main__":
    collateral_eth, debt_usd = 10.0, 12000.0
    print(f"=== Loan: {collateral_eth} ETH collateral against ${debt_usd:,.0f} debt ===")
    print(f"  At real ETH price $2,000: ratio = {(collateral_eth*2000)/debt_usd:.2f} "
          f"(threshold is 1.5 -- this is genuinely healthy)\n")

    honest = [Oracle("Coinbase-Feed", 2000.0), Oracle("Kraken-Feed", 1990.0), Oracle("Binance-Feed", 2010.0)]
    manipulated = Oracle("Thin-DEX-Feed", 500.0)  # one exchange's price got attacked

    print("=== Naive contract: trusts ONLY the manipulated feed ===")
    print(f"  Liquidated? {naive_liquidation_check(collateral_eth, debt_usd, manipulated)}"
          f"  <- WRONG, attacker just stole this collateral\n")

    print("=== Robust contract: median of several independent oracles ===")
    all_oracles = honest + [manipulated]
    prices = sorted(o.reported_price for o in all_oracles)
    print(f"  Prices seen: {prices} | median: {prices[len(prices)//2]}")
    print(f"  Liquidated? {robust_liquidation_check(collateral_eth, debt_usd, all_oracles)}"
          f"  <- CORRECT, one bad feed couldn't move the median\n")

    print("=== But if the REAL market crashes (all oracles honestly agree) ===")
    crashed = [Oracle("Coinbase-Feed", 600.0), Oracle("Kraken-Feed", 580.0), Oracle("Binance-Feed", 590.0)]
    print(f"  Prices seen: {sorted(o.reported_price for o in crashed)}")
    print(f"  Liquidated? {robust_liquidation_check(collateral_eth, debt_usd, crashed)}"
          f"  <- Still triggers. Honest agreement is no defense if reality itself was manipulated first.")
# %%
