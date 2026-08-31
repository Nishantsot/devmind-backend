import os
import uuid
import tempfile
import zipfile

import httpx

from bs4 import BeautifulSoup

from urllib.parse import urlparse

from dotenv import load_dotenv
from fastapi.responses import StreamingResponse
from fastapi import (
    FastAPI,
    HTTPException,
    Depends,
    UploadFile,
    File,
)

from fastapi.responses import StreamingResponse

from fastapi.middleware.cors import CORSMiddleware

from pydantic import BaseModel

from sqlalchemy.orm import Session

from google import genai


# =========================================================
# LOCAL IMPORTS
# =========================================================

from database import get_db

from models import (
    User,
    Conversation,
    Message,
)

from schemas import (
    UserRegister,
    UserLogin,
    TokenResponse,
    UserResponse,
)

from auth import (
    hash_password,
    verify_password,
    create_access_token,
    get_current_user,
)

from rag import (
    extract_text,
    index_document,
    search_document,
)

from codebase import (
    extract_project,
    collect_source_files,
    build_project_context,
    cleanup_project,
)

from github_service import (
    parse_repo_url,
    github_get,
    get_repository,
    get_repository_contents,
    search_repository_issues,
    get_pull_request,
    get_pull_request_files,
    collect_repository_source_files,
    build_repository_context,
)


# =========================================================
# LOAD ENVIRONMENT VARIABLES
# =========================================================

load_dotenv()


# =========================================================
# FASTAPI APPLICATION
# =========================================================

app = FastAPI(
    title="DevMind AI Developer Assistant",
    description=(
        "AI-powered software engineering assistant "
        "with authentication, chat history, RAG, "
        "codebase analysis, GitHub integration "
        "and documentation search"
    ),
    version="2.1.0",
)


# =========================================================
# CORS
# =========================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://devmind-frontend-ten.vercel.app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "X-Conversation-Id"
    ],
)


# =========================================================
# GEMINI CONFIGURATION
# =========================================================

API_KEY = os.getenv(
    "GEMINI_API_KEY"
)


if not API_KEY:

    raise RuntimeError(
        "GEMINI_API_KEY is not set. "
        "Please add it to the .env file."
    )


client = genai.Client(
    api_key=API_KEY
)


GEMINI_MODEL = (
    "gemini-3.6-flash"
)


# =========================================================
# TEMPORARY CODEBASE STORAGE
# =========================================================

PROJECTS = {}


# =========================================================
# OFFICIAL DOCUMENTATION DOMAINS
# =========================================================

ALLOWED_DOC_DOMAINS = {

    "react.dev",

    "www.react.dev",

    "fastapi.tiangolo.com",

    "docs.python.org",

    "developer.mozilla.org",

    "docs.oracle.com",

    "docs.spring.io",

    "docs.docker.com",

    "docs.github.com",

    "nodejs.org",

    "www.typescriptlang.org",

    "vite.dev",

    "reactrouter.com",

    "spring.io",

    "docs.npmjs.com",

    "expressjs.com",

    "nextjs.org",

}


# =========================================================
# REQUEST MODELS
# =========================================================

class ChatRequest(BaseModel):

    message: str

    conversation_id: int | None = None


class FileQuestionRequest(BaseModel):

    document_id: str

    question: str


class CodebaseQuestionRequest(BaseModel):

    project_id: str

    question: str


class GitHubRepoRequest(BaseModel):
    repo_url: str


class GitHubIssueSearchRequest(BaseModel):
    repo_url: str
    query: str


class GitHubPRRequest(BaseModel):
    repo_url: str
    pull_number: int


class GitHubAnalyzeRequest(BaseModel):
    repo_url: str
    question: str


class GitHubIssueFixRequest(BaseModel):
    repo_url: str
    issue_number: int
    
class DocsSearchRequest(BaseModel):

    question: str

    url: str

class StreamChatRequest(BaseModel):
    message: str
    conversation_id: int | None = None

   
    
# =========================================================
# ROOT
# =========================================================

@app.get("/")
def home():

    return {

        "message":
            "DevMind AI Developer Assistant API",

        "status":
            "running",

        "version":
            "2.1.0",

    }


# =========================================================
# HEALTH
# =========================================================

@app.get("/health")
def health():

    return {
        "status":
            "healthy"
    }


# =========================================================
# REGISTER
# =========================================================

@app.post(
    "/register",
    response_model=UserResponse,
)
def register(
    request: UserRegister,

    db: Session = Depends(
        get_db
    ),
):

    try:

        existing_user = (
            db.query(User)
            .filter(
                User.email
                == request.email
            )
            .first()
        )


        if existing_user:

            raise HTTPException(
                status_code=400,

                detail=
                    "Email already registered",
            )


        hashed_password = (
            hash_password(
                request.password
            )
        )


        new_user = User(

            name=
                request.name,

            email=
                request.email,

            hashed_password=
                hashed_password,

        )


        db.add(
            new_user
        )


        db.commit()


        db.refresh(
            new_user
        )


        return new_user


    except HTTPException:

        raise


    except Exception as error:

        db.rollback()


        print("=" * 50)

        print(
            "REGISTER ERROR:"
        )

        print(
            repr(error)
        )

        print("=" * 50)


        raise HTTPException(
            status_code=500,

            detail=
                "Registration failed",
        )


# =========================================================
# LOGIN
# =========================================================

@app.post(
    "/login",
    response_model=TokenResponse,
)
def login(
    request: UserLogin,

    db: Session = Depends(
        get_db
    ),
):

    user = (
        db.query(User)
        .filter(
            User.email
            == request.email
        )
        .first()
    )


    if not user:

        raise HTTPException(
            status_code=401,

            detail=
                "Invalid email or password",
        )


    if not verify_password(
        request.password,
        user.hashed_password,
    ):

        raise HTTPException(
            status_code=401,

            detail=
                "Invalid email or password",
        )


    access_token = (
        create_access_token(
            {

                "sub":
                    str(user.id),

                "email":
                    user.email,

            }
        )
    )


    return {

        "access_token":
            access_token,

        "token_type":
            "bearer",

    }


