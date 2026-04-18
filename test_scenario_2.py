import asyncio
import os
from run_simulation import run_test_scenario

# --- Simulation Parameters ---
SIMULATION_TICKS = 100
NUM_AGENTS = 4
NUM_TOKENS = 25
  
async def scenario_2_price_discovery():
    """Scenario 2: Price Discovery with a single seller and multiple EQUAL Utility buyers."""

    agent_configs = [
        # Seller Agent
        {
            "utility_per_mhz": 5, 
            "need_schedule": [0] * SIMULATION_TICKS,
        },
        # Buyer Agents
        {'utility_per_mhz': 20.0, "need_schedule": [100] * SIMULATION_TICKS, "need_volatility": 0},
        {'utility_per_mhz': 20.0, "need_schedule": [100] * SIMULATION_TICKS, "need_volatility": 0},
        {'utility_per_mhz': 20.0, "need_schedule": [100] * SIMULATION_TICKS, "need_volatility": 0},
    ]

    initial_balances = {
        "agent-0": 5000.0,
        "agent-1": 5000.0,
        "agent-2": 5000.0,
        "agent-3": 5000.0,
    }

    initial_ownership = {f"token_{i}": "agent-0" for i in range(NUM_TOKENS)}


    # --- Second-Price Auction ---
    scenario_name_second_price = "scenario_2_price_discovery_second_price"

    await run_test_scenario(
        scenario_name=scenario_name_second_price,
        num_agents=NUM_AGENTS,
        num_tokens=NUM_TOKENS,
        simulation_ticks=SIMULATION_TICKS,
        agent_configs=agent_configs,
        initial_balances=initial_balances,
        initial_ownership=initial_ownership,
        auction_type="second_price"
    )

    # --- First-Price Auction ---
    scenario_name_first_price = "scenario_2_price_discovery_first_price"

    await run_test_scenario(
        scenario_name=scenario_name_first_price,
        num_agents=NUM_AGENTS,
        num_tokens=NUM_TOKENS,
        simulation_ticks=SIMULATION_TICKS,
        agent_configs=agent_configs,
        initial_balances=initial_balances,
        initial_ownership=initial_ownership,
        auction_type="first_price"
    )

    # --- Direct Sale Auction ---
    scenario_name_direct_sale = "scenario_2_price_discovery_direct_sale"

    await run_test_scenario(
        scenario_name=scenario_name_direct_sale,
        num_agents=NUM_AGENTS,
        num_tokens=NUM_TOKENS,
        simulation_ticks=SIMULATION_TICKS,
        agent_configs=agent_configs,
        initial_balances=initial_balances,
        initial_ownership=initial_ownership,
        auction_type="direct_sale"
    )

if __name__ == "__main__":
    project_id = os.getenv("GOOGLE_CLOUD_PROJECT")
    if not project_id:
        raise RuntimeError(
            "GOOGLE_CLOUD_PROJECT is not set. Export your Google Cloud project ID before running this scenario."
        )

    os.environ.setdefault("GOOGLE_CLOUD_MODEL", "gemini-2.5-flash")
    print("--- Running Scenario 2: Price Discovery ---")
    asyncio.run(scenario_2_price_discovery())