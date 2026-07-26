"""
Blockchain 101 -- Toy Example #13: Optimistic concurrency, with retry.

Extends v12: Tx2 is genuinely endorsed concurrently with Tx1 (both against
Alice-Account version 0), loses the MVCC race when Tx1 commits first, and
then a retry loop -- exactly what a real Fabric SDK does automatically --
re-executes against fresh state and succeeds. Same code as v12 for
MembershipService, WorldState, chaincode, Peer, OrderingService, Block,
and PermissionedBlockchain; only the __main__ story and the retry helper
are new.
"""

from __future__ import annotations

import hashlib
import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field


def sha256(data: str) -> str:
    return hashlib.sha256(data.encode()).hexdigest()


class MembershipService:
    def __init__(self) -> None:
        self.registered_orgs: set[str] = set()

    def register(self, org_name: str) -> None:
        print(f"  [MembershipService] Registered org: {org_name}")
        self.registered_orgs.add(org_name)

    def is_registered(self, org_name: str) -> bool:
        return org_name in self.registered_orgs


@dataclass
class WorldState:
    balances: dict[str, float] = field(default_factory=dict)
    versions: dict[str, int] = field(default_factory=dict)

    def version_of(self, key: str) -> int:
        return self.versions.get(key, 0)


@dataclass
class ExecutionResult:
    write_set: dict[str, float]
    read_versions: dict[str, int]


