import json
import random
import time
from textwrap import dedent
from typing import Any, Dict, List, Optional

import httpx
import os

from google.adk import Agent
from google.adk.agents.callback_context import CallbackContext
from google.adk.agents.readonly_context import ReadonlyContext
from google.adk.agents.sequential_agent import SequentialAgent
from google.adk.planners.built_in_planner import BuiltInPlanner
from google.adk.tools import FunctionTool
from google.genai.types import ThinkingConfig
from pydantic import PrivateAttr

# --- Configuration ---
BLOCKCHAIN_URL = os.getenv("BLOCKCHAIN_URL", "http://127.0.0.1:8000")

VERBOSE_AGENT_LOGS = os.getenv("VERBOSE_AGENT_LOGS", "0").lower() in {"1", "true", "yes", "on"}


def _log_verbose(message: str) -> None:
    if VERBOSE_AGENT_LOGS:
        print(message)


class HistoricalAnalyzerStage(Agent):
    _coordinator: "CognitiveRadioAgent" = PrivateAttr()
    """Stage 1: inspect blockchain history and log profitability signals."""

    def __init__(self, coordinator: "CognitiveRadioAgent") -> None:
        super().__init__(
            name=f"{coordinator.agent_label}_historical_analyzer",
            description="Reviews recent auction resolutions and records profitability metrics.",
            instruction=self._instruction,
            model=coordinator.model_name,
            planner=BuiltInPlanner(thinking_config=ThinkingConfig(include_thoughts=False)),
            tools=[FunctionTool(coordinator.record_historical_analysis)],
        )
        self._coordinator = coordinator

    @property
    def coordinator(self) -> "CognitiveRadioAgent":
        return self._coordinator

    def _instruction(self, context: ReadonlyContext) -> str:
        history_context = self.coordinator.get_history_context()
        payload = json.dumps(history_context, indent=2)
        _log_verbose(
            f"  [{self.coordinator.agent_label}] Stage 1 - Historical Analyzer: reviewing recent outcomes for tick {self.coordinator.current_tick}"
        )
        return dedent(
            f"""
            You are the Historical Analyzer stage for agent {self.coordinator.agent_label}.
            Review the structured blockchain data below and quantify how profitable our recent
            participation has been.

            DATA:
            {payload}

            Tasks:
            1. Focus on `agent_recent_transactions` to compute realized profit per win.
            2. Identify whether competitor bids appear homogeneous or dispersed using
               `recent_price_samples` and `recent_winning_bids`.
            3. Summarize at most three concise competitor signals (e.g., "all bids at $20/MHz").

            After reasoning, you MUST call `record_historical_analysis` with:
              - avg_profit_per_win (float, USD; 0 if no wins)
              - win_rate (0-1)
              - observed_bid_range (short string describing min/max bids)
              - competitor_signals (list[str])
              - notes (single sentence rationale)

            Only after calling the tool, provide a one-sentence natural-language recap.
            """
        )


class MarketHypothesisStage(Agent):
    _coordinator: "CognitiveRadioAgent" = PrivateAttr()
    """Stage 2: infer market structure from historical insights."""

    def __init__(self, coordinator: "CognitiveRadioAgent") -> None:
        super().__init__(
            name=f"{coordinator.agent_label}_market_hypothesis",
            description="Classifies the market as homogeneous or heterogeneous and logs confidence.",
            instruction=self._instruction,
            model=coordinator.model_name,
            planner=BuiltInPlanner(thinking_config=ThinkingConfig(include_thoughts=False)),
            tools=[FunctionTool(coordinator.record_market_hypothesis)],
        )
        self._coordinator = coordinator

    @property
    def coordinator(self) -> "CognitiveRadioAgent":
        return self._coordinator

    def _instruction(self, context: ReadonlyContext) -> str:
        history_summary = self.coordinator.pipeline_memory.get("historical_analysis", {})
        decision_context = self.coordinator.get_decision_context(include_history=False)
        payload = json.dumps(
            {
                "historical_analysis": history_summary,
                "current_state": decision_context,
            },
            indent=2,
        )
        _log_verbose(
            f"  [{self.coordinator.agent_label}] Stage 2 - Market Hypothesis: classifying market conditions for tick {self.coordinator.current_tick}"
        )
        return dedent(
            f"""
            You are the Market Hypothesis stage for agent {self.coordinator.agent_label}.
            Use the recorded historical analysis plus current state to infer the competitive landscape.

            DATA:
            {payload}

            Tasks:
            1. Decide whether the market is homogeneous (everyone bids the same), heterogeneous,
               or uncertain due to limited evidence.
            2. Assess strategic risk (e.g., "zero-profit second-price trap").

            After reasoning, you MUST call `record_market_hypothesis` with:
              - market_type ("homogeneous", "heterogeneous", or "uncertain")
              - confidence (0-1 float)
              - rationale (concise explanation)
              - risk_assessment (short description of risk or opportunity)

            Provide one short textual confirmation after the tool call.
            """
        )


class DecisionRouterStage(Agent):
    _coordinator: "CognitiveRadioAgent" = PrivateAttr()
    """Stage 3: choose whether to buy, sell, or stay idle."""

    def __init__(self, coordinator: "CognitiveRadioAgent") -> None:
        super().__init__(
            name=f"{coordinator.agent_label}_decision_router",
            description="Determines intent (buy, sell, idle) before specialized planners run.",
            instruction=self._instruction,
            model=coordinator.model_name,
            planner=BuiltInPlanner(
                thinking_config=ThinkingConfig(
                    include_thoughts=True,
                )
            ),
            tools=[FunctionTool(coordinator.record_strategy_directive)],
        )
        self._coordinator = coordinator

    @property
    def coordinator(self) -> "CognitiveRadioAgent":
        return self._coordinator

    def _instruction(self, context: ReadonlyContext) -> str:
        decision_context = self.coordinator.get_decision_context()
        payload = json.dumps(
            {
                "decision_context": decision_context,
                "historical_analysis": self.coordinator.pipeline_memory.get("historical_analysis", {}),
                "market_hypothesis": self.coordinator.pipeline_memory.get("market_hypothesis", {}),
            },
            indent=2,
        )
        _log_verbose(
            f"  [{self.coordinator.agent_label}] Stage 3 - Decision Router: selecting intent for tick {self.coordinator.current_tick}"
        )
        return dedent(
            f"""
            You are the Decision Router stage for agent {self.coordinator.agent_label}.
            Decide whether the agent should BUY, SELL, or remain IDLE this tick and provide
            candidate tokens for downstream planners.

            DATA:
            {payload}

            Guidelines:
                        - Think step-by-step. First, measure demand (spectrum_gap & urgency), then supply (owned tokens, active listings), then historical performance, and finally wallet/balance feasibility.
                        - Trace every inference back to the structured data; chain through historical_analysis, market_hypothesis, and current auctions before deciding.
            - If perception_error is true or there are no viable actions, choose intent="idle".
            - When the spectrum_gap_mhz is positive and balance is sufficient, prefer intent="buy".
            - When our spectrum gap minus the number of active listings is zero or negative and we hold surplus tokens, prefer intent="sell".
            - Use market_hypothesis + historical signals to set urgency ("low", "normal", "high").
            - Provide `candidate_tokens` (token ids) that best match the intent (auctions worth buying or tokens we can list).
            - `preferred_action` should hint whether planners should bid, buy_now, or start_auction.
                        - Before calling the tool, explicitly summarize (internally) how each data slice influenced the choice so the downstream planners inherit a well-justified directive.

            After reasoning, call `record_strategy_directive` with:
              - intent ("buy", "sell", or "idle")
              - urgency ("low", "normal", or "high")
              - candidate_tokens (list[str])
              - preferred_action ("place_bid", "buy_now", "start_auction", or "no_action")
              - notes (short justification)

            The downstream planners rely on this directive; be decisive.
            """
        )


