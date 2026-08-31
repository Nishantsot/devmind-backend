import os
import base64

import httpx

from dotenv import load_dotenv

from urllib.parse import quote


load_dotenv()


GITHUB_TOKEN = os.getenv(
    "GITHUB_TOKEN"
)


GITHUB_API = (
    "https://api.github.com"
)


# =========================================================
# SOURCE CODE CONFIG
# =========================================================

SUPPORTED_EXTENSIONS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".html",
    ".css",
    ".scss",
    ".json",
    ".md",
    ".sql",
    ".xml",
    ".yml",
    ".yaml",
    ".properties",
    ".gradle",
    ".sh",
}


SUPPORTED_FILENAMES = {
    "Dockerfile",
    "requirements.txt",
    "package.json",
    "pom.xml",
    "build.gradle",
    "settings.gradle",
    "vite.config.js",
    "vite.config.ts",
}


IGNORED_DIRECTORIES = {
    ".git",
    ".github",
    "node_modules",
    "dist",
    "build",
    "target",
    "coverage",
    ".next",
    ".vite",
    ".idea",
    ".vscode",
    "__pycache__",
    ".venv",
    "venv",
    "vendor",
}


MAX_FILES = 80

MAX_FILE_CHARS = 12000

MAX_CONTEXT_CHARS = 100000


# =========================================================
# HEADERS
# =========================================================

def get_headers():

    headers = {
        "Accept":
            "application/vnd.github+json",

        "X-GitHub-Api-Version":
            "2026-03-10",
    }


    if GITHUB_TOKEN:

        headers[
            "Authorization"
        ] = (
            f"Bearer {GITHUB_TOKEN}"
        )


    return headers


# =========================================================
# PARSE GITHUB REPOSITORY
# =========================================================

def parse_repo_url(
    repo_url: str
):

    repo_url = (
        repo_url
        .strip()
        .rstrip("/")
    )


    if repo_url.endswith(
        ".git"
    ):

        repo_url = (
            repo_url[:-4]
        )


    parts = (
        repo_url.split("/")
    )


    if len(parts) < 2:

        raise ValueError(
            "Invalid GitHub repository URL"
        )


    owner = parts[-2]

    repo = parts[-1]


    if not owner or not repo:

        raise ValueError(
            "Invalid GitHub repository URL"
        )


    return owner, repo


# =========================================================
# REQUEST HELPER
# =========================================================

async def github_get(
    endpoint: str,
    params=None,
):

    url = (
        f"{GITHUB_API}{endpoint}"
    )


    async with httpx.AsyncClient(
        timeout=30.0
    ) as client:

        response = await client.get(
            url,
            headers=get_headers(),
            params=params,
        )


    if response.status_code == 404:

        raise ValueError(
            "GitHub resource not found"
        )


    if response.status_code == 401:

        raise ValueError(
            "Invalid GitHub token"
        )


    if response.status_code == 403:

        raise ValueError(
            "GitHub API access denied "
            "or rate limit exceeded"
        )


    if not response.is_success:

        raise ValueError(
            f"GitHub API error: "
            f"{response.status_code}"
        )


    return response.json()


# =========================================================
# REPOSITORY INFO
# =========================================================

async def get_repository(
    owner: str,
    repo: str,
):

    return await github_get(
        f"/repos/{owner}/{repo}"
    )


# =========================================================
# REPOSITORY CONTENTS
# =========================================================

async def get_repository_contents(
    owner: str,
    repo: str,
    path: str = "",
):

    endpoint = (
        f"/repos/{owner}/{repo}/contents"
    )


    if path:

        safe_path = quote(
            path,
            safe="/"
        )

        endpoint += (
            f"/{safe_path}"
        )


    return await github_get(
        endpoint
    )


# =========================================================
# CHECK SUPPORTED SOURCE FILE
# =========================================================

def is_supported_source_file(
    filename: str
):

    if filename in SUPPORTED_FILENAMES:

        return True


    extension = (
        os.path.splitext(
            filename
        )[1]
        .lower()
    )


    return (
        extension
        in SUPPORTED_EXTENSIONS
    )


# =========================================================
# CHECK IGNORED PATH
# =========================================================

def should_ignore_path(
    path: str
):

    parts = (
        path
        .replace("\\", "/")
        .split("/")
    )


    for part in parts:

        if part in IGNORED_DIRECTORIES:

            return True


    return False


# =========================================================
# READ ONE GITHUB FILE
# =========================================================

async def get_repository_file_text(
    owner: str,
    repo: str,
    path: str,
):

    safe_path = quote(
        path,
        safe="/"
    )


    data = await github_get(
        f"/repos/{owner}/{repo}/contents/{safe_path}"
    )


    if not isinstance(
        data,
        dict
    ):

        return ""


    if data.get("type") != "file":

        return ""


    encoded_content = (
        data.get("content")
    )


    encoding = (
        data.get("encoding")
    )


    if (
        not encoded_content
        or encoding != "base64"
    ):

        return ""


    try:

        decoded_bytes = (
            base64.b64decode(
                encoded_content
            )
        )


        text = (
            decoded_bytes.decode(
                "utf-8",
                errors="ignore",
            )
        )


        return text[
            :MAX_FILE_CHARS
        ]


    except Exception as error:

        print(
            "FILE DECODE ERROR:",
            path,
            repr(error),
        )


        return ""


