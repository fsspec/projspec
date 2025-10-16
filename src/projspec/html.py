def dict_to_html(data: dict, title="Data", open_level=2) -> str:
    """
    Convert a nested dictionary to expandable HTML using <details> tags.

    Args:
        data: The dictionary to convert
        title: Title for the details element
        open_level: whether to set elements as expanded; yes if > 0, and will
            decrement for inner levels.

    Returns:
        String containing HTML with expandable details elements
    """
    # With help from Claude Sonnet 4.
    if not isinstance(data, dict):
        return f"<span>{data}</span>"

    if not data:
        return ""
    open = "open" if open_level > 0 else "closed"

    html = [
        f'<details {open} style="margin-left: 20px; margin-bottom: 10px;"><summary style="cursor: pointer; color: #2c5aa0; padding: 5px;"><strong>{title}</strong></summary>'
    ]

    for key, value in data.items():
        if isinstance(value, dict):
            html.append(dict_to_html(value, key, open_level - 1))
        elif isinstance(value, (list, tuple)):
            html.append(
                f'<details style="margin-left: 20px; margin-bottom: 10px;"><summary style="cursor: pointer; color: #2c5aa0; padding: 5px;"><strong>{key}</strong></summary>'
            )
            for i, item in enumerate(value):
                if isinstance(item, dict):
                    html.append(dict_to_html(item, f"{key}[{i}]", open_level - 1))
                else:
                    html.append(f'<div style=" margin: 5px 0;"> {item}</div>')
            html.append("</details>")
        else:
            html.append(
                f'<div style=" margin: 5px 0;"><strong>{key}:</strong> {value}</div>'
            )

    html.append("</details>")
    return "".join(html)
