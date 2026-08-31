import httpx
from bs4 import BeautifulSoup
from urllib.parse import quote_plus


TRUSTED_DOCS = {
    "react": [
        "react.dev",
    ],

    "fastapi": [
        "fastapi.tiangolo.com",
    ],

    "python": [
        "docs.python.org",
    ],

    "javascript": [
        "developer.mozilla.org",
    ],

    "java": [
        "docs.oracle.com",
    ],

    "spring": [
        "docs.spring.io",
    ],

    "docker": [
        "docs.docker.com",
    ],

    "github": [
        "docs.github.com",
    ],
}


def detect_domains(question: str):

    text = question.lower()

    selected = []

    for key, domains in TRUSTED_DOCS.items():

        if key in text:

            selected.extend(domains)

    if not selected:

        selected = [
            "react.dev",
            "fastapi.tiangolo.com",
            "docs.python.org",
            "developer.mozilla.org",
            "docs.github.com",
        ]

    return selected


async def fetch_page_text(url: str):

    try:

        async with httpx.AsyncClient(
            timeout=15.0,
            follow_redirects=True,
            headers={
                "User-Agent": "DevMind/1.0"
            },
        ) as client:

            response = await client.get(url)

        if not response.is_success:
            return ""

        content_type = response.headers.get(
            "content-type",
            ""
        )

        if "text/html" not in content_type:
            return ""

        soup = BeautifulSoup(
            response.text,
            "html.parser",
        )

        for tag in soup(
            [
                "script",
                "style",
                "nav",
                "footer",
                "header",
            ]
        ):
            tag.decompose()

        text = soup.get_text(
            separator="\n"
        )

        lines = [
            line.strip()
            for line in text.splitlines()
            if line.strip()
        ]

        return "\n".join(lines)[:15000]

    except Exception as error:

        print(
            "DOC PAGE ERROR:",
            repr(error)
        )

        return ""