def transfer_chaincode(state: WorldState, frm: str, to: str, amount: float) -> ExecutionResult:
    if state.balances.get(frm, 0) < amount:
        raise ValueError(f"Insufficient funds: {frm} has {state.balances.get(frm, 0)}, needs {amount}")
    return ExecutionResult(
        write_set={frm: state.balances.get(frm, 0) - amount, to: state.balances.get(to, 0) + amount},
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

    def endorse(self, chaincode: Callable, state: WorldState, *args) -> tuple[Endorsement, ExecutionResult]:
        if not self.membership.is_registered(self.name):
            raise PermissionError(f"{self.name} is not a registered participant.")
        result = chaincode(state, *args)
        result_hash = sha256(json.dumps(result.write_set, sort_keys=True))
        return Endorsement(peer_name=self.name, result_hash=result_hash), result


@dataclass
class ProposedTransaction:
    description: str
    endorsements: list[Endorsement]
    execution_result: ExecutionResult


class OrderingService:
    def __init__(self, name: str) -> None:
        self.name = name

    def order(self, proposals: list[ProposedTransaction]) -> list[ProposedTransaction]:
        print(f"  [{self.name}] Sequencing {len(proposals)} proposal(s).")
        return list(proposals)


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


class PermissionedBlockchain:
    def __init__(self, required_endorsers: set[str], min_endorsements: int, orderer_name: str) -> None:
        self.required_endorsers = required_endorsers
        self.min_endorsements = min_endorsements
        self.orderer_name = orderer_name
        self.chain: list[Block] = [Block(0, "Genesis Block", "0" * 64, orderer_name)]
        self.state = WorldState()

    def validate_and_commit(self, tx: ProposedTransaction) -> bool:
        endorser_names = {e.peer_name for e in tx.endorsements}
        if not endorser_names.issuperset(self.required_endorsers):
            print("    REJECTED: missing required endorsers")
            return False
        if len(tx.endorsements) < self.min_endorsements:
            print("    REJECTED: not enough endorsements")
            return False
        if len({e.result_hash for e in tx.endorsements}) > 1:
            print("    REJECTED: endorsers disagree")
            return False
        for key, read_version in tx.execution_result.read_versions.items():
            current_version = self.state.version_of(key)
            if current_version != read_version:
                print(f"    REJECTED: MVCC CONFLICT on '{key}' -- endorsed against "
                      f"version {read_version}, current is {current_version}")
                return False
        for key, new_value in tx.execution_result.write_set.items():
            self.state.balances[key] = new_value
            self.state.versions[key] = self.state.version_of(key) + 1
        record = json.dumps({"description": tx.description, "write_set": tx.execution_result.write_set}, sort_keys=True)
        previous_block = self.chain[-1]
        new_block = Block(len(self.chain), record, previous_block.hash, self.orderer_name)
        self.chain.append(new_block)
        print(f"    COMMITTED as Block #{new_block.index}")
        return True


def propose_with_retry(
    description: str,
    peers: list[Peer],
    chaincode: Callable,
    chain: PermissionedBlockchain,
    orderer: OrderingService,
    args: tuple,
    max_attempts: int = 3,
) -> bool:
    """The client-side retry loop -- what a real Fabric SDK does
    automatically. On an MVCC conflict, don't give up: re-run EXECUTE
    against whatever the CURRENT state now is, and try again. This is
    the 'optimistic' half of optimistic concurrency control -- pay the
    retry cost only on an actual collision, not on every transaction.

    Args:
        description: Label for this transaction.
        peers: Endorsing peers to use.
        chaincode: The smart contract function to run.
        chain: The ledger to submit to.
        orderer: The ordering service to sequence through.
        args: Arguments to pass to the chaincode.
        max_attempts: How many times to retry before giving up.

    Returns:
        True if eventually committed, False if all attempts were exhausted.
    """
    for attempt in range(1, max_attempts + 1):
        print(f"  Attempt {attempt}: {description} (fresh EXECUTE against current state)")
        endorsements: list[Endorsement] = []
        execution_result: ExecutionResult | None = None
        for peer in peers:
            endorsement, result = peer.endorse(chaincode, chain.state, *args)
            endorsements.append(endorsement)
            execution_result = result
        tx = ProposedTransaction(description, endorsements, execution_result)
        ordered = orderer.order([tx])
        if chain.validate_and_commit(ordered[0]):
            return True
        print("    -> stale, retrying...\n")
    print(f"  Gave up after {max_attempts} attempts.")
    return False


if __name__ == "__main__":
    print("=== Setup ===\n")
    membership = MembershipService()
    membership.register("Mastercard-Bank-A")
    membership.register("Mastercard-Bank-B")
    peer_a = Peer("Mastercard-Bank-A", membership)
    peer_b = Peer("Mastercard-Bank-B", membership)
    peers = [peer_a, peer_b]

    chain = PermissionedBlockchain(
        required_endorsers={"Mastercard-Bank-A", "Mastercard-Bank-B"},
        min_endorsements=2,
        orderer_name="Shared-Ordering-Service",
    )
    orderer = OrderingService("Shared-Ordering-Service")
    chain.state.balances = {"Alice-Account": 1000.0, "Bob-Account": 500.0, "Carol-Account": 0.0}
    print(f"  Starting balances: {chain.state.balances}\n")

    print("=== Two clients endorse CONCURRENTLY, both against Alice-Account version 0 ===\n")
    e_a1, res1 = peer_a.endorse(transfer_chaincode, chain.state, "Alice-Account", "Bob-Account", 200.0)
    e_b1, _ = peer_b.endorse(transfer_chaincode, chain.state, "Alice-Account", "Bob-Account", 200.0)
    tx1 = ProposedTransaction("Alice pays Bob $200", [e_a1, e_b1], res1)

    e_a2, res2 = peer_a.endorse(transfer_chaincode, chain.state, "Alice-Account", "Carol-Account", 150.0)
    e_b2, _ = peer_b.endorse(transfer_chaincode, chain.state, "Alice-Account", "Carol-Account", 150.0)
    tx2_stale_attempt = ProposedTransaction("Alice pays Carol $150", [e_a2, e_b2], res2)
    print("  Both endorsed. Neither peer knew about the other proposal.\n")

    print("=== ORDER + VALIDATE: Tx1 happens to get sequenced first ===\n")
    ordered1 = orderer.order([tx1])
    chain.validate_and_commit(ordered1[0])

    print("\n=== Tx2's ORIGINAL (now-stale) endorsement finally reaches Validate ===\n")
    success = chain.validate_and_commit(tx2_stale_attempt)
    print(f"  First attempt succeeded? {success}\n")

    print("=== Client retries automatically, re-executing against CURRENT state ===\n")
    success = propose_with_retry(
        "Alice pays Carol $150", peers, transfer_chaincode, chain, orderer,
        ("Alice-Account", "Carol-Account", 150.0),
    )
    print(f"\n  Eventually succeeded? {success}\n")

    print("=== Final state ===")
    print(f"  Balances: {chain.state.balances}")
    print(f"  Versions: {chain.state.versions}")
    print(f"  Chain length: {len(chain.chain)} blocks")