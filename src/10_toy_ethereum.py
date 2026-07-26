"""
Blockchain 101 -- Toy Example #14: A toy EVM with gas metering.

Demonstrates the exact thing gas is FOR: a public network, with no
membership list to ban anyone, must still survive buggy or malicious
code. This toy virtual machine runs simple stack-based programs,
charges gas per instruction, and forcibly halts (with a full state
ROLLBACK) the instant gas runs out -- no matter how far through
execution it got.
"""

from __future__ import annotations

from dataclasses import dataclass, field


class OutOfGasError(Exception):
    """Raised when execution would need more gas than was authorized.
    In real Ethereum, this doesn't crash the network -- it just fails
    THIS ONE transaction, and the sender still pays for the gas burned
    up to the failure point. That's deliberate: even a failed attack
    costs the attacker real money."""


# Fixed, published cost per operation -- exactly like Ethereum's own gas
# schedule. Notice STORE costs far more than arithmetic: writing to
# permanent storage is genuinely expensive for every node to maintain
# forever, so it's priced accordingly (real Ethereum's SSTORE really is
# disproportionately costly compared to ADD/SUB for this exact reason).
GAS_COSTS: dict[str, int] = {
    "PUSH": 3,
    "POP": 2,
    "ADD": 3,
    "SUB": 3,
    "STORE": 20,
    "LOAD": 5,
    "JUMP": 8,
}


@dataclass
class ExecutionContext:
    """The scratch space for one contract call: a working stack, a view
    of storage, and a running gas tally."""
    storage: dict[str, int] = field(default_factory=dict)
    stack: list[int] = field(default_factory=list)
    gas_remaining: int = 0
    gas_used: int = 0


def execute(program: list[tuple], ctx: ExecutionContext) -> None:
    """Run a simple stack-based program, instruction by instruction,
    charging gas for each step. Mutates ctx in place. Raises
    OutOfGasError the instant gas_remaining can't cover the next
    instruction's cost -- execution stops EXACTLY there, not one
    instruction later.

    Args:
        program: A list of (opcode, *operands) tuples.
        ctx: The execution context to run against and mutate.
    """
    pc = 0
    while pc < len(program):
        opcode, *operand = program[pc]
        cost = GAS_COSTS[opcode]

        if ctx.gas_remaining < cost:
            raise OutOfGasError(
                f"Out of gas at instruction #{pc} ({opcode}): "
                f"needed {cost}, had {ctx.gas_remaining} remaining"
            )
        ctx.gas_remaining -= cost
        ctx.gas_used += cost

        if opcode == "PUSH":
            ctx.stack.append(operand[0])
        elif opcode == "POP":
            ctx.stack.pop()
        elif opcode == "ADD":
            b, a = ctx.stack.pop(), ctx.stack.pop()
            ctx.stack.append(a + b)
        elif opcode == "SUB":
            b, a = ctx.stack.pop(), ctx.stack.pop()
            ctx.stack.append(a - b)
        elif opcode == "STORE":
            key = operand[0]
            ctx.storage[key] = ctx.stack.pop()
        elif opcode == "LOAD":
            key = operand[0]
            ctx.stack.append(ctx.storage.get(key, 0))
        elif opcode == "JUMP":
            pc = operand[0]
            continue

        pc += 1


def run_transaction(
    program: list[tuple], gas_limit: int, persistent_storage: dict[str, int]
) -> tuple[bool, int, str]:
    """Run a contract call in an ISOLATED sandbox. State changes only
    get written back to persistent_storage on success -- exactly like a
    database transaction, and exactly like our very first Blockchain's
    all-or-nothing tamper-evidence, just applied to execution instead
    of hashing.

    Args:
        program: The instructions to run.
        gas_limit: Maximum gas authorized for this call.
        persistent_storage: The REAL, shared contract storage. Only
            touched if execution succeeds completely.

    Returns:
        (success, gas actually used, human-readable outcome message)
    """
    sandbox = dict(persistent_storage)  # execute against a throwaway copy
    ctx = ExecutionContext(storage=sandbox, gas_remaining=gas_limit)
    try:
        execute(program, ctx)
    except OutOfGasError as e:
        # ROLLBACK: persistent_storage is untouched. Gas is still "spent"
        # in reality (the attacker/bug author still pays), even though
        # nothing they attempted actually took effect.
        return False, ctx.gas_used, str(e)

    persistent_storage.clear()
    persistent_storage.update(ctx.storage)  # COMMIT
    return True, ctx.gas_used, "Success"


if __name__ == "__main__":
    print("=== Program 1: a normal, well-behaved token transfer ===\n")
    storage: dict[str, int] = {"alice_balance": 1000, "bob_balance": 500}
    print(f"  Starting storage: {storage}")

    transfer_program = [
        ("LOAD", "alice_balance"),
        ("PUSH", 200),
        ("SUB",),
        ("STORE", "alice_balance"),
        ("LOAD", "bob_balance"),
        ("PUSH", 200),
        ("ADD",),
        ("STORE", "bob_balance"),
    ]

    success, gas_used, msg = run_transaction(transfer_program, gas_limit=100, persistent_storage=storage)
    print(f"  Success? {success} | Gas used: {gas_used}/100 | {msg}")
    print(f"  Storage now: {storage}\n")

    print("=== Program 2: a genuinely infinite loop (no exit condition, ever) ===\n")
    storage2: dict[str, int] = {"counter": 0}
    print(f"  Starting storage: {storage2}")

    infinite_loop_program = [
        ("LOAD", "counter"),   # instruction 0 -- the loop re-enters HERE
        ("PUSH", 1),
        ("ADD",),
        ("STORE", "counter"),
        ("JUMP", 0),           # jump back to instruction 0 -- forever
    ]

    success2, gas_used2, msg2 = run_transaction(infinite_loop_program, gas_limit=500, persistent_storage=storage2)
    print(f"  Success? {success2} | Gas used: {gas_used2}/500 | {msg2}")
    print(f"  Storage now: {storage2}  (unchanged -- rolled back, despite {gas_used2} gas of real work happening)")
    print("\n  This loop would run FOREVER on a normal computer. On Ethereum, it ran")
    print(f"  exactly as many iterations as {500} gas could buy, then stopped hard.")
    print(f"  The caller still pays for those {gas_used2} gas units -- a real cost for")
    print("  submitting broken (or malicious) code, even though nothing they")
    print("  attempted actually took effect on-chain.")