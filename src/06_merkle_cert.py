"""
Blockchain 101 -- Toy Example #8: The full Merkle certificate lifecycle.

Demonstrates that the full tree is needed EXACTLY ONCE -- at issuance --
and can be discarded immediately after. Verification, years later, uses
only (a) the graduate's own certificate and (b) the root looked up
on-chain. No tree object exists anywhere by that point.
"""

from __future__ import annotations

import copy
import hashlib
from dataclasses import dataclass


def sha256(data: str) -> str:
    """Deterministic hash helper used throughout."""
    return hashlib.sha256(data.encode()).hexdigest()


class MerkleTree:
    """Same as v7 -- see that file for full annotation."""

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
    """What a graduate actually receives and keeps -- self-contained and
    independently verifiable forever. No tree required, ever again.

    Attributes:
        holder: Whose certificate this is.
        content: The actual diploma text (what gets hashed as the leaf).
        proof: This holder's personal sibling-hash path to the root,
            computed once at issuance time and embedded here permanently.
    """
    holder: str
    content: str
    proof: list[tuple[str, str]]


def issue_batch(holders: list[str], contents: list[str]) -> tuple[dict[str, Certificate], str]:
    """NUS's one-time issuance process.

    This function is the ONLY place in the entire system where the full
    Merkle tree ever exists. It's built, used to generate every
    graduate's individual proof, and then goes out of scope the moment
    this function returns -- nothing outside keeps a reference to it.

    Args:
        holders: Names of the graduates in this batch.
        contents: The diploma text for each graduate, same order.

    Returns:
        (certificates keyed by holder name, the Merkle root to publish on-chain)
    """
    tree = MerkleTree(contents)
    root = tree.root

    certificates: dict[str, Certificate] = {}
    for i, (holder, content) in enumerate(zip(holders, contents)):
        proof = tree.get_proof(i)
        certificates[holder] = Certificate(holder=holder, content=content, proof=proof)

    return certificates, root
    # <- `tree` dies here. Python garbage-collects it. It is never coming back.


def verify_certificate(cert: Certificate, published_root: str) -> bool:
    """Standalone verification: only this certificate + an on-chain root.

    No tree object exists anywhere at the point this function runs --
    none is constructed, none is needed.

    Args:
        cert: The certificate being checked.
        published_root: The root looked up from the blockchain.

    Returns:
        True if this certificate genuinely belongs to the batch that
        produced published_root.
    """
    leaf_hash = sha256(cert.content)
    return verify_proof(leaf_hash, cert.proof, published_root)


# Stand-in for "the blockchain" -- in reality this is an Ethereum smart
# contract storage slot, not a Python dict. Same idea: a small amount of
# permanent, publicly readable, tamper-evident storage.
on_chain_registry: dict[str, str] = {}


if __name__ == "__main__":
    print("=== NUS issues a batch -- the ONLY moment the full tree exists ===\n")

    holders = [
        "Alice Tan", "Bob Lim", "Carol Ng", "Titus Lim",
        "Emma Koh", "Farid Rahman", "Grace Wong", "Hafiz Ismail",
    ]
    majors = [
        "Computer Science", "Chemical Engineering", "Economics", "AI Engineering",
        "Mathematics", "Physics", "Biology", "Statistics",
    ]
    contents = [f"Diploma: {h}, {m}, 2026" for h, m in zip(holders, majors)]

    certificates, root = issue_batch(holders, contents)
    on_chain_registry["NUS-Grad-2026-Batch-14"] = root

    print("  Published to chain, batch 'NUS-Grad-2026-Batch-14':")
    print(f"  root = {root[:24]}...\n")
    print(f"  Each of the {len(certificates)} graduates now holds their OWN")
    print("  Certificate object, independently, with nothing shared between them\n")

    print("=== What Titus's certificate actually contains ===\n")
    titus_cert = certificates["Titus Lim"]
    print(f"  holder:  {titus_cert.holder}")
    print(f"  content: {titus_cert.content}")
    print(f"  proof:   {len(titus_cert.proof)} sibling hashes, baked in permanently")
    for pos, h in titus_cert.proof:
        print(f"             ({pos}, {h[:16]}...)")

    print("\n=== Confirming the tree genuinely no longer exists anywhere ===\n")
    print(f"  Is there a variable named 'tree' in this scope? {'tree' in dir()}")
    print("  (issue_batch() never returned one, and never kept one -- it can't leak out)\n")

    print("=== Years later: Titus hands ONLY his certificate to an employer ===\n")
    published_root = on_chain_registry["NUS-Grad-2026-Batch-14"]
    is_valid = verify_certificate(titus_cert, published_root)
    print("  Verifying using ONLY Titus's file + the on-chain root...")
    print(f"  Verified genuine? {is_valid}")
    print("  (Employer never contacted NUS. Never saw Alice, Bob, or anyone")
    print("   else's diploma. Never needed a tree to exist anywhere.)\n")

    print("=== What if the certificate is tampered with after issuance? ===\n")
    forged_cert = copy.deepcopy(titus_cert)
    forged_cert.content = forged_cert.content + ", FIRST CLASS HONOURS"
    is_valid_forged = verify_certificate(forged_cert, published_root)
    print(f"  Tampered content: {forged_cert.content}")
    print(f"  Verified genuine? {is_valid_forged}")