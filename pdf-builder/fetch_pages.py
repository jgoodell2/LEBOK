import sys
import requests
import re
from pathlib import Path

current_dir = Path(__file__).resolve().parent
project_root = current_dir.parent
sys.path.append(str(project_root))

from common.wiki_client import run_graphql_query


CHAPTER_ORDER = [
    "home",
    "copyright-copyleft-intentions-and-recommended-citation",
    "foreword",
    "editor-contributing-editors-contributors-and-reviewers",
    "introduction-to-the-guide",
    "knowledge-area-1-learning-engineering-basics",
    "knowledge-area-2-human-centered-design-foundations",
    "knowledge-area-3-learning-sciences-foundations",
    "knowledge-area-4-engineering-foundations",
    "knowledge-area-5-learning-engineering-models-and-methods",
    "knowledge-area-6-the-learning-engineering-process",
    "knowledge-area-7-data-instrumentation",
    "knowledge-area-8-learning-analytics",
    "knowledge-area-9-lean-agile-methodologies-in-learning-engineering",
    "knowledge-area-10-learning-engineering-operations-project-management",
    "knowledge-area-11-learning-engineering-professional-practice",
    "knowledge-area-12-the-learning-engineering-enterprise",
    "glossary-of-terms",
    "consolidated-references",
]


def get_natural_sort_key(page_obj):
    """
    Helper to sort sub-pages (Topics) numerically (1.1, 1.2, 1.10).
    """
    path = page_obj["path"]
    segments = path.split("/")
    parsed_segments = []
    for seg in segments:
        # Split text and numbers: "topic-1-10" -> ['topic-', 1, '-', 10]
        parts = [
            int(text) if text.isdigit() else text.lower()
            for text in re.split(r"(\d+)", seg)
        ]
        parsed_segments.append(parts)
    return parsed_segments


def fetch_ordered_pages():
    # Load query
    query_path = project_root / "queries" / "list_pages.gql"
    with open(query_path, "r") as f:
        query = f.read()

    print("Fetching pages from Wiki...")
    data = run_graphql_query(query)
    all_pages = data.get("data", {}).get("pages", {}).get("list", [])

    if not all_pages:
        print("No pages found.")
        return []

    # 1. Group pages by their "Root Slug" (The top-level chapter)
    #    e.g. 'knowledge-area-1/topic-1' belongs to 'knowledge-area-1'
    grouped_pages = {slug: [] for slug in CHAPTER_ORDER}
    orphans = []

    for page in all_pages:
        path = page["path"]
        # Extract the first part of the path (the root folder)
        root_slug = path.split("/")[0]

        if root_slug in grouped_pages:
            grouped_pages[root_slug].append(page)
        elif path in grouped_pages:
            # Handle cases where the page IS the root slug
            grouped_pages[path].append(page)
        else:
            # Edge case: Sometimes 'knowledge-area-1' might match 'knowledge-area-1-basics'
            orphans.append(page)

    # 2. Build the final sorted list
    sorted_output = []

    for chapter_slug in CHAPTER_ORDER:
        pages_in_chapter = grouped_pages.get(chapter_slug, [])

        # Sort these pages naturally so that:
        # KA1 (Parent) comes before KA1/Topic 1
        # KA1/Topic 2 comes before KA1/Topic 10
        pages_in_chapter.sort(key=get_natural_sort_key)

        sorted_output.extend(pages_in_chapter)

    # 3. Handle orphans
    if orphans:
        print(f"\n[Warning] {len(orphans)} pages did not match the navigation order:")
        for o in orphans:
            print(f" - {o['path']}")
        # sorted_output.extend(orphans) # Uncomment to include them at the end

    return sorted_output


if __name__ == "__main__":
    ordered_pages = fetch_ordered_pages()
    print(f"\nSuccessfully ordered {len(ordered_pages)} pages based on navigation.")

    # Print preview
    for p in ordered_pages:
        print(p["path"])
