#%%
"""
Blockchain 101 -- Toy Example #3: Proof of Stake, bug fixed, fully annotated.

A validator's eligibility is now checked AS OF THE HEIGHT the block was created, 
not against their current live status. Historical blocks stay valid even after the same
validator is later caught cheating and slashed.
"""

from __future__ import annotations

import hashlib
import json
import secrets
import time


class Validator:
    """A network participant who has locked up a stake (deposit) as
    collateral in order to be eligible to propose new blocks.

    Attributes:
        name: Human-readable identifier for this validator.
        stake: The amount of currency this validator has locked up.
            Higher stake means a higher probability of being selected
            to propose the next block -- see pick_proposer().
        slashed_at_height: The block height at which this validator was
            caught cheating and had their stake destroyed, or None if
            they have never been slashed. This is the field that fixes
            the v4 bug: eligibility is judged relative to THIS height,
            not relative to "are they currently marked as bad."
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
        """Was this validator in good standing at the given block height?

        A validator slashed at height H remains eligible for every block
        strictly BEFORE H (their earlier honest work stays valid), and
        becomes ineligible for block H itself and everything after it.

        Args:
            height: The block height being checked.

        Returns:
            True if this validator was allowed to propose at that height.
        """
        if self.slashed_at_height is None:
            return True
        return height < self.slashed_at_height

    def __repr__(self) -> str:
        status = f"SLASHED at height {self.slashed_at_height}" if self.is_slashed else "active"
        return f"{self.name}: stake={self.stake} [{status}]"


class Block:
    """A single entry in the chain: a bundle of data, a pointer to the
    previous block, and a record of who proposed it.

    Attributes:
        index: This block's position in the chain (0 = genesis).
        timestamp: When this block object was created (informational only).
        data: The payload -- in a real chain, a batch of transactions.
        previous_hash: The hash of the block immediately before this one.
            This is what makes the chain a CHAIN: change any earlier
            block, and every previous_hash after it stops matching.
        proposer: The name of the validator who proposed this block.
        hash: This block's own hash, computed once at creation time.
    """

    def __init__(self, index: int, data: str, previous_hash: str, proposer: str) -> None:
        self.index = index
        self.timestamp = time.time()
        self.data = data
        self.previous_hash = previous_hash
        self.proposer = proposer
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        """Deterministically hash this block's contents.

        Same inputs always produce the same output -- this is what lets
        every node on the network independently re-verify a block
        without trusting whoever proposed it.

        Returns:
            A hex-encoded SHA-256 digest of this block's contents.
        """
        block_contents = json.dumps(
            {
                "index": self.index,
                "timestamp": self.timestamp,
                "data": self.data,
                "previous_hash": self.previous_hash,
                "proposer": self.proposer,
            },
            sort_keys=True,
        )
        return hashlib.sha256(block_contents.encode()).hexdigest()

    def __repr__(self) -> str:
        return (
            f"Block #{self.index} proposed by {self.proposer}\n"
            f"  data:          {self.data}\n"
            f"  previous_hash: {self.previous_hash[:16]}...\n"
            f"  hash:          {self.hash[:16]}...\n"
        )


def pick_proposer(validators: list[Validator]) -> Validator:
    """Select the next block proposer at random, weighted by stake.

    Uses secrets.randbelow() -- a cryptographically secure random source
    backed by the OS's CSPRNG -- rather than the `random` module. `random`
    is a Mersenne Twister: deterministic and predictable once its internal
    state is known. If proposer selection were predictable, an attacker
    could pre-target whoever is about to be picked (DoS them right before
    their slot) or try to bias who gets selected (a "grinding" attack).
    Real chains take this seriously: Ethereum combines RANDAO with a VDF,
    Algorand uses a Verifiable Random Function (VRF) -- different
    mechanisms, same underlying goal.

    Args:
        validators: The full validator set. Slashed validators are
            excluded automatically -- they have zero chance of selection.

    Returns:
        The Validator selected to propose the next block.
    """
    active = [v for v in validators if not v.is_slashed]
    weights = [v.stake for v in active]
    total = sum(weights)
    pick = secrets.randbelow(int(total))
    cumulative = 0.0
    for validator, weight in zip(active, weights):
        cumulative += weight
        if pick < cumulative:
            return validator
    return active[-1]


def slash(validator: Validator, height: int, penalty_fraction: float = 1.0) -> None:
    """Destroy (some or all of) a validator's stake as punishment, and
    permanently record the height at which the misbehaviour occurred.

    Args:
        validator: The validator being punished.
        height: The block height at which the misbehaviour occurred.
            This is what lets is_valid() later distinguish this
            validator's honest earlier blocks from their dishonest
            later ones.
        penalty_fraction: Fraction of stake destroyed, from 0 to 1.
            Real protocols vary this by offence severity; we default
            to a full wipe for simplicity.
    """
    lost = validator.stake * penalty_fraction
    validator.stake -= lost
    validator.slashed_at_height = height
    print(
        f"  SLASHED: {validator.name} loses {lost:.0f} coins for cheating "
        f"at height {height}. Remaining stake: {validator.stake:.0f}"
    )


class Blockchain:
    """Owns the chain and enforces what counts as a legitimate next block.

    Same architectural role as the Proof-of-Work version's Blockchain
    class -- add_block() and is_valid() -- but the RULES for legitimacy
    are PoS-flavoured: no difficulty target, but proposer eligibility
    (judged historically, not by current status) instead.
    """

    def __init__(self, validators: list[Validator]) -> None:
        self.validators = validators
        self.chain: list[Block] = [Block(0, "Genesis Block", "0" * 64, "network")]

    def add_block(self, data: str) -> tuple[Block, Validator]:
        """Select a proposer via weighted lottery and append their block.

        Args:
            data: The payload for the new block.

        Returns:
            A tuple of (the new Block, the Validator who proposed it).
        """
        proposer = pick_proposer(self.validators)
        previous_block = self.chain[-1]
        new_block = Block(len(self.chain), data, previous_block.hash, proposer.name)
        self.chain.append(new_block)
        return new_block, proposer

    def is_valid(self) -> tuple[bool, str]:
        """Re-verify the entire chain's integrity from scratch.

        Checks, for every block:
          1. Tamper-evidence -- does the stored hash match a fresh
             recomputation of this block's contents right now?
          2. Linkage -- does this block correctly point to the previous
             block's actual hash?
          3. Proposer eligibility AT THE TIME -- was the named proposer
             a real validator who was still in good standing AT THIS
             BLOCK'S OWN HEIGHT specifically? (The v4 fix: we ask "were
             they eligible back then," never "are they clean right now.")

        Returns:
            (True, "Chain is valid.") if every check passes, otherwise
            (False, <reason the first failing block was rejected>).
        """
        validators_by_name = {v.name: v for v in self.validators}

        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]

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
                    f"already slashed (at height {proposer.slashed_at_height}) by the "
                    f"time this block was created."
                )

            # Honest gap: real PoS chains additionally require CRYPTOGRAPHIC
            # PROOF the proposer was genuinely selected for this slot (a VRF
            # proof or equivalent), not just a name we're trusting. Our toy
            # doesn't carry that proof around -- flagging it, not hiding it.

        return True, "Chain is valid."

    def detect_equivocation(
        self, index: int, proposer_name: str, candidate_blocks: list[Block]
    ) -> tuple[bool, str]:
        """Detect whether a proposer signed multiple conflicting blocks
        for the same height -- unambiguous, provable misbehaviour.

        Not caught by is_valid() above, because equivocation isn't a
        property of one block in isolation; it requires comparing two
        candidate blocks proposed for the same slot side by side.

        Args:
            index: The block height in question.
            proposer_name: The validator being checked.
            candidate_blocks: All block versions proposed for this height.

        Returns:
            (True, <description>) if equivocation is detected, else
            (False, <description>).
        """
        hashes = {b.hash for b in candidate_blocks}
        if len(hashes) > 1:
            return True, (
                f"{proposer_name} signed {len(hashes)} conflicting blocks "
                f"at height {index} -- equivocation."
            )
        return False, "No equivocation detected."

#%%
if __name__ == "__main__":
    print("=== Setting up validators ===\n")
    validators: list[Validator] = [
        Validator("Mastercard-Node", stake=500),
        Validator("NUS-Node", stake=100),
        Validator("SketchyGuy-Node", stake=50),
    ]
    for v in validators:
        print(f"  {v}")

    chain = Blockchain(validators)

    print("\n=== Adding 5 blocks honestly, via chain.add_block() ===\n")
    for i in range(1, 6):
        block, proposer = chain.add_block(f"Legit transaction batch #{i}")
        print(f"  Block #{block.index} proposed by {proposer.name} (stake={proposer.stake})")

    valid, msg = chain.is_valid()
    print(f"\nChain valid? {valid} -- {msg}\n")

    print("=== SketchyGuy-Node equivocates at height 6 (two conflicting proposals) ===\n")
    sketchy = validators[2]
    prev_hash = chain.chain[-1].hash
    block_6a = Block(6, "Alice sends Bob $100", prev_hash, sketchy.name)
    block_6b = Block(6, "Alice sends CAROL the same $100", prev_hash, sketchy.name)

    caught, msg = chain.detect_equivocation(6, sketchy.name, [block_6a, block_6b])
    print(f"  {msg}")
    if caught:
        slash(sketchy, height=6)

    print("\n=== SketchyGuy tries to sneak a forged block in anyway, post-slashing ===\n")
    forged = Block(len(chain.chain), "SketchyGuy tries to sneak one in", chain.chain[-1].hash, sketchy.name)
    chain.chain.append(forged)

    valid, msg = chain.is_valid()
    print(f"  Chain valid? {valid} -- {msg}")

    print("\n=== Sanity check: is Block #5 (honest, pre-crime) still valid on its own terms? ===\n")
    block_5 = chain.chain[5]
    print(
        f"  Was {sketchy.name} eligible at height {block_5.index}? "
        f"{sketchy.was_eligible_at(block_5.index)}  (should be True -- honest history stays honest)"
    )

    print("\n=== Final validator state ===")
    for v in validators:
        print(f"  {v}")
# %%
