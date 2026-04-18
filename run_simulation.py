# run_simulation.py

import warnings
warnings.filterwarnings("ignore")
import logging
logging.getLogger("google_genai.types").setLevel(logging.ERROR)

import asyncio
import time
import json
import os
import httpx
import subprocess
import atexit
import psutil
import sys
import re
from typing import List, Dict, Any

from dotenv import load_dotenv
load_dotenv()
load_dotenv(dotenv_path='spectrum_agent/.env')

from google.genai import types
from google.genai import errors as genai_errors
from google.adk.apps.app import App
from google.adk.runners import Runner
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from spectrum_agent.agent import CognitiveRadioAgent

# --- Simulation Configuration ---
BLOCKCHAIN_URL = os.getenv("BLOCKCHAIN_URL", "http://127.0.0.1:8000")

def kill_process_on_port(port):
    """Finds and kills a process running on a specific port."""
    for proc in psutil.process_iter(['pid', 'name']):
        try:
            for conn in proc.connections(kind='inet'):
                if conn.laddr.port == port:
                    print(f"Killing process {proc.pid} ({proc.name()}) on port {port}")
                    proc.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            pass

# --- Data Collection ---

def get_gini_coefficient(balances: List[float]) -> float:
    """Calculates the Gini coefficient for a list of balances."""
    if not balances or len(balances) < 2:
        return 0.0

    # Ensure all balances are non-negative
    if any(x < 0 for x in balances):
        # Or handle this case as an error, depending on requirements
        # For now, returning 0.0 as negative balances make Gini ambiguous
        return 0.0

    sorted_balances = sorted(balances)
    n = len(sorted_balances)
    total_balance = sum(sorted_balances)

    if total_balance == 0:
        return 0.0

    weighted_sum = sum(i * balance for i, balance in enumerate(sorted_balances, 1))
    
    # Using the formula: G = (2 * sum(i * y_i)) / (n * sum(y)) - (n + 1) / n
    gini = (2 * weighted_sum) / (n * total_balance) - (n + 1) / n
    
    return round(gini, 4)

def get_hhi(token_ownership: Dict[str, str]) -> float:
    """Calculates the Herfindahl-Hirschman Index for token ownership."""
    if not token_ownership:
        return 0
    owner_counts = {}
    for owner in token_ownership.values():
        owner_counts[owner] = owner_counts.get(owner, 0) + 1
    total_tokens = len(token_ownership)
    if total_tokens == 0:
        return 0
    hhi = sum([(count / total_tokens) ** 2 for count in owner_counts.values()])
    return round(hhi, 4)

def get_spectrum_utilization(agents: List[CognitiveRadioAgent]) -> Dict[str, Any]:
    """Calculates spectrum utilization metrics across all agents."""
    total_need = sum(agent.state.get('current_spectrum_need', 0) for agent in agents)
    total_owned_capacity = sum(agent.state.get('owned_capacity', 0) for agent in agents)
    utilization_percentage = (total_owned_capacity / total_need) * 100 if total_need > 0 else 0

    agent_details = {
        agent.name.replace("_", "-"):
        {
            'need': agent.state.get('current_spectrum_need', 0),
            'owned': agent.state.get('owned_capacity', 0),
            'gap': agent.state.get('spectrum_gap', 0)
        } for agent in agents
    }

    return {
        "total_spectrum_need": total_need,
        "total_owned_capacity": total_owned_capacity,
        "system_utilization_percentage": round(utilization_percentage, 2),
        "agent_utilization_details": agent_details
    }

# --- Simulation Runner ---

