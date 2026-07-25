#%%
"""
Blockchain 101 -- Toy Example #2: Adding Proof-of-Work
Same chain-linking as v1 (toy_blockchain.py), but now writing a block
actually costs something. This is the difference between a "chain of
hashes" and a "blockchain" in the Proof-of-Work sense.
"""

import hashlib
import json
import time


class Block:
    def __init__(self, index, data, previous_hash, difficulty=5):
        self.index = index
        self.timestamp = time.time()
        self.data = data
        self.previous_hash = previous_hash
        self.difficulty = difficulty   # how many leading zeros the hash must have
        self.nonce = 0                 # the number we brute-force search over
        self.hash = self.mine()

    def compute_hash(self):
        block_contents = json.dumps({
            "index": self.index,
            "timestamp": self.timestamp,
            "data": self.data,
            "previous_hash": self.previous_hash,
            "nonce": self.nonce,          # nonce is now part of what gets hashed
        }, sort_keys=True)
        return hashlib.sha256(block_contents.encode()).hexdigest()

    def mine(self):
        target = "0" * self.difficulty
        start = time.time()
        attempts = 0
        candidate_hash = self.compute_hash()
        # This is the main workhorse. It's a while loop until the hash generated starts with
        # difficulty * "0". So if difficulty is 19, the hash must start with 19 zeros
        while not candidate_hash.startswith(target):
            self.nonce += 1
            attempts += 1
            candidate_hash = self.compute_hash()
        elapsed = time.time() - start
        print(f"  mined Block #{self.index} in {attempts:,} attempts, {elapsed:.2f}s "
              f"(nonce={self.nonce}, hash={candidate_hash[:16]}...)")
        return candidate_hash

    def __repr__(self):
        return (f"Block #{self.index}\n"
                f"  data:          {self.data}\n"
                f"  nonce:         {self.nonce}\n"
                f"  previous_hash: {self.previous_hash[:16]}...\n"
                f"  hash:          {self.hash[:16]}...\n")


class Blockchain:
    def __init__(self, difficulty=5):
        self.difficulty = difficulty
        self.chain = [Block(0, "Genesis Block", "0" * 64, difficulty)]

    def add_block(self, data):
        previous_block = self.chain[-1]
        new_block = Block(len(self.chain), data, previous_block.hash, self.difficulty)
        self.chain.append(new_block)

    def is_valid(self):
        target = "0" * self.difficulty
        for i in range(1, len(self.chain)):
            current = self.chain[i]
            previous = self.chain[i - 1]

            if current.hash != current.compute_hash():
                return False, f"Block #{current.index} was tampered with directly."
            if current.previous_hash != previous.hash:
                return False, f"Block #{current.index} is disconnected from Block #{previous.index}."
            if not current.hash.startswith(target):
                return False, f"Block #{current.index} doesn't satisfy the difficulty target -- no real work was done."
        return True, "Chain is valid."

#%%
if __name__ == "__main__":
    print("=== Mining a chain at difficulty 5 (hash must start with '00000') ===\n")
    chain = Blockchain(difficulty=5)
    chain.add_block("Titus joins Mastercard R&D")
    chain.add_block("Titus starts NTU MSc in Blockchain")

    valid, msg = chain.is_valid()
    print(f"\nChain valid? {valid} -- {msg}\n")

    print("=== Attacker fakes a block's DATA and re-hashes it, but skips re-mining ===\n")
    fake_block = chain.chain[1]
    fake_block.data = "Titus actually works for a rival bank"
    fake_block.hash = fake_block.compute_hash()   # recomputed, but never re-mined!

    valid, msg = chain.is_valid()
    print(f"Chain valid? {valid} -- {msg}")
# %%
