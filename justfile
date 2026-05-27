# List available recipes
default:
    @just --list

# Install project dependencies
install:
    uv sync

# Run the Streamlit app
run:
    uv run streamlit run streamlit_app.py

# Lint with ruff
lint:
    uvx ruff check streamlit_app.py

# Reorder imports then format with ruff
format:
    -uvx reorder-python-imports streamlit_app.py
    uvx ruff format streamlit_app.py