async def run_tick_for_agent(
    agent: CognitiveRadioAgent,
    tick_num: int,
    runner,
    session,
    max_retries: int = 3,
    base_retry_delay: float = 5.0,
):
    """Runs a single simulation tick for one agent with retry handling for transient LLM failures."""

    attempt = 0
    while attempt < max_retries:
        attempt += 1
        try:
            async for _ in runner.run_async(
                user_id=session.user_id,
                session_id=session.id,
                new_message=types.Content(
                    role='user', parts=[types.Part(text=f"Tick {tick_num}: Evaluate and act.")]
                ),
            ):
                pass
            return
        except (genai_errors.ServerError, genai_errors.APIError) as exc:
            if attempt < max_retries:
                delay = base_retry_delay * attempt
                print(
                    f"  [{agent.blockchain_agent_name}] LLM call failed ({exc.__class__.__name__}: {exc}). "
                    f"Retrying in {delay:.1f}s (attempt {attempt}/{max_retries})."
                )
                await asyncio.sleep(delay)
            else:
                message = (
                    f"LLM service unavailable after {max_retries} attempts; holding position this tick."
                )
                print(f"  [{agent.blockchain_agent_name}] {message}")
                agent.record_no_action(message)
                return
        except Exception as exc:
            message = f"Unexpected agent error: {exc}. Holding position."
            print(f"  [{agent.blockchain_agent_name}] {message}")
            agent.record_no_action(message)
            return