# =========================================================
# CURRENT USER
# =========================================================

@app.get("/me")
def get_me(
    current_user: User =
        Depends(
            get_current_user
        ),
):

    return {

        "id":
            current_user.id,

        "name":
            current_user.name,

        "email":
            current_user.email,

    }


# =========================================================
# NORMAL AI CHAT
# =========================================================

@app.post("/chat")
async def chat(
    request: ChatRequest,

    current_user: User =
        Depends(
            get_current_user
        ),

    db: Session =
        Depends(
            get_db
        ),
):

    if not request.message.strip():

        raise HTTPException(
            status_code=400,

            detail=
                "Message cannot be empty",
        )


    try:

        # =================================================
        # EXISTING CONVERSATION
        # =================================================

        if request.conversation_id:

            conversation = (
                db.query(
                    Conversation
                )
                .filter(

                    Conversation.id
                    == request.conversation_id,

                    Conversation.user_id
                    == current_user.id,

                )
                .first()
            )


            if not conversation:

                raise HTTPException(
                    status_code=404,

                    detail=
                        "Conversation not found",
                )


        # =================================================
        # NEW CONVERSATION
        # =================================================

        else:

            conversation = Conversation(

                title=
                    request.message[:60],

                user_id=
                    current_user.id,

            )


            db.add(
                conversation
            )


            db.commit()


            db.refresh(
                conversation
            )


        # =================================================
        # SAVE USER MESSAGE
        # =================================================

        user_message = Message(

            role=
                "user",

            content=
                request.message,

            conversation_id=
                conversation.id,

        )


        db.add(
            user_message
        )


        db.commit()


        # =================================================
        # LOAD CONVERSATION HISTORY
        # =================================================

        previous_messages = (
            db.query(Message)
            .filter(

                Message.conversation_id
                == conversation.id

            )
            .order_by(
                Message.created_at.asc()
            )
            .all()
        )


        conversation_history = []


        for item in previous_messages:

            if item.role == "user":

                conversation_history.append(
                    f"User: {item.content}"
                )


            elif item.role == "assistant":

                conversation_history.append(
                    f"Assistant: {item.content}"
                )


        history_text = "\n\n".join(
            conversation_history
        )


        # =================================================
        # GEMINI PROMPT
        # =================================================

        prompt = f"""
You are DevMind, an AI Software Engineering Assistant.

You help developers with:

- Programming
- Debugging
- Software architecture
- APIs
- Databases
- React
- JavaScript
- TypeScript
- Python
- Java
- Spring Boot
- FastAPI
- DevOps
- Docker
- CI/CD
- Generative AI
- Testing
- GitHub
- Pull request review
- Documentation understanding

Continue the conversation naturally.

CONVERSATION HISTORY:

{history_text}

Give a clear, practical and technically accurate answer.
"""


        response = (
            await client.aio.models.generate_content(

                model=
                    GEMINI_MODEL,

                contents=
                    prompt,

            )
        )


        answer = (
            response.text
        )


        # =================================================
        # SAVE AI RESPONSE
        # =================================================

        ai_message = Message(

            role=
                "assistant",

            content=
                answer,

            conversation_id=
                conversation.id,

        )


        db.add(
            ai_message
        )


        db.commit()


        db.refresh(
            ai_message
        )


        return {

            "conversation_id":
                conversation.id,

            "answer":
                answer,

            "user": {

                "id":
                    current_user.id,

                "name":
                    current_user.name,

                "email":
                    current_user.email,

            },

        }


    except HTTPException:

        raise


    except Exception as error:

        db.rollback()


        print("=" * 50)

        print(
            "CHAT ERROR:"
        )

        print(
            repr(error)
        )

        print("=" * 50)


        raise HTTPException(
            status_code=500,

            detail=
                "AI request failed",
        )

# =========================================================
# STREAMING AI CHAT
# =========================================================

# =========================================================
# STREAMING AI CHAT WITH HISTORY
# =========================================================

# =========================================================
# STREAMING AI CHAT WITH HISTORY
# =========================================================

