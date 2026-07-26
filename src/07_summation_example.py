"""
Blockchain 101 -- Combined Example: PoS + Rewards + Merkle Trees + Certificates.

This wires together everything into ONE coherent story instead
of separate demos, so you can see how the pieces actually interlock:

  1. NUS builds a Merkle tree of a diploma batch (MerkleTree)
  2. NUS submits ONLY the resulting root as a transaction's payload
  3. A Proof-of-Stake validator wins the weighted lottery, includes that
     transaction in a block, and earns a reward for doing so
     (Validator, Block, Blockchain, pick_proposer)
  4. Years later, an employer verifies one graduate's certificate using
     ONLY that graduate's own file + the root now permanently on-chain
     (Certificate, issue_batch, verify_certificate)

Proof-of-Work is deliberately excluded -- this models a PoS chain only
(which is what Ethereum, and therefore OpenCerts, actually runs on).
"""

from __future__ import annotations

import copy
import hashlib
import json
import secrets
import time
from dataclasses import dataclass

# ---------------------------------------------------------------------------
# Shared hashing primitive
# ---------------------------------------------------------------------------

def sha256(data: str) -> str:
    """Deterministic hash helper used by every layer below."""
    return hashlib.sha256(data.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Layer 1: Merkle trees -- batching many documents into one provable root
# ---------------------------------------------------------------------------

class MerkleTree:
    """A binary tree of hashes built bottom-up from a list of documents.
    See toy_blockchain_v7 for the fully worked index-arithmetic example."""

    def __init__(self, documents: list[str]) -> None:
        if not documents:
            raise ValueError("Need at least one document to build a tree.")
        self.leaves: list[str] = [sha256(doc) for doc in documents]
        self.layers: list[list[str]] = [self.leaves]
        self._build()

    def _build(self) -> None:
        current = self.layers[0]
        while len(current) > 1:
            next_layer: list[str] = []
            for i in range(0, len(current), 2):
                left = current[i]
                right = current[i + 1] if i + 1 < len(current) else current[i]
                next_layer.append(sha256(left + right))
            self.layers.append(next_layer)
            current = next_layer

    @property
    def root(self) -> str:
        """The single hash summarizing the entire batch -- this, and only
        this, is what ends up inside a Block's data field below."""
        return self.layers[-1][0]

    def get_proof(self, leaf_index: int) -> list[tuple[str, str]]:
        proof: list[tuple[str, str]] = []
        index = leaf_index
        for layer in self.layers[:-1]:
            is_right_node = index % 2 == 1
            pair_index = index - 1 if is_right_node else index + 1
            if pair_index < len(layer):
                sibling_hash = layer[pair_index]
                position = "left" if is_right_node else "right"
                proof.append((position, sibling_hash))
            index //= 2
        return proof


def verify_proof(leaf_hash: str, proof: list[tuple[str, str]], root: str) -> bool:
    """Recompute the root from a leaf + its proof. No tree object involved."""
    current_hash = leaf_hash
    for position, sibling_hash in proof:
        if position == "left":
            current_hash = sha256(sibling_hash + current_hash)
        else:
            current_hash = sha256(current_hash + sibling_hash)
    return current_hash == root


@dataclass
class Certificate:
    """What a graduate actually keeps -- self-contained and independently
    verifiable forever, no tree required after issuance."""
    holder: str
    content: str
    proof: list[tuple[str, str]]


def issue_batch(holders: list[str], contents: list[str]) -> tuple[dict[str, Certificate], str]:
    """NUS's one-time issuance: build the tree, hand out proofs, let the
    tree die. Returns (certificates, root-to-be-published-on-chain)."""
    tree = MerkleTree(contents)
    root = tree.root
    certificates = {
        holder: Certificate(holder=holder, content=content, proof=tree.get_proof(i))
        for i, (holder, content) in enumerate(zip(holders, contents))
    }
    return certificates, root
    # `tree` dies here -- nothing below this line ever references it again.


def verify_certificate(cert: Certificate, published_root: str) -> bool:
    """Standalone verification: only this certificate + an on-chain root."""
    return verify_proof(sha256(cert.content), cert.proof, published_root)


# ---------------------------------------------------------------------------
# Layer 2: Proof of Stake -- who gets to include a transaction, and why
# ---------------------------------------------------------------------------

BLOCK_REWARD: float = 2.0
FEE_PER_TX: float = 0.1


class Validator:
    """A staked network participant, eligible to propose blocks."""

    def __init__(self, name: str, stake: float) -> None:
        self.name = name
        self.stake = stake
        self.slashed_at_height: int | None = None

    @property
    def is_slashed(self) -> bool:
        return self.slashed_at_height is not None

    def was_eligible_at(self, height: int) -> bool:
        if self.slashed_at_height is None:
            return True
        return height < self.slashed_at_height

    def __repr__(self) -> str:
        status = f"SLASHED at height {self.slashed_at_height}" if self.is_slashed else "active"
        return f"{self.name}: stake={self.stake:.2f} [{status}]"


class Block:
    """A chain entry. `data` here will typically hold a Merkle root, NOT
    raw content -- that's the whole point of Layer 1 above."""

    def __init__(
        self, index: int, data: str, previous_hash: str, proposer: str, num_transactions: int = 1
    ) -> None:
        self.index = index
        self.timestamp = time.time()
        self.data = data
        self.previous_hash = previous_hash
        self.proposer = proposer
        self.num_transactions = num_transactions
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
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
            f"Block #{self.index} proposed by {self.proposer} ({self.num_transactions} txs)\n"
            f"  data (Merkle root): {self.data[:24]}...\n"
        )


