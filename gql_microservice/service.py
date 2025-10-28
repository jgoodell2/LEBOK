#!/usr/bin/env python
from dotenv import load_dotenv
from flask import Flask, jsonify, request
import requests
from typing import Dict, List, Any
import sys
import os
import json
import re

load_dotenv()

API_URL = os.getenv("API_URL")
API_TOKEN = os.getenv("API_KEY")
QUERIES_BASEPATH = os.getenv("QUERIES_BASEPATH")
WIKI_LOCALE = os.getenv("WIKI_LOCALE")
WIKI_URL = os.getenv("WIKI_URL")
GET_PAGE_QUERY_FILE = "get_page.gql"

app = Flask(__name__)

try:
    full_query_path = os.path.join(QUERIES_BASEPATH, GET_PAGE_QUERY_FILE)
    with open(full_query_path, "r") as f:
        GET_PAGE_QUERY = f.read()
except FileNotFoundError:
    print(f"Error: Query file '{full_query_path}' not found!")
    sys.exit(1)


def get_name_from_slug(slug: str) -> str:
    """
    Reverses a slug back into a readable name
    """
    # Remove the reference code
    slug = re.sub(r"^[\d-]+-", "", slug)

    # Replace hyphens with spaces
    name = slug.replace("-", " ")

    # Transform it to title case
    return name.title().strip()


def get_topic_name(title: str, level_designator: str | None) -> str:
    """
    Extracts the Topic or Subtopic name from the title by removing the level code
    """
    if not title:
        return ""

    if level_designator:
        remove_designator_pattern = re.compile(
            r"^\s*" + re.escape(level_designator) + r"\s*", re.IGNORECASE
        )
        content = remove_designator_pattern.sub("", title, 1).strip()

    else:
        content = title.strip()

    return content


def get_level_designator(title: str) -> str | None:
    """
    Tries to find a dot notation competency level desginator (e.g. "1.1") in the title
    """
    # Regex to find a pattern like "1.1" or "2.4" or the like
    pattern = r"(\d+(\.\d+)+)"

    # Find the pattern at the beginning of the title
    title_match = re.search(r"^\s*" + pattern, title)
    if title_match:
        return title_match.group(1)

    # Return None if not found in the title
    return None


def transform_to_ldjson(data):
    try:
        page_data = data["data"]["pages"]["singleByPath"]
    except KeyError:
        return {}

    base_url = WIKI_URL

    title = page_data.get("title")
    path = page_data.get("path", "")
    competencyLevel = get_level_designator(title)
    description = page_data.get("content")

    # Get current page's base name
    current_name = get_topic_name(title, competencyLevel)
    is_subtopic = competencyLevel and (len(competencyLevel.split(".")) >= 3)

    # Initial type label
    type_label = current_name

    if is_subtopic:
        # Find parent's slug
        path_parts = path.strip("/").split("/")

        if len(path_parts) >= 2:
            topic_slug = path_parts[1]

            topic_name = get_name_from_slug(topic_slug)

            # Build the final type label
            if topic_name:
                type_label = f"{topic_name} / {current_name}"

    ld_json = {
        "@context": {
            "scd": "https://opensource.ieee.org/scd/",
            "skos": "http://www.w3.org/2004/02/skos/core#",
            "xsd": "http://www.w3.org/2001/XMLSchema#",
            "id": {"@id": "@id", "@type": "@id"},
            "scd:associationType": {
                "@type": "@id",
                "@context": {
                    "@base": "https://opensource.ieee.org/scd/AssociationTypes/"
                },
            },
            "scd:category": {"@container": "@language"},
            "scd:competencyStatement": {"@container": "@language"},
            "scd:competencyLevel": {"@type": "@id"},
            "scd:description": {"@container": "@language"},
            "scd:destination": {"@type": "@id"},
            "scd:feedback": {"@container": "@language"},
            "scd:hasCompetencyDefinition": {"@type": "@id"},
            "scd:hasCompetencyFramework": {"@type": "@id"},
            "scd:hasCriterion": {"@type": "@id"},
            "scd:hasRubric": {"@type": "@id"},
            "scd:method": {
                "@type": "@id",
                "@context": {"@base": "https://opensource.ieee.org/scd/Methods/"},
            },
            "scd:name": {"@container": "@language"},
            "scd:originalFramework": {"@type": "@id"},
            "scd:position": {"@type": "xsd:decimal"},
            "scd:referenceCode": {},
            "scd:resourceAssociation": {"@type": "@id"},
            "scd:rubricCriterionLevel": {"@type": "@id"},
            "scd:score": {"@type": "xsd:decimal"},
            "scd:source": {"@type": "@id"},
            "scd:type": {
                "@type": "@id",
                "@context": {"@base": "https://opensource.ieee.org/scd/Types/"},
            },
            "scd:typeLabel": {"@container": "@language"},
            "scd:weight": {"@type": "xsd:decimal"},
        },
        # "@type": page_data.get("title"),
        "@id": os.path.join(base_url, WIKI_LOCALE, page_data.get("path", "")),
        "scd:name": title,
        "scd:description": description,
        "scd:competencyDefinition": description,
        "scd:typeLabel": type_label,
    }

    if competencyLevel:
        ld_json["scd:referenceCode"] = competencyLevel

    return ld_json


def run_graphql_query(query: str, variables: Dict | None = None) -> Dict:
    """Runs a GraphQL query and returns the result"""
    if not API_TOKEN:
        print("Error: API_KEY environment variable not set!")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    payload = {"query": query}

    print(f"  -> Sending payload to {API_URL}:")
    print(json.dumps(payload, indent=2))

    if variables:
        payload["variables"] = variables

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            for err in data["errors"]:
                print(f"  -> GraphQL Error: {err.get('message', 'Unknown error')}")

        ldjson = transform_to_ldjson(data)
        return ldjson
    except requests.exceptions.RequestException as e:
        print(f"  -> HTTP Request Error: {e}")
    except json.JSONDecodeError:
        print("  -> Error: Could not decode JSON response from the server.")
    # Return an empty dict on failure
    return {}


@app.route("/", defaults={"path": ""})
@app.route("/<path:path>")
def handle_request(path):
    # The page path will probably start with the locale.
    if path.startswith(f"{WIKI_LOCALE}/"):
        # If it does, strip the prefix to get the clean page path slug.
        page_path = path[len(f"{WIKI_LOCALE}/") :]
    else:
        # Otherwise, use the path as-is (or default to 'home' if it's empty).
        page_path = path or "home"

    print(f"Received request for '{path}', querying Wiki.js API for {page_path}...")

    query_variables = {"path": page_path, "locale": WIKI_LOCALE}

    response = run_graphql_query(GET_PAGE_QUERY, query_variables)

    status_code = 502 if "errors" in response else 200

    return jsonify(response), status_code


if __name__ == "__main__":
    if not all([API_URL, API_TOKEN, WIKI_LOCALE, QUERIES_BASEPATH]):
        print(
            "Error: One or more required environment variables (API_URL, API_KEY, WIKI_LOCALE, QUERIES_BASEPATH) are not set."
        )
        sys.exit(1)
    app.run(host="127.0.0.1", port=9000)
