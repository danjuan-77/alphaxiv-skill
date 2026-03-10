# AlphaXiv Skill

Search and retrieve research papers from [AlphaXiv](https://www.alphaxiv.org) — a platform built on top of arXiv that adds AI-generated overviews, social features, benchmarks, and community engagement to research papers.

## Features

- Search papers by title or topic
- Get paper details, metrics (views, votes, comments), and AI overviews
- Find similar papers and trending/top AI papers
- Browse paper implementations (code repos)
- Look up SOTA benchmarks and tasks
- Ask questions about a paper via AlphaXiv's AI assistant

## Installation

Copy the `alphaxiv/` directory into your agent's skills folder:

```bash
# Claude Code (personal)
cp -r alphaxiv/ ~/.claude/skills/alphaxiv/

# Claude Code (project)
cp -r alphaxiv/ .claude/skills/alphaxiv/
```

Then use `/alphaxiv` or let the agent invoke it automatically.

## Usage

```bash
python3 scripts/alphaxiv.py <command> [options]
```

### Commands

| Command | Description |
|---------|-------------|
| `search <query>` | Search papers by title or topic |
| `paper <arxiv-id>` | Get paper details |
| `metrics <arxiv-id>` | Get views, votes, comments |
| `overview <arxiv-id>` | Get AI-generated overview |
| `similar <arxiv-id>` | Find similar papers |
| `top` | Get top trending AI papers |
| `feed` | Get feed sorted by Hot/Views/Likes/Comments |
| `implementations <arxiv-id>` | Get code implementations |
| `sota` | List SOTA tasks and benchmarks |
| `metadata <arxiv-id>` | Get authors, institutions, topics, GitHub |
| `ask <question>` | Ask a question about a paper (requires token) |

### Examples

```bash
python3 scripts/alphaxiv.py search "diffusion models" --limit 5
python3 scripts/alphaxiv.py paper 1706.03762
python3 scripts/alphaxiv.py overview 1706.03762 --language zh
python3 scripts/alphaxiv.py top --limit 10
python3 scripts/alphaxiv.py feed --sort Hot --interval "7 Days" --limit 10
python3 scripts/alphaxiv.py ask "What is the main contribution?" --paper 1706.03762
```

## Authentication (for `ask` command only)

1. Log in at https://www.alphaxiv.org
2. Go to Profile → User Settings → API Keys
3. Create a new API key
4. Export it in your shell:
   ```bash
   export ALPHAXIV_TOKEN=your_api_key_here
   ```

All other commands work without authentication.

## Requirements

- Python 3.10+
- No third-party dependencies (uses stdlib only)
- `curl` (for `ask` command streaming)

## Compatibility

This skill follows the [Agent Skills open standard](https://agentskills.io) and works with any compatible agent framework. The `SKILL.md` frontmatter is optimized for Claude Code but the script runs standalone in any environment.