def pick_proposer(validators: list[Validator]) -> Validator:
    """Cryptographically secure, stake-weighted proposer selection.
    See toy_blockchain_v5/v6 for the full rationale on secrets vs random."""
    active = [v for v in validators if not v.is_slashed]
    weights = [v.stake for v in active]
    total = sum(weights)
    pick = secrets.randbelow(int(total * 1000)) / 1000
    cumulative = 0.0
    for validator, weight in zip(active, weights):
        cumulative += weight
        if pick < cumulative:
            return validator
    return active[-1]


def slash(validator: Validator, height: int, penalty_fraction: float = 1.0) -> None:
    lost = validator.stake * penalty_fraction
    validator.stake -= lost
    validator.slashed_at_height = height
    print(f"  SLASHED: {validator.name} loses {lost:.2f} coins at height {height}.")


class Blockchain:
    """Owns the chain; PoS-flavoured legitimacy rules (see v5 for the
    historical-eligibility bug fix this already includes)."""

    def __init__(self, validators: list[Validator]) -> None:
        self.validators = validators
        self.chain: list[Block] = [Block(0, "Genesis Block", "0" * 64, "network")]

    def add_block(self, data: str, num_transactions: int = 1) -> tuple[Block, Validator]:
        proposer = pick_proposer(self.validators)
        previous_block = self.chain[-1]
        new_block = Block(len(self.chain), data, previous_block.hash, proposer.name, num_transactions)
        self.chain.append(new_block)
        proposer.stake += BLOCK_REWARD + num_transactions * FEE_PER_TX
        return new_block, proposer

    def is_valid(self) -> tuple[bool, str]:
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
                return False, f"Block #{current.index} was proposed by an already-slashed validator."
        return True, "Chain is valid."


# ---------------------------------------------------------------------------
# Layer 3: The combined story -- everything above, working together
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("=== Step 1: NUS builds the Merkle tree for a diploma batch ===\n")
    holders = ["Alice Tan", "Bob Lim", "Carol Ng", "Titus Lim"]
    majors = ["Computer Science", "Chemical Engineering", "Economics", "AI Engineering"]
    contents = [f"Diploma: {h}, {m}, 2026" for h, m in zip(holders, majors)]

    certificates, merkle_root = issue_batch(holders, contents)
    print(f"  Merkle root of this 4-diploma batch: {merkle_root[:24]}...")
    print(f"  {len(certificates)} Certificate objects handed out, tree already gone.\n")

    print("=== Step 2: the root gets submitted to a PoS blockchain as a transaction ===\n")
    validators = [
        Validator("Mastercard-Node", stake=500),
        Validator("NUS-Node", stake=100),
        Validator("SketchyGuy-Node", stake=50),
    ]
    chain = Blockchain(validators)

    # a few unrelated prior blocks, so this isn't suspiciously the first thing ever
    chain.add_block("Some unrelated earlier transaction batch", num_transactions=5)
    chain.add_block("Another unrelated batch", num_transactions=3)

    diploma_block, proposer = chain.add_block(
        data=merkle_root, num_transactions=len(certificates)
    )
    print(f"  {proposer.name} won the lottery for this slot and included NUS's transaction.")
    print(f"  {proposer.name} earned {BLOCK_REWARD + len(certificates) * FEE_PER_TX:.2f} coins for it.")
    print(f"  {diploma_block}")

    valid, msg = chain.is_valid()
    print(f"  Chain valid? {valid} -- {msg}\n")

    print("=== Step 3: years later, an employer verifies Titus's certificate ===\n")
    titus_cert = certificates["Titus Lim"]

    # The employer doesn't need "the tree" or "NUS's database" -- just the
    # root that's now permanently sitting inside diploma_block on-chain.
    published_root = diploma_block.data
    is_valid = verify_certificate(titus_cert, published_root)
    print(f"  Looked up block #{diploma_block.index} on-chain, read its root.")
    print("  Verified using ONLY Titus's own certificate + that root.")
    print(f"  Verified genuine? {is_valid}\n")

    print("=== Step 4: what if Titus's certificate is tampered with? ===\n")
    forged = copy.deepcopy(titus_cert)
    forged.content += ", FIRST CLASS HONOURS"
    is_valid_forged = verify_certificate(forged, published_root)
    print(f"  Tampered content: {forged.content}")
    print(f"  Verified genuine? {is_valid_forged}\n")

    print("=== Final validator stakes (notice who earned from this) ===")
    for v in validators:
        print(f"  {v}")