@app.post("/chat/stream")
async def chat_stream(
    request: StreamChatRequest,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):

    if not request.message.strip():
        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty",
        )

    # =====================================================
    # EXISTING OR NEW CONVERSATION
    # =====================================================

    if request.conversation_id:

        conversation = (
            db.query(Conversation)
            .filter(
                Conversation.id == request.conversation_id,
                Conversation.user_id == current_user.id,
            )
            .first()
        )

        if not conversation:
            raise HTTPException(
                status_code=404,
                detail="Conversation not found",
            )

    else:

        conversation = Conversation(
            title=request.message[:60],
            user_id=current_user.id,
        )

        db.add(conversation)
        db.commit()
        db.refresh(conversation)

    # =====================================================
    # SAVE USER MESSAGE
    # =====================================================

    user_message = Message(
        role="user",
        content=request.message,
        conversation_id=conversation.id,
    )

    db.add(user_message)
    db.commit()

    # =====================================================
    # LOAD HISTORY
    # =====================================================

    previous_messages = (
        db.query(Message)
        .filter(
            Message.conversation_id == conversation.id
        )
        .order_by(
            Message.created_at.asc()
        )
        .all()
    )

    history = []

    for item in previous_messages:

        if item.role == "user":
            history.append(
                f"User: {item.content}"
            )

        elif item.role == "assistant":
            history.append(
                f"Assistant: {item.content}"
            )

    history_text = "\n\n".join(history)

    # =====================================================
    # PROMPT
    # =====================================================

    prompt = f"""
You are DevMind, an AI Software Engineering Assistant.

You help developers with:

- Programming
- Debugging
- Software architecture
- APIs
- Databases
- React
- JavaScript
- TypeScript
- Python
- Java
- Spring Boot
- FastAPI
- DevOps
- Docker
- CI/CD
- Generative AI
- Testing
- GitHub
- Documentation

Continue the conversation naturally.

CONVERSATION HISTORY:

{history_text}

Give a clear, practical and technically accurate answer.

Use code examples when useful.
"""

    # =====================================================
    # STREAM GENERATOR
    # =====================================================

    async def generate():

        full_answer = ""

        try:

            response = (
                await client.aio.models
                .generate_content_stream(
                    model=GEMINI_MODEL,
                    contents=prompt,
                )
            )

            async for chunk in response:

                text = getattr(
                    chunk,
                    "text",
                    None,
                )

                if text:

                    full_answer += text

                    yield text

            # =============================================
            # SAVE AI RESPONSE
            # =============================================

            if full_answer.strip():

                ai_message = Message(
                    role="assistant",
                    content=full_answer,
                    conversation_id=conversation.id,
                )

                db.add(ai_message)
                db.commit()

        except Exception as error:

            db.rollback()

            print("=" * 50)
            print("STREAMING CHAT ERROR:")
            print(repr(error))
            print("=" * 50)

            yield (
                "\n\n❌ AI streaming request failed."
            )

    # =====================================================
    # RETURN STREAM
    # =====================================================

    return StreamingResponse(
        generate(),
        media_type="text/plain; charset=utf-8",
        headers={
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
            "X-Conversation-Id": str(
                conversation.id
            ),
        },
    )
# =========================================================
# GET ALL CONVERSATIONS
# =========================================================

@app.get("/conversations")
def get_conversations(
    current_user: User =
        Depends(
            get_current_user
        ),

    db: Session =
        Depends(
            get_db
        ),
):

    conversations = (
        db.query(
            Conversation
        )
        .filter(

            Conversation.user_id
            == current_user.id

        )
        .order_by(
            Conversation.created_at.desc()
        )
        .all()
    )


    return [

        {

            "id":
                conversation.id,

            "title":
                conversation.title,

            "created_at":
                conversation.created_at,

        }

        for conversation
        in conversations

    ]


# =========================================================
# GET ONE CONVERSATION
# =========================================================

@app.get(
    "/conversations/{conversation_id}"
)
def get_conversation(
    conversation_id: int,

    current_user: User =
        Depends(
            get_current_user
        ),

    db: Session =
        Depends(
            get_db
        ),
):

    conversation = (
        db.query(
            Conversation
        )
        .filter(

            Conversation.id
            == conversation_id,

            Conversation.user_id
            == current_user.id,

        )
        .first()
    )


    if not conversation:

        raise HTTPException(
            status_code=404,

            detail=
                "Conversation not found",
        )


    messages = (
        db.query(
            Message
        )
        .filter(

            Message.conversation_id
            == conversation.id

        )
        .order_by(
            Message.created_at.asc()
        )
        .all()
    )


    return {

        "id":
            conversation.id,

        "title":
            conversation.title,

        "created_at":
            conversation.created_at,

        "messages": [

            {

                "id":
                    item.id,

                "role":
                    item.role,

                "content":
                    item.content,

                "created_at":
                    item.created_at,

            }

            for item
            in messages

        ],

    }


# =========================================================
# DELETE CONVERSATION
# =========================================================

@app.delete(
    "/conversations/{conversation_id}"
)
def delete_conversation(
    conversation_id: int,

    current_user: User =
        Depends(
            get_current_user
        ),

    db: Session =
        Depends(
            get_db
        ),
):

    conversation = (
        db.query(
            Conversation
        )
        .filter(

            Conversation.id
            == conversation_id,

            Conversation.user_id
            == current_user.id,

        )
        .first()
    )


    if not conversation:

        raise HTTPException(
            status_code=404,

            detail=
                "Conversation not found",
        )


    db.delete(
        conversation
    )


    db.commit()


    return {

        "message":
            "Conversation deleted successfully"

    }


# =========================================================
# DOCUMENT RAG UPLOAD
# =========================================================

@app.post("/upload")
async def upload_file(
    file: UploadFile =
        File(...),

    current_user: User =
        Depends(
            get_current_user
        ),
):

    if not file.filename:

        raise HTTPException(
            status_code=400,

            detail=
                "File name is missing",
        )


    allowed_extensions = (

        ".pdf",

        ".txt",

        ".py",

        ".js",

        ".jsx",

        ".ts",

        ".tsx",

        ".java",

        ".json",

        ".md",

        ".html",

        ".css",

    )


    extension = (
        os.path.splitext(
            file.filename
        )[1]
        .lower()
    )


    if extension not in allowed_extensions:

        raise HTTPException(
            status_code=400,

            detail=
                "Unsupported file type",
        )


    document_id = str(
        uuid.uuid4()
    )


    with tempfile.NamedTemporaryFile(

        delete=False,

        suffix=extension,

    ) as temp_file:

        content = (
            await file.read()
        )


        temp_file.write(
            content
        )


        temp_path = (
            temp_file.name
        )


    try:

        text = extract_text(
            temp_path
        )


        if not text.strip():

            raise HTTPException(
                status_code=400,

                detail=
                    "No readable text found",
            )


        chunk_count = (
            index_document(

                document_id,

                text,

            )
        )


        return {

            "document_id":
                document_id,

            "filename":
                file.filename,

            "chunks":
                chunk_count,

            "message":
                "File indexed successfully",

        }


    finally:

        if os.path.exists(
            temp_path
        ):

            os.remove(
                temp_path
            )


