# Fuzzy extrction of brand and models

## Process
### Configuration Loading
The system first loads brand configurations from either:
* Brand-specific configuration files
* Default brand settings
### Prompt Analysis
The process involves analyzing prompts through several steps:

Matching Methods
Direct Matching: Looking for exact brand names
Pattern Recognition: Identifying brand-specific formatting
Contextual Analysis: Understanding brand context from surrounding text
Fuzzy Matching: Handling misspellings and variations
Validation
The extracted brand information is validated against:

## How to run

### Create Env
```
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

### Setup and run server

1. Edit brands.yml to update brand list, aliases, or regex hints
2. Input file: prompts.csv
3. Outputs: outputs.csv, outputs.jsonl
4. API endpoint: http://localhost:8000/extract_brand

### Start server
```
cd slm/
python app.py
```

### Run client
```
cd slm/
(.venv) @ucKaizen ➜ /workspaces/mcpagents/slm (main) $ python client.py 
Done. Processed: 25, errors: 0
```
- Input:  /workspaces/mcpagents/slm/prompts.csv
- Output: /workspaces/mcpagents/slm/outputs.csv
- Output: /workspaces/mcpagents/slm/outputs.jsonl
