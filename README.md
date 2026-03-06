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
| Single squad touched | `squad_reviewers` from that squad + `outsider_reviewers` outsiders |
| Multiple squads touched | `squad_reviewers` from each squad + `outsider_reviewers` outsiders |
| No squad owns the files | `squad_reviewers + outsider_reviewers` random from all members |

By default, `squad_reviewers=1` and `outsider_reviewers=1`, matching the original behavior. Both can be set to `0` (e.g., only squad reviewers, or only outsiders). When there aren't enough candidates, as many as available are picked.

### Outsider pool from GitHub

By default, outsiders are picked only from squad members. You can expand the pool by setting `outsider_source`:

- **`contributors`** — people who have committed to the repo
- **`collaborators`** — people with access to the repo (can include the entire org)

You can filter out specific users (bots, service accounts) with the `exclude` config option.

### Deficit compensation

When a squad doesn't have enough candidates (e.g., the PR author is the only member), the shortfall is compensated by picking extra outsiders. This ensures the total reviewer count stays consistent regardless of who opens the PR.

The PR author is always excluded from candidates.

## Setup

### 1. Create `.github/squads.yml`

By default, the action looks for the config file at `.github/squads.yml` — no need to specify `config-path` in your workflow unless you want a different location.

```yaml
strategy: random  # random | round-robin | least-recent
squad_reviewers: 1   # reviewers picked per affected squad (default: 1)
outsider_reviewers: 1 # reviewers picked from outside affected squads (default: 1)
# outsider_source: contributors  # contributors | collaborators

exclude:           # users to never assign as reviewers (default: [])
  - dependabot[bot]
  - renovate[bot]

squads:
  - name: payments
    members: [alice, bob, charlie]   # inline list syntax
    paths:
      - src/payments/**
      - src/billing/**

  - name: platform
    members:                          # multi-line syntax
      - dave
      - eve
      - frank
    paths:
      - src/infra/**
      - src/auth/**
```

Both list styles (`[a, b]` and multi-line `- a`) are valid YAML and work interchangeably for `members`, `paths`, and `exclude`.

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
      - uses: andret13pinto/who-reviews@v0.1
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
- Negative reviewer counts
- Invalid strategy names

| Config key | Type | Default | Description |
|------------|------|---------|-------------|
| `strategy` | string | `random` | Selection strategy (`random`, `round-robin`, `least-recent`) |
| `squad_reviewers` | int | `1` | Reviewers picked per affected squad |
| `outsider_reviewers` | int | `1` | Reviewers picked from outside affected squads |
| `exclude` | list | `[]` | Users to never assign (bots, service accounts, etc.) |
| `outsider_source` | string | not set | Where to fetch outsider candidates (`contributors` or `collaborators`) |

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
