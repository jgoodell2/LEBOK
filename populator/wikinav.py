from dotenv import load_dotenv
from typing import List, Dict, Any
from pathlib import Path
import json
import os


script_dir = Path(__file__).resolve().parent
dotenv_path = script_dir.parent / ".env"
load_dotenv(dotenv_path)

LOCALE = os.getenv("WIKI_LOCALE")


def is_home(node: Dict[str, Any]):
    return node["slug"].startswith("/home")


def is_glossary(node: Dict[str, Any]):
    return node["level"] == 1 and node["title"].startswith("Glossary")


def is_knowledge_area(node: Dict[str, Any]):
    """
    Determine whether the node represents a top-level knowledge area
    """
    return node["level"] == 1 and node["title"].startswith("Knowledge Area")


def create_nav_item(node: Dict[str, Any]):
    """
    Map a node to a navlink item
    """
    return {
        "id": node["slug"],
        "kind": "link",
        "label": node["title"],
        "icon": "mdi-folder" if node["children"] else "mdi-text-box",
        "targetType": "page",
        "target": f"/{LOCALE}/{node['slug']}",
        "visibilityMode": "all",
        "visibilityGroups": [],
    }


def create_nav_header(title: str):
    """
    Create a header in the navigation menu
    """
    return {
        "id": f"header: {title}",
        "kind": "header",
        "label": title,
        "icon": "",
        "targetType": "",
        "target": "",
        "visibilityMode": "all",
        "visibilityGroups": [],
    }


def create_divider():
    """
    Create a horizontal divider in the navigation menu
    """
    return {
        "id": "divider",
        "kind": "divider",
        "label": "",
        "icon": "",
        "targetType": "",
        "target": "",
        "visibilityMode": "all",
        "visibilityGroups": [],
    }


def create_navlinks(nodes: List[Dict[str, Any]]) -> List:
    """
    Create a list of links to be shown in the navigation sidebar.
    """

    knowledge_areas = map(create_nav_item, filter(is_knowledge_area, nodes))
    glossary = map(create_nav_item, filter(is_glossary, nodes))

    # Everything that isn't a knowledge area or the glossary is probably the
    # introductory information and copyright stuff
    everything_else = (
        create_nav_item(node)
        for node in nodes
        if not is_knowledge_area(node)
        and not is_glossary(node)
        and node["content"] != ""
    )

    return (
        [create_nav_header("Introduction"), create_divider()]
        + list(everything_else)
        + [create_nav_header("Knowledge Areas"), create_divider()]
        + list(knowledge_areas)
        + [create_divider()]
        + list(glossary)
    )


if __name__ == "__main__":
    mock_document_tree = [
        # This will be included in the nav links
        {
            "title": "Knowledge Area 1: Introduction",
            "level": 1,
            "slug": "knowledge-area-1-introduction",
            "content": "...",
            "children": [
                # This child will be filtered out (level != 1)
                {
                    "title": "1.1 Basic Concepts",
                    "level": 2,
                    "slug": "1-1-basic-concepts",
                    "content": "...",
                    "children": [],
                },
            ],
        },
        # This will be included in the nav links
        {
            "title": "Knowledge Area 2: Fundamentals",
            "level": 1,
            "slug": "knowledge-area-2-fundamentals",
            "content": "...",
            "children": [],
        },
        # This will be filtered out (doesn't start with "Knowledge Area")
        {
            "title": "Appendix A: Glossary",
            "level": 1,
            "slug": "appendix-a-glossary",
            "content": "...",
            "children": [],
        },
    ]

    # Generate the navigation links list
    nav_items = create_navlinks(mock_document_tree)

    # Print the resulting list in a readable JSON format
    print("--- Generated Navigation Items (Flat List) ---")
    print(json.dumps(nav_items, indent=4))
    print("---------------------------------------------")
