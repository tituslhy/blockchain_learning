#%%
"""
Blockchain 101 -- Toy Example #5: Merkle Trees.

How NUS publishes ONE hash for a whole batch of diplomas, while any one
graduate can prove their specific diploma was in that batch -- without
needing, revealing, or even seeing anyone else's diploma.
"""

from __future__ import annotations

import hashlib


def sha256(data: str) -> str:
    """Deterministic hash helper used throughout."""
    return hashlib.sha256(data.encode()).hexdigest()


class MerkleTree:
    """A binary tree of hashes, built bottom-up from a list of documents.

    Each document becomes a "leaf" (individually hashed). Leaves are
    paired up and hashed together to form the next layer up. This
    repeats until exactly one hash remains -- the "Merkle root" -- which
    is the ONLY thing that needs to be published on-chain.

    Attributes:
        leaves: Hashes of the original documents, in order.
        layers: Every layer of the tree, from leaves (layers[0]) up to
            the root (layers[-1], containing exactly one hash).
    """

    def __init__(self, documents: list[str]) -> None:
        if not documents:
            raise ValueError("Need at least one document to build a tree.")
        self.leaves: list[str] = [sha256(doc) for doc in documents]
        self.layers: list[list[str]] = [self.leaves]
        self._build()

    def _build(self) -> None:
        """Repeatedly hash pairs of the current layer until one hash remains."""
        current = self.layers[0]
        while len(current) > 1:
            next_layer: list[str] = []
            for i in range(0, len(current), 2):
                left = current[i]
                # odd count -> duplicate the last item so it can pair with itself
                right = current[i + 1] if i + 1 < len(current) else current[i]
                next_layer.append(sha256(left + right))
            self.layers.append(next_layer)
            current = next_layer

    @property
    def root(self) -> str:
        """The single hash summarizing the ENTIRE batch of documents."""
        return self.layers[-1][0]

    def get_proof(self, leaf_index: int) -> list[tuple[str, str]]:
        """Build the minimal sibling-hash path proving a document's membership.

        This is the entire point of the structure: instead of needing
        ALL other documents, you need exactly one sibling hash per
        LEVEL of the tree -- log2(N) hashes total, not N-1.

        Args:
            leaf_index: Position of the document to prove membership for.

        Returns:
            A list of (position, hash) pairs. Position ("left"/"right")
            tells the verifier which side of the combination the
            sibling hash belongs on.
        """
        proof: list[tuple[str, str]] = []
        index = leaf_index
        for layer in self.layers[:-1]:  # every layer except the root itself
            is_right_node = index % 2 == 1
            pair_index = index - 1 if is_right_node else index + 1
            if pair_index < len(layer):
                sibling_hash = layer[pair_index]
                position = "left" if is_right_node else "right"
                proof.append((position, sibling_hash))
            index //= 2
        return proof


def verify_proof(leaf_hash: str, proof: list[tuple[str, str]], root: str) -> bool:
    """Independently recompute the root from a leaf hash + its proof, and
    check it matches the published root -- without ever seeing any other
    document in the batch.

    Args:
        leaf_hash: Hash of the document being proven.
        proof: Sibling hashes returned by MerkleTree.get_proof().
        root: The published root hash to check against.

    Returns:
        True if the leaf genuinely belongs to the tree that produced root.
    """
    current_hash = leaf_hash
    for position, sibling_hash in proof:
        if position == "left":
            current_hash = sha256(sibling_hash + current_hash)
        else:
            current_hash = sha256(current_hash + sibling_hash)
    return current_hash == root

#%%
if __name__ == "__main__":
    print("=== NUS issues 8 diplomas in one graduation batch ===\n")
    diplomas = [
        "Diploma: Alice Tan, Computer Science, 2026",
        "Diploma: Bob Lim, Chemical Engineering, 2026",
        "Diploma: Carol Ng, Economics, 2026",
        "Diploma: Titus Lim, AI Engineering, 2026",
        "Diploma: Emma Koh, Mathematics, 2026",
        "Diploma: Farid Rahman, Physics, 2026",
        "Diploma: Grace Wong, Biology, 2026",
        "Diploma: Hafiz Ismail, Statistics, 2026",
    ]
    tree = MerkleTree(diplomas)
    print(f"Merkle root (the ONLY thing NUS publishes on-chain):\n  {tree.root}\n")

    print("=== Titus wants to prove HIS diploma is in the batch ===\n")
    titus_index = diplomas.index("Diploma: Titus Lim, AI Engineering, 2026")
    proof = tree.get_proof(titus_index)
    print(f"  Titus's diploma is at position {titus_index} of {len(diplomas)}.")
    print(f"  His proof needs only {len(proof)} sibling hashes "
          f"(not the other {len(diplomas) - 1} diplomas!):")
    for pos, h in proof:
        print(f"    combine on the {pos}: {h[:16]}...")

    print("\n=== Employer verifies, using ONLY Titus's document + his proof + the public root ===\n")
    titus_leaf_hash = sha256("Diploma: Titus Lim, AI Engineering, 2026")
    is_valid = verify_proof(titus_leaf_hash, proof, tree.root)
    print(f"  Verified genuine? {is_valid}")

    print("\n=== What if Titus tries to upgrade his own grade after the fact? ===\n")
    forged_leaf_hash = sha256("Diploma: Titus Lim, AI Engineering, 2026, FIRST CLASS HONOURS")
    is_valid_forged = verify_proof(forged_leaf_hash, proof, tree.root)
    print(f"  Verified genuine? {is_valid_forged}")

    print("\n=== Did any of this require touching Alice, Bob, Carol, or anyone else's diploma? ===\n")
    print("  Not once. That's the entire point.")
# %%
