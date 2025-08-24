# Mock FHIR Server

This project is a mock FHIR server. It is **not intended for public use**.

## Getting Started

Follow these instructions to get a copy of the project up and running on your local machine for development and testing purposes.

### Prerequisites

*   [Git](https://git-scm.com/)
*   [uv](https://github.com/astral-sh/uv)
*   A Python version compatible with this project (as defined in `.python-version`).

### Installation & Running

1.  **Clone the repository:**

    ```bash
    git clone <repository-url>
    cd fhir-mcp
    ```
    *(Replace `<repository-url>` with the actual URL of this repository.)*

2.  **Create and activate a virtual environment:**

    It's recommended to use the Python version specified in the `.python-version` file.

    ```bash
    # Create the virtual environment
    python -m venv .venv

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