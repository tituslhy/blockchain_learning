#%%
"""
Blockchain 101 -- Toy Example #4: Rewards, compounding, and accidental
equivocation.

Builds on v3 (Validator, Block, Blockchain, pick_proposer, slash are
unchanged in spirit -- see that file for full annotation). Two additions:

  1. Reward mechanics -- proposers earn a block reward + transaction fees,
     credited directly to their stake. Run enough rounds and you can watch
     the "rich get richer" dynamic happen numerically, not just in theory.

  2. Accidental equivocation -- a well-intentioned redundancy setup (the
     SAME validator identity running "primary" and "backup" processes for
     reliability) accidentally produces two conflicting signatures during
     a botched failover. detect_equivocation() cannot tell this apart from
     deliberate cheating -- and in the real world, neither can Ethereum.
     This is why "just run a backup machine" is a genuine anti-pattern in
     PoS systems, unlike almost every other kind of distributed system.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time

BLOCK_REWARD: float = 2.0    # newly issued currency paid to the proposer
FEE_PER_TX: float = 0.1      # fee paid by each transaction bundled into the block


class Validator:
    """A network participant who has locked up a stake as collateral.

    Attributes:
        name: Human-readable identifier for this validator.
        stake: Currency locked up. Grows over time as rewards/fees are
            earned -- see Blockchain.add_block().
        slashed_at_height: Block height at which this validator was
            caught cheating, or None if never slashed.
    """

    def __init__(self, name: str, stake: float) -> None:
        self.name = name
        self.stake = stake
        self.slashed_at_height: int | None = None

    @property
    def is_slashed(self) -> bool:
        """Whether this validator has ever been slashed, at any point."""
        return self.slashed_at_height is not None

    def was_eligible_at(self, height: int) -> bool:
        """Was this validator in good standing as of the given height?"""
        if self.slashed_at_height is None:
            return True
        return height < self.slashed_at_height

    def __repr__(self) -> str:
        status = f"SLASHED at height {self.slashed_at_height}" if self.is_slashed else "active"
        return f"{self.name}: stake={self.stake:.2f} [{status}]"


class Block:
    """A single entry in the chain.

    Attributes:
        index: Position in the chain (0 = genesis).
        data: The payload for this block.
        previous_hash: Hash of the block immediately before this one.
        proposer: Name of the validator who proposed this block.
        num_transactions: How many transactions this block bundles --
            used to calculate the proposer's fee earnings.
        hash: This block's own hash, computed once at creation.
    """

    def __init__(
        self,
        index: int,
        data: str,
        previous_hash: str,
        proposer: str,
        num_transactions: int = 1,
    ) -> None:
        self.index = index
        self.timestamp = time.time()
        self.data = data
        self.previous_hash = previous_hash
        self.proposer = proposer
        self.num_transactions = num_transactions
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        """Deterministically hash this block's contents."""
        block_contents = json.dumps(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "data": self.data,
                "previous_hash": self.previous_hash,
                "proposer": self.proposer,
                "num_transactions": self.num_transactions,
            },
            sort_keys=True,
        )
        return hashlib.sha256(block_contents.encode()).hexdigest()

    def __repr__(self) -> str:
        return (
            f"Block #{self.index} proposed by {self.proposer} "
            f"({self.num_transactions} txs)\n"
            f"  data: {self.data}\n"
        )


def pick_proposer(validators: list[Validator]) -> Validator:
    """Select the next proposer at random, weighted by stake, using a
    cryptographically secure random source."""
    active = [v for v in validators if not v.is_slashed]
    weights = [v.stake for v in active]
    total = sum(weights)
    pick = secrets.randbelow(int(total * 1000)) / 1000  # sub-integer precision, stakes now have decimals
    cumulative = 0.0
    for validator, weight in zip(active, weights):
        cumulative += weight
        if pick < cumulative:
            return validator
    return active[-1]


def slash(validator: Validator, height: int, penalty_fraction: float = 1.0) -> None:
    """Destroy a fraction of a validator's stake and record when it happened.

    Args:
        validator: The validator being punished.
        height: Block height at which the misbehaviour occurred.
        penalty_fraction: Fraction of stake destroyed (0 to 1). Real
            protocols vary this by severity -- a small accidental
            first offence is penalized far more gently than repeated
            or coordinated attacks.
    """
    lost = validator.stake * penalty_fraction
    validator.stake -= lost
    validator.slashed_at_height = height
    print(
        f"  SLASHED: {validator.name} loses {lost:.2f} coins "
        f"({penalty_fraction:.0%} of stake) at height {height}. "
        f"Remaining stake: {validator.stake:.2f}"
    )


