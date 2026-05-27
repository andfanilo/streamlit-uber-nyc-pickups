# Streamlit Demo: Uber Pickups in New York City

Rebuilding <https://demo-uber-nyc-pickups.streamlit.app/> with modern Streamlit

## Prerequisites

- [`uv`](https://docs.astral.sh/uv/getting-started/installation/) — Python package and project manager
- [`just`](https://github.com/casey/just#installation) — command runner

## Development

Run `just` (no args) to list commands.

| Command        | What it does                                                      |
| -------------- | ----------------------------------------------------------------- |
| `just install` | Install project dependencies with `uv sync`                       |
| `just run`     | Run the Streamlit app                                             |
| `just lint`    | Lint with `ruff check`                                            |
| `just format`  | Reorder imports with `reorder-python-imports`, then `ruff format` |

## Resources

- Uber website: https://www.uber.com
- Uber Base design system: https://base.uber.com