# =========================================================
# ASK DOCUMENT
# =========================================================

@app.post("/ask-file")
async def ask_file(
    request:
        FileQuestionRequest,

    current_user: User =
        Depends(
            get_current_user
        ),
):

    if not request.question.strip():

        raise HTTPException(
            status_code=400,

            detail=
                "Question cannot be empty",
        )


    results = search_document(

        request.document_id,

        request.question,

    )


    if not results:

        raise HTTPException(
            status_code=404,

            detail=
                "Document not found",
        )


    context = "\n\n".join(

        item["text"]

        for item
        in results

    )


    prompt = f"""
You are DevMind, an AI Software Engineering Assistant.

Answer the question using the uploaded document context.

If the answer cannot be found in the document,
say that you could not find it in the uploaded document.

DOCUMENT CONTEXT:

{context}

USER QUESTION:

{request.question}
"""


    try:

        response = (
            await client.aio.models.generate_content(

                model=
                    GEMINI_MODEL,

                contents=
                    prompt,

            )
        )


        return {

            "answer":
                response.text,

            "sources":
                results,

        }


    except Exception as error:

        print("=" * 50)

        print(
            "RAG ERROR:"
        )

        print(
            repr(error)
        )

        print("=" * 50)


        raise HTTPException(
            status_code=500,

            detail=
                "RAG request failed",
        )


# =========================================================
# UPLOAD ZIP PROJECT
# =========================================================

@app.post("/upload-project")
async def upload_project(
    file: UploadFile =
        File(...),

    current_user: User =
        Depends(
            get_current_user
        ),
):

    if not file.filename:

        raise HTTPException(
            status_code=400,

            detail=
                "File name is missing",
        )


    if not file.filename.lower().endswith(
        ".zip"
    ):

        raise HTTPException(
            status_code=400,

            detail=
                "Please upload a ZIP project",
        )


    project_id = str(
        uuid.uuid4()
    )


    zip_path = None

    project_dir = None


    try:

        with tempfile.NamedTemporaryFile(

            delete=False,

            suffix=".zip",

        ) as temp_file:

            content = (
                await file.read()
            )


            # Maximum ZIP size = 25MB

            if len(content) > (
                25
                * 1024
                * 1024
            ):

                raise HTTPException(
                    status_code=400,

                    detail=(
                        "ZIP file is too large. "
                        "Maximum size is 25 MB."
                    ),
                )


            temp_file.write(
                content
            )


            zip_path = (
                temp_file.name
            )


        # =================================================
        # EXTRACT PROJECT
        # =================================================

        project_dir = (
            extract_project(
                zip_path
            )
        )


        # =================================================
        # COLLECT SOURCE FILES
        # =================================================

        files = (
            collect_source_files(
                project_dir
            )
        )


        if not files:

            raise HTTPException(
                status_code=400,

                detail=
                    "No supported source files found",
            )


        # =================================================
        # TEMPORARY STORAGE
        # =================================================

        PROJECTS[
            project_id
        ] = {

            "user_id":
                current_user.id,

            "filename":
                file.filename,

            "files":
                files,

        }


        return {

            "project_id":
                project_id,

            "filename":
                file.filename,

            "file_count":
                len(files),

            "files": [

                item["path"]

                for item
                in files[:100]

            ],

            "message":
                "Project indexed successfully",

        }


    except HTTPException:

        raise


    except zipfile.BadZipFile:

        raise HTTPException(
            status_code=400,

            detail=
                "Invalid ZIP file",
        )


    except ValueError as error:

        raise HTTPException(
            status_code=400,

            detail=
                str(error),
        )


    except Exception as error:

        print("=" * 50)

        print(
            "PROJECT UPLOAD ERROR:"
        )

        print(
            repr(error)
        )

        print("=" * 50)


        raise HTTPException(
            status_code=500,

            detail=
                "Project upload failed",
        )


    finally:

        if (
            zip_path
            and os.path.exists(
                zip_path
            )
        ):

            os.remove(
                zip_path
            )


        if project_dir:

            cleanup_project(
                project_dir
            )


# =========================================================
# ASK / ANALYZE CODEBASE
# =========================================================

@app.post("/ask-codebase")
async def ask_codebase(
    request:
        CodebaseQuestionRequest,

    current_user: User =
        Depends(
            get_current_user
        ),
):

    if not request.question.strip():

        raise HTTPException(
            status_code=400,

            detail=
                "Question cannot be empty",
        )


    project = PROJECTS.get(
        request.project_id
    )


    if not project:

        raise HTTPException(
            status_code=404,

            detail=(
                "Project not found. "
                "Please upload the ZIP project again."
            ),
        )


    if (
        project["user_id"]
        != current_user.id
    ):

        raise HTTPException(
            status_code=403,

            detail=
                "Access denied",
        )


    context = (
        build_project_context(
            project["files"]
        )
    )


    if not context.strip():

        raise HTTPException(
            status_code=400,

            detail=
                "Project contains no readable source code",
        )


    prompt = f"""
You are DevMind, an expert AI Developer Assistant.

You are analyzing a real software codebase.

You can help with:

- Understanding unfamiliar codebases
- Explaining architecture
- Explaining files
- Explaining classes
- Explaining functions
- Finding bugs
- Finding suspicious code
- Finding security problems
- Suggesting fixes
- Generating tests
- Explaining dependencies
- Explaining module interactions
- Suggesting improvements

IMPORTANT RULES:

1. Base your answer on the supplied project.

2. Mention exact file paths whenever possible.

3. Do not invent files that do not exist.

4. If information cannot be determined, say so.

When reporting bugs provide:

- File
- Problem
- Reason
- Severity
- Suggested fix

When generating tests:

- Mention target file
- Mention testing framework
- Provide runnable test code

When fixing code:

- Explain problem
- Show corrected code

PROJECT NAME:

{project["filename"]}

CODEBASE:

{context}

DEVELOPER QUESTION:

{request.question}
"""


    try:

        response = (
            await client.aio.models.generate_content(

                model=
                    GEMINI_MODEL,

                contents=
                    prompt,

            )
        )


        return {

            "project_id":
                request.project_id,

            "project_name":
                project["filename"],

            "answer":
                response.text,

        }


    except Exception as error:

        print("=" * 50)

        print(
            "CODEBASE ANALYSIS ERROR:"
        )

        print(
            repr(error)
        )

        print("=" * 50)


        raise HTTPException(
            status_code=500,

            detail=
                "Codebase analysis failed",
        )