# =========================================================
# RECURSIVELY COLLECT SOURCE FILE PATHS
# =========================================================

async def collect_repository_source_paths(
    owner: str,
    repo: str,
    path: str = "",
    collected=None,
):

    if collected is None:

        collected = []


    if len(collected) >= MAX_FILES:

        return collected


    contents = (
        await get_repository_contents(
            owner,
            repo,
            path,
        )
    )


    if not isinstance(
        contents,
        list
    ):

        return collected


    for item in contents:

        if len(collected) >= MAX_FILES:

            break


        item_type = (
            item.get("type")
        )


        item_path = (
            item.get("path")
            or ""
        )


        item_name = (
            item.get("name")
            or ""
        )


        if should_ignore_path(
            item_path
        ):

            continue


        # =================================================
        # DIRECTORY
        # =================================================

        if item_type == "dir":

            await collect_repository_source_paths(
                owner,
                repo,
                item_path,
                collected,
            )


        # =================================================
        # FILE
        # =================================================

        elif item_type == "file":

            if is_supported_source_file(
                item_name
            ):

                collected.append(
                    {
                        "name":
                            item_name,

                        "path":
                            item_path,

                        "size":
                            item.get(
                                "size",
                                0,
                            ),

                        "url":
                            item.get(
                                "html_url"
                            ),
                    }
                )


    return collected


# =========================================================
# READ REPOSITORY SOURCE CODE
# =========================================================

async def collect_repository_source_files(
    owner: str,
    repo: str,
):

    paths = (
        await collect_repository_source_paths(
            owner,
            repo,
        )
    )


    source_files = []


    total_chars = 0


    for item in paths:

        if (
            total_chars
            >= MAX_CONTEXT_CHARS
        ):

            break


        path = item[
            "path"
        ]


        try:

            content = (
                await get_repository_file_text(
                    owner,
                    repo,
                    path,
                )
            )


            if not content.strip():

                continue


            remaining = (
                MAX_CONTEXT_CHARS
                - total_chars
            )


            content = (
                content[:remaining]
            )


            source_files.append(
                {
                    "name":
                        item["name"],

                    "path":
                        path,

                    "content":
                        content,

                    "url":
                        item.get(
                            "url"
                        ),
                }
            )


            total_chars += (
                len(content)
            )


        except ValueError as error:

            print(
                "SKIPPING FILE:",
                path,
                repr(error),
            )


        except Exception as error:

            print(
                "FILE READ ERROR:",
                path,
                repr(error),
            )


    return source_files


# =========================================================
# BUILD AI REPOSITORY CONTEXT
# =========================================================

def build_repository_context(
    files
):

    sections = []


    total_chars = 0


    for item in files:

        content = (
            item.get(
                "content",
                ""
            )
        )


        path = (
            item.get(
                "path",
                "unknown"
            )
        )


        if not content.strip():

            continue


        section = f"""
=================================================
FILE: {path}
=================================================

{content}
"""


        if (
            total_chars
            + len(section)
            > MAX_CONTEXT_CHARS
        ):

            remaining = (
                MAX_CONTEXT_CHARS
                - total_chars
            )


            if remaining <= 0:

                break


            section = (
                section[:remaining]
            )


        sections.append(
            section
        )


        total_chars += (
            len(section)
        )


        if (
            total_chars
            >= MAX_CONTEXT_CHARS
        ):

            break


    return "\n\n".join(
        sections
    )


# =========================================================
# ISSUES
# =========================================================

async def get_repository_issues(
    owner: str,
    repo: str,
    state: str = "open",
    per_page: int = 30,
):

    return await github_get(
        f"/repos/{owner}/{repo}/issues",

        params={
            "state":
                state,

            "per_page":
                per_page,
        },
    )


# =========================================================
# SEARCH ISSUES
# =========================================================

async def search_repository_issues(
    owner: str,
    repo: str,
    query: str,
):

    search_query = (
        f"{query} "
        f"repo:{owner}/{repo} "
        f"is:issue"
    )


    data = await github_get(
        "/search/issues",

        params={
            "q":
                search_query,

            "per_page":
                20,
        },
    )


    return data.get(
        "items",
        []
    )


# =========================================================
# GET PULL REQUEST
# =========================================================

async def get_pull_request(
    owner: str,
    repo: str,
    pull_number: int,
):

    return await github_get(
        f"/repos/{owner}/{repo}/pulls/{pull_number}"
    )


# =========================================================
# GET PR FILES
# =========================================================

async def get_pull_request_files(
    owner: str,
    repo: str,
    pull_number: int,
):

    return await github_get(
        f"/repos/{owner}/{repo}/pulls/{pull_number}/files",

        params={
            "per_page":
                100
        },
    )