async def run_test_scenario(scenario_name: str, num_agents: int, num_tokens: int, simulation_ticks: int, agent_configs: List[Dict[str, Any]], auction_type: str = "second_price", initial_balances: Dict[str, float] = None, initial_ownership: Dict[str, str] = None):
    """Instantiates and runs a multi-agent simulation for a specific test scenario."""
    
    server_process = None
    blockchain_log_file = None
    try:
        # --- Setup ---
        kill_process_on_port(8000)
        os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "true")
        if not os.environ.get("GOOGLE_CLOUD_PROJECT"):
            print("FATAL: GOOGLE_CLOUD_PROJECT environment variable not set.")
            return
        os.environ.setdefault("GOOGLE_CLOUD_LOCATION", "global")

        print(f"--- Starting Test Scenario: {scenario_name} ---")
        
        blockchain_log_file = open("blockchain.log", "w")
        server_process = subprocess.Popen([sys.executable, "-u", "main.py"], stdout=blockchain_log_file, stderr=subprocess.STDOUT)

        # Wait for the server to be. ready
        max_retries = 5
        retry_delay = 5
        for i in range(max_retries):
            try:
                response = httpx.get(f"{BLOCKCHAIN_URL}/world_state")
                if response.status_code == 200:
                    print("Blockchain server is ready.")
                    break
            except httpx.RequestError:
                pass
            print(f"Waiting for blockchain server... attempt {i+1}/{max_retries}")
            time.sleep(retry_delay)
        else:
            print("FATAL: Blockchain server did not start.")
            return

        # --- Initialization ---
        init_config = {
            "num_agents": num_agents,
            "num_tokens": num_tokens,
            "agent_balances": initial_balances,
            "token_ownership": initial_ownership,
            "auction_type": auction_type
        }
        try:
            httpx.post(f"{BLOCKCHAIN_URL}/initialize", json=init_config, timeout=20)
            spectrum_tokens = httpx.get(f"{BLOCKCHAIN_URL}/spectrum_tokens").json()
        except httpx.RequestError as e:
            print(f"FATAL: Could not initialize blockchain server: {e}")
            return

        session_service = InMemorySessionService()
        agents = [CognitiveRadioAgent(name=f"agent_{i}", auction_type=auction_type, **agent_configs[i]) for i in range(num_agents)]
        for agent in agents:
            agent.set_token_catalog(spectrum_tokens)
        
        apps = [App(name=f"spectrum_sim_{agent.name}", root_agent=agent) for agent in agents]
        runners = [Runner(app=app, session_service=session_service) for app in apps]

        log_data = []
        try:
            chain_info = httpx.get(f"{BLOCKCHAIN_URL}/full_chain", timeout=10).json()
            last_committed_block_index = chain_info.get("chain", [])[-1]["index"] if chain_info.get("chain") else 0
        except Exception:
            last_committed_block_index = 0
        # Track how many transaction-history entries we've already seen
        last_tx_index = 0

        # --- Main Loop ---
        for tick in range(simulation_ticks):
            print(f"\n--- Tick {tick + 1} ---")
            # Fetch shared perception data once per tick
            try:
                shared_world_state = httpx.get(f"{BLOCKCHAIN_URL}/world_state", timeout=10).json()
            except httpx.RequestError as exc:
                print(f"ERROR: Could not refresh world state before tick {tick + 1}: {exc}")
                shared_world_state = {}
            try:
                shared_history = httpx.get(f"{BLOCKCHAIN_URL}/transaction_history", timeout=15).json()
            except httpx.RequestError as exc:
                print(f"ERROR: Could not refresh transaction history before tick {tick + 1}: {exc}")
                shared_history = []
            auction_snapshot = {}
            if last_committed_block_index is not None:
                try:
                    snapshot_res = httpx.get(
                        f"{BLOCKCHAIN_URL}/block/{last_committed_block_index}/active_auctions",
                        timeout=10,
                    )
                    snapshot_res.raise_for_status()
                    auction_snapshot = snapshot_res.json().get("active_auctions_snapshot", {}) or {}
                except (httpx.RequestError, httpx.HTTPStatusError):
                    auction_snapshot = {}
            # Reset the action lock and set the current tick for each agent
            for agent in agents:
                agent.action_taken_this_tick = False
                agent.current_tick = tick + 1
                agent.last_committed_block_index = last_committed_block_index
                agent.preload_perception(shared_world_state, shared_history, auction_snapshot)
                agent.prepare_for_tick()

            sessions = await asyncio.gather(
                *[
                    session_service.create_session(
                        app_name=apps[i].name,
                        user_id=f"user_{agents[i].name}",
                        session_id=f"{agents[i].name}_tick_{tick + 1}",
                    )
                    for i in range(num_agents)
                ]
            )
            agent_tasks = [run_tick_for_agent(agents[i], tick + 1, runners[i], sessions[i]) for i in range(num_agents)]
            await asyncio.gather(*agent_tasks)

            await asyncio.gather(
                *[
                    session_service.delete_session(
                        app_name=apps[i].name,
                        user_id=f"user_{agents[i].name}",
                        session_id=sessions[i].id,
                    )
                    for i in range(num_agents)
                ]
            )
            
            try:
                response = httpx.post(f"{BLOCKCHAIN_URL}/mine_block", timeout=20)
                response.raise_for_status()
                mining_data = response.json()
                print("  [Blockchain] Mined a new block.")
                block_info = mining_data.get("block", {})
                if block_info:
                    last_committed_block_index = block_info.get("index", last_committed_block_index)
                
                world_state = httpx.get(f"{BLOCKCHAIN_URL}/world_state").json()
                balances = list(world_state.get('agent_balances', {}).values())
                
                # Log data for the tick
                # Use the structured block transactions and authoritative transaction history
                transactions = []
                auctions_started = []
                bids = []
                rejected_bids = []

                # 1) Parse structured transactions included in the newly-mined block
                block = mining_data.get("block", {}) or {}
                for tx in block.get("transactions", []):
                    # Some legacy entries may not have 'tx_type' set; fall back to 'capability'
                    tx_type = tx.get("tx_type") or tx.get("capability")
                    if tx_type == "start_auction":
                        token_id = tx["payload"].get("token_id")
                        price = tx["payload"].get("price")
                        token_info = spectrum_tokens.get(token_id, {})
                        auctions_started.append({
                            "token_id": token_id,
                            "agent_id": tx.get("agent_id"),
                            "reserve_price": price,
                            "token_size_mhz": token_info.get("capacity")
                        })
                    elif tx_type == "place_bid":
                        payload = tx.get("payload", {})
                        # Only include accepted bids (phantom bids removed)
                        if tx.get("accepted", True):
                            bids.append({
                                "token_id": payload.get("token_id"),
                                "agent_id": tx.get("agent_id"),
                                "bid_amount": payload.get("bid_amount")
                            })
                        else:
                            rejected_bids.append({
                                "token_id": payload.get("token_id"),
                                "agent_id": tx.get("agent_id"),
                                "bid_amount": payload.get("bid_amount"),
                                "accepted": False,
                                "rejection_reason": tx.get("rejection_reason")
                            })

                # 2) Fetch authoritative transaction history and extract any new auction resolutions
                try:
                    tx_history = httpx.get(f"{BLOCKCHAIN_URL}/transaction_history").json()
                except Exception:
                    tx_history = []

                # Process only the new entries since last tick
                new_tx_entries = tx_history[last_tx_index:]
                for tx in new_tx_entries:
                    if tx.get("tx_type") == "auction_resolution":
                        # Map the blockchain's resolution record directly into our logged transactions
                        transactions.append({
                            "buyer": tx.get("winner_id"),
                            "seller": tx.get("seller_id"),
                            "token": tx.get("token_id"),
                            "price": tx.get("final_price"),
                            "reserve_price": tx.get("reserve_price"),
                            "highest_bid": None if not tx.get("bids") else max((b.get("amount") for b in tx.get("bids", [])), default=None),
                            "auction_type": tx.get("auction_type")
                        })

                # Update the last seen index
                try:
                    last_tx_index = len(tx_history)
                except Exception:
                    last_tx_index = last_tx_index

                # Collect decision events from all agents
                agent_decisions = []
                for agent in agents:
                    if agent.last_decision_event:
                        agent_decisions.append(agent.last_decision_event)

                tick_log = {
                    "tick": tick + 1,
                    "gini_coefficient": get_gini_coefficient(balances),
                    "hhi": get_hhi(world_state.get('token_ownership', {})),
                    "auctions_resolved": len([m for m in mining_data.get("processing_messages", []) if "AUCTION RESOLVED" in m or "AUCTION FAILED" in m]),
                    "successful_auctions": len([m for m in mining_data.get("processing_messages", []) if "won" in m]),
                    "agent_balances": world_state.get('agent_balances'),
                    "token_ownership": world_state.get('token_ownership'),
                    "spectrum_utilization": get_spectrum_utilization(agents),
                    "auctions_started": auctions_started,
                    "transactions": transactions,
                    "bids": bids,
                    "rejected_bids": rejected_bids,
                    "active_auctions_snapshot": block.get("active_auctions_snapshot", {}),
                    "agent_decisions": agent_decisions
                }
                log_data.append(tick_log)

            except httpx.RequestError as e:
                print(f"ERROR: Could not trigger mining: {e}")
            except json.JSONDecodeError:
                print("ERROR: Failed to decode JSON response from mining endpoint.")

        # --- Final Reporting ---
        print(f"\n--- Test Scenario {scenario_name} Complete ---")
        
        results = {
            "agent_configs": agent_configs,
            "scenario_results": log_data,
            "spectrum_tokens": spectrum_tokens
        }

        log_filename = f"./{scenario_name}_results.json"
        with open(log_filename, 'w') as f:
            json.dump(results, f, indent=2)
        print(f"Results saved to {log_filename}")

        # --- Save Full Blockchain History ---
        try:
            blockchain_history = httpx.get(f"{BLOCKCHAIN_URL}/full_chain").json()
            blockchain_log_filename = f"./{scenario_name}_blockchain.json"
            with open(blockchain_log_filename, 'w') as f:
                json.dump(blockchain_history, f, indent=2)
            print(f"Full blockchain history saved to {blockchain_log_filename}")
        except httpx.RequestError as e:
            print(f"ERROR: Could not retrieve full blockchain history: {e}")
        except json.JSONDecodeError:
            print("ERROR: Failed to decode JSON response from full_chain endpoint.")



    finally:
        if server_process:
            server_process.terminate()
            server_process.wait()
        if blockchain_log_file:
            blockchain_log_file.close()

if __name__ == "__main__":
    print("This script is not meant to be run directly. Please use a test scenario script.")
