# Blockchain Learning

*Claude teaches Titus about blockchain. Titus teaches future-Titus via toy Python scripts that fit in one coffee break each.*

This repo is a **revision cheat sheet disguised as a codebase**. Every file in `src/` is a self-contained demo: run it, watch the print statements narrate what just happened, close the laptop feeling smug. No Docker. No testnet faucets. No "please install 47 GB of dependencies and pray."

There is also [`index.html`](index.html) — a visual knowledge gallery if you prefer reading with typography instead of terminal green.

---

## Quick Start

**Requirements:** Python 3.13+ (managed via [uv](https://docs.astral.sh/uv/))

```bash
# Install dependencies
uv sync

# Run any module — they all have a __main__ story at the bottom
uv run python src/01_basic_blockchain.py
```

Open `index.html` in a browser for the prose version. No build step. We're not that fancy yet.

---

## The Curriculum (Read This When Your Brain Needs a Refresher)

Work through the files in order the first time. Come back to individual files when you forget *why* something exists — not just *what* it is.

| # | File | One-line pitch | Concepts to revise |
|---|------|----------------|-------------------|
| 01 | [`01_basic_blockchain.py`](src/01_basic_blockchain.py) | The "chain" before the "block" | Hash-linked blocks, genesis block, tamper detection (recompute hash vs. fix `previous_hash`) |
| 02 | [`02_blockchain_pow.py`](src/02_blockchain_pow.py) | Making writes expensive on purpose | Nonce, difficulty target, mining as brute-force search, "re-hashed but not re-mined" attacks |
| 03 | [`03_blockchain_pos.py`](src/03_blockchain_pos.py) | Rich validators take turns | Stake-weighted proposer selection, slashing, **historical** eligibility (`was_eligible_at`), equivocation |
| 04 | [`04_blockchain_pos_reward.py`](src/04_blockchain_pos_reward.py) | The rich get richer (numerically!) | Block rewards + tx fees compounding into stake, accidental equivocation from HA backups |
| 05 | [`05_merkle_trees.py`](src/05_merkle_trees.py) | One hash for 8 diplomas | Merkle tree construction, sibling proofs, O(log N) verification, forgery fails silently |
| 06 | [`06_merkle_cert.py`](src/06_merkle_cert.py) | Issue once, verify forever | `Certificate` objects, tree exists **only at issuance**, on-chain root registry |
| 07 | [`07_summation_example.py`](src/07_summation_example.py) | Everything clicks together | Merkle root → PoS block payload → employer verifies years later (OpenCerts-shaped story) |
| 08 | [`08_permissioned_chains.py`](src/08_permissioned_chains.py) | Hyperledger Fabric, but readable | Execute → Order → Validate, endorsement policy, MVCC staleness, concurrent double-spend |
| 09 | [`09_permissioned_chains_with_retry.py`](src/09_permissioned_chains_with_retry.py) | MVCC said "try again" | Optimistic concurrency, client-side retry loop (what Fabric SDKs do for you) |
| 10 | [`10_toy_ethereum.py`](src/10_toy_ethereum.py) | Gas exists because humans write bugs | Stack VM, gas metering, infinite loops die politely, rollback on failure |
| 11 | [`11_oracle.py`](src/11_oracle.py) | Blockchains are blind to the real world | Single-oracle manipulation, median of many oracles, honest agreement on a crashed market |

---

## Mental Model Map

If you're cramming before a meeting and only have 90 seconds:

```
PUBLIC CHAINS                          PERMISSIONED CHAINS (Fabric-ish)
─────────────────                      ─────────────────────────────────
01 Hash chain                            08 Execute → Order → Validate
02 + PoW (anyone can mine)               09 + retry on MVCC conflict
03 + PoS (stake lottery)
04 + rewards (compounding)
         │                                        │
         ▼                                        ▼
05 Merkle trees (batch → one root)       Endorsement policy = "who must agree"
06 Certificates (proof baked in)         MVCC = "was my read still true?"
07 PoS block stores the root             Ordering = "who goes first?"
         │
         ▼
10 Smart contracts need GAS (no membership list to ban attackers)
11 Oracles bridge off-chain → on-chain (and lie sometimes)
```

**The recurring theme:** *many independent parties must agree on something* — whether that's a hash chain, a proposer, an endorsement, a median price, or an ordering of transactions. The mechanism changes; the paranoia doesn't.

---

## File-by-File Revision Notes

### Part 1: "It's Just Hashes All the Way Down"

**`01_basic_blockchain.py`** — Start here if you remember nothing else.

- A block stores: index, timestamp, data, `previous_hash`, and its own `hash`.
- Tamper attempt #1: edit data, leave old hash → caught immediately.
- Tamper attempt #2: recompute hash too → still caught, because `previous_hash` on the *next* block no longer matches.

**`02_blockchain_pow.py`** — PoW adds a cost to appending blocks.

- Mining = increment `nonce` until `hash` starts with N zeros.
- Validation checks hash linkage **and** difficulty target.
- Attacker who re-hashes without re-mining gets rejected. Work matters, not just math.

---

### Part 2: "Stakeholders With Stake"

**`03_blockchain_pos.py`** — PoW's electricity bill replaced by a deposit.

- Validators lock stake; `pick_proposer()` uses `secrets` (not `random` — predictable proposer = grinding/DoS).
- Slashing records **height**, not just "bad forever." Honest blocks before the crime stay valid.
- `detect_equivocation()` catches two conflicting signatures at the same height. Protocols can't read intent.

**`04_blockchain_pos_reward.py`** — Why big validators stay big.

- Proposers earn `BLOCK_REWARD + num_txs × FEE_PER_TX`, credited to stake.
- More stake → picked more often → earns more → repeat. Compounding, not conspiracy.
- **Plot twist:** running a "backup" validator with the same key is an anti-pattern. Failover can accidentally equivocate. Ethereum can't tell "oops" from "malice."

---

### Part 3: "Batch 8 Diplomas, Publish 1 Hash"

**`05_merkle_trees.py`** — The NUS graduation batch demo.

- Leaves = `sha256(document)`. Pairs hash upward until one root remains.
- `get_proof(index)` returns ~log₂(N) sibling hashes, not N−1 documents.
- Change your grade after issuance? Proof still fails. The root doesn't care about your ambitions.

**`06_merkle_cert.py`** — Operational reality of Merkle proofs.

- `issue_batch()` builds the tree once, embeds each graduate's proof in a `Certificate`, then the tree **dies**.
- Verification years later: certificate + on-chain root. No tree. No NUS phone call. No Alice's diploma.

**`07_summation_example.py`** — The "so what's the point?" file.

1. NUS issues certificates → Merkle root
2. Root submitted as a transaction on a PoS chain
3. Winning validator includes it, earns fees
4. Employer verifies Titus's cert against the root in that block

This is the OpenCerts / Ethereum mental model in ~300 lines.

---

### Part 4: "We Know Who You Are, Actually"

**`08_permissioned_chains.py`** — Fabric's Execute-Order-Validate, properly modeled.

| Phase | What happens |
|-------|--------------|
| **Execute** | Peers simulate chaincode locally, return endorsements + read/write sets |
| **Order** | Ordering service imposes ONE sequence on concurrent proposals |
| **Validate** | Check endorsement policy + MVCC (read versions still current?) |

- Alice pays Bob $200 and Carol $150 concurrently — both honestly endorsed against Alice v0.
- Whichever tx orders first commits; the other gets MVCC-rejected. Nobody lied. Order won.

**`09_permissioned_chains_with_retry.py`** — Same as 08, but Tx2 retries.

- `propose_with_retry()` re-runs Execute against fresh state after MVCC failure.
- This is optimistic concurrency: assume no conflict, pay retry cost only on collision.

---

### Part 5: "Public Networks Can't Just Ban People"

**`10_toy_ethereum.py`** — Why gas exists.

- Stack-based VM: PUSH, POP, ADD, SUB, STORE, LOAD, JUMP.
- Each opcode costs gas; `STORE` >> `ADD` (writing state is forever-expensive for every node).
- Infinite loop? Burns through gas limit, rolls back storage, caller still pays. Attackers pay rent.

**`11_oracle.py`** — Smart contracts can't Google ETH price.

- Naive: one oracle lies → wrongful liquidation.
- Robust: median of many oracles → one bad feed can't move the needle.
- Limit: if the **real market** crashes, honest oracles agree and liquidation is correct. Oracles report reality; they don't create it.

---

## Cheat Sheet: "They'll Probably Ask About..."

| Question | Go read | Remember |
|----------|---------|----------|
| Why is blockchain tamper-evident? | `01` | Changing block N breaks every hash after it |
| What does mining actually do? | `02` | Proves work via difficulty; not magic randomness |
| PoW vs PoS in one sentence? | `02` vs `03` | Work vs stake as the scarce resource |
| Why not run a backup validator? | `04` | Accidental equivocation = slashing, no mercy for intent |
| Why Merkle trees? | `05`–`07` | One on-chain hash, many off-chain proofs |
| What is MVCC in Fabric? | `08` | Endorsement computed against version X; commit fails if version moved |
| Why retry transactions? | `09` | Stale read sets are normal under concurrency |
| Why gas? | `10` | Halts runaway code; failed txs still cost money |
| Oracle attacks? | `11` | Single source bad; median helps; systemic crash is different |

---

## Cast of Recurring Characters

You'll meet these names more than once. Think of them as a sitcom cast:

- **Titus** — protagonist, occasionally tries to upgrade his own diploma
- **Mastercard-Node** — high stake, wins lotteries, compounds wealth like a bank account with ambition
- **SketchyGuy-Node** — teaches equivocation so you don't have to learn it the hard way
- **Alice / Bob / Carol** — eternal victims of concurrent transaction demos
- **NUS** — issuer of diplomas and Merkle roots, phone never rings during verification

---

## What This Repo Is Not

- Not production blockchain software (if you deploy this, please don't tell anyone I helped)
- Not a cryptocurrency (no token, no Discord, no roadmap slide deck)
- Not exhaustive (no ZK proofs, no sharding, no MEV drama — yet)

It *is* a structured path from "hash the previous block" to "oracles lie sometimes" with runnable code at every step.

---

## License

See [LICENSE](LICENSE).
