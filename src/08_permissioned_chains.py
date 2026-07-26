#%%
"""
Blockchain 101 -- Toy Example #12: Execute-Order-Validate, properly modeled.

Closes the two gaps from v11:
  1. ORDER is now a real, separate step -- an OrderingService that takes
     MULTIPLE concurrently-proposed transactions and imposes ONE sequence
     on them, instead of processing things one at a time with no real
     ordering decision to make.
  2. VALIDATE now includes an MVCC (multi-version concurrency control)
     check -- was the state a transaction's endorsement was computed
     against still current by the time its turn came up to commit, or
     did an EARLIER-ordered transaction already change the same data?
     This is architecturally the double-spend problem again, just
     relocated to the gap between endorsement-time and commit-time.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Membership (unchanged)
# ---------------------------------------------------------------------------

class MembershipService:
    def __init__(self) -> None:
        self.registered_orgs: set[str] = set()

    def register(self, org_name: str) -> None:
        print(f"  [MembershipService] Registered org: {org_name}")
        self.registered_orgs.add(org_name)

    def is_registered(self, org_name: str) -> bool:
        return org_name in self.registered_orgs


# ---------------------------------------------------------------------------
# World state -- now version-tracked, so staleness can be detected
# ---------------------------------------------------------------------------

@dataclass
class WorldState:
    """Current account balances, PLUS a version number per key that
    increments every time that key is written. Real Fabric tracks
    exactly this (key, version) pairing -- it's what makes MVCC
    conflict detection possible."""
    balances: dict[str, float] = field(default_factory=dict)
    versions: dict[str, int] = field(default_factory=dict)

    def version_of(self, key: str) -> int:
        return self.versions.get(key, 0)


@dataclass
class ExecutionResult:
    """What chaincode execution actually produces: not just a new value,
    but a RECORD of which keys it read (and at what version) and which
    keys it intends to write. This read/write set is what Validate later
    checks for staleness."""
    write_set: dict[str, float]
    read_versions: dict[str, int]


def transfer_chaincode(state: WorldState, frm: str, to: str, amount: float) -> ExecutionResult:
    """Same business logic as v10/v11, now returning read/write sets
    instead of a whole new state dict."""
    if state.balances.get(frm, 0) < amount:
        raise ValueError(f"Insufficient funds: {frm} has {state.balances.get(frm, 0)}, needs {amount}")
    return ExecutionResult(
        write_set={
            frm: state.balances.get(frm, 0) - amount,
            to: state.balances.get(to, 0) + amount,
        },
        read_versions={frm: state.version_of(frm), to: state.version_of(to)},
    )


@dataclass
class Endorsement:
    peer_name: str
    result_hash: str


@dataclass
class Peer:
    name: str
    membership: MembershipService

    def endorse(
        self, chaincode: Callable, state: WorldState, *args
    ) -> tuple[Endorsement, ExecutionResult]:
        """EXECUTE step: simulate locally against a SNAPSHOT of current
        state. Multiple peers can do this concurrently, on the same
        starting state, without knowing about each other."""
        if not self.membership.is_registered(self.name):
            raise PermissionError(f"{self.name} is not a registered participant.")
        result = chaincode(state, *args)
        result_hash = sha256(json.dumps(result.write_set, sort_keys=True))
        return Endorsement(peer_name=self.name, result_hash=result_hash), result


# ---------------------------------------------------------------------------
# A fully-endorsed, not-yet-ordered transaction proposal
# ---------------------------------------------------------------------------

@dataclass
class ProposedTransaction:
    """The output of EXECUTE: endorsed, but not yet sequenced or committed."""
    description: str
    endorsements: list[Endorsement]
    execution_result: ExecutionResult


# ---------------------------------------------------------------------------
# ORDER -- now a real, separate step
# ---------------------------------------------------------------------------

class OrderingService:
    """A dedicated service whose ONLY job is deciding the canonical
    sequence for a batch of already-endorsed, concurrently-submitted
    transactions. Real Fabric uses Raft among known ordering nodes for
    this -- crash-fault-tolerant, not Byzantine, because these are
    trusted consortium members, not anonymous strangers."""

    def __init__(self, name: str) -> None:
        self.name = name

    def order(self, proposals: list[ProposedTransaction]) -> list[ProposedTransaction]:
        """Impose ONE sequence on a batch of proposals that arrived
        concurrently, with no coordination between the clients who
        submitted them. Here: simple arrival order. Real systems use
        their own consensus algorithm for this -- the ordering nodes
        must themselves agree on the sequence, same 'many independent
        parties agreeing' principle as everything else this whole
        conversation, just applied to SEQUENCING instead of CONTENT."""
        print(f"  [{self.name}] Received {len(proposals)} concurrently-proposed "
              f"transactions -- imposing a single order.")
        return list(proposals)  # FIFO for this toy; real orderers may reorder


# ---------------------------------------------------------------------------
# Blocks (unchanged in spirit from v11)
# ---------------------------------------------------------------------------

class Block:
    def __init__(self, index: int, data: str, previous_hash: str, orderer: str) -> None:
        self.index = index
        self.timestamp = time.time()
        self.data = data
        self.previous_hash = previous_hash
        self.orderer = orderer
        self.hash = self.compute_hash()

    def compute_hash(self) -> str:
        block_contents = json.dumps(
            {"index": self.index, "timestamp": self.timestamp, "data": self.data,
             "previous_hash": self.previous_hash, "orderer": self.orderer},
            sort_keys=True,
        )
        return hashlib.sha256(block_contents.encode()).hexdigest()

    def __repr__(self) -> str:
        return f"Block #{self.index}: {self.data}\n"


# ---------------------------------------------------------------------------
# VALIDATE + commit -- now with a real MVCC staleness check
# ---------------------------------------------------------------------------

class PermissionedBlockchain:
    def __init__(
        self, required_endorsers: set[str], min_endorsements: int, orderer_name: str
    ) -> None:
        self.required_endorsers = required_endorsers
        self.min_endorsements = min_endorsements
        self.orderer_name = orderer_name
        self.chain: list[Block] = [Block(0, "Genesis Block", "0" * 64, orderer_name)]
        self.state = WorldState()

    def validate_and_commit(self, tx: ProposedTransaction) -> bool:
        """VALIDATE step, now with TWO independent checks:
          (a) endorsement policy -- same as v10/v11
          (b) MVCC freshness -- did the state this tx's endorsement was
              computed against still hold true by the time it's actually
              being committed, or did an earlier transaction in this
              same ordered batch already change the same keys?
        """
        endorser_names = {e.peer_name for e in tx.endorsements}

        if not endorser_names.issuperset(self.required_endorsers):
            print(f"  REJECTED ({tx.description}): missing required endorsers "
                  f"{self.required_endorsers - endorser_names}")
            return False
        if len(tx.endorsements) < self.min_endorsements:
            print(f"  REJECTED ({tx.description}): not enough endorsements")
            return False
        if len({e.result_hash for e in tx.endorsements}) > 1:
            print(f"  REJECTED ({tx.description}): endorsers disagree on the result")
            return False

        # MVCC check: for every key this tx's endorsement read, is its
        # CURRENT version still what the endorsement assumed?
        for key, read_version in tx.execution_result.read_versions.items():
            current_version = self.state.version_of(key)
            if current_version != read_version:
                print(f"  REJECTED ({tx.description}): MVCC CONFLICT on '{key}' -- "
                      f"endorsed against version {read_version}, but current version "
                      f"is now {current_version} (changed by an earlier-ordered tx)")
                return False

        # Passed everything -- commit: apply the write set, bump versions,
        # and wrap it in a real hash-linked Block.
        for key, new_value in tx.execution_result.write_set.items():
            self.state.balances[key] = new_value
            self.state.versions[key] = self.state.version_of(key) + 1

        record = json.dumps(
            {"description": tx.description, "write_set": tx.execution_result.write_set},
            sort_keys=True,
        )
        previous_block = self.chain[-1]
        new_block = Block(len(self.chain), record, previous_block.hash, self.orderer_name)
        self.chain.append(new_block)

        print(f"  COMMITTED as Block #{new_block.index}: {tx.description}")
        return True

#%%
if __name__ == "__main__":
    print("=== Setup ===\n")
    membership = MembershipService()
    membership.register("Mastercard-Bank-A")
    membership.register("Mastercard-Bank-B")
    peer_a = Peer("Mastercard-Bank-A", membership)
    peer_b = Peer("Mastercard-Bank-B", membership)

    chain = PermissionedBlockchain(
        required_endorsers={"Mastercard-Bank-A", "Mastercard-Bank-B"},
        min_endorsements=2,
        orderer_name="Shared-Ordering-Service",
    )
    chain.state.balances = {"Alice-Account": 1000.0, "Bob-Account": 500.0, "Carol-Account": 0.0}
    print(f"  Starting balances: {chain.state.balances}")
    print(f"  Starting versions: {chain.state.versions}\n")

    print("=== EXECUTE: two clients propose CONFLICTING spends of Alice's money, ===")
    print("=== both endorsed against the SAME starting version (true concurrency) ===\n")

    # Client 1: Alice pays Bob $200
    e_a1, res1 = peer_a.endorse(transfer_chaincode, chain.state, "Alice-Account", "Bob-Account", 200.0)
    e_b1, res1b = peer_b.endorse(transfer_chaincode, chain.state, "Alice-Account", "Bob-Account", 200.0)
    tx1 = ProposedTransaction("Alice pays Bob $200", [e_a1, e_b1], res1)
    print(f"  Tx1 endorsed. Read versions assumed: {res1.read_versions}")

    # Client 2: Alice ALSO pays Carol $150, endorsed before Tx1 has committed
    e_a2, res2 = peer_a.endorse(transfer_chaincode, chain.state, "Alice-Account", "Carol-Account", 150.0)
    e_b2, res2b = peer_b.endorse(transfer_chaincode, chain.state, "Alice-Account", "Carol-Account", 150.0)
    tx2 = ProposedTransaction("Alice pays Carol $150", [e_a2, e_b2], res2)
    print(f"  Tx2 endorsed. Read versions assumed: {res2.read_versions}")
    print("  (Both transactions were endorsed against Alice-Account version 0 --")
    print("   neither peer knew about the other proposal while endorsing.)\n")

    print("=== ORDER: both proposals arrive at the ordering service together ===\n")
    orderer = OrderingService("Shared-Ordering-Service")
    ordered_batch = orderer.order([tx1, tx2])

    print("\n=== VALIDATE + COMMIT: process the ordered batch, one at a time ===\n")
    for tx in ordered_batch:
        validate_and_commit_result = chain.validate_and_commit(tx)

    print("\n=== Final state ===\n")
    print(f"  Balances: {chain.state.balances}")
    print(f"  Versions: {chain.state.versions}")
    print(f"  Chain length: {len(chain.chain)} blocks (genesis + only the tx that actually committed)")
    print("\n  Tx2 wasn't rejected because anyone lied or cheated -- BOTH endorsements")
    print("  were completely honest. It lost purely because Tx1 got ordered first")
    print("  and changed Alice-Account's version before Tx2's turn came up.")
# %%
