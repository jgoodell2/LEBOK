#!/usr/bin/env python

from typing import Dict, List
import mammoth
import re


def convert_docx_to_md(filepath: str) -> str:
    """Convert a DOCX file to Markdown"""
    with open(filepath, "rb") as docx_file:
        result = mammoth.convert_to_markdown(docx_file)
        markdown_text = result.value
        return markdown_text


def strip_html_tags(text: str) -> str:
    """Remove HTML tags and preserve inner text"""
    return re.sub(r"<[^>]+>", "", text)


def clean_heading_text(text: str) -> str:
    # Unescape periods
    text = re.sub(r"\\\.", ".", text)

    return text.strip()


def split_by_headings(md_text: str) -> Dict[str, List[str]]:
    """
    Split a Markdown string by headings
    Returns: {heading: [paragraphs]}
    """

    sections: Dict[str, List[str]] = {}
    current_heading = None
    buffer: List[str] = []

    # Match all heading levels
    heading_pattern = re.compile(r"^(#{1,6})\s+(.*)$")

    # Split markdown into lines
    lines = md_text.splitlines()

    for line in lines:
        line = line.rstrip()
        match = heading_pattern.match(line)

        if match:
            # Found a new heading
            if current_heading and buffer:
                sections[current_heading].append("\n".join(buffer).strip())
                buffer = []

            # Set new heading
            current_heading = (
                strip_html_tags(match.group(2).strip()) or "Untitled Section"
            )
            current_heading = clean_heading_text(current_heading)
            if current_heading not in sections:
                sections[current_heading] = []
        else:
            if current_heading:
                buffer.append(line)

    # Save any remaining buffer
    if current_heading and buffer:
        sections[current_heading].append("\n".join(buffer).rstrip())

    return sections


def getSections(filepath: str) -> Dict[str, List[str]]:
    """
    Returns document content split by headings into markdown paragraphs
    """
    md_text = convert_docx_to_md(filepath)
    sections = split_by_headings(md_text)
    return sections


if __name__ == "__main__":
    filepath = "lebok.docx"
    sections = getSections(filepath)

    for heading, paragraphs in sections.items():
        print(f"--- {heading} ---")
        for paragraph in paragraphs:
            print(paragraph)
            print()
