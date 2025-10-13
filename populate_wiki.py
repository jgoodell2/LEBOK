#!/usr/bin/env python
import requests
import json
from urllib import parse
import re
import argparse
from dotenv import load_dotenv
import os
import parseBook

load_dotenv()

API_URL = os.getenv("API_URL")
API_TOKEN = os.getenv(("API_KEY"))

queries_basepath = "queries"
create_page_query_file = "create_page.gql"

fullpath = f"{queries_basepath}/{create_page_query_file}"

# print("Full path:", fullpath)


def clean_heading(heading: str) -> str:
    # Remove html tags
    cleaned = re.sub(r"<[^>]+>", "", heading)

    # Remove leading and trailing whitespace
    return cleaned.strip()


def nukeIt():
    listPages = """
        query {
            pages {
                list {
                    id
                    path
                }
            }
        }
        """
    headers = {"Authorization": f"Bearer {API_TOKEN}"}

    print("Getting all page ids...")
    try:
        response = requests.post(API_URL, headers=headers, json={"query": listPages})
        response.raise_for_status()
        pages = response.json().get("data", {}).get("pages", {}).get("list", [])

        if not pages:
            print("No pages found to delete.")
            return

        print(f"Found {len(pages)} pages to delete.")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching pages: {e}")
        return
    except json.JSONDecodeError:
        print("Error decoding JSON response from the server.")
        return

    deletePages = """
        mutation($id: Int!) {
            pages {
                delete(id: $id) {
                    responseResult {
                        succeeded
                        message
                    }
                }
            }
        }
    """

    deleted_count = 0
    failed_count = 0

    for page in pages:
        page_id = page["id"]
        page_path = page["path"]
        variables = {"id": page_id}
        if page_path != "home":
            try:
                print(f"Deleting page '{page_path}' (ID: {page_id})...", end="")
                delete_response = requests.post(
                    API_URL,
                    headers=headers,
                    json={"query": deletePages, "variables": variables},
                )
                delete_response.raise_for_status()

                result = delete_response.json()
                succeeded = (
                    result.get("data", {})
                    .get("pages", {})
                    .get("delete", {})
                    .get("responseResult", {})
                    .get("succeeded", False)
                )

                if succeeded:
                    print(" Success.")
                    deleted_count += 1
                else:
                    message = (
                        result.get("data", {})
                        .get("pages", {})
                        .get("delete", {})
                        .get("responseResult", {})
                        .get("message", "Unknown error")
                    )
                    print(f" Failed. Reason: {message}")
                    failed_count += 1

            except requests.exceptions.RequestException as e:
                print(f" Failed. Request error: {e}")
                failed_count += 1
            except json.JSONDecodeError:
                print("Failed. Could not decode server response.")
                failed_count += 1

    print("\n--- Deletion Complete ---")
    print(f"Successfully deleted: {deleted_count} pages.")
    print(f"Failed to delete: {failed_count} pages.")


def makePage(book_sections):
    try:
        with open(fullpath, "r", encoding="utf-8") as file:
            queryString = file.read()
            # print("Query string:", queryString)

            print("Going to print the headings now.")
            for heading, paragraphs in book_sections.items():
                content = ""
                content = "\n\n".join(paragraphs)

                print(f"Path: /{parse.quote(heading)}")
                title = clean_heading(heading)

                # Make query variables object
                variables = {
                    "path": f"/{create_slug(title)}",
                    "title": f"{title}",
                    "description": f"Test {title} - is this thing on?",
                    "locale": "en",
                    "content": content,
                    "editor": "markdown",
                }

                payload = {"query": queryString, "variables": variables}
                headers = {"Authorization": f"Bearer {API_TOKEN}"}

                response = requests.post(API_URL, json=payload, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    # print(json.dumps(data, indent=2))
                    if "errors" in data:
                        print(f"QraphQL error for '{heading}':")
                        for err in data["errors"]:
                            message = err.get("message", "Unknown error")
                            print("    ->", message)
                        continue
                else:
                    print(
                        f"Error: {response.status_code} - {json.dumps(response.text, indent=2)}"
                    )

    except FileNotFoundError:
        print(f"Error: The file '{fullpath}' was not found.")
    except Exception as e:
        print(f"An error occurred: {e}")


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


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Populate wiki from DOCX file")
    parser.add_argument(
        "--nuke",
        action="store_true",
        help="Delete all existing pages (except Home) before populating",
    )
    args = parser.parse_args()

    if args.nuke:
        nukeIt()

    docSections = parseBook.getSections("lebok.docx")
    makePage(docSections)
