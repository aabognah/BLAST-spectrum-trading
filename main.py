# main.py

import json
import hashlib
import time
import random
import copy
import os
from typing import List, Dict, Any
from fastapi import FastAPI
import uvicorn
from pydantic import BaseModel

# --- Data Models ---
from typing_extensions import TypedDict

class SpectrumToken(TypedDict):
    token_id: str
    band: str
    frequency_mhz: int
    bandwidth_mhz: int
    capacity: int
    location: str

class Transaction(TypedDict, total=False):
    timestamp: float
    agent_id: str
    capability: str
    payload: Dict[str, Any]
    tx_type: str # Added for easier history filtering

class Block(TypedDict, total=False):
    index: int
    timestamp: float
    transactions: List[Transaction]
    previous_hash: str
    hash: str

class SimulationConfig(BaseModel):
    num_agents: int
    num_tokens: int
    agent_balances: Dict[str, float] | None = None
    token_ownership: Dict[str, str] | None = None
    auction_type: str = "second_price"

# --- SpectrumBlockchain ---

class SpectrumBlockchain:
    """
    A blockchain that acts as a decentralized ledger for spectrum token auctions and ownership.
    Includes "smart contract" logic for managing auctions.
    """
    def __init__(self):
        self.reset()

    def reset(self):
        """Resets the blockchain to a clean state."""
        self.chain: List[Block] = []
        self.pending_transactions: List[Transaction] = []
        self.transaction_history: List[Transaction] = [] # For agent learning
        self.spectrum_tokens: Dict[str, SpectrumToken] = {}
        self.world_state = {
            "agent_balances": {},
            "token_ownership": {},
            "token_ownership_history": {}
        }
        self.auction_type = "second_price"
        self.active_auctions: Dict[str, Dict[str, Any]] = {}
        self.create_genesis_block()

    def create_genesis_block(self):
        genesis_block = {"index": 0, "timestamp": time.time(), "transactions": [], "previous_hash": "0", "active_auctions_snapshot": {}}
        genesis_block["hash"] = self.hash(genesis_block)
        self.chain.append(genesis_block)

    def new_transaction(self, transaction: Transaction):
        tx_with_timestamp = transaction.copy()
        tx_with_timestamp['timestamp'] = time.time()
        self.pending_transactions.append(tx_with_timestamp)

    def new_block(self, active_snapshot: Dict[str, Any] | None = None) -> Block:
        block = {
            "index": len(self.chain),
            "timestamp": time.time(),
            "transactions": copy.deepcopy(self.pending_transactions),
            "previous_hash": self.get_last_block()['hash'],
            "active_auctions_snapshot": copy.deepcopy(active_snapshot) if active_snapshot is not None else {}
        }
        block["hash"] = self.hash(block)
        self.chain.append(block)
        self.transaction_history.extend(self.pending_transactions)
        self.pending_transactions = []
        return block

    def process_pending_transactions(self) -> List[str]:
        """
        The "smart contract" engine. Resolves finished auctions and processes new transactions.
        Returns a list of messages about what happened.
        """
        messages = []
        current_block_index = len(self.chain)
        MIN_AUCTION_PERIOD = 2
        MAX_AUCTION_PERIOD = 5

        def _finalize_direct_sale(token_id: str, auction: Dict[str, Any], buyer_id: str) -> Transaction:
            """Settle direct-sale listings immediately once a buyer accepts the price."""
            price = auction.get("price", auction.get("reserve_price", 0))
            seller = auction["seller_id"]
            self.world_state['agent_balances'][buyer_id] -= price
            self.world_state['agent_balances'][seller] += price
            self.world_state['token_ownership'][token_id] = buyer_id
            self.world_state['token_ownership_history'][token_id].append(buyer_id)
            resolution_tx: Transaction = {
                "tx_type": "auction_resolution",
                "token_id": token_id,
                "seller_id": seller,
                "winner_id": buyer_id,
                "final_price": price,
                "reserve_price": auction['reserve_price'],
                "tick_resolved": current_block_index,
                "timestamp": time.time(),
                "success": True,
                "bids": [],
                "auction_type": "direct_sale",
                "creation_block": auction.get('creation_block'),
            }
            return resolution_tx

        # 1. Process new transactions from the pending pool (Bids, new auctions, etc.)
        # Collect any resolution transactions created while processing here so they
        # are not processed in the same loop iteration (avoids key-errors on synthetic records).
        new_pending = []
        if self.pending_transactions:
            # Deterministic ordering: start_auction -> place_bid -> buy_now -> others
            start_txs = [tx for tx in self.pending_transactions if tx.get('capability') == 'start_auction']
            bid_txs = [tx for tx in self.pending_transactions if tx.get('capability') == 'place_bid']
            buy_now_txs = [tx for tx in self.pending_transactions if tx.get('capability') == 'buy_now']
            other_txs = [tx for tx in self.pending_transactions if tx.get('capability') not in {'start_auction','place_bid','buy_now'}]

            ordered = start_txs + bid_txs + buy_now_txs + other_txs

            for tx in ordered:
                capability = tx.get('capability')
                payload = tx.get('payload', {})
                agent_id = tx.get('agent_id')

                if capability == 'start_auction':
                    tx['tx_type'] = 'start_auction'
                    token_id = payload.get('token_id')
                    if self.world_state['token_ownership'].get(token_id) == agent_id and token_id not in self.active_auctions:
                        reserve_price = payload.get('price')
                        auction_type = self.auction_type
                        msg = f"    - Starting auction for {token_id} by {agent_id} with reserve price {reserve_price:.2f}."
                        messages.append(msg)
                        auction_record: Dict[str, Any] = {
                            "seller_id": agent_id,
                            "reserve_price": reserve_price,
                            "bids": [],
                            "auction_type": auction_type,
                            "creation_block": current_block_index,  # Auction becomes bid-able next block
                        }
                        if auction_type == "direct_sale":
                            auction_record["price"] = reserve_price
                        else:
                            auction_record["end_block"] = current_block_index + MIN_AUCTION_PERIOD
                            auction_record["max_end_block"] = current_block_index + MAX_AUCTION_PERIOD
                        self.active_auctions[token_id] = auction_record

                elif capability == 'place_bid':
                    tx['tx_type'] = 'place_bid'
                    token_id = payload.get('token_id')
                    bid_amount = payload.get('bid_amount')
                    accepted = False
                    if token_id in self.active_auctions:
                        auction = self.active_auctions[token_id]
                        if auction.get('auction_type') == 'direct_sale':
                            rejection_reason = 'direct_sale_buy_now_only'
                            msg = f"    - Bid REJECTED for {token_id} from {agent_id} (direct-sale listings must use buy_now)."
                            messages.append(msg)
                            tx['accepted'] = False
                            tx['rejection_reason'] = rejection_reason
                            continue
                        # Enforce one-block propagation delay
                        creation_block = auction.get('creation_block', current_block_index)
                        if current_block_index <= creation_block:
                            rejection_reason = 'same_block'
                            msg = f"    - Bid REJECTED for {token_id} from {agent_id} (same-block; creation_block={creation_block})."
                            messages.append(msg)
                            tx['accepted'] = False
                            tx['rejection_reason'] = rejection_reason
                            continue
                        is_not_seller = auction['seller_id'] != agent_id
                        has_not_bid = agent_id not in [b['bidder_id'] for b in auction['bids']]
                        has_balance = self.world_state['agent_balances'].get(agent_id, 0) >= bid_amount
                        if is_not_seller and has_not_bid and has_balance:
                            auction['bids'].append({"bidder_id": agent_id, "amount": bid_amount})
                            msg = f"    - Bid of {bid_amount:.2f} for {token_id} from {agent_id} accepted."
                            messages.append(msg)
                            accepted = True
                        else:
                            # Derive structured rejection reason
                            if not is_not_seller:
                                rejection_reason = 'seller_is_bidder'
                            elif not has_not_bid:
                                rejection_reason = 'duplicate_bid'
                            elif not has_balance:
                                rejection_reason = 'insufficient_balance'
                            else:
                                rejection_reason = 'unknown'
                            msg = f"    - Bid REJECTED for {token_id} from {agent_id} ({rejection_reason})."
                            messages.append(msg)
                    else:
                        rejection_reason = 'auction_not_active'
                        msg = f"    - Bid REJECTED for {token_id} from {agent_id} (auction not active)."
                        messages.append(msg)
                    tx['accepted'] = accepted
                    if not accepted and 'rejection_reason' not in tx:
                        tx['rejection_reason'] = rejection_reason

                elif capability == 'buy_now':
                    tx['tx_type'] = 'buy_now'
                    token_id = payload.get('token_id')
                    if token_id in self.active_auctions:
                        auction = self.active_auctions[token_id]
                        if auction.get("auction_type") == "direct_sale":
                            price = auction.get("price")
                            if self.world_state['agent_balances'].get(agent_id, 0) >= price:
                                seller = auction['seller_id']
                                msg = f"    - AUCTION RESOLVED (direct_sale): {agent_id} won {token_id} from {seller} for ${price:.2f}."
                                messages.append(msg)
                                resolution_tx = _finalize_direct_sale(token_id, auction, agent_id)
                                new_pending.append(resolution_tx)
                                self.active_auctions.pop(token_id)
                            else:
                                msg = f"    - BUY_NOW REJECTED for {token_id} from {agent_id} (insufficient balance)."
                                messages.append(msg)
                        else:
                            msg = f"    - BUY_NOW REJECTED for {token_id} from {agent_id} (auction type {auction.get('auction_type')} does not support direct sale)."
                            messages.append(msg)
                else:
                    # Generic transactions (could add tx_type for consistency if needed)
                    pass


        # 2. Resolve finished auctions
        auctions_to_resolve = list(self.active_auctions.keys())
        for token_id in auctions_to_resolve:
            auction = self.active_auctions[token_id]
            auction_type = auction.get('auction_type', self.auction_type)

            if auction_type == 'direct_sale':
                continue

            is_expired = current_block_index >= auction['end_block']
            if not is_expired:
                continue

            seller = auction['seller_id']
            reserve_price = auction['reserve_price']
            bids = auction['bids']
            valid_bids = [b for b in bids if b['amount'] >= reserve_price]

            # Determine minimum required valid bids: allow single-bid resolutions for first-price auctions
            min_required = 1 if auction_type == 'first_price' else 2

            if len(valid_bids) < min_required and current_block_index < auction['max_end_block']:
                auction['end_block'] += 1
                msg = f"    - AUCTION EXTENDED: Not enough bids for {token_id}. Extending to block {auction['end_block']}."
                messages.append(msg)
                continue

            self.active_auctions.pop(token_id)
            if len(valid_bids) < min_required:
                msg = f"    - AUCTION FAILED: Not enough valid bids for {token_id} after reaching max duration. Valid bids: {len(valid_bids)}."
                messages.append(msg)
                success = False
                winner, price = None, 0
            else:
                max_amount = max(b['amount'] for b in valid_bids)
                top_indices = [idx for idx, bid in enumerate(valid_bids) if bid['amount'] == max_amount]
                winner_idx = random.choice(top_indices)
                winner_bid = valid_bids[winner_idx]
                winner = winner_bid['bidder_id']
                highest_bid = winner_bid['amount']

                remaining_bids = [bid for idx, bid in enumerate(valid_bids) if idx != winner_idx]
                remaining_bids.sort(key=lambda x: x['amount'], reverse=True)

                if auction_type == 'first_price':
                    price = highest_bid
                else: # Second-price auction
                    # If only one valid bid in second-price, fall back to that bid amount
                    if remaining_bids:
                        price = remaining_bids[0]['amount']
                    else:
                        price = highest_bid

                msg = f"    - AUCTION RESOLVED ({auction_type}): {winner} won {token_id} from {seller} for ${price:.2f} (Highest bid was ${highest_bid:.2f}, Reserve was ${reserve_price:.2f})."
                messages.append(msg)
                self.world_state['agent_balances'][winner] -= price
                self.world_state['agent_balances'][seller] += price
                self.world_state['token_ownership'][token_id] = winner
                self.world_state['token_ownership_history'][token_id].append(winner)
                success = True

            resolution_tx = {
                "tx_type": "auction_resolution",
                "token_id": token_id,
                "seller_id": seller,
                "winner_id": winner,
                "final_price": price,
                "reserve_price": reserve_price,
                "tick_resolved": current_block_index,
                "timestamp": time.time(),
                "success": success,
                "bids": bids,
                "auction_type": auction_type,
                "creation_block": auction.get('creation_block')
            }
            # Collect the resolution to add to pending transactions so it appears
            # in the next block and is appended to `transaction_history` by `new_block()`.
            new_pending.append(resolution_tx)

        # Add any newly-created resolution transactions to pending so they are
        # included in the block but not processed in the same loop above.
        if new_pending:
            self.pending_transactions.extend(new_pending)

        # Snapshot active auctions AFTER processing & resolution
        active_snapshot = self.active_auctions
        self.new_block(active_snapshot=active_snapshot)
        return messages

    @staticmethod
    def hash(block: Block) -> str:
        block_string = json.dumps(block, sort_keys=True).encode()
        return hashlib.sha256(block_string).hexdigest()

    def get_last_block(self) -> Block:
        return self.chain[-1]

