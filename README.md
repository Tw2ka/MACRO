# MACRO — Part 1

MACRO compares two ways of evaluating recipe recommendations with AG2:

- **Single judge:** one AI agent evaluates all criteria.
- **Specialist judges:** three independent AI agents evaluate preferences, recipe attributes and constraints, and explanations. A Python coordinator combines their findings using a fixed policy.

The current pilot contains **20 cases** built from real HUMMUS recipes and constructed user profiles: 7 constraint violations, 6 dominated recommendations (one option is at least as good on every objective and better on one), and 7 genuine trade-offs. This is a small demonstration before the larger course study.

The coordinator uses the judges' reported feasibility first, then dominance, then declared user priorities. A trade-off without enough priorities can remain unresolved. Reference answers are kept separate from agent inputs.

## 1. Set up

Use **Python 3.11 or newer**. Open PowerShell in the project folder and run:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.lock.txt
.\.venv\Scripts\python.exe -m pip install --no-deps -e .
```

If you use PyCharm, select `.venv\Scripts\python.exe` as the project interpreter.

The prepared cases are in `data/pilot/`; you do not need to download the original dataset to run them. Read [the case preview](data/pilot/preview.md) for examples.

## 2. Set your API key

In the same PowerShell terminal, replace the placeholder with your OpenAI API key:

```powershell
$env:OPENAI_API_KEY = "your-api-key"
```

The application does not automatically read `.env` files. The model and other settings are in [configs/pilot.json](configs/pilot.json); the current model is `gpt-5-nano`.

## 3. Try one case

**Preview the run — no API calls or charges:**

```powershell
.\.venv\Scripts\python.exe -m macro plan --limit 1
```

**Run the real AI judges — incurs OpenAI API charges:**

```powershell
.\.venv\Scripts\python.exe -m macro run --allow-paid-api --limit 1 --max-calls 24 --run-id live-smoke-03
```

Here, `python -m macro` starts the project. `plan` previews the request count; `run` performs the evaluation.

| Option | Meaning |
|---|---|
| `--allow-paid-api` | Explicitly permits paid API calls |
| `--limit 1` | Evaluates one case |
| `--max-calls 24` | Caps API requests at 24; this is not a money limit |
| `--run-id live-smoke-03` | Saves this experiment under `results/live-smoke-03/` |

Each case is evaluated with both A/B and B/A ordering to check whether order changes the decision. That means **8 initial calls per case**: 2 single-judge calls and 6 specialist calls. Retries and tool follow-ups can add calls; reaching the cap can leave a run incomplete. The Python coordinator adds no API calls.

## 4. Run all 20 cases

After checking the one-case result:

```powershell
.\.venv\Scripts\python.exe -m macro run --allow-paid-api --limit 20 --max-calls 240 --run-id live-pilot-03
```

This starts with **160 model calls**, plus any retries or tool follow-ups within the request cap.

Use a **new run ID** for a new experiment or after changing code, settings, or cases. To resume an interrupted run, repeat its original command with the same ID; completed assessments are reused. Do not run two processes with the same ID at once. If the application reports an uncertain API request, inspect its saved call record before allowing a retry, since it may already have been billed.

## 5. Read the results

Open **`results/live-pilot-03/report.html`** in your browser (or `results/live-smoke-03/report.html` for the one-case run).

The HTML report is generated automatically. It shows decisions, each judge's explanation, evidence references, warnings, and expandable raw responses.

Other saved files include:

- `summary.json`: overall metrics and API usage.
- `roles/`: individual judge responses and errors.
- `evaluations/`: single-judge and coordinator decisions.
- `calls/`: API request records and usage.

To rebuild reports from an existing run **without making API calls**:

```powershell
.\.venv\Scripts\python.exe -m macro summarize results/live-pilot-03
```

## Where to find the code

| Folder inside `src/macro/` | Purpose |
|---|---|
| `evaluate_case_generation/` | Prepare recipes and evaluation cases |
| `ai_agents/` | AG2 agents, prompts, response schemas, and tools |
| `coordinator/` | Combine specialist findings using the fixed policy |
| `evaluation/` | Run experiments and calculate metrics |
| `reporting/` | Generate HTML, Markdown, and JSON reports |
| `shared/` | Common evaluation rules and file helpers |

[cli.py](src/macro/cli.py) defines the commands. See [ARCHITECTURE.md](ARCHITECTURE.md) for the detailed code guide and [PLAN.md](PLAN.md) for the project scope and phases.
