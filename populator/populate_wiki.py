#!/usr/bin/env python
import enum
import requests
import json
import re
import argparse
from dotenv import load_dotenv
import os
import sys
from typing import Dict, List, Any
import parse_book
import html
from pathlib import Path
from wikinav import create_navlinks

script_dir = Path(__file__).resolve().parent
dotenv_path = script_dir.parent / ".env"
load_dotenv(dotenv_path)

project_root = dotenv_path.parent

API_URL = os.getenv("API_URL")
API_TOKEN = os.getenv("API_KEY")
LOCALE = os.getenv("WIKI_LOCALE")

queries_path_relative = os.getenv("QUERIES_BASEPATH")
QUERIES_BASEPATH = (project_root / queries_path_relative).resolve()

LIST_PAGES_QUERY_FILE = "list_pages.gql"
GET_PAGE_QUERY_FILE = "get_page.gql"
UPDATE_PAGE_MUTATION_FILE = "update_page.gql"
CREATE_PAGE_MUTATION_FILE = "create_page.gql"
DELETE_PAGE_MUTATION_FILE = "delete_page.gql"
CREATE_NAV_MUTATION_FILE = "update_navigation.gql"


def run_graphql_query(query: str, variables: Dict = None) -> Dict:
    """Runs a GraphQL query and returns the result"""
    if not API_TOKEN:
        print("Error: API_KEY environment variable not set!")
        sys.exit(1)

    headers = {"Authorization": f"Bearer {API_TOKEN}"}
    payload = {"query": query}

    if variables:
        payload["variables"] = variables

    try:
        response = requests.post(API_URL, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        if "errors" in data:
            for err in data["errors"]:
                print(f"  -> GraphQL Error: {err.get('message', 'Unknown error')}")
        return data
    except requests.exceptions.RequestException as e:
        print(f"  -> HTTP Request Error: {e}")
    except json.JSONDecodeError:
        print("  -> Error: Could not decode JSON response from the server.")
    # Return an empty dict on failure
    return {}


def delete_all_pages(list_query: str, delete_mutation: str):
    """Gets all page ids and deletes the associated pages"""
    print("Getting all page ids...")
    response_data = run_graphql_query(list_query)
    pages = response_data.get("data", {}).get("pages", {}).get("list", [])

    if not pages:
        print("No pages found to delete.")
        return

    print(f"Found {len(pages)} pages. Starting deletion...")

    deleted_count, failed_count = 0, 0

    for page in pages:
        # if page["path"] == "home":
        #     continue

        print(f"Deleting page '{page['path']}' (ID: {page['id']})...", end="")
        delete_response = run_graphql_query(delete_mutation, {"id": page["id"]})

        succeeded = (
            delete_response.get("data", {})
            .get("pages", {})
            .get("delete", {})
            .get("responseResult", {})
            .get("succeeded", False)
        )

        if succeeded:
            print(" Done.")
            deleted_count += 1
        else:
            print(" Failed.")
            failed_count += 1

    print("\n--- Deletion Complete ---")
    print(f"Successfully deleted: {deleted_count} pages.")
    print(f"Failed to delete: {failed_count} pages.")


def get_page(path: str):
    """
    Get a page by its path.
    """
    try:
        get_page_query_path = os.path.join(QUERIES_BASEPATH, GET_PAGE_QUERY_FILE)

        with open(get_page_query_path, "r") as f:
            get_page_q = f.read()

            variables = {"path": path, "locale": LOCALE}

            response = run_graphql_query(get_page_q, variables)
            return response.get("data", {}).get("pages", {}).get("singleByPath")
    except FileNotFoundError as e:
        print(f"Error: Could not find query file for getting a page: {e.filename}")


def update_page(id: int, path: str, title: str, content: str) -> bool:
    """
    Update a page's content given its id.
    """
    try:
        update_page_mutation_path = os.path.join(
            QUERIES_BASEPATH, UPDATE_PAGE_MUTATION_FILE
        )

        with open(update_page_mutation_path) as f:
            update_page_m = f.read()

            variables = {
                "id": id,
                "path": path,
                "title": title,
                "description": title,
                "locale": LOCALE,
                "content": content,
                "editor": "code",
            }

            response = run_graphql_query(update_page_m, variables)
            return (
                response.get("data", {})
                .get("pages", {})
                .get("update", {})
                .get("responseResult", {})
                .get("succeeded", False)
            )
    except FileNotFoundError as e:
        print(f"Error: Could not find mutation file for updating a page: {e.filename}")
        return False


def delete_page(id: int) -> bool:
    """
    Delete a page, referencing it by its id.
    """
    try:
        delete_page_mutation_path = os.path.join(
            QUERIES_BASEPATH, DELETE_PAGE_MUTATION_FILE
        )

        with open(delete_page_mutation_path, "r") as f:
            delete_mutation = f.read()

        response = run_graphql_query(delete_mutation, {"id": id})

        return (
            response.get("data", {})
            .get("pages", {})
            .get("delete", {})
            .get("responseResult", {})
            .get("succeeded", False)
        )
    except FileNotFoundError as e:
        print(f"Error: Could not find mutation to delete a page: {e.filename}")
        return False


def create_navigation(nav_items: List[Dict[str, Any]]):
    try:
        create_nav_mutation_path = os.path.join(
            QUERIES_BASEPATH, CREATE_NAV_MUTATION_FILE
        )

        with open(create_nav_mutation_path, "r") as f:
            make_navbar = f.read()

        variables = {"tree": [{"locale": LOCALE, "items": nav_items}]}
        response_data = run_graphql_query(make_navbar, variables)

        result = (
            response_data.get("data", {})
            .get("navigation", {})
            .get("updateTree", {})
            .get("responseResult", {})
        )

        if result.get("succeeded"):
            print("Done.")
        else:
            print(" Failed.")
            msg = result.get("message", "Unknown error")
            print(f"  -> Error: {msg}")

        # print(json.dumps(response_data, indent=4))

        # succeeded = (
        #     response_data.get("data", {})
        #     .get("pages", {})
        #     .get("delete", {})
        #     .get("responseResult", {})
        #     .get("succeeded", False)
        # )

    except FileNotFoundError as e:
        print(f"Error: Could not find mutation file for making navlinks: {e.filename}")
        sys.exit(1)


def flatten_tree(nodes: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Flatten the wiki tree into a linear list
    """
    flattened_tree = []
    for node in nodes:
        flattened_tree.append(node)
        if node["children"]:
            flattened_tree.extend(flatten_tree(node["children"]))

    return flattened_tree


def build_nav_map(nodes: List[Dict[str, Any]]) -> Dict[str, str]:
    """
    Builds a map of slugs and HTML strings for previous/next buttons
    """
    flat_list = flatten_tree(nodes)
    nav_map = {}

    for i, node in enumerate(flat_list):
        prev_link = ""
        next_link = ""

        # Make link to previous page
        if i > 0:
            prev_node = flat_list[i - 1]
            prev_url = f"/{LOCALE}/{prev_node['slug']}"
            prev_title = html.escape(prev_node["title"])
            prev_link = f'<a href="{prev_url}" style="text-decoration: none;">&larr; {prev_title}</a>'

        # Make link to next page
        if i < len(flat_list) - 1:
            next_node = flat_list[i + 1]
            next_url = f"/{LOCALE}/{next_node['slug']}"
            next_title = html.escape(next_node["title"])
            next_link = f'<a href="{next_url}" style="text-decoration: none;">{next_title} &rarr;</a>'

        # Build the HTML block to display the links
        nav_html = f"""
        <hr>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 2em; padding-top: 1em;">
            <div style="text-align: left; max-width: 45%;">{prev_link}</div>
            <div style="text-align: right; max-width: 45%;">{next_link}</div>
        </div>
        """
        nav_map[node["slug"]] = nav_html

    return nav_map


def create_wiki_pages(
    nodes: List[Dict[str, Any]],
    create_page_mutation: str,
    do_replace: bool = False,
    do_update: bool = False,
    nav_map: Dict[str, str] = None,
):
    """
    Traverse the document tree and create a wiki page for each section
    """
    for node in nodes:
        title = node["title"]
        content = node["content"]
        # current_slug = create_slug(title)
        # if parent_path:
        #     full_page_path = f"{parent_path.strip('/')}/{current_slug}"
        # else:
        #     full_page_path = current_slug

        full_page_path = node["slug"]

        # Generate subheading links
        if node["children"]:
            subheading_links = []
            for child in node["children"]:
                child_full_slug = child["slug"]
                # Use the full path for the link
                child_path = f"/{LOCALE}/{child_full_slug}"
                # Sanitize the title
                sanitized_title = html.escape(child["title"])
                subheading_links.append(
                    f'<li><a href="{child_path}">{sanitized_title}</a></li>'
                )

            links_list = "\n".join(subheading_links)
            # Append the list of links to the parent page content
            content += f"\n<hr>\n<h2>Subsections:</h2>\n<ul>\n{links_list}\n</ul>"

        # Inject prev/next buttons
        if nav_map and full_page_path in nav_map:
            content += nav_map[full_page_path]

        # Check if page exists
        page_info = get_page(full_page_path)
        page_exists = page_info and "id" in page_info
        page_id = int(page_info["id"]) if page_exists else None

        # Update existing pages if update flag is set
        if do_update:
            print(f"Updating page '{full_page_path}' (ID: {page_id})...", end="")

            if update_page(page_id, full_page_path, title, content):
                print("Done.")
            else:
                print("Failed.")

            # If successful, recurse and then continue (skip page creation) to the next sibling page
            if node["children"]:
                create_wiki_pages(
                    node["children"],
                    create_page_mutation,
                    do_replace,
                    do_update,
                    nav_map,
                )
            continue

        # Delete existing page if replacement flag is set
        if do_replace:
            print(f"Deleting page '{full_page_path}' (ID: {page_id})...", end="")
            page_info = get_page(full_page_path)

            if page_info and "id" in page_info:
                page_id = page_info["id"]

                if delete_page(page_id):
                    print("Done.")
                else:
                    print("Failed (API error).")

        # Call the API to create the page
        print(f"Creating page: '{title}' at path '{full_page_path}'")
        variables = {
            "path": full_page_path,
            "title": title,
            "description": f"{title}",
            "locale": LOCALE,
            "content": content,
            "editor": "code",
        }

        run_graphql_query(create_page_mutation, variables)

        if node["children"]:
            create_wiki_pages(
                node["children"], create_page_mutation, do_replace, do_update, nav_map
            )


def create_slug(text):
    """Converts a string into a URL-friendly slug."""

    # Replace periods with hyphens
    text = text.replace(".", "-")

    # Convert to lowercase
    text = text.lower()

    # Remove all characters that are not letters, numbers, or spaces
    text = re.sub(r"[^a-z0-9\s-]", "", text)

    # Replace one or more spaces with a single hyphen
    text = re.sub(r"\s+", "-", text)

    return text


def main():
    if not all([API_URL, API_TOKEN, LOCALE, QUERIES_BASEPATH]):
        print(
            "Error: One or more required environment variables (API_URL, API_KEY, WIKI_LOCALE, QUERIES_BASEPATH) is not set."
        )
        sys.exit(1)

    parser = argparse.ArgumentParser(description="Populate wiki from DOCX file")
    parser.add_argument(
        "filepath", nargs="?", default=None, type=str, help="Path to the DOCX file"
    )

    group = parser.add_mutually_exclusive_group()

    group.add_argument(
        "--purge",
        action="store_true",
        help="Delete all existing pages before populating",
    )
    group.add_argument(
        "--purge-only",
        action="store_true",
        help="Delete all existing pages and do not populate the wiki",
    )

    group.add_argument(
        "--replace",
        action="store_true",
        help="Delete a page (if it exists) before creating it on the wiki",
    )

    group.add_argument(
        "--update",
        action="store_true",
        help="Updates pages (if existing) to preserve history instead of deleting",
    )

    args = parser.parse_args()

    if args.purge or args.purge_only:
        try:
            list_pages_path = os.path.join(QUERIES_BASEPATH, LIST_PAGES_QUERY_FILE)
            delete_page_path = os.path.join(QUERIES_BASEPATH, DELETE_PAGE_MUTATION_FILE)

            with open(list_pages_path, "r") as f:
                list_query = f.read()
            with open(delete_page_path, "r") as f:
                delete_mutation = f.read()

            delete_all_pages(list_query, delete_mutation)
        except FileNotFoundError as e:
            print(f"Error: Could not find query file for deletion: {e.filename}")
            sys.exit(1)

        if args.purge_only:
            sys.exit(0)

    do_replace = args.replace
    do_update = args.update

    if not args.filepath:
        print("Error: filepath option required unless using --purge-only")
        sys.exit(1)

    try:
        create_page_path = os.path.join(QUERIES_BASEPATH, CREATE_PAGE_MUTATION_FILE)
        with open(create_page_path, "r", encoding="utf-8") as file:
            create_page_mutation = file.read()
    except FileNotFoundError:
        print(f"Error: The query file '{create_page_path}' was not found.")
        sys.exit(1)

    print(f"Parsing content from {args.filepath}...")
    document_tree = parse_book.get_sections(args.filepath)
    nav_items = create_navlinks(document_tree)

    # Build navigation map
    nav_map = build_nav_map(document_tree)

    print("Populating wiki...")
    create_wiki_pages(
        document_tree, create_page_mutation, do_replace, do_update, nav_map
    )

    print("Making navlinks...", end="")
    create_navigation(nav_items)

    print("\n--- Population Complete ---")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nProcess cancelled by user. Exiting.")
        sys.exit(0)