# =========================================================
# GITHUB REPOSITORY INFO
# =========================================================
# =========================================================
# AI ANALYZE GITHUB REPOSITORY
# =========================================================

@app.post("/github/analyze")
async def analyze_github_repository(
    request: GitHubAnalyzeRequest,

    current_user: User =
        Depends(get_current_user),
):

    repo_url = (
        request.repo_url.strip()
    )

    question = (
        request.question.strip()
    )


    # =====================================================
    # VALIDATION
    # =====================================================

    if not repo_url:

        raise HTTPException(
            status_code=400,
            detail="Repository URL cannot be empty",
        )


    if not question:

        raise HTTPException(
            status_code=400,
            detail="Question cannot be empty",
        )


    try:

        # =================================================
        # PARSE REPOSITORY
        # =================================================

        owner, repo = (
            parse_repo_url(
                repo_url
            )
        )


        # =================================================
        # GET REPOSITORY INFO
        # =================================================

        repository = (
            await get_repository(
                owner,
                repo,
            )
        )


        # =================================================
        # COLLECT SOURCE FILES
        # =================================================

        files = (
            await collect_repository_source_files(
                owner,
                repo,
            )
        )


        if not files:

            raise HTTPException(
                status_code=400,
                detail=(
                    "No supported source files "
                    "were found in this repository"
                ),
            )


        # =================================================
        # BUILD CODE CONTEXT
        # =================================================

        context = (
            build_repository_context(
                files
            )
        )


        if not context.strip():

            raise HTTPException(
                status_code=400,
                detail=(
                    "Repository contains no "
                    "readable source code"
                ),
            )


        # =================================================
        # AI PROMPT
        # =================================================

        prompt = f"""
You are DevMind, an expert AI Software Engineer.

You are analyzing a real GitHub repository.

REPOSITORY:

{owner}/{repo}

DESCRIPTION:

{repository.get("description") or "No description provided"}

PRIMARY LANGUAGE:

{repository.get("language") or "Unknown"}

DEFAULT BRANCH:

{repository.get("default_branch") or "Unknown"}


SOURCE CODE:

{context}


DEVELOPER QUESTION:

{question}


IMPORTANT RULES:

1. Base your analysis only on the supplied repository code.

2. Do not invent files, classes, functions,
   dependencies or behavior.

3. Mention exact file paths whenever possible.

4. If something cannot be determined from the
   supplied code, clearly say so.

5. When reporting bugs provide:

   - File path
   - Problem
   - Why it is a problem
   - Severity: LOW / MEDIUM / HIGH
   - Suggested fix

6. For security analysis check for:

   - Authentication problems
   - Authorization problems
   - Exposed secrets
   - Injection vulnerabilities
   - Unsafe input handling
   - Insecure API usage
   - Sensitive data exposure

7. For performance analysis check for:

   - Expensive loops
   - Repeated network requests
   - Database query problems
   - Unnecessary rendering
   - Large memory usage
   - Blocking operations

8. When generating tests:

   - Mention target file
   - Choose an appropriate testing framework
   - Provide runnable examples

9. When suggesting code changes,
   explain the problem before showing corrected code.

Give a practical developer-friendly response.
"""


        # =================================================
        # GEMINI
        # =================================================

        response = (
            await client.aio.models.generate_content(

                model=
                    GEMINI_MODEL,

                contents=
                    prompt,
            )
        )


        # =================================================
        # RESPONSE
        # =================================================

        return {

            "repository":
                f"{owner}/{repo}",

            "repository_url":
                repository.get(
                    "html_url"
                ),

            "language":
                repository.get(
                    "language"
                ),

            "file_count":
                len(files),

            "analyzed_files": [

                item.get(
                    "path"
                )

                for item in files

            ],

            "question":
                question,

            "answer":
                response.text,
        }


    except HTTPException:

        raise


    except ValueError as error:

        raise HTTPException(
            status_code=400,
            detail=str(error),
        )


    except Exception as error:

        print("=" * 50)

        print(
            "GITHUB REPOSITORY ANALYSIS ERROR:"
        )

        print(
            repr(error)
        )

        print("=" * 50)


        raise HTTPException(
            status_code=500,
            detail=(
                "GitHub repository "
                "analysis failed"
            ),
        )