# --- FastAPI Server ---
blockchain = SpectrumBlockchain()
app = FastAPI()

@app.post("/initialize")
def initialize_simulation(config: SimulationConfig):
    """Initializes or resets the simulation with a given configuration."""
    blockchain.reset()
    blockchain.auction_type = config.auction_type
    spectrum_tokens_to_create = []
    for i in range(config.num_tokens):
        bandwidth = random.choice([5, 10, 15])
        spectrum_tokens_to_create.append({
            "token_id": f"token_{i}",
            "band": random.choice(["CBRS", "ISM 2.4GHz", "ISM 5GHz", "U-NII"]),
            "frequency_mhz": random.randint(2400, 5800),
            "bandwidth_mhz": bandwidth,
            "capacity": bandwidth,
            "location": f"sim_coord_{random.randint(1,5)}"
        })
    blockchain.spectrum_tokens = {t['token_id']: t for t in spectrum_tokens_to_create}
    agent_ids = [f"agent-{i}" for i in range(config.num_agents)]

    if config.agent_balances:
        blockchain.world_state["agent_balances"] = config.agent_balances
    else:
        for aid in agent_ids:
            blockchain.world_state["agent_balances"][aid] = round(random.uniform(500.0, 1500.0), 2)
    
    if config.token_ownership:
        blockchain.world_state["token_ownership"] = config.token_ownership
    else:
        token_ids = list(blockchain.spectrum_tokens.keys())
        random.shuffle(token_ids)
        for i, token_id in enumerate(token_ids):
            blockchain.world_state["token_ownership"][token_id] = agent_ids[i % config.num_agents]

    for token_id, owner in blockchain.world_state["token_ownership"].items():
        blockchain.world_state["token_ownership_history"][token_id] = [owner]
    
    return {"message": "Simulation initialized successfully."}

