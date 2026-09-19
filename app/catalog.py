"""Landing-page tool categories and ordered slug lists.

Every registered tool should appear exactly once: either as an essential
card or inside the "More tools" disclosure (grouped by category). Unknown
slugs (new tools not yet listed) are appended under "Other" so nothing is
dropped.
"""

# Always-visible card grid (~8–12 primary tools).
ESSENTIALS = [
    "merge",
    "split",
    "compress",
    "organize_pdf",
    "rotate",
    "pdf_to_images",
    "images_to_pdf",
    "office_to_pdf",
    "protect_pdf",
    "unlock_pdf",
    "ocr_pdf",
    "watermark",
]

# Ordered categories: (section title, ordered tool slugs)
CATEGORIES = [
    (
        "Organize & pages",
        [
            "merge",
            "split",
            "organize_pdf",
            "reverse_pages",
            "add_blank_pages",
            "remove_blank_pages",
            "duplicate_pages",
            "rotate",
            "nup",
            "pdf_booklet",
            "crop_pdf",
        ],
    ),
    (
        "Edit & annotate",
        [
            "watermark",
            "page_numbers",
            "header_footer",
            "redact_pdf",
            "sign_pdf",
            "fill_pdf_forms",
            "flatten_pdf",
            "remove_annotations",
        ],
    ),
    (
        "Secure & info",
        [
            "protect_pdf",
            "unlock_pdf",
            "metadata_editor",
            "remove_metadata",
            "pdf_compare",
            "pdf_repair",
        ],
    ),
    (
        "Convert from PDF",
        [
            "pdf_to_images",
            "pdf_to_pptx",
            "pdf_to_docx",
            "pdf_to_excel",
            "pdf_to_text",
            "pdf_to_html",
            "pdf_to_svg",
            "extract_images",
            "ocr_pdf",
        ],
    ),
    (
        "Create / convert to PDF",
        [
            "images_to_pdf",
            "office_to_pdf",
            "text_to_pdf",
            "html_to_pdf",
            "md_to_pdf",
            "compress",
            "grayscale_pdf",
            "pdf_color_converter",
            "deskew_pdf",
        ],
    ),
    (
        "Images & spreadsheets",
        [
            "image_convert",
            "csv_to_xlsx",
            "xlsx_to_csv",
        ],
    ),
]


def _card(slug, entry):
    return {
        "slug": slug,
        "title": entry.manifest.get("title", slug),
        "description": entry.manifest.get("description", ""),
        "icon": entry.manifest.get("icon", "📄"),
        "url": entry.url(),
        "available": entry.available,
    }


def group_tools(tool_entries):
    """Build landing-page sections.

    Returns ``{"essentials": [card, ...], "more": [{"title", "tools"}, ...]}``.
    Essentials are always-visible cards; ``more`` is category-grouped links
    for everything else. Unknown registered slugs land under "Other".
    """
    essential_set = set(ESSENTIALS)
    known = set()
    for _, slugs in CATEGORIES:
        known.update(slugs)

    essentials = [
        _card(slug, tool_entries[slug])
        for slug in ESSENTIALS
        if slug in tool_entries
    ]

    more = []
    for title, slugs in CATEGORIES:
        tools = [
            _card(slug, tool_entries[slug])
            for slug in slugs
            if slug in tool_entries and slug not in essential_set
        ]
        if tools:
            more.append({"title": title, "tools": tools})

    other_slugs = sorted(s for s in tool_entries if s not in known)
    if other_slugs:
        more.append({
            "title": "Other",
            "tools": [_card(s, tool_entries[s]) for s in other_slugs],
        })

    # Never leave the homepage empty when tools are registered.
    if not essentials and tool_entries:
        essentials = [
            _card(slug, tool_entries[slug])
            for slug in sorted(tool_entries)
        ]
        more = []

    return {"essentials": essentials, "more": more}
