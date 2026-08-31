import os
import zipfile
import tempfile
import shutil


# =========================================================
# SUPPORTED SOURCE FILES
# =========================================================

ALLOWED_EXTENSIONS = {

    ".py",

    ".js",

    ".jsx",

    ".ts",

    ".tsx",

    ".java",

    ".html",

    ".css",

    ".json",

    ".md",

    ".yml",

    ".yaml",

    ".xml",

    ".sql",

}


# =========================================================
# FOLDERS TO IGNORE
# =========================================================

IGNORED_FOLDERS = {

    "node_modules",

    ".git",

    "dist",

    "build",

    "__pycache__",

    "venv",

    ".venv",

    ".idea",

    ".vscode",

}


# =========================================================
# EXTRACT ZIP
# =========================================================

def extract_project(
    zip_path: str
):

    project_dir = tempfile.mkdtemp(
        prefix="devmind_project_"
    )


    with zipfile.ZipFile(
        zip_path,
        "r",
    ) as zip_ref:

        base_path = os.path.realpath(
            project_dir
        )


        # Prevent ZIP path traversal
        for member in zip_ref.infolist():

            target_path = os.path.realpath(
                os.path.join(
                    project_dir,
                    member.filename,
                )
            )


            if not target_path.startswith(
                base_path + os.sep
            ):

                raise ValueError(
                    "Unsafe ZIP file detected"
                )


        zip_ref.extractall(
            project_dir
        )


    return project_dir


# =========================================================
# COLLECT SOURCE FILES
# =========================================================

def collect_source_files(
    project_dir: str
):

    files = []


    for root, dirs, filenames in os.walk(
        project_dir
    ):

        dirs[:] = [

            folder

            for folder
            in dirs

            if folder
            not in IGNORED_FOLDERS

        ]


        for filename in filenames:

            extension = (
                os.path.splitext(
                    filename
                )[1]
                .lower()
            )


            if (
                extension
                not in
                ALLOWED_EXTENSIONS
            ):

                continue


            full_path = os.path.join(
                root,
                filename,
            )


            relative_path = os.path.relpath(
                full_path,
                project_dir,
            )


            try:

                # Skip > 1 MB files
                if (
                    os.path.getsize(
                        full_path
                    )
                    > 1_000_000
                ):

                    continue


                with open(
                    full_path,
                    "r",
                    encoding="utf-8",
                    errors="ignore",
                ) as source_file:

                    content = (
                        source_file.read()
                    )


                if content.strip():

                    files.append({

                        "path":
                            relative_path,

                        "content":
                            content,

                    })


            except Exception as error:

                print(
                    "FILE READ ERROR:",
                    relative_path,
                    repr(error),
                )


    return files


# =========================================================
# BUILD PROJECT CONTEXT
# =========================================================

def build_project_context(
    files,
    max_chars=70000,
):

    parts = []

    total_chars = 0


    for source_file in files:

        block = (
            "\n\n"
            "===== FILE: "
            f"{source_file['path']}"
            " =====\n"
            f"{source_file['content']}"
        )


        remaining = (
            max_chars
            - total_chars
        )


        if remaining <= 0:

            break


        if len(block) > remaining:

            block = block[
                :remaining
            ]


        parts.append(
            block
        )


        total_chars += (
            len(block)
        )


    return "".join(
        parts
    )


# =========================================================
# CLEAN TEMP PROJECT
# =========================================================

def cleanup_project(
    project_dir: str
):

    if (
        project_dir
        and os.path.exists(
            project_dir
        )
    ):

        shutil.rmtree(
            project_dir,
            ignore_errors=True,
        )