@app.post("/new_transaction")
def new_transaction(transaction: Transaction):
    blockchain.new_transaction(transaction)
    return {"message": f"Transaction added to pool. Pool size: {len(blockchain.pending_transactions)}"}

@app.post("/mine_block")
def mine_block():
    messages = blockchain.process_pending_transactions()
    return {"message": "New block forged", "block": blockchain.get_last_block(), "processing_messages": messages}

@app.get("/spectrum_tokens")
def get_spectrum_tokens():
    return blockchain.spectrum_tokens

@app.get("/active_auctions")
def get_active_auctions():
    return blockchain.active_auctions

@app.get("/full_chain")
def get_full_chain():
    return {"chain": blockchain.chain, "length": len(blockchain.chain)}

@app.get("/block/{index}/active_auctions")
def get_block_active_auctions(index: int):
    if index < 0 or index >= len(blockchain.chain):
        return {"error": "Block index out of range", "length": len(blockchain.chain)}
    block = blockchain.chain[index]
    return {"block_index": index, "active_auctions_snapshot": block.get("active_auctions_snapshot", {})}

@app.get("/world_state")
def get_world_state():
    return blockchain.world_state

@app.get("/transaction_history")
def get_transaction_history():
    return blockchain.transaction_history

if __name__ == "__main__":
    host = os.getenv("BLOCKCHAIN_HOST", "127.0.0.1")
    port = int(os.getenv("BLOCKCHAIN_PORT", "8000"))
    uvicorn.run(app, host=host, port=port, log_level="info")