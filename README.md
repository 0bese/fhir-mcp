# Mock Remote FHIR MCP

This project is a mock remote FHIR mcp. It is **not intended for production use**.

## Getting Started

Follow these instructions to get a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

*   [Git](https://git-scm.com/)
*   [uv](https://github.com/astral-sh/uv)
*   A Python version compatible with this project (as defined in `.python-version`).

### Installation & Running

1.  **Clone the repository:**

    ```bash
    git clone https://github.com/0bese/fhir-mcp.git
    cd fhir-mcp
    ```

2.  **Create and activate a virtual environment:**

    It's recommended to use the Python version specified in the `.python-version` file.

    ```bash
    # Create the virtual environment
    uv venv

    # Activate the virtual environment
    # On macOS and Linux:
    source .venv/bin/activate
    # On Windows:
    # .\.venv\Scripts\activate
    ```

3.  **Sync the dependencies using uv:**

    This will install all the necessary packages listed in `pyproject.toml` and `uv.lock`.

    ```bash
    uv sync
    ```

4.  **Run the application:**

    ```bash
    uv run main.py
    ```