@app.post("/github/repository")
async def github_repository(
    request:
        GitHubRepoRequest,

    current_user: User =
        Depends(
            get_current_user
        ),
):

    if not request.repo_url.strip():

        raise HTTPException(
            status_code=400,

            detail=
                "Repository URL cannot be empty",
        )


    try:

        owner, repo = (
            parse_repo_url(
                request.repo_url
            )
        )


        repository = (
            await get_repository(
                owner,
                repo,
            )
        )


        contents = (
            await get_repository_contents(
                owner,
                repo,
            )
        )


        files = []


        if isinstance(
            contents,
            list
        ):

            for item in contents:

                files.append(
                    {

                        "name":
                            item.get(
                                "name"
                            ),

                        "path":
                            item.get(
                                "path"
                            ),

                        "type":
                            item.get(
                                "type"
                            ),

                        "url":
                            item.get(
                                "html_url"
                            ),

                    }
                )


        return {

            "owner":
                owner,

            "repo":
                repo,

            "name":
                repository.get(
                    "name"
                ),

            "full_name":
                repository.get(
                    "full_name"
                ),

            "description":
                repository.get(
                    "description"
                ),

            "language":
                repository.get(
                    "language"
                ),

            "stars":
                repository.get(
                    "stargazers_count"
                ),

            "forks":
                repository.get(
                    "forks_count"
                ),

            "open_issues":
                repository.get(
                    "open_issues_count"
                ),

            "default_branch":
                repository.get(
                    "default_branch"
                ),

            "private":
                repository.get(
                    "private"
                ),

            "url":
                repository.get(
                    "html_url"
                ),

            "files":
                files,

        }


    except ValueError as error:

        raise HTTPException(
            status_code=400,

            detail=
                str(error),
        )


    except Exception as error:

        print("=" * 50)

        print(
            "GITHUB REPOSITORY ERROR:"
        )

        print(
            repr(error)
        )

        print("=" * 50)


        raise HTTPException(
            status_code=500,

            detail=
                "GitHub repository request failed",
        )


# =========================================================
# SEARCH GITHUB ISSUES
# =========================================================

@app.post("/github/issues/search")
async def github_issue_search(
    request:
        GitHubIssueSearchRequest,

    current_user: User =
        Depends(
            get_current_user
        ),
):

    if not request.repo_url.strip():

        raise HTTPException(
            status_code=400,

            detail=
                "Repository URL cannot be empty",
        )


    if not request.query.strip():

        raise HTTPException(
            status_code=400,

            detail=
                "Search query cannot be empty",
        )


    try:

        owner, repo = (
            parse_repo_url(
                request.repo_url
            )
        )


        issues = (
            await search_repository_issues(

                owner,

                repo,

                request.query,

            )
        )


        return {

            "repository":
                f"{owner}/{repo}",

            "query":
                request.query,

            "count":
                len(issues),

            "issues": [

                {

                    "number":
                        issue.get(
                            "number"
                        ),

                    "title":
                        issue.get(
                            "title"
                        ),

                    "state":
                        issue.get(
                            "state"
                        ),

                    "url":
                        issue.get(
                            "html_url"
                        ),

                    "body":
                        issue.get(
                            "body"
                        ),

                    "author":
                        issue
                        .get(
                            "user",
                            {}
                        )
                        .get(
                            "login"
                        ),

                    "created_at":
                        issue.get(
                            "created_at"
                        ),

                    "updated_at":
                        issue.get(
                            "updated_at"
                        ),

                }

                for issue
                in issues

            ],

        }


    except ValueError as error:

        raise HTTPException(
            status_code=400,

            detail=
                str(error),
        )


    except Exception as error:

        print("=" * 50)

        print(
            "GITHUB ISSUE SEARCH ERROR:"
        )

        print(
            repr(error)
        )

        print("=" * 50)


        raise HTTPException(
            status_code=500,

            detail=
                "GitHub issue search failed",
        )


# =========================================================
# GET GITHUB PULL REQUEST
# =========================================================

@app.post("/github/pr")
async def github_pull_request(
    request:
        GitHubPRRequest,

    current_user: User =
        Depends(
            get_current_user
        ),
):

    if not request.repo_url.strip():

        raise HTTPException(
            status_code=400,

            detail=
                "Repository URL cannot be empty",
        )


    if request.pull_number <= 0:

        raise HTTPException(
            status_code=400,

            detail=(
                "Pull request number must "
                "be greater than 0"
            ),
        )


    try:

        owner, repo = (
            parse_repo_url(
                request.repo_url
            )
        )


        pull_request = (
            await get_pull_request(

                owner,

                repo,

                request.pull_number,

            )
        )


        files = (
            await get_pull_request_files(

                owner,

                repo,

                request.pull_number,

            )
        )


        return {

            "repository":
                f"{owner}/{repo}",

            "number":
                pull_request.get(
                    "number"
                ),

            "title":
                pull_request.get(
                    "title"
                ),

            "state":
                pull_request.get(
                    "state"
                ),

            "url":
                pull_request.get(
                    "html_url"
                ),

            "author":
                pull_request
                .get(
                    "user",
                    {}
                )
                .get(
                    "login"
                ),

            "body":
                pull_request.get(
                    "body"
                ),

            "created_at":
                pull_request.get(
                    "created_at"
                ),

            "updated_at":
                pull_request.get(
                    "updated_at"
                ),

            "merged":
                pull_request.get(
                    "merged"
                ),

            "changed_files":
                pull_request.get(
                    "changed_files"
                ),

            "additions":
                pull_request.get(
                    "additions"
                ),

            "deletions":
                pull_request.get(
                    "deletions"
                ),

            "files": [

                {

                    "filename":
                        item.get(
                            "filename"
                        ),

                    "status":
                        item.get(
                            "status"
                        ),

                    "additions":
                        item.get(
                            "additions"
                        ),

                    "deletions":
                        item.get(
                            "deletions"
                        ),

                    "changes":
                        item.get(
                            "changes"
                        ),

                    "patch":
                        item.get(
                            "patch"
                        ),

                }

                for item
                in files

            ],

        }


    except ValueError as error:

        raise HTTPException(
            status_code=400,

            detail=
                str(error),
        )


    except Exception as error:

        print("=" * 50)

        print(
            "GITHUB PR ERROR:"
        )

        print(
            repr(error)
        )

        print("=" * 50)


        raise HTTPException(
            status_code=500,

            detail=
                "GitHub pull request request failed",
        )


# =========================================================
# AI REVIEW GITHUB PULL REQUEST
# =========================================================

