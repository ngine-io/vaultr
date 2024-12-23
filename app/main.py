import asyncio
import os
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

from app.version import __version__

load_dotenv(verbose=True)

os.environ["ANSIBLE_VAULT_PASSWORD"] = "test"
os.environ["ANSIBLE_VAULT_PASSWORD_FILE"] = "vault.sh"

app_name: str = os.getenv("APP_NAME", "Ansible Vault Encrypter/Decrypter Service")

logger.debug(f"App started: {app_name}")

templates = Jinja2Templates(directory="app/html/templates")

prefix: str = os.getenv("URL_PREFIX", "")
app = FastAPI(
    title=app_name,
    version=__version__,
)

app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(request=request, name="index.html")


@app.post("/encrypt", response_class=HTMLResponse)
async def encrypt(request: Request, content: Annotated[str, Form()]):

    command = f"echo '{content}' | ansible-vault encrypt_string"

    proc = await asyncio.create_subprocess_shell(
        command,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    stdout, stderr = await proc.communicate()
    return templates.TemplateResponse(request=request, name="index.html", context={"encrypted_content": stdout.decode()})