class BuyerPlannerStage(Agent):
    _coordinator: "CognitiveRadioAgent" = PrivateAttr()
    """Stage 4: craft buy-side bids based on the router directive."""

    def __init__(self, coordinator: "CognitiveRadioAgent") -> None:
        super().__init__(
            name=f"{coordinator.agent_label}_buyer_planner",
            description="Generates buy-side plans (bid or buy-now).",
            instruction=self._instruction,
            model=coordinator.model_name,
            planner=BuiltInPlanner(thinking_config=ThinkingConfig(include_thoughts=False)),
            tools=[FunctionTool(coordinator.record_strategy_plan)],
        )
        self._coordinator = coordinator

    @property
    def coordinator(self) -> "CognitiveRadioAgent":
        return self._coordinator

    def _instruction(self, context: ReadonlyContext) -> str:
        decision_context = self.coordinator.get_decision_context()
        directive = self.coordinator.ensure_strategy_directive()
        payload = json.dumps(
            {
                "decision_context": decision_context,
                "strategy_directive": directive,
            },
            indent=2,
        )
        _log_verbose(
            f"  [{self.coordinator.agent_label}] Stage 4 - Buyer Planner: evaluating purchases for tick {self.coordinator.current_tick}"
        )
        return dedent(
            f"""
            You are the Buyer Planner stage for agent {self.coordinator.agent_label}.
            Only act when `strategy_directive.intent == "buy"`. If the intent is not "buy",
            respond with the single word SKIP and do not call any tool.

            DATA:
            {payload}

            Guidelines when intent == "buy":
            - Respect balance constraints, avoid bidding twice on the same auction, and obey `candidate_tokens`.
            - Profit is the goal: explicitly maximize surplus = valuation - expected payment, and never submit a bid or buy_now price above your valuation (that locks in negative utility).
            - For first_price auctions, shade bids below valuation based on competitive pressure (use historical signals) so the expected payment stays comfortably below valuation.
            - For second_price auctions, bid near valuation since payment equals the second price.
            - For direct_sale mode, prefer `buy_now` immediately when listing price <= valuation and spectrum gap exists.
            - If no viable auction fits, fall back to no_action with a reason.
            - Always reason about expected surplus. In first_price auctions, bidding your full valuation yields zero profit, so articulate how much profit you expect and why that bid still wins given observed competition.
            - Use historical_analysis.recent_winning_bids and market_hypothesis.risk_assessment to calibrate how aggressively to shade; cite those signals in your justification.
            - Do not approve a plan that produces non-positive expected profit unless urgency is "high" and you explain why breaking even is acceptable; if urgency is "high" you still must keep bids <= valuation.

            After reasoning, call `record_strategy_plan` with action_type ("place_bid" or "buy_now"),
            token_id, bid_amount/reserve_price as needed, urgency, and a concise reason.
            """
        )


class SellerPlannerStage(Agent):
    _coordinator: "CognitiveRadioAgent" = PrivateAttr()
    """Stage 5: craft sell-side listings/reserves based on router directive."""

    def __init__(self, coordinator: "CognitiveRadioAgent") -> None:
        super().__init__(
            name=f"{coordinator.agent_label}_seller_planner",
            description="Generates sell-side plans (start_auction listings).",
            instruction=self._instruction,
            model=coordinator.model_name,
            planner=BuiltInPlanner(thinking_config=ThinkingConfig(include_thoughts=False)),
            tools=[FunctionTool(coordinator.record_strategy_plan)],
        )
        self._coordinator = coordinator

    @property
    def coordinator(self) -> "CognitiveRadioAgent":
        return self._coordinator

    def _instruction(self, context: ReadonlyContext) -> str:
        decision_context = self.coordinator.get_decision_context()
        directive = self.coordinator.ensure_strategy_directive()
        payload = json.dumps(
            {
                "decision_context": decision_context,
                "strategy_directive": directive,
            },
            indent=2,
        )
        _log_verbose(
            f"  [{self.coordinator.agent_label}] Stage 5 - Seller Planner: evaluating listings for tick {self.coordinator.current_tick}"
        )
        return dedent(
            f"""
            You are the Seller Planner stage for agent {self.coordinator.agent_label}.
            Only act when `strategy_directive.intent == "sell"`. If the intent is not "sell",
            respond with the single word SKIP and do not call any tool.

            DATA:
            {payload}

            Guidelines when intent == "sell":
            - List only tokens we own and avoid duplicating active listings.
            - Use valuations + market price data to set reserve_price; direct_sale mode should
              publish at least one token when none are listed.
            - Prefer the token IDs suggested via `candidate_tokens`; if none are viable, choose any surplus token.
            - If no token can be listed safely, fall back to a no_action plan that explains the blocker.

            After reasoning, call `record_strategy_plan` with action_type="start_auction", token_id,
            reserve_price, urgency, and a brief reason aligned with the directive.
            """
        )


class ActionExecutorStage(Agent):
    _coordinator: "CognitiveRadioAgent" = PrivateAttr()
    """Stage 4: execute the chosen action via blockchain tools."""

    def __init__(self, coordinator: "CognitiveRadioAgent") -> None:
        super().__init__(
            name=f"{coordinator.agent_label}_action_executor",
            description="Executes the finalized plan with blockchain tool calls.",
            instruction=self._instruction,
            model=coordinator.model_name,
            planner=BuiltInPlanner(thinking_config=ThinkingConfig(include_thoughts=False)),
            tools=[
                FunctionTool(coordinator.start_auction),
                FunctionTool(coordinator.place_bid),
                FunctionTool(coordinator.buy_now),
                FunctionTool(coordinator.record_no_action),
            ],
        )
        self._coordinator = coordinator

    @property
    def coordinator(self) -> "CognitiveRadioAgent":
        return self._coordinator

    def _instruction(self, context: ReadonlyContext) -> str:
        action_context = self.coordinator.get_action_context()
        payload = json.dumps(action_context, indent=2)
        _log_verbose(
            f"  [{self.coordinator.agent_label}] Stage 6 - Action Executor: executing planned action for tick {self.coordinator.current_tick}"
        )
        return dedent(
            f"""
            You are the Action Executor stage for agent {self.coordinator.agent_label}.
            Use the structured context plus the recorded plan to take exactly one action.

            DATA:
            {payload}

            Guidelines:
            - Follow `strategy_plan.action_type` unless it is infeasible. If infeasible, explain why
              and call `record_no_action` to log the reason.
            - Validate ownership before `start_auction`, budget before `place_bid`, and affordability
              before `buy_now`.
            - Never act twice. After calling a tool, provide a short confirmation sentence.
            - If the plan is no_action or perception_error is true, call `record_no_action` describing
              the blocker.
            """
        )