class Blockchain:
    """Owns the chain; enforces legitimacy rules for new blocks."""

    def __init__(self, validators: list[Validator]) -> None:
        self.validators = validators
        self.chain: list[Block] = [Block(0, "Genesis Block", "0" * 64, "network")]

    def add_block(self, data: str, num_transactions: int = 1) -> tuple[Block, Validator]:
        """Select a proposer, append their block, and pay them.

        The proposer earns BLOCK_REWARD (newly issued currency) plus
        num_transactions * FEE_PER_TX (fees from whoever's transactions
        got bundled in), credited straight into their stake. Since stake
        determines future selection odds, this is the entire "rich get
        richer" mechanic in three lines.

        Args:
            data: The payload for the new block.
            num_transactions: How many transactions this block bundles.

        Returns:
            (the new Block, the Validator who proposed and earned from it)
        """
        proposer = pick_proposer(self.validators)
        previous_block = self.chain[-1]
        new_block = Block(
            len(self.chain), data, previous_block.hash, proposer.name, num_transactions
        )
        self.chain.append(new_block)

        earnings = BLOCK_REWARD + num_transactions * FEE_PER_TX
        proposer.stake += earnings

        return new_block, proposer

    def is_valid(self) -> tuple[bool, str]:
        """Re-verify the whole chain: tamper-evidence, linkage, and
        proposer eligibility judged AS OF each block's own height."""
        validators_by_name = {v.name: v for v in self.validators}
        for i in range(1, len(self.chain)):
            current, previous = self.chain[i], self.chain[i - 1]
            if current.hash != current.compute_hash():
                return False, f"Block #{current.index} was tampered with directly."
            if current.previous_hash != previous.hash:
                return False, f"Block #{current.index} is disconnected from Block #{previous.index}."
            proposer = validators_by_name.get(current.proposer)
            if proposer is None:
                return False, f"Block #{current.index} was proposed by an unknown validator."
            if not proposer.was_eligible_at(current.index):
                return False, (
                    f"Block #{current.index} was proposed by {proposer.name}, who was "
                    f"already slashed (at height {proposer.slashed_at_height}) by then."
                )
        return True, "Chain is valid."

    def detect_equivocation(
        self, index: int, proposer_name: str, candidate_blocks: list[Block]
    ) -> tuple[bool, str]:
        """Detect a proposer signing multiple conflicting blocks for the
        same height. NOTE: this function has zero concept of intent --
        it purely compares hashes. That's not a simplification; that's
        exactly how real protocols work. They cannot read minds."""
        hashes = {b.hash for b in candidate_blocks}
        if len(hashes) > 1:
            return True, (
                f"{proposer_name} signed {len(hashes)} conflicting blocks "
                f"at height {index} -- equivocation."
            )
        return False, "No equivocation detected."

#%%
if __name__ == "__main__":
    print("=== PART 1: watching stake compound over 20 honest rounds ===\n")
    validators = [
        Validator("Mastercard-Node", stake=500),
        Validator("NUS-Node", stake=100),
        Validator("SketchyGuy-Node", stake=50),
    ]
    chain = Blockchain(validators)

    for i in range(1, 21):
        num_txs = secrets.randbelow(20) + 1
        chain.add_block(f"Batch #{i}", num_transactions=num_txs)
        if i % 5 == 0:
            print(f"  -- after {i} rounds --")
            for v in validators:
                print(f"     {v}")
            print()

    total_stake = sum(v.stake for v in validators)
    print("Final stake share after 20 rounds:")
    for v in validators:
        print(f"  {v.name}: {v.stake:.2f}  ({100 * v.stake / total_stake:.1f}% of total)")
    print("(Watch who pulled further ahead: more stake -> picked more often -> earns")
    print(" more -> even more stake next time. Compounding, exactly like a bank account.)\n")

    print("=== PART 2: an HONEST validator accidentally equivocates ===\n")
    validators2 = [Validator("Titus-Home-Validator", stake=200)]
    chain2 = Blockchain(validators2)
    for i in range(1, 4):
        chain2.add_block(f"Legit batch #{i}")

    print("  Scenario: runs a 'backup' node for reliability -- same validator key")
    print("  on both machines, standard HA instinct. The primary briefly drops off")
    print("  the network; the backup takes over and proposes a block. A moment")
    print("  later the primary reconnects, unaware a failover happened, and ALSO")
    print("  proposes for the same height. Neither machine did anything malicious.\n")

    solo = validators2[0]
    prev_hash = chain2.chain[-1].hash
    height = len(chain2.chain)
    block_primary = Block(height, "Primary node's version of events", prev_hash, solo.name)
    block_backup = Block(height, "Backup node's version of events", prev_hash, solo.name)

    caught, msg = chain2.detect_equivocation(height, solo.name, [block_primary, block_backup])
    print(f"  {msg}")
    print("  detect_equivocation() never asked WHY there were two signatures.")
    print("  It only sees: same identity, same height, conflicting content. Guilty.\n")

    if caught:
        # Real protocols penalize a first, apparently-accidental offence far more
        # gently than a repeated or clearly coordinated attack -- hence the small
        # penalty_fraction here, echoing the real post-2025 reduction in Ethereum's
        # initial slashing penalty.
        slash(solo, height=height, penalty_fraction=0.02)

    print(f"\n  Final state: {solo}")
# %%
