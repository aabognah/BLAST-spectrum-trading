# BLAST Spectrum Trading Simulation

BLAST (Blockchain-power LLM-based Spectrum Trading) is a proposed model for decentralized and agentic spectrum management on a blockchain. This repository contains the core code for the reproducible version of the BLAST simulation: a blockchain-based spectrum trading market where LLM agents buy/sell spectrum tokens through auction mechanisms.

## Related Paper

This codebase accompanies the BLAST paper:

- Abognah, A., and Basir, O. "BLAST: Blockchain-based LLM-powered Agentic Spectrum Trading." arXiv preprint arXiv:2604.12127, 2026. https://doi.org/10.48550/arXiv.2604.12127

Paper links:

- Abstract: https://arxiv.org/abs/2604.12127
- PDF: https://arxiv.org/pdf/2604.12127
- DOI: https://doi.org/10.48550/arXiv.2604.12127

If you use this repository in academic work, please cite the paper.

Suggested IEEE-style citation:

Anas Abognah and Otman Basir, "BLAST: Blockchain-based LLM-powered Agentic Spectrum Trading," arXiv preprint arXiv:2604.12127, 2026, doi: 10.48550/arXiv.2604.12127.


## What Is Included

- `main.py`: FastAPI blockchain server and auction logic.
- `run_simulation.py`: simulation orchestrator that starts agents, runs ticks, mines blocks, and writes results.
- `spectrum_agent/agent.py`: LLM-powered cognitive radio agent pipeline.
- `test_scenario_1.py`: scenario 1 (single seller, heterogeneous buyers).
- `test_scenario_2.py`: scenario 2 (single seller, equal-utility buyers).
- `run_simulations.sh`: helper to run scenario 1 and 2 in background with logs.

## Prerequisites

- Python 3.9+
- A Google Cloud project with Vertex AI enabled
- Google credentials available to your runtime (for example via `gcloud auth application-default login`)

## Quick Start

1. Create and activate a virtual environment.

```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies.

```bash
pip install -r requirements.txt
```

3. Configure environment variables.

```bash
cp .env.example .env
# edit .env with your project values
```

```bash
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
export GOOGLE_CLOUD_MODEL="gemini-2.5-flash"
export GOOGLE_CLOUD_LOCATION="global"
```

4. Run one scenario.

```bash
python3 test_scenario_1.py
```

Results are written as JSON files in the repository root, for example:

- `scenario_1_price_discovery_second_price_results.json`
- `scenario_1_price_discovery_first_price_results.json`
- `scenario_1_price_discovery_direct_sale_results.json`

## Configuration Reference

The following variables can be set in your shell or in a `.env` file.

- `GOOGLE_CLOUD_PROJECT` (required for LLM scenarios): your GCP project ID.
- `GOOGLE_CLOUD_MODEL` (optional): defaults to `gemini-2.5-flash`.
- `GOOGLE_CLOUD_LOCATION` (optional): defaults to `global`.
- `GOOGLE_GENAI_USE_VERTEXAI` (optional): defaults to `true`.
- `BLOCKCHAIN_URL` (optional): defaults to `http://127.0.0.1:8000`.
- `BLOCKCHAIN_HOST` (optional): defaults to `127.0.0.1`.
- `BLOCKCHAIN_PORT` (optional): defaults to `8000`.
- `VERBOSE_AGENT_LOGS` (optional): set to `1`/`true` for detailed agent-stage logs.

## Scenarios

- `test_scenario_1.py`: seller utility 5, buyers with utilities 10/15/20.
- `test_scenario_2.py`: seller utility 5, buyers all utility 20.

Each scenario runs three auction modes in sequence:

- second-price
- first-price
- direct-sale


## Run In Background

To run both LLM scenarios in background and write logs to `logs/`:

```bash
export GOOGLE_CLOUD_PROJECT="your-gcp-project-id"
./run_simulations.sh
```

Then inspect progress:

```bash
tail -f loutput.log
tail -f blockchain.log
```

Results are written as JSON files in the repository root, for example:

- `scenario_1_price_discovery_second_price_results.json`
- `scenario_1_price_discovery_first_price_results.json`
- `scenario_1_price_discovery_direct_sale_results.json`



## Understanding Results

The `results/` directory includes example results for running scenario 1 second price aution. The directory includes machine-readable outputs (`*.json`), human-readable summaries (`*.md`, `transactions_list.txt`), and figures (`*.png`).



### Reading outcomes by auction type

- Second-price: winner pays the second-highest bid (subject to reserve), so buyer surplus is often visible when willingness-to-pay is high.
- First-price: winner pays own bid, so expect lower buyer surplus and stronger bid-shading incentives.
- Direct-sale: no competitive bidding; outcomes depend more directly on ask-vs-valuation matching.

For fair comparison across auction types, focus on the same scenario and compare:

- total successful auctions
- average transaction price and price per MHz
- total buyer profit vs total seller profit
- utilization (`system_utilization_percentage`) and concentration (`hhi`, `gini_coefficient`)

## Common Issues

- `GOOGLE_CLOUD_PROJECT is not set`:
  - Export `GOOGLE_CLOUD_PROJECT` before running LLM scenarios.
- Vertex model `404 NOT_FOUND`:
  - Use a model your project has access to, for example `gemini-2.5-flash`.
- `ModuleNotFoundError`:
  - Activate `venv` and reinstall with `pip install -r requirements.txt`.