class ConsolidatedAnalystStage(Agent):
    _coordinator: "CognitiveRadioAgent" = PrivateAttr()
    """Stage 1 (Consolidated): inspect blockchain history and infer market structure."""

    def __init__(self, coordinator: "CognitiveRadioAgent") -> None:
        super().__init__(
            name=f"{coordinator.agent_label}_consolidated_analyst",
            description="Reviews history and classifies market conditions in one step.",
            instruction=self._instruction,
            model=coordinator.model_name,
            planner=BuiltInPlanner(thinking_config=ThinkingConfig(include_thoughts=False)),
            tools=[FunctionTool(coordinator.record_consolidated_analysis)],
        )
        self._coordinator = coordinator

    @property
    def coordinator(self) -> "CognitiveRadioAgent":
        return self._coordinator

    def _instruction(self, context: ReadonlyContext) -> str:
        history_context = self.coordinator.get_history_context()
        decision_context = self.coordinator.get_decision_context(include_history=False)
        payload = json.dumps(
            {
                "history": history_context,
                "current_state": decision_context,
            },
            indent=2,
        )
        _log_verbose(
            f"  [{self.coordinator.agent_label}] Stage 1 - Consolidated Analyst: analyzing market for tick {self.coordinator.current_tick}"
        )
        return dedent(
            f"""
            You are the Consolidated Analyst for agent {self.coordinator.agent_label}.
            Analyze the blockchain data to quantify profitability AND classify the market structure.

            DATA:
            {payload}

            Tasks:
            1. Compute realized profit per win and win rate from `agent_recent_transactions`.
            2. For First-Price Auctions: Analyze the distribution of `recent_winning_bids` to help the planner estimate the probability of winning at different bid levels.
            3. For Direct-Sale (Buy-Now): Identify "Demand Fading" by checking if your previous listings in `agent_recent_outcomes` failed to sell (role="seller", no transaction success or low price).
            4. Classify the market (homogeneous/heterogeneous) and assess risk.

            After reasoning, you MUST call `record_consolidated_analysis` with:
              - avg_profit_per_win (float)
              - win_rate (float)
              - observed_bid_range (str)
              - competitor_signals (list[str])
              - market_type (str)
              - confidence (float)
              - rationale (str)
              - risk_assessment (str)

            Provide a one-sentence recap after the tool call.
            """
        )


class ConsolidatedPlannerStage(Agent):
    _coordinator: "CognitiveRadioAgent" = PrivateAttr()
    """Stage 2 (Consolidated): decide intent and craft the specific plan."""

    def __init__(self, coordinator: "CognitiveRadioAgent") -> None:
        super().__init__(
            name=f"{coordinator.agent_label}_consolidated_planner",
            description="Decides intent and generates the specific action plan.",
            instruction=self._instruction,
            model=coordinator.model_name,
            planner=BuiltInPlanner(thinking_config=ThinkingConfig(include_thoughts=True)),
            tools=[FunctionTool(coordinator.record_strategy_plan)],
        )
        self._coordinator = coordinator

    @property
    def coordinator(self) -> "CognitiveRadioAgent":
        return self._coordinator

    def _instruction(self, context: ReadonlyContext) -> str:
        decision_context = self.coordinator.get_decision_context()
        payload = json.dumps(
            {
                "decision_context": decision_context,
                "analysis": self.coordinator.pipeline_memory.get("consolidated_analysis", {}),
            },
            indent=2,
        )
        _log_verbose(
            f"  [{self.coordinator.agent_label}] Stage 2 - Consolidated Planner: planning action for tick {self.coordinator.current_tick}"
        )
        return dedent(
            f"""
            You are the Consolidated Planner for agent {self.coordinator.agent_label}.
            Decide on a strategy (BUY, SELL, or IDLE) based on Game Theoretical Optima.

            DATA:
            {payload}

            Guidelines:
            1. **Determine Intent**:
               - If spectrum_gap > 0 and balance is sufficient -> BUY.
               - If spectrum_gap <= 0 and owned_tokens > 0 -> SELL.
               - Else -> IDLE.

            2. **Formulate Plan based on Auction Type**:
               - **IF FIRST_PRICE AUCTION**:
                 - **Cold Start**: If less than 5 recent winning bids are visible, use Symmetric Nash Equilibrium: Bid `0.67 * valuation` (assuming N=3 competitors).
                 - **Learning**: If history exists, estimate the empirical probability of winning P(win|b) from `recent_winning_bids`. Choose bid `b` that maximizes `(valuation - b) * P(win|b)`.
                 - **Constraint**: Bid must NEVER exceed valuation.

               - **IF SECOND_PRICE (VICKREY) AUCTION**:
                 - **Dominant Strategy**: Bid exactly your `valuation` (or very close to it).
                 - Do not shade bids; learning history does not improve payoff in Second-Price.

               - **IF DIRECT_SALE (BUY_NOW)**:
                 - **Buying**: Buy immediately if `listing_price <= valuation`.
                 - **Selling (Price Skimming)**:
                    - If listing a token for the first time, set a HIGH reserve price (e.g., 1.5 * valuation) to capture surplus from high-value buyers.
                    - If a token failed to sell in previous ticks (check analysis), lower the price (e.g., by 15%) to find the demand curve.
                    - Stop lowering if price would fall below `valuation` (break-even).

            3. **Safety Guardrails**:
               - Never bid more than your valuation (negative profit).
               - Never bid more than your available balance.

            After reasoning, call `record_strategy_plan` with:
              - action_type ("place_bid", "buy_now", "start_auction", "no_action")
              - token_id (optional)
              - bid_amount (optional)
              - reserve_price (optional)
              - urgency ("low", "normal", "high")
              - reason (concise justification referencing the strategy used)
            """
        )


