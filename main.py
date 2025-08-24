from server import mcp

# ------------------------------------------------------------------ #
# Entry point
# ------------------------------------------------------------------ #

if __name__ == "__main__":
    mcp.run(transport="streamable-http", host="0.0.0.0", port=8000)