@app.post("/github/pr/review")
async def review_github_pull_request(
    request:
        GitHubPRRequest,

    current_user: User =
        Depends(
            get_current_user
        ),
):

    if not request.repo_url.strip():

        raise HTTPException(
            status_code=400,

            detail=
                "Repository URL cannot be empty",
        )


    if request.pull_number <= 0:

        raise HTTPException(
            status_code=400,

            detail=(
                "Pull request number must "
                "be greater than 0"
            ),
        )


    try:

        owner, repo = (
            parse_repo_url(
                request.repo_url
            )
        )


        pull_request = (
            await get_pull_request(

                owner,

                repo,

                request.pull_number,

            )
        )


        files = (
            await get_pull_request_files(

                owner,

                repo,

                request.pull_number,

            )
        )


        patches = []


        for item in files:

            patch = (
                item.get(
                    "patch"
                )
            )


            if not patch:

                continue


            patches.append(
                f"""
=================================================
FILE: {item.get("filename")}

STATUS: {item.get("status")}

ADDITIONS: {item.get("additions")}

DELETIONS: {item.get("deletions")}

PATCH:

{patch}
=================================================
"""
            )


        if not patches:

            raise HTTPException(
                status_code=400,

                detail=
                    "No readable PR diff was found",
            )


        diff_context = (
            "\n\n".join(
                patches
            )
        )


        diff_context = (
            diff_context[:80000]
        )


        prompt = f"""
You are DevMind, an expert AI software engineer.

Perform a professional GitHub pull request review.

REPOSITORY:

{owner}/{repo}

PULL REQUEST:

#{request.pull_number}

TITLE:

{pull_request.get("title")}

DESCRIPTION:

{pull_request.get("body") or "No description provided"}

CHANGED CODE:

{diff_context}


REVIEW FOR:

- Bugs
- Logic errors
- Security vulnerabilities
- Breaking changes
- Missing validation
- Missing error handling
- Edge cases
- Performance problems
- Maintainability
- Code quality
- Missing tests
- Potential regressions


IMPORTANT RULES:

1. Only review code visible in the supplied diff.

2. Do not invent files or changes.

3. Mention exact file paths.

4. For every important issue provide:

   - File path
   - Severity: LOW / MEDIUM / HIGH
   - Problem
   - Why it matters
   - Suggested fix

5. Provide corrected code when useful.

6. Suggest important tests.

7. Mention positive aspects of the PR.

8. End with exactly one recommendation:

APPROVE

COMMENT

REQUEST CHANGES


OUTPUT FORMAT:

# PR Summary

# What Looks Good

# Problems Found

# Security Review

# Suggested Improvements

# Tests Needed

# Final Recommendation
"""


        response = (
            await client.aio.models.generate_content(

                model=
                    GEMINI_MODEL,

                contents=
                    prompt,

            )
        )


        return {

            "repository":
                f"{owner}/{repo}",

            "pull_number":
                request.pull_number,

            "title":
                pull_request.get(
                    "title"
                ),

            "changed_files":
                pull_request.get(
                    "changed_files"
                ),

            "additions":
                pull_request.get(
                    "additions"
                ),

            "deletions":
                pull_request.get(
                    "deletions"
                ),

            "review":
                response.text,

        }


    except HTTPException:

        raise


    except ValueError as error:

        raise HTTPException(
            status_code=400,

            detail=
                str(error),
        )


    except Exception as error:

        print("=" * 50)

        print(
            "GITHUB PR REVIEW ERROR:"
        )

        print(
            repr(error)
        )

        print("=" * 50)


        raise HTTPException(
            status_code=500,

            detail=
                "AI pull request review failed",
        )


# =========================================================
# FETCH OFFICIAL DOCUMENTATION PAGE
# =========================================================

async def fetch_documentation_page(
    url: str,
):

    parsed_url = (
        urlparse(
            url
        )
    )


    # =====================================================
    # VALIDATE PROTOCOL
    # =====================================================

    if parsed_url.scheme not in (
        "http",
        "https",
    ):

        raise HTTPException(
            status_code=400,

            detail=(
                "Documentation URL must "
                "use http or https"
            ),
        )


    hostname = (
        parsed_url.hostname
        or ""
    ).lower()


    # =====================================================
    # VALIDATE OFFICIAL DOMAIN
    # =====================================================

    if hostname not in ALLOWED_DOC_DOMAINS:

        raise HTTPException(
            status_code=400,

            detail=(
                "This documentation website "
                "is not currently supported"
            ),
        )


    try:

        async with httpx.AsyncClient(

            timeout=20.0,

            follow_redirects=True,

            headers={

                "User-Agent":
                    "DevMind-AI-Developer-Assistant/1.0"

            },

        ) as http_client:

            response = (
                await http_client.get(
                    url
                )
            )


        if not response.is_success:

            raise HTTPException(
                status_code=400,

                detail=(
                    "Could not load "
                    "documentation page"
                ),
            )


        content_type = (
            response.headers
            .get(
                "content-type",
                ""
            )
            .lower()
        )


        if "text/html" not in content_type:

            raise HTTPException(
                status_code=400,

                detail=(
                    "Documentation URL does "
                    "not contain an HTML page"
                ),
            )


        # =================================================
        # PARSE HTML
        # =================================================

        soup = BeautifulSoup(

            response.text,

            "html.parser",

        )


        # =================================================
        # REMOVE UNNECESSARY HTML
        # =================================================

        for tag in soup.find_all(

            [

                "script",

                "style",

                "nav",

                "footer",

                "header",

                "noscript",

                "svg",

            ]

        ):

            tag.decompose()


        # =================================================
        # GET TEXT
        # =================================================

        text = soup.get_text(
            separator="\n"
        )


        clean_lines = [

            line.strip()

            for line
            in text.splitlines()

            if line.strip()

        ]


        cleaned_text = (
            "\n".join(
                clean_lines
            )
        )


        # Prevent excessively large AI prompts
        return cleaned_text[:25000]


    except HTTPException:

        raise


    except httpx.TimeoutException:

        raise HTTPException(
            status_code=408,

            detail=(
                "Documentation website "
                "took too long to respond"
            ),
        )


    except Exception as error:

        print("=" * 50)

        print(
            "DOCUMENTATION FETCH ERROR:"
        )

        print(
            repr(error)
        )

        print("=" * 50)


        raise HTTPException(
            status_code=500,

            detail=
                "Could not read documentation page",
        )


