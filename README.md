# Who Reviews

A GitHub Action that automatically assigns PR reviewers based on code ownership. Define squads that own parts of your codebase, and reviewers are assigned based on which files a PR touches.

## How It Works

1. A PR is opened (or marked ready for review)
2. The action checks which files changed
3. Changed files are matched against squad path patterns
4. Reviewers are selected based on ownership rules

### Assignment Rules

| Scenario | Reviewers |
|----------|-----------|
| Single squad touched | 1 from that squad + 1 outsider |
| Multiple squads touched | 1 from each squad + 1 outsider |
| No squad owns the files | 2 random from all members |

The PR author is always excluded from candidates.

## Setup

### 1. Create `.github/squads.yml`

By default, the action looks for the config file at `.github/squads.yml` — no need to specify `config-path` in your workflow unless you want a different location.

```yaml
strategy: random  # random | round-robin | least-recent

squads:
  - name: payments
    members:
      - alice
      - bob
      - charlie
    paths:
      - src/payments/**
      - src/billing/**

  - name: platform
    members:
      - dave
      - eve
      - frank
    paths:
      - src/infra/**
      - src/auth/**
```

### 2. Add the workflow

```yaml
# .github/workflows/assign-reviewers.yml
name: Assign PR Reviewers

on:
  pull_request:
    types: [opened, ready_for_review]

jobs:
  assign:
    runs-on: ubuntu-latest
    if: github.event.pull_request.draft == false
    steps:
      - uses: actions/checkout@v4
      - uses: your-org/who-reviews@main
```

## Configuration

### Inputs

| Input | Description | Default |
|-------|-------------|---------|
| `config-path` | Path to squads config file | `.github/squads.yml` |

### Selection Strategies

- **`random`** — picks reviewers randomly
- **`round-robin`** — tracks assignment counts, picks the least-assigned person
- **`least-recent`** — tracks timestamps, picks whoever was assigned longest ago

Round-robin and least-recent persist state in `.pr-review-state.json`. This file is automatically cached between runs — no manual setup needed.

### Validation

The config is validated on load. It will reject:
- Empty squads (no members or no paths)
- Duplicate members across squads
- Invalid strategy names

## Development

```bash
# Install dependencies
uv sync

# Run tests
uv run pytest -v

# Run a specific test file
uv run pytest tests/test_reviewer_selector.py -v
```

## License

MIT
