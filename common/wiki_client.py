import os
import sys
import requests
import json
from pathlib import Path
from dotenv import load_dotenv

# --- Environment Setup ---
# Calculate project root relative to this file (common/wiki_client.py)
current_file = Path(__file__).resolve()
project_root = current_file.parent.parent
dotenv_path = project_root / ".env"
load_dotenv(dotenv_path)

API_URL = os.getenv("API_URL")
API_KEY = os.getenv("API_KEY")
LOCALE = os.getenv("WIKI_LOCALE", "en")


def run_graphql_query(query, variables=None):
    """
    Executes a GraphQL query against the Wiki.js API.
    """
    if not API_KEY:
        print("Error: API_KEY environment variable not set!")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {API_KEY}"}
    payload = {"query": query}

    if variables:
        payload["variables"] = variables

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            print("GraphQL Errors:", data["errors"])

        return data
    except requests.exceptions.RequestException as e:
        print(f"HTTP Request Failed: {e}")
        return {}