# =========================================================
# DOCUMENTATION SEARCH
# =========================================================

@app.post("/docs/search")
async def search_documentation(
    request:
        DocsSearchRequest,

    current_user: User =
        Depends(
            get_current_user
        ),
):

    question = (
        request.question.strip()
    )


    url = (
        request.url.strip()
    )


    # =====================================================
    # VALIDATION
    # =====================================================

    if not question:

        raise HTTPException(
            status_code=400,

            detail=
                "Question cannot be empty",
        )


    if not url:

        raise HTTPException(
            status_code=400,

            detail=
                "Documentation URL cannot be empty",
        )


    # =====================================================
    # FETCH DOCUMENTATION
    # =====================================================

    documentation = (
        await fetch_documentation_page(
            url
        )
    )


    if not documentation.strip():

        raise HTTPException(
            status_code=400,

            detail=
                "No readable documentation text found",
        )


    # =====================================================
    # AI DOCUMENTATION PROMPT
    # =====================================================

    prompt = f"""
You are DevMind, an AI Developer Assistant.

A developer has provided an official software
documentation page.

Answer the developer's question using the
documentation content supplied below.

IMPORTANT RULES:

1. Base your answer on the supplied documentation.

2. Do not invent APIs, methods, functions, parameters,
   configuration options or behavior.

3. Explain concepts clearly in developer-friendly language.

4. Give practical code examples when useful.

5. Mention important warnings, limitations or requirements.

6. If the supplied documentation does not contain enough
   information to answer the question, clearly say so.

7. Do not claim information came from the documentation
   unless it actually appears in the supplied content.

8. Prefer concise practical explanations before deeper details.


DOCUMENTATION SOURCE:

{url}


DOCUMENTATION CONTENT:

{documentation}


DEVELOPER QUESTION:

{question}
"""


    # =====================================================
    # GEMINI
    # =====================================================

    try:

        response = (
            await client.aio.models.generate_content(

                model=
                    GEMINI_MODEL,

                contents=
                    prompt,

            )
        )


        return {

            "question":
                question,

            "source":
                url,

            "answer":
                response.text,

        }


    except Exception as error:

        print("=" * 50)

        print(
            "DOCUMENTATION SEARCH ERROR:"
        )

        print(
            repr(error)
        )

        print("=" * 50)


        raise HTTPException(
            status_code=500,

            detail=
                "Documentation AI request failed",
        )
    # =========================================================
# AI FIX GITHUB ISSUE
# =========================================================

@app.post("/github/issues/fix")
async def fix_github_issue(
    request: GitHubIssueFixRequest,
    current_user: User = Depends(get_current_user),
):

    if not request.repo_url.strip():
        raise HTTPException(
            status_code=400,
            detail="Repository URL cannot be empty",
        )

    if request.issue_number <= 0:
        raise HTTPException(
            status_code=400,
            detail="Issue number must be greater than 0",
        )

    try:

        owner, repo = parse_repo_url(
            request.repo_url
        )

        # Get issue directly
        issue = await github_get(
            f"/repos/{owner}/{repo}/issues/{request.issue_number}"
        )

        if "pull_request" in issue:
            raise HTTPException(
                status_code=400,
                detail="That number belongs to a pull request, not an issue",
            )

        # Read repository code
        files = await collect_repository_source_files(
            owner,
            repo,
        )

        if not files:
            raise HTTPException(
                status_code=400,
                detail="No supported source files found",
            )

        context = build_repository_context(
            files
        )

        if not context.strip():
            raise HTTPException(
                status_code=400,
                detail="Repository contains no readable source code",
            )

        prompt = f"""
You are DevMind, an expert software engineer.

Analyze this GitHub issue against the supplied repository code.

REPOSITORY:
{owner}/{repo}

ISSUE NUMBER:
#{issue.get("number")}

ISSUE TITLE:
{issue.get("title")}

ISSUE BODY:
{issue.get("body") or "No issue description provided"}

REPOSITORY SOURCE CODE:

{context}

Your task:

1. Explain the likely root cause.
2. Identify the most relevant files.
3. Mention exact file paths.
4. Explain why the issue happens.
5. Provide a step-by-step fix plan.
6. Provide corrected code when the repository context supports it.
7. Suggest tests that should be added.
8. Mention any uncertainty if the supplied code is not enough.

Output format:

# Issue Summary

# Likely Root Cause

# Relevant Files

# Suggested Fix

# Corrected Code

# Tests To Add

# Confidence / Limitations
"""

        response = await client.aio.models.generate_content(
            model=GEMINI_MODEL,
            contents=prompt,
        )

        return {
            "repository":
                f"{owner}/{repo}",

            "issue_number":
                issue.get("number"),

            "title":
                issue.get("title"),

            "state":
                issue.get("state"),

            "url":
                issue.get("html_url"),

            "file_count":
                len(files),

            "fix":
                response.text,
        }

    except HTTPException:
        raise

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        )

    except Exception as error:

        print(
            "GITHUB ISSUE FIX ERROR:",
            repr(error),
        )

        raise HTTPException(
            status_code=500,
            detail="AI issue fix analysis failed",
        )