class CognitiveRadioAgent(SequentialAgent):
    need_schedule: Optional[List[int]] = None
    need_volatility: float = 0.0
    state: Dict[str, Any] = {}
    current_tick: int = 0
    action_taken_this_tick: bool = False
    utility_per_mhz: float = 10.0
    auction_type: str = "second_price"
    last_decision_event: Optional[Dict[str, Any]] = None
    model_name: str = "gemini-2.5-flash"
    agent_label: str = ""
    pipeline_memory: Dict[str, Any] = {}
    last_committed_block_index: int = 0

    def __init__(self, **data: Any) -> None:
        super().__init__(**data)

        # Respect explicit model_name first, then environment override, then safe default.
        if "model_name" not in data:
            self.model_name = os.getenv("GOOGLE_CLOUD_MODEL", self.model_name)
        if not self.model_name:
            self.model_name = "gemini-2.5-flash"

        if self.need_schedule is None:
            self.need_schedule = [random.randint(10, 100)]

        self.state = {
            "my_tokens": [],
            "balance": 0.0,
            "current_spectrum_need": self.need_schedule[0],
            "owned_capacity": 0.0,
            "spectrum_gap": 0.0,
            "auctions_bid_on": [],
            "average_market_price_per_mhz": 0.0,
            "active_auctions": {},
            "all_tokens_info": {},
            "transaction_history_snapshot": [],
            "recent_agent_transactions": [],
            "recent_price_samples": [],
            "recent_winning_bids": [],
            "agent_recent_outcomes": [],
            "perception_error": False,
        }
        self.pipeline_memory = {}
        self.action_taken_this_tick = False
        self.current_tick = 0
        self.last_decision_event = None
        self.agent_label = self.name
        self._last_prepared_tick = 0
        self._last_state_reset_tick = 0
        self._static_tokens: Dict[str, Any] = {}
        self._preloaded_world_state: Optional[Dict[str, Any]] = None
        self._preloaded_history: Optional[List[Dict[str, Any]]] = None
        self._preloaded_snapshot: Optional[Dict[str, Any]] = None

        self.sub_agents = [
            ConsolidatedAnalystStage(self),
            ConsolidatedPlannerStage(self),
            ActionExecutorStage(self),
        ]
        self.before_agent_callback = self._before_agent_callback
        self.after_agent_callback = self._after_agent_callback

    def set_token_catalog(self, tokens: Dict[str, Any]) -> None:
        self._static_tokens = tokens or {}

    def preload_perception(
        self,
        world_state: Optional[Dict[str, Any]] = None,
        transaction_history: Optional[List[Dict[str, Any]]] = None,
        auction_snapshot: Optional[Dict[str, Any]] = None,
    ) -> None:
        if world_state is not None:
            self._preloaded_world_state = world_state
        if transaction_history is not None:
            self._preloaded_history = transaction_history
        if auction_snapshot is not None:
            self._preloaded_snapshot = auction_snapshot

    def _before_agent_callback(self, callback_context: CallbackContext, **_) -> None:
        self._reset_sequential_state(callback_context)

    def _reset_sequential_state(self, callback_context: CallbackContext) -> None:
        invocation_context = getattr(callback_context, "_invocation_context", None)
        if not invocation_context:
            return
        if getattr(self, "_last_state_reset_tick", None) == self.current_tick:
            return
        invocation_context.set_agent_state(self.name)
        invocation_context.reset_sub_agent_states(self.name)
        self._last_state_reset_tick = self.current_tick

    def prepare_for_tick(self) -> None:
        if self.current_tick == getattr(self, "_last_prepared_tick", None):
            return
        self._last_prepared_tick = self.current_tick
        self._reset_pipeline_memory()
        self._prepare_no_action_event()
        perception_ok = self._refresh_world_state()
        self.state["perception_error"] = not perception_ok

    def _after_agent_callback(self, callback_context: CallbackContext, **_) -> None:
        if self.last_decision_event and self.last_decision_event.get("decision_type") == "no_action":
            self._finalize_no_action_event()

    def _reset_pipeline_memory(self) -> None:
        self.pipeline_memory = {
            "historical_analysis": {},
            "market_hypothesis": {},
            "strategy_directive": {},
            "strategy_plan": {},
        }

    def _prepare_no_action_event(self) -> None:
        blockchain_agent = self.blockchain_agent_name
        self.last_decision_event = {
            "tick": self.current_tick,
            "agent_id": blockchain_agent,
            "decision_type": "no_action",
            "market_price_per_mhz": self.state.get("average_market_price_per_mhz", 0),
            "agent_balance": self.state.get("balance", 0),
            "spectrum_gap": self.state.get("spectrum_gap", 0),
            "auctions_available": len(self.state.get("active_auctions", {})),
            "tokens_owned": len(self.state.get("my_tokens", [])),
            "outcome": None,
        }

    def _refresh_world_state(self) -> bool:
        tick_index = max(0, min(self.current_tick - 1, len(self.need_schedule) - 1))
        base_need = self.need_schedule[tick_index]
        fluctuation = random.uniform(-self.need_volatility, self.need_volatility)
        self.state["current_spectrum_need"] = max(0.0, base_need + fluctuation)

        blockchain_agent = self.blockchain_agent_name
        max_retries = 3
        retry_delay = 2
        perception_loaded = False
        world_state: Optional[Dict[str, Any]] = self._preloaded_world_state
        tokens_payload: Optional[Dict[str, Any]] = self._static_tokens or None

        for attempt in range(max_retries):
            try:
                if world_state is None:
                    ws_res = httpx.get(f"{BLOCKCHAIN_URL}/world_state", timeout=10)
                    ws_res.raise_for_status()
                    world_state = ws_res.json()

                if tokens_payload is None:
                    tokens_res = httpx.get(f"{BLOCKCHAIN_URL}/spectrum_tokens", timeout=10)
                    tokens_res.raise_for_status()
                    tokens_payload = tokens_res.json()
                    self._static_tokens = tokens_payload
                self.state["all_tokens_info"] = tokens_payload or {}

                self.state["my_tokens"] = [
                    token_id
                    for token_id, owner in world_state.get("token_ownership", {}).items()
                    if owner == blockchain_agent
                ]
                balances = world_state.get("agent_balances", {})
                self.state["balance"] = balances.get(blockchain_agent, 0.0)
                self.state["owned_capacity"] = sum(
                    self.state["all_tokens_info"].get(token_id, {}).get("capacity", 0)
                    for token_id in self.state["my_tokens"]
                )
                self.state["spectrum_gap"] = (
                    self.state["current_spectrum_need"] - self.state["owned_capacity"]
                )
                perception_loaded = True
                break
            except httpx.RequestError as exc:
                print(
                    f"  [{self.agent_label}] ERROR on attempt {attempt + 1}: Could not connect to blockchain: {exc}"
                )
                if attempt < max_retries - 1:
                    time.sleep(retry_delay)
                else:
                    self.state["active_auctions"] = {}
                    self.state["all_tokens_info"] = {}
                    return False
            except httpx.HTTPStatusError as exc:
                print(f"  [{self.agent_label}] ERROR: Blockchain HTTP error {exc}")
                return False

        if not perception_loaded:
            return False

        self._load_visible_auctions_snapshot()

        try:
            if self._preloaded_history is not None:
                transaction_history = self._preloaded_history
            else:
                history_res = httpx.get(f"{BLOCKCHAIN_URL}/transaction_history", timeout=15)
                history_res.raise_for_status()
                transaction_history = history_res.json()
            self.state["transaction_history_snapshot"] = transaction_history[-50:]
        except (httpx.RequestError, httpx.HTTPStatusError) as exc:
            print(f"  [{self.agent_label}] ERROR: Could not fetch transaction history: {exc}")
            self.state["transaction_history_snapshot"] = []
            self.state["average_market_price_per_mhz"] = 0.0
            self.state["recent_agent_transactions"] = []
            self.state["recent_price_samples"] = []
            self.state["recent_winning_bids"] = []
            self.state["agent_recent_outcomes"] = []
            return False

        self._compute_average_market_price()
        self._build_recent_history_views(blockchain_agent)

        self._preloaded_world_state = None
        self._preloaded_history = None
        return True

    def _load_visible_auctions_snapshot(self) -> None:
        snapshot_index = getattr(self, "last_committed_block_index", None)
        snapshot: Dict[str, Any] = {}
        if self._preloaded_snapshot is not None:
            snapshot = self._preloaded_snapshot
        elif snapshot_index is not None:
            try:
                snap_res = httpx.get(
                    f"{BLOCKCHAIN_URL}/block/{snapshot_index}/active_auctions",
                    timeout=10,
                )
                snap_res.raise_for_status()
                payload = snap_res.json()
                snapshot = payload.get("active_auctions_snapshot", {}) or {}
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                print(
                    f"  [{self.agent_label}] WARNING: Could not load block snapshot {snapshot_index}: {exc}"
                )
                snapshot = {}

        if not snapshot:
            try:
                auc_res = httpx.get(f"{BLOCKCHAIN_URL}/active_auctions", timeout=10)
                auc_res.raise_for_status()
                snapshot = auc_res.json()
            except (httpx.RequestError, httpx.HTTPStatusError) as exc:
                print(f"  [{self.agent_label}] ERROR: Could not fetch live active auctions: {exc}")
                snapshot = {}

        self.state["active_auctions"] = snapshot
        self.state["visible_block_index"] = snapshot_index
        self._preloaded_snapshot = None

    def _compute_average_market_price(self) -> None:
        successful_sales = [
            tx
            for tx in self.state.get("transaction_history_snapshot", [])
            if tx.get("success") and tx.get("tx_type") == "auction_resolution"
        ]
        total_price = 0.0
        total_capacity = 0.0
        for tx in successful_sales:
            token_id = tx.get("token_id")
            token_info = self.state.get("all_tokens_info", {}).get(token_id, {})
            capacity = token_info.get("capacity") or 0
            if capacity:
                total_price += tx.get("final_price", 0.0)
                total_capacity += capacity
        if total_capacity > 0:
            self.state["average_market_price_per_mhz"] = round(total_price / total_capacity, 2)
        else:
            self.state["average_market_price_per_mhz"] = 0.0

    def _build_recent_history_views(self, blockchain_agent: str) -> None:
        recent_resolutions = [
            tx
            for tx in self.state.get("transaction_history_snapshot", [])
            if tx.get("tx_type") == "auction_resolution"
        ]
        agent_resolutions = [
            tx
            for tx in recent_resolutions
            if tx.get("winner_id") == blockchain_agent or tx.get("seller_id") == blockchain_agent
        ]
        price_samples: List[Dict[str, Any]] = []
        winning_bids: List[Dict[str, Any]] = []
        agent_outcomes: List[Dict[str, Any]] = []

        for tx in recent_resolutions[-50:]:
            token_id = tx.get("token_id")
            token_info = self.state.get("all_tokens_info", {}).get(token_id, {})
            capacity = token_info.get("capacity") or 0
            if capacity:
                price_samples.append(
                    {
                        "token_id": token_id,
                        "auction_type": tx.get("auction_type"),
                        "price_per_mhz": round(tx.get("final_price", 0.0) / capacity, 2),
                    }
                )

        for tx in agent_resolutions[-20:]:
            token_id = tx.get("token_id")
            token_info = self.state.get("all_tokens_info", {}).get(token_id, {})
            capacity = token_info.get("capacity") or 0
            valuation = self.utility_per_mhz * capacity if capacity else None
            entry = {
                "token_id": token_id,
                "role": "buyer" if tx.get("winner_id") == blockchain_agent else "seller",
                "final_price": tx.get("final_price", 0.0),
                "auction_type": tx.get("auction_type"),
                "capacity_mhz": capacity,
                "success": tx.get("success", True) # Assuming resolution implies success unless stated
            }
            if valuation is not None and entry["role"] == "buyer":
                entry["profit"] = round(valuation - tx.get("final_price", 0.0), 2)
                entry["valuation"] = valuation
            elif valuation is not None:
                entry["profit"] = round(tx.get("final_price", 0.0) - valuation, 2)
                entry["valuation"] = valuation
            agent_outcomes.append(entry)
            winning_bids.append(
                {
                    "token_id": token_id,
                    "winner_id": tx.get("winner_id"),
                    "final_price": tx.get("final_price", 0.0),
                    "second_price": tx.get("second_price"),
                }
            )

        self.state["recent_agent_transactions"] = agent_resolutions[-20:]
        self.state["recent_price_samples"] = price_samples[-20:]
        self.state["recent_winning_bids"] = winning_bids[-20:]
        self.state["agent_recent_outcomes"] = agent_outcomes[-20:]

    def get_history_context(self, window: int = 12) -> Dict[str, Any]:
        return {
            "tick": self.current_tick,
            "agent_id": self.blockchain_agent_name,
            "auction_type": self.auction_type,
            "utility_per_mhz": self.utility_per_mhz,
            "balance": self.state.get("balance", 0.0),
            "spectrum_gap": self.state.get("spectrum_gap", 0.0),
            "agent_recent_transactions": self.state.get("agent_recent_transactions", [])[-window:],
            "agent_recent_outcomes": self.state.get("agent_recent_outcomes", [])[-window:],
            "recent_price_samples": self.state.get("recent_price_samples", [])[-window:],
            "recent_winning_bids": self.state.get("recent_winning_bids", [])[-window:],
            "perception_error": self.state.get("perception_error", False),
        }

    def get_decision_context(self, include_history: bool = True) -> Dict[str, Any]:
        context = {
            "tick": self.current_tick,
            "agent_id": self.blockchain_agent_name,
            "auction_type": self.auction_type,
            "utility_per_mhz": self.utility_per_mhz,
            "balance": self.state.get("balance", 0.0),
            "current_need_mhz": self.state.get("current_spectrum_need", 0.0),
            "owned_capacity_mhz": self.state.get("owned_capacity", 0.0),
            "spectrum_gap_mhz": self.state.get("spectrum_gap", 0.0),
            "average_market_price_per_mhz": self.state.get("average_market_price_per_mhz", 0.0),
            "owned_tokens": self._get_owned_tokens_summary(),
            "active_auctions": self._get_enriched_active_auctions(),
            "auctions_bid_on": list(self.state.get("auctions_bid_on", [])),
            "perception_error": self.state.get("perception_error", False),
        }
        if include_history:
            context["historical_analysis"] = self.pipeline_memory.get("historical_analysis", {})
            context["market_hypothesis"] = self.pipeline_memory.get("market_hypothesis", {})
        return context

    def get_action_context(self) -> Dict[str, Any]:
        context = self.get_decision_context()
        context["strategy_plan"] = self.pipeline_memory.get("strategy_plan", {})
        return context

    def _get_enriched_active_auctions(self) -> List[Dict[str, Any]]:
        enriched: List[Dict[str, Any]] = []
        active = self.state.get("active_auctions", {})
        for token_id, details in active.items():
            token_info = self.state.get("all_tokens_info", {}).get(token_id, {})
            capacity = token_info.get("capacity", 0)
            valuation = self.utility_per_mhz * capacity if capacity else 0.0
            reference_price = (
                details.get("reserve_price")
                if details.get("reserve_price") is not None
                else details.get("price")
            )
            entry = {
                "token_id": token_id,
                "seller_id": details.get("seller_id"),
                "reserve_price": details.get("reserve_price"),
                "token_capacity_mhz": capacity,
                "my_valuation": valuation,
                "already_bid": token_id in self.state.get("auctions_bid_on", []),
            }
            if self.auction_type == "direct_sale":
                entry["buy_now_price"] = details.get("price")
            if valuation and reference_price is not None:
                entry["expected_surplus"] = round(valuation - reference_price, 2)
            enriched.append(entry)
        return enriched

    def _get_owned_tokens_summary(self) -> Dict[str, Dict[str, float]]:
        summary: Dict[str, Dict[str, float]] = {}
        for token_id in self.state.get("my_tokens", []):
            token_info = self.state.get("all_tokens_info", {}).get(token_id, {})
            capacity = token_info.get("capacity", 0)
            valuation = self.utility_per_mhz * capacity if capacity else 0.0
            summary[token_id] = {
                "token_capacity_mhz": capacity,
                "my_valuation": valuation,
            }
        return summary

    def record_historical_analysis(
        self,
        avg_profit_per_win: float,
        win_rate: float,
        observed_bid_range: str,
        competitor_signals: List[str],
        notes: str,
    ) -> str:
        self.pipeline_memory["historical_analysis"] = {
            "avg_profit_per_win": avg_profit_per_win,
            "win_rate": win_rate,
            "observed_bid_range": observed_bid_range,
            "competitor_signals": competitor_signals,
            "notes": notes,
        }
        _log_verbose(
            f"  [{self.agent_label}] Stage 1 summary: avg_profit={avg_profit_per_win:.2f}, win_rate={win_rate:.2f}, bid_range={observed_bid_range}"
        )
        return "Historical analysis recorded."

    def record_market_hypothesis(
        self,
        market_type: str,
        confidence: float,
        rationale: str,
        risk_assessment: str,
    ) -> str:
        self.pipeline_memory["market_hypothesis"] = {
            "market_type": market_type,
            "confidence": confidence,
            "rationale": rationale,
            "risk_assessment": risk_assessment,
        }
        _log_verbose(
            f"  [{self.agent_label}] Stage 2 summary: market={market_type}, confidence={confidence:.2f}, risk={risk_assessment}"
        )
        return "Market hypothesis captured."

    def record_strategy_directive(
        self,
        intent: str,
        urgency: str,
        candidate_tokens: List[str],
        preferred_action: str,
        notes: str,
    ) -> str:
        directive = {
            "intent": intent,
            "urgency": urgency,
            "candidate_tokens": candidate_tokens,
            "preferred_action": preferred_action,
            "notes": notes,
        }
        self.pipeline_memory["strategy_directive"] = directive
        _log_verbose(
            f"  [{self.agent_label}] Stage 3 directive: intent={intent}, preferred={preferred_action}, urgency={urgency}, candidates={candidate_tokens}"
        )
        if intent == "idle":
            fallback_reason = notes or "Router recommended holding position."
            self.record_strategy_plan(
                action_type="no_action",
                token_id=None,
                bid_amount=None,
                reserve_price=None,
                urgency=urgency or "normal",
                reason=fallback_reason,
            )
        return "Strategy directive recorded."

    def ensure_strategy_directive(self) -> Dict[str, Any]:
        directive = self.pipeline_memory.get("strategy_directive") or {}
        if directive:
            return directive
        directive = self._build_fallback_directive()
        self.pipeline_memory["strategy_directive"] = directive
        _log_verbose(
            f"  [{self.agent_label}] Stage 3 fallback: intent={directive.get('intent')} preferred={directive.get('preferred_action')} candidates={directive.get('candidate_tokens')}"
        )
        seeded = False
        if not self.pipeline_memory.get("strategy_plan", {}).get("action_type"):
            seeded = self._seed_plan_from_directive(directive)
        if (
            directive.get("intent") == "idle"
            and not self.pipeline_memory.get("strategy_plan", {}).get("action_type")
        ):
            self.record_strategy_plan(
                action_type="no_action",
                token_id=None,
                bid_amount=None,
                reserve_price=None,
                urgency=directive.get("urgency", "normal"),
                reason=directive.get("notes", "Fallback idle directive."),
            )
        return directive

    def _seed_plan_from_directive(self, directive: Dict[str, Any]) -> bool:
        intent = directive.get("intent")
        if intent != "sell":
            return False

        candidate_tokens = directive.get("candidate_tokens") or []
        token_id = candidate_tokens[0] if candidate_tokens else self._select_surplus_token_for_listing()
        if not token_id:
            return False

        reserve_price = self._compute_reserve_for_token(token_id)
        auto_plan = {
            "action_type": "start_auction",
            "token_id": token_id,
            "bid_amount": None,
            "reserve_price": reserve_price,
            "urgency": directive.get("urgency", "normal"),
            "reason": directive.get(
                "notes",
                "Fallback sell plan seeded because router provided no executable plan.",
            ),
        }
        self.pipeline_memory["strategy_plan"] = auto_plan
        _log_verbose(
            f"  [{self.agent_label}] Stage 3 fallback: seeded start_auction for {token_id} at reserve {reserve_price}"
        )
        return True

    def _build_fallback_directive(self) -> Dict[str, Any]:
        state = self.state
        directive = {
            "intent": "idle",
            "urgency": "normal",
            "candidate_tokens": [],
            "preferred_action": "no_action",
            "notes": "Fallback idle directive; router did not supply guidance.",
        }
        if state.get("perception_error", False):
            directive["notes"] = "Fallback idle directive due to perception error."
            return directive

        gap = state.get("spectrum_gap", 0.0)
        need = state.get("current_spectrum_need", 0.0)
        balance = state.get("balance", 0.0)
        avg_profit = (
            self.pipeline_memory.get("consolidated_analysis", {}).get("avg_profit_per_win")
        )
        profitability_blocked = avg_profit is not None and avg_profit <= 0
        affordable_tokens: List[str] = []
        for auction in self._get_enriched_active_auctions():
            token_id = auction["token_id"]
            reserve = (
                auction.get("reserve_price")
                if auction.get("reserve_price") is not None
                else auction.get("buy_now_price")
            )
            valuation = auction.get("my_valuation", 0.0)
            already_bid = auction.get("already_bid", False)
            expected_surplus = auction.get("expected_surplus")
            if reserve is None or valuation <= 0 or already_bid:
                continue
            if expected_surplus is not None and expected_surplus <= 0:
                continue
            if balance <= 0 or reserve > balance:
                continue
            affordable_tokens.append(token_id)

        if gap > 0 and affordable_tokens and not profitability_blocked:
            urgency = "high" if gap >= max(need * 0.5, 1.0) else "normal"
            directive.update(
                intent="buy",
                urgency=urgency,
                candidate_tokens=affordable_tokens[:3],
                preferred_action="buy_now" if self.auction_type == "direct_sale" else "place_bid",
                notes="Fallback buy directive triggered by spectrum gap with positive expected surplus.",
            )
            return directive

        if profitability_blocked and gap > 0:
            directive["notes"] = "Fallback idle directive; recent wins are unprofitable so we pause buying."
            return directive

        surplus_token = self._select_surplus_token_for_listing()
        if surplus_token and not self._has_active_listing():
            directive.update(
                intent="sell",
                urgency="normal",
                candidate_tokens=[surplus_token],
                preferred_action="start_auction",
                notes="Fallback sell directive to keep supply flowing.",
            )
            return directive

        directive["notes"] = "Fallback idle directive; no viable buy or sell action detected."
        return directive

    def record_strategy_plan(
        self,
        action_type: str,
        token_id: Optional[str] = None,
        bid_amount: Optional[float] = None,
        reserve_price: Optional[float] = None,
        urgency: str = "normal",
        reason: str = "",
    ) -> str:
        plan = {
            "action_type": action_type,
            "token_id": token_id,
            "bid_amount": bid_amount,
            "reserve_price": reserve_price,
            "urgency": urgency,
            "reason": reason,
        }
        plan = self._maybe_force_listing_plan(plan)
        self.pipeline_memory["strategy_plan"] = plan
        action_detail = plan.get("token_id") or "n/a"
        _log_verbose(
            f"  [{self.agent_label}] Strategy plan: action={plan.get('action_type')}, target={action_detail}, bid={plan.get('bid_amount')}, reserve={plan.get('reserve_price')}, urgency={plan.get('urgency')}"
        )
        return "Strategy plan stored."

    def record_no_action(self, reason: str) -> str:
        blockchain_agent = self.blockchain_agent_name
        self.pipeline_memory["strategy_plan"] = {
            "action_type": "no_action",
            "reason": reason,
        }
        self.last_decision_event = {
            "tick": self.current_tick,
            "agent_id": blockchain_agent,
            "decision_type": "no_action",
            "reason": reason,
            "market_price_per_mhz": self.state.get("average_market_price_per_mhz", 0),
            "agent_balance": self.state.get("balance", 0),
            "spectrum_gap": self.state.get("spectrum_gap", 0),
            "auctions_available": len(self.state.get("active_auctions", {})),
            "tokens_owned": len(self.state.get("my_tokens", [])),
            "outcome": "held_position",
        }
        self.action_taken_this_tick = True
        _log_verbose(f"  [{self.agent_label}] Stage 4 outcome: no_action because {reason}")
        return "No-action decision logged."

    def _maybe_force_listing_plan(self, plan: Dict[str, Any]) -> Dict[str, Any]:
        if plan.get("action_type") != "no_action":
            return plan
        if not self._should_force_listing():
            return plan

        token_id = self._select_surplus_token_for_listing()
        if not token_id:
            return plan

        reserve_price = self._compute_reserve_for_token(token_id)
        auto_plan = {
            "action_type": "start_auction",
            "token_id": token_id,
            "bid_amount": None,
            "reserve_price": reserve_price,
            "urgency": "normal",
            "reason": "Auto-listed surplus token to keep supply flowing.",
        }
        _log_verbose(
            f"  [{self.agent_label}] Stage 3 override: forcing start_auction for {token_id} at reserve {reserve_price} to address buyer demand."
        )
        return auto_plan

    def _should_force_listing(self) -> bool:
        if self.auction_type not in {"first_price", "second_price"}:
            return False
        if self.state.get("perception_error", False):
            return False
        if self.state.get("spectrum_gap", 0.0) > 0:
            return False
        if self._select_surplus_token_for_listing() is None:
            return False
        if self._has_active_listing():
            return False
        return True

    def _select_surplus_token_for_listing(self) -> Optional[str]:
        my_tokens = self.state.get("my_tokens", [])
        if not my_tokens:
            return None
        active = self.state.get("active_auctions", {})
        owned_active = {
            token_id
            for token_id, details in active.items()
            if details.get("seller_id") == self.blockchain_agent_name
        }
        for token_id in my_tokens:
            if token_id not in owned_active:
                return token_id
        return None

    def _compute_reserve_for_token(self, token_id: str) -> float:
        token_info = self.state.get("all_tokens_info", {}).get(token_id, {})
        capacity = token_info.get("capacity") or 0
        valuation = self.utility_per_mhz * capacity if capacity else 0.0
        if valuation > 0:
            return round(valuation, 2)
        fallback_price = token_info.get("price") or 1.0
        return float(fallback_price)

    def _has_active_listing(self) -> bool:
        active = self.state.get("active_auctions", {})
        for details in active.values():
            if details.get("seller_id") == self.blockchain_agent_name:
                return True
        return False

    def start_auction(self, token_id: str, reserve_price: float) -> str:
        if self.action_taken_this_tick:
            return "You have already acted this turn."

        blockchain_agent_name = self.blockchain_agent_name
        if token_id not in self.state.get("my_tokens", []):
            return f"Error: You do not own token {token_id}."

        token_capacity = self.state.get("all_tokens_info", {}).get(token_id, {}).get("capacity", 0)
        token_valuation = self.utility_per_mhz * token_capacity if token_capacity else 0
        self.last_decision_event = {
            "tick": self.current_tick,
            "agent_id": blockchain_agent_name,
            "decision_type": "start_auction",
            "token_id": token_id,
            "reserve_price": reserve_price,
            "token_valuation": token_valuation,
            "token_capacity_mhz": token_capacity,
            "reserve_markup": (
                (reserve_price - token_valuation) / token_valuation if token_valuation > 0 else 0
            ),
            "market_price_per_mhz": self.state.get("average_market_price_per_mhz", 0),
            "agent_balance": self.state.get("balance", 0),
            "spectrum_gap": self.state.get("spectrum_gap", 0),
            "outcome": None,
        }

        _log_verbose(f"  [{self.agent_label}] Starting auction for {token_id} with reserve price {reserve_price}...")
        try:
            transaction = {
                "agent_id": blockchain_agent_name,
                "capability": "start_auction",
                "payload": {
                    "token_id": token_id,
                    "price": reserve_price,
                },
            }
            response = httpx.post(
                f"{BLOCKCHAIN_URL}/new_transaction",
                json=transaction,
                timeout=10,
            )
            response.raise_for_status()
            self.action_taken_this_tick = True
            return response.json().get("message", "Auction started successfully.")
        except httpx.RequestError as exc:
            return f"Error starting auction: Could not connect to blockchain: {exc}"
        except httpx.HTTPStatusError as exc:
            return f"Error starting auction: {exc.response.text}"

    def place_bid(self, token_id: str, bid_amount: float) -> str:
        if self.action_taken_this_tick:
            return "You have already acted this turn."

        blockchain_agent_name = self.blockchain_agent_name
        if token_id in self.state.get("auctions_bid_on", []):
            return f"Error: You have already placed a bid on auction {token_id}."

        balance = self.state.get("balance", 0.0)
        if balance <= 0:
            reason = "Skipped bidding because balance is depleted."
            self.record_no_action(reason)
            return reason

        token_capacity = self.state.get("all_tokens_info", {}).get(token_id, {}).get("capacity", 0)
        token_valuation = self.utility_per_mhz * token_capacity if token_capacity else 0
        if token_valuation <= 0:
            reason = f"Skipped bidding on {token_id} because valuation is undefined."
            self.record_no_action(reason)
            return reason

        safe_cap = self._max_profitable_bid(token_valuation)
        if safe_cap <= 0:
            reason = f"Skipped bidding on {token_id} because no profit-safe bid exists."
            self.record_no_action(reason)
            return reason

        adjusted_bid = min(bid_amount, safe_cap, balance)
        if adjusted_bid <= 0:
            reason = f"Skipped bidding on {token_id} because adjusted bid would be non-positive."
            self.record_no_action(reason)
            return reason

        if adjusted_bid != bid_amount:
            _log_verbose(
                f"  [{self.agent_label}] Adjusted bid on {token_id} from {bid_amount} to profit-safe {adjusted_bid}."
            )
        bid_amount = adjusted_bid

        bid_shading = (
            (token_valuation - bid_amount) / token_valuation if token_valuation > 0 else 0
        )
        self.last_decision_event = {
            "tick": self.current_tick,
            "agent_id": blockchain_agent_name,
            "decision_type": "place_bid",
            "token_id": token_id,
            "bid_amount": bid_amount,
            "token_valuation": token_valuation,
            "token_capacity_mhz": token_capacity,
            "bid_shading": bid_shading,
            "market_price_per_mhz": self.state.get("average_market_price_per_mhz", 0),
            "agent_balance": self.state.get("balance", 0),
            "spectrum_gap": self.state.get("spectrum_gap", 0),
            "outcome": None,
        }

        _log_verbose(f"  [{self.agent_label}] Placing bid of {bid_amount} on {token_id}...")
        try:
            transaction = {
                "agent_id": blockchain_agent_name,
                "capability": "place_bid",
                "payload": {
                    "token_id": token_id,
                    "bid_amount": bid_amount,
                },
            }
            response = httpx.post(
                f"{BLOCKCHAIN_URL}/new_transaction",
                json=transaction,
                timeout=10,
            )
            response.raise_for_status()
            self.state.setdefault("auctions_bid_on", []).append(token_id)
            self.action_taken_this_tick = True
            return response.json().get("message", "Bid placed successfully.")
        except httpx.RequestError as exc:
            return f"Error placing bid: Could not connect to blockchain: {exc}"
        except httpx.HTTPStatusError as exc:
            return f"Error placing bid: {exc.response.text}"

    def buy_now(self, token_id: str) -> str:
        if self.action_taken_this_tick:
            return "You have already acted this turn."

        blockchain_agent_name = self.blockchain_agent_name
        token_capacity = self.state.get("all_tokens_info", {}).get(token_id, {}).get("capacity", 0)
        token_valuation = self.utility_per_mhz * token_capacity if token_capacity else 0
        listing_price = self._get_listing_price(token_id)
        if listing_price is None:
            reason = f"Unable to buy {token_id} because the listing price is unknown."
            self.record_no_action(reason)
            return reason

        balance = self.state.get("balance", 0.0)
        if listing_price > balance:
            reason = f"Skipped buy_now on {token_id}; listing price {listing_price} exceeds balance {balance}."
            self.record_no_action(reason)
            return reason

        safe_cap = self._max_profitable_bid(token_valuation)
        if safe_cap <= 0:
            reason = f"Skipped buy_now on {token_id} because valuation is undefined or non-positive."
            self.record_no_action(reason)
            return reason
        if listing_price > safe_cap:
            reason = f"Skipped buy_now on {token_id}; listing price {listing_price} exceeds profit-safe cap {safe_cap}."
            self.record_no_action(reason)
            return reason
        self.last_decision_event = {
            "tick": self.current_tick,
            "agent_id": blockchain_agent_name,
            "decision_type": "buy_now",
            "token_id": token_id,
            "token_valuation": token_valuation,
            "token_capacity_mhz": token_capacity,
            "market_price_per_mhz": self.state.get("average_market_price_per_mhz", 0),
            "agent_balance": self.state.get("balance", 0),
            "spectrum_gap": self.state.get("spectrum_gap", 0),
            "outcome": None,
        }

        _log_verbose(f"  [{self.agent_label}] Attempting to buy token {token_id} directly...")
        try:
            transaction = {
                "agent_id": blockchain_agent_name,
                "capability": "buy_now",
                "payload": {
                    "token_id": token_id,
                },
            }
            response = httpx.post(
                f"{BLOCKCHAIN_URL}/new_transaction",
                json=transaction,
                timeout=10,
            )
            response.raise_for_status()
            self.action_taken_this_tick = True
            self.state.setdefault("auctions_bid_on", []).append(token_id)
            return response.json().get("message", "Token purchased successfully.")
        except httpx.RequestError as exc:
            return f"Error buying token: Could not connect to blockchain: {exc}"
        except httpx.HTTPStatusError as exc:
            return f"Error buying token: {exc.response.text}"

    def _get_listing_price(self, token_id: str) -> Optional[float]:
        details = self.state.get("active_auctions", {}).get(token_id)
        if not details:
            return None
        if details.get("price") is not None:
            return details.get("price")
        return details.get("reserve_price")

    def _max_profitable_bid(self, token_valuation: float) -> float:
        if token_valuation <= 0:
            return 0.0
        if self.auction_type == "second_price":
            return token_valuation
        margin = self._minimum_profit_margin(token_valuation)
        return max(0.0, token_valuation - margin)

    def _minimum_profit_margin(self, token_valuation: float) -> float:
        return max(0.5, 0.01 * token_valuation)

    def _finalize_no_action_event(self) -> None:
        if self.last_decision_event and self.last_decision_event.get("decision_type") == "no_action":
            self.last_decision_event.update(
                {
                    "market_price_per_mhz": self.state.get("average_market_price_per_mhz", 0),
                    "agent_balance": self.state.get("balance", 0),
                    "spectrum_gap": self.state.get("spectrum_gap", 0),
                    "auctions_available": len(self.state.get("active_auctions", {})),
                    "tokens_owned": len(self.state.get("my_tokens", [])),
                }
            )

    @property
    def blockchain_agent_name(self) -> str:
        return self.agent_label.replace("_", "-")

    def record_consolidated_analysis(
        self,
        avg_profit_per_win: float,
        win_rate: float,
        observed_bid_range: str,
        competitor_signals: List[str],
        market_type: str,
        confidence: float,
        rationale: str,
        risk_assessment: str,
    ) -> str:
        self.pipeline_memory["consolidated_analysis"] = {
            "avg_profit_per_win": avg_profit_per_win,
            "win_rate": win_rate,
            "observed_bid_range": observed_bid_range,
            "competitor_signals": competitor_signals,
            "market_type": market_type,
            "confidence": confidence,
            "rationale": rationale,
            "risk_assessment": risk_assessment,
        }
        # Also populate legacy keys for compatibility if needed
        self.pipeline_memory["historical_analysis"] = {
            "avg_profit_per_win": avg_profit_per_win,
            "win_rate": win_rate,
            "observed_bid_range": observed_bid_range,
            "competitor_signals": competitor_signals,
            "notes": rationale,
        }
        self.pipeline_memory["market_hypothesis"] = {
            "market_type": market_type,
            "confidence": confidence,
            "rationale": rationale,
            "risk_assessment": risk_assessment,
        }
        _log_verbose(
            f"  [{self.agent_label}] Stage 1 summary: market={market_type}, profit={avg_profit_per_win:.2f}, risk={risk_assessment}"
        )
        return "Consolidated analysis recorded."