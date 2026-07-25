"""
Blockchain 101 -- Toy Example #1: The Anatomy of a Block
A minimal, dependency-free blockchain to show ONE thing clearly:
each block contains the hash of the block before it, so tampering
with ANY block breaks the hash of every block after it.

No mining yet. No consensus yet. Just the "chain" part of "blockchain."
"""

import hashlib
import json
import time


class Block:
    def __init__(self, index, data, previous_hash):
        self.index = index
        self.timestamp = time.time()
        self.data = data
        self.previous_hash = previous_hash
        self.hash = self.compute_hash()

    def compute_hash(self):
        # Turn this block's contents into one deterministic string...
        block_contents = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
        }, sort_keys=True)
        # ...then hash it. Same input -> same output. Always. Everywhere.
        return hashlib.sha256(block_contents.encode()).hexdigest()

    def __repr__(self):
        return (f"Block #{self.index}\n"
                f"  data:          {self.data}\n"
                f"  previous_hash: {self.previous_hash[:16]}...\n"
                f"  hash:          {self.hash[:16]}...\n")


class Blockchain:
    def __init__(self):
        # every chain needs a first block with no parent -- the "genesis block"
        self.chain = [Block(0, "Genesis Block", "0" * 64)]

    def add_block(self, data):
        previous_block = self.chain[-1]
        new_block = Block(len(self.chain), data, previous_block.hash)
        self.chain.append(new_block)

    def is_valid(self):
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]

            # Rule 1: this block's stored hash must match what we get
            # from recomputing it right now.
            if current.hash != current.compute_hash():
                return False, f"Block #{current.index} was tampered with directly."

            # Rule 2: this block must correctly point to the block before it.
            if current.previous_hash != previous.hash:
                return False, f"Block #{current.index} is disconnected from Block #{previous.index}."

        return True, "Chain is valid."

    def print_chain(self):
        for block in self.chain:
            print(block)


if __name__ == "__main__":
    print("=== Building the chain ===\n")
    titus_chain = Blockchain()
    titus_chain.add_block("Titus joins Mastercard R&D, 6 July 2026")
    titus_chain.add_block("Titus starts NTU MSc in Blockchain")
    titus_chain.add_block("Titus finally understands why PoW isn't magic")

    titus_chain.print_chain()

    valid, msg = titus_chain.is_valid()
    print(f"Chain valid? {valid} -- {msg}\n")

    print("=== Attempt 1: sloppy tamper -- edit the data, leave the old hash ===\n")
    titus_chain.chain[1].data = "Titus joins Mastercard R&D... as a spy for a rival bank"

    valid, msg = titus_chain.is_valid()
    print(f"Chain valid? {valid} -- {msg}\n")

    print("=== Attempt 2: clever tamper -- also recompute Block #1's own hash to cover tracks ===\n")
    titus_chain.chain[1].hash = titus_chain.chain[1].compute_hash()

    valid, msg = titus_chain.is_valid()
    print(f"Chain valid? {valid} -- {msg}")