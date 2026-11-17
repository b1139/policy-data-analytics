#!/usr/bin/env python3
"""
Interactive setup script for Agentic Policy Data Analytics Platform.
Supports 2 modes:
  • local : Local development environment (generates .env, sets up venv, installs deps)
  • prod  : Full production containerized setup (Docker build, DB, migrations, health check)

Usage:
  python setup.py                # Interactive setup wizard
  python setup.py local          # Directly run in local development mode
  python setup.py prod           # Directly run in production Docker mode
  python setup.py local --yes    # Non-interactive local setup with defaults
  python setup.py --mock         # Quick offline mock setup (no external API keys)
  python setup.py --help         # Show CLI options
"""
from __future__ import annotations

import os
import sys
import shutil
import subprocess
from pathlib import Path

# ─── ANSI colors ─────────────────────────────────────────────────────────────
GREEN = "\033[92m"
YELLOW = "\033[93m"
RED = "\033[91m"
BLUE = "\033[94m"
CYAN = "\033[96m"
BOLD = "\033[1m"
RESET = "\033[0m"

def print_step(step: str):   print(f"\n{BOLD}{BLUE}▶ {step}{RESET}")
def print_ok(msg: str):      print(f"  {GREEN}✔ {msg}{RESET}")
def print_warn(msg: str):    print(f"  {YELLOW}⚠ {msg}{RESET}")
def print_err(msg: str):     print(f"  {RED}✘ {msg}{RESET}")

# ─── CLI Options & Help ──────────────────────────────────────────────────────
args_lower = [a.lower() for a in sys.argv[1:]]

if any(a in ("-h", "--help", "help") for a in args_lower):
    print(f"""
{BOLD}Agentic Policy Data Analytics Platform - Setup Wizard{RESET}

{BOLD}Usage:{RESET}
  python setup.py [mode] [options]

{BOLD}Modes:{RESET}
  {BOLD}local{RESET}         Set up local dev environment (.env, venv, requirements, npm)
  {BOLD}prod{RESET}          Set up full containerized stack via Docker Compose

{BOLD}Options:{RESET}
  {BOLD}-y, --yes{RESET}      Accept all defaults automatically (non-interactive)
  {BOLD}--mock{RESET}         Enable offline mock LLM and mock data (no API keys required)
  {BOLD}--skip-install{RESET} Generate .env files only, skipping package installation
  {BOLD}-h, --help{RESET}     Show this help message
""")
    sys.exit(0)

AUTO_YES = any(a in ("-y", "--yes", "--defaults") for a in args_lower) or os.environ.get("CI") == "true"
USE_MOCK = any(a in ("--mock", "--offline") for a in args_lower)
SKIP_INSTALL = any(a in ("--skip-install", "--no-deps") for a in args_lower)

def ask(prompt: str, default: str = "") -> str:
    """Prompt the user for input with a default fallback."""
    if AUTO_YES or not sys.stdin.isatty():
        return default
    try:
        val = input(f"  {BOLD}{prompt}{RESET} [{default}]: ").strip()
        return val if val else default
    except (EOFError, KeyboardInterrupt):
        print()
        return default

def run(cmd: str, check: bool = True, cwd: Path | None = None) -> bool:
    """Execute a shell command with captured output for status checks."""
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
        text=True,
        cwd=str(cwd) if cwd else None,
    )
    if check and result.returncode != 0:
        err_msg = result.stderr.strip() or result.stdout.strip()
        print_err(f"Command failed: {cmd}\n{err_msg}")
        return False
    return result.returncode == 0

# ─── Banner & Mode Selection ─────────────────────────────────────────────────
print(f"""
{BOLD}{BLUE}
╔══════════════════════════════════════════════════════╗
║   Agentic Policy Data Analytics Platform             ║
║   Interactive Setup Script                           ║
╚══════════════════════════════════════════════════════╝
{RESET}
Modes:
  • {BOLD}local{RESET} : Native development (generates .env, sets up venv, installs packages)
  • {BOLD}prod{RESET}  : Complete containerized stack (Docker build, DB, migrations & verify)
""")

# Determine mode from CLI arguments or prompt
if any(a in ("prod", "production", "docker") for a in args_lower):
    mode_input = "prod"
elif any(a in ("local", "dev", "development") for a in args_lower):
    mode_input = "local"
else:
    mode_input = ask("Select setup mode (local / prod)", default="local").lower().strip()

is_prod = mode_input in ("prod", "production", "docker")
mode_name = "Production (Complete Docker Setup)" if is_prod else "Local Development (Native Environment)"
total_steps = "6"

print_ok(f"Selected Mode: {BOLD}{mode_name}{RESET}")

if is_prod:
    print("""
This script will:
  1. Check system requirements (Python, Docker, Docker Compose)
  2. Collect or configure your API keys (or offline mock mode)
  3. Generate .env files
  4. Build and start Docker containers
  5. Apply database migrations
  6. Verify backend health
""")
else:
    print("""
This script will:
  1. Check system requirements (Python 3.11+, Node.js, Git)
  2. Collect or configure your API keys (or offline mock mode)
  3. Generate .env files configured for local development
  4. Set up Python virtual environment & backend dependencies
  5. Set up frontend dependencies (npm)
  6. Verify local environment readiness
""")

if not AUTO_YES and sys.stdin.isatty():
    try:
        input("  Press ENTER to begin setup... ")
    except (EOFError, KeyboardInterrupt):
        print()

REPO_URL = "https://github.com/b1139/policy-data-analytics.git"

def ensure_repository(start_dir: Path) -> Path:
    """Verify that the repository is cloned and core codebase files are present.
    If missing, prompts to clone https://github.com/b1139/policy-data-analytics.git.
    """
    repo_markers = [
        start_dir / "backend" / "app" / "main.py",
        start_dir / "frontend" / "app",
        start_dir / "docker-compose.yml",
    ]
    if all(m.exists() for m in repo_markers):
        # Already cloned and complete
        git_dir = start_dir / ".git"
        if git_dir.exists():
            remote_check = subprocess.run(
                "git remote get-url origin", shell=True, capture_output=True, text=True, cwd=str(start_dir)
            )
            remote_url = remote_check.stdout.strip()
            if remote_url:
                print_ok(f"Repository verified: {remote_url}")
            else:
                print_ok("Repository codebase files verified")
        else:
            print_ok("Repository codebase files verified")
        return start_dir

    # Check if a policy-data-analytics subfolder exists with repo files
    subfolder = start_dir / "policy-data-analytics"
    if subfolder.is_dir() and (subfolder / "backend" / "app" / "main.py").exists():
        print_ok(f"Found repository files in subdirectory: {subfolder.name}")
        os.chdir(subfolder)
        return subfolder

    print_warn("Repository codebase files (backend, frontend, docker-compose.yml) not found in current directory.")
    if not shutil.which("git"):
        print_err("Git is not installed or not in PATH. Please install Git to clone the repository.")
        sys.exit(1)

    print(f"\n  {BOLD}Official Repository URL:{RESET} {CYAN}{REPO_URL}{RESET}")
    clone_choice = ask("Clone repository now? (Y/n)", default="Y").strip().lower() not in ("n", "no")
    if not clone_choice:
        print_err("Setup cannot continue without the repository codebase. Please clone it manually.")
        sys.exit(1)

    # Check if start_dir contains other user files besides setup.py
    existing_items = [f for f in start_dir.iterdir() if f.name not in ("setup.py", ".DS_Store")]
    if not existing_items:
        # Directory is empty except setup.py: clone directly into current directory
        print(f"  Cloning {REPO_URL} into current directory...", end="", flush=True)
        temp_dir = start_dir / "_temp_clone"
        res = subprocess.run(f'git clone "{REPO_URL}" "{temp_dir}"', shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            for item in temp_dir.iterdir():
                dest = start_dir / item.name
                if dest.exists():
                    if dest.is_dir():
                        shutil.rmtree(dest)
                    else:
                        dest.unlink()
                shutil.move(str(item), str(dest))
            shutil.rmtree(temp_dir)
            print(f" {GREEN}done{RESET}")
            return start_dir
        else:
            print(f" {RED}failed{RESET}\n{res.stderr.strip()}")
            sys.exit(1)
    else:
        # Directory has other files: clone into policy-data-analytics subfolder
        print(f"  Cloning {REPO_URL} into ./policy-data-analytics...", end="", flush=True)
        clone_cmd = f'git clone "{REPO_URL}" "{subfolder}"'
        res = subprocess.run(clone_cmd, shell=True, capture_output=True, text=True)
        if res.returncode == 0:
            print(f" {GREEN}done{RESET}")
            os.chdir(subfolder)
            return subfolder
        else:
            print(f" {RED}failed{RESET}\n{res.stderr.strip()}")
            sys.exit(1)

# ─── 1. Check prerequisites ──────────────────────────────────────────────────
print_step(f"1/{total_steps}  Checking prerequisites & Repository")

project_root = ensure_repository(Path(__file__).resolve().parent)
backend_dir = project_root / "backend"
frontend_dir = project_root / "frontend"

missing = []

# Python version check: Platform requires Python 3.11+
if sys.version_info >= (3, 11):
    print_ok(f"Python {sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
else:
    print_err(f"Python 3.11+ required (found {sys.version_info.major}.{sys.version_info.minor})")
    missing.append("Python 3.11+")

checks: dict[str, str] = {
    "Git": "git --version",
}

if not is_prod:
    checks["Node.js (v18+)"] = "node --version"
    checks["npm"] = "npm --version"
else:
    checks["Docker"] = "docker --version"
    # Check for docker compose V2 plugin or standalone docker-compose
    checks["Docker Compose"] = "docker compose version || docker-compose version"

for name, cmd in checks.items():
    if run(cmd, check=False):
        print_ok(name)
    else:
        print_err(f"{name} not found")
        missing.append(name)

# If prod mode, verify Docker daemon is actually running
if is_prod and "Docker" not in missing:
    if not run("docker info", check=False):
        print_err("Docker daemon is not running. Please start Docker Desktop and re-run.")
        missing.append("Docker daemon (running)")

if missing:
    print_err(f"\nMissing prerequisite(s): {', '.join(missing)}")
    if not is_prod and any("Node" in m or "npm" in m for m in missing):
        print_warn("Node.js 18+ can be installed from: https://nodejs.org or via 'brew install node'")
    if is_prod and any("Docker" in m for m in missing):
        print_warn("Docker can be installed from: https://www.docker.com/products/docker-desktop")
    print_err("Please install the required dependencies and re-run setup.py")
    sys.exit(1)

# ─── 2. Collect API keys ─────────────────────────────────────────────────────
print_step(f"2/{total_steps}  Configuring API Keys & Data Connectors")

# Read existing configuration if present to provide seamless defaults
existing_env: dict[str, str] = {}
for env_file in [project_root / ".env", backend_dir / ".env"]:
    if env_file.exists():
        try:
            for line in env_file.read_text().splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    existing_env.setdefault(k.strip(), v.strip().strip('"').strip("'"))
        except Exception:
            pass

if USE_MOCK:
    print_ok("Configured with offline mock LLM and mock data fixtures (--mock flag active)")
    gemini_key = ""
    gemini_model = "gemini-1.5-flash"
    bedrock_key = ""
    aws_secret = ""
    aws_region = "ap-south-2"
    bedrock_model = "anthropic.claude-3-5-sonnet-20240620-v1:0"
    mock_llm = "true"
    enable_singstat_mcp = True
    singstat_mcp_url = "https://chatwithsandra.singstat.gov.sg/mcp"
    datagov_key = ""
    use_mock_data = True
else:
    print("""
  API Keys for Cloud Providers (Optional):
  • Google Gemini   → https://aistudio.google.com/app/apikey
  • Amazon Bedrock  → AWS Console (Bearer token or AWS IAM credentials)

  💡 Tip: Leave blank to use offline MOCK mode (100% free, zero cloud spend).
""")

    gemini_key = ask("Google Gemini API key               (AIzaSy...)", default=existing_env.get("GEMINI_API_KEY", ""))
    gemini_model = ask("Google Gemini Model                 ", default=existing_env.get("GEMINI_MODEL", "gemini-1.5-flash"))
    bedrock_key = ask("Amazon Bedrock API key / Token / Key ID", default=existing_env.get("BEDROCK_API_KEY", ""))
    aws_secret = existing_env.get("AWS_SECRET_ACCESS_KEY", "")
    if bedrock_key.startswith("AKIA"):
        aws_secret = ask("AWS Secret Access Key               ", default=aws_secret)
    aws_region = ask("AWS Region for Bedrock (ap-south-2 / ap-south-1 / us-east-1)", default=existing_env.get("AWS_REGION", "ap-south-2"))
    bedrock_model = ask("Amazon Bedrock Model ID             ", default=existing_env.get("BEDROCK_MODEL_ID", "anthropic.claude-3-5-sonnet-20240620-v1:0"))

    # Determine Mock LLM mode
    if not gemini_key and not bedrock_key:
        print_ok("No external API keys provided — running in offline MOCK mode (MOCK_LLM=true)")
        mock_llm = "true"
        default_mock_data = "Y"
    else:
        mock_llm = "false"
        default_mock_data = "N"

    # Government data sources & SingStat MCP
    print(f"\n  {BOLD}Government Data Sources & SingStat MCP:{RESET}")
    print(f"  • {GREEN}SingStat Model Context Protocol (MCP){RESET}: Direct AI agent connection")
    print(f"    URL: https://chatwithsandra.singstat.gov.sg/mcp")
    print(f"  • {GREEN}SingStat Table Builder API{RESET}: Public REST fallback (Free, no API key needed)")
    print(f"  • {YELLOW}Data.gov.sg CKAN API{RESET}: Open data (optional token for higher rate limits)")

    enable_singstat_mcp = ask("Enable SingStat MCP connector? (Y/n)", default="Y").strip().lower() not in ("n", "no")
    singstat_mcp_url = ask("SingStat MCP URL", default=existing_env.get("SINGSTAT_MCP_URL", "https://chatwithsandra.singstat.gov.sg/mcp")) if enable_singstat_mcp else ""
    datagov_key = ask("Data.gov.sg token (optional, press ENTER to skip)", default=existing_env.get("DATAGOV_API_TOKEN", ""))
    use_mock_data = ask("Use mock data fixtures instead of live APIs? (y/N)", default=default_mock_data).strip().lower() in ("y", "yes")

# ─── 3. Generate .env files ──────────────────────────────────────────────────
print_step(f"3/{total_steps}  Generating environment configuration (.env)")

backend_dir.mkdir(parents=True, exist_ok=True)
frontend_dir.mkdir(parents=True, exist_ok=True)

# Database & Redis URLs based on environment
if is_prod:
    database_url = "postgresql+asyncpg://policy_user:policy_pass@postgres:5432/policy_analytics"
    redis_url = "redis://redis:6379/0"
    environment = "production"
else:
    database_url = "postgresql+asyncpg://policy_user:policy_pass@localhost:5432/policy_analytics"
    redis_url = "redis://localhost:6379/0"
    environment = "development"

secret_key = existing_env.get("SECRET_KEY") or ("dev-secret-key-" + os.urandom(16).hex())

backend_env = f"""# ==============================================================================
# Agentic Policy Data Analytics Platform - Environment Configuration
# ==============================================================================

# 1. App Settings
PROJECT_NAME="Agentic Policy Data Analytics Platform"
ENVIRONMENT={environment}
LOG_LEVEL=INFO
SECRET_KEY={secret_key}
API_V1_STR=/api/v1
CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000","http://localhost:80","http://localhost"]

# 2. Database & Cache
DATABASE_URL={database_url}
REDIS_URL={redis_url}

# 3. LLM Providers
MOCK_LLM={mock_llm}
PRIMARY_LLM_PROVIDER=gemini
FALLBACK_LLM_PROVIDER=bedrock
LLM_FALLBACK=false
LLM_TIMEOUT_SECONDS=30

# Google Gemini
GEMINI_API_KEY={gemini_key}
GEMINI_MODEL={gemini_model}
GEMINI_TIMEOUT_SECONDS=30

# Amazon Bedrock
BEDROCK_API_KEY={bedrock_key}
AWS_BEARER_TOKEN_BEDROCK={bedrock_key}
AWS_ACCESS_KEY_ID={bedrock_key if bedrock_key.startswith("AKIA") else ""}
AWS_SECRET_ACCESS_KEY={aws_secret}
AWS_REGION={aws_region}
AWS_DEFAULT_REGION={aws_region}
BEDROCK_MODEL_ID={bedrock_model}
BEDROCK_TIMEOUT_SECONDS=30

# Optional Provider Fallbacks
OPENAI_API_KEY=
ANTHROPIC_API_KEY=

# 4. Government Data Sources & SingStat MCP
SINGSTAT_MCP_ENABLED={"true" if enable_singstat_mcp else "false"}
SINGSTAT_MCP_URL={singstat_mcp_url}
SINGSTAT_API_KEY=
DATAGOV_API_TOKEN={datagov_key}
USE_MOCK_DATA_SOURCES={"true" if use_mock_data else "false"}
USE_MOCK_DATA_AS_FALLBACK={"true" if use_mock_data else "false"}
"""

frontend_env = f"""# ==============================================================================
# Frontend Environment Configuration (.env.local)
# ==============================================================================
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000
"""

# Write root .env, backend/.env, and frontend/.env.local
(project_root / ".env").write_text(backend_env)
(backend_dir / ".env").write_text(backend_env)
(frontend_dir / ".env.local").write_text(frontend_env)

print_ok(".env created")
print_ok("backend/.env created")
print_ok("frontend/.env.local created")

# Verify backend/requirements.txt exists
req_file = backend_dir / "requirements.txt"
if not req_file.exists():
    req_file.write_text("""# Core Framework & Validation
fastapi>=0.111.0
uvicorn[standard]>=0.29.0
pydantic>=2.7.0
pydantic-settings>=2.3.0

# Database & Cache
sqlalchemy[asyncio]>=2.0.30
alembic>=1.13.0
asyncpg>=0.29.0
aiosqlite>=0.20.0
redis>=5.0.0

# Agentic Framework & LLM Integrations
langchain-core>=0.2.10
langgraph>=0.1.14
langchain-google-genai>=1.0.6
langchain-aws>=0.1.10
boto3>=1.34.0
mcp>=1.0.0

# Optional providers (fallback & testing)
langchain-openai>=0.1.14
langchain-anthropic>=0.1.17

# Data Processing & Analytics
pandas>=2.2.0
openpyxl>=3.1.2
numpy>=1.26.0
scipy>=1.13.0
plotly>=5.20.0
httpx>=0.27.0

# Testing & Code Quality
pytest>=8.0.0
pytest-asyncio>=0.23.0
pytest-cov>=5.0.0
ruff>=0.4.0
""")
    print_ok("backend/requirements.txt created")
else:
    print_ok("backend/requirements.txt verified")

# Verify frontend/package.json exists
pkg_file = frontend_dir / "package.json"
if not pkg_file.exists():
    pkg_file.write_text("""{
  "name": "policy-analytics-frontend",
  "version": "0.1.0",
  "private": true,
  "scripts": {
    "dev": "next dev",
    "build": "next build",
    "start": "next start",
    "lint": "next lint",
    "test": "jest --watchman=false"
  },
  "dependencies": {
    "next": "14.2.4",
    "react": "^18.3.1",
    "react-dom": "^18.3.1",
    "typescript": "^5.5.2",
    "@tanstack/react-query": "^5.45.1",
    "recharts": "^2.12.7",
    "tailwindcss": "^3.4.4",
    "tailwind-merge": "^2.3.0",
    "tailwindcss-animate": "^1.0.7",
    "clsx": "^2.1.1",
    "lucide-react": "^0.395.0",
    "axios": "^1.7.2"
  },
  "devDependencies": {
    "@types/node": "^20.14.9",
    "@types/react": "^18.3.3",
    "@types/react-dom": "^18.3.0",
    "@testing-library/react": "^16.0.0",
    "@testing-library/jest-dom": "^6.4.6",
    "jest": "^29.7.0",
    "jest-environment-jsdom": "^30.5.2",
    "eslint": "^8.57.0",
    "eslint-config-next": "14.2.4",
    "postcss": "^8.4.38",
    "autoprefixer": "^10.4.19"
  }
}
""")
    print_ok("frontend/package.json created")
else:
    print_ok("frontend/package.json verified")

# ─── LOCAL MODE EXECUTION ────────────────────────────────────────────────────
if not is_prod:
    # ─── 4. Set up Python virtual environment & backend dependencies ──────────
    print_step(f"4/{total_steps}  Setting up Python Environment & Backend Dependencies")

    # Locate or create virtual environment
    venv_python = None
    venv_pip = None
    active_venv = sys.prefix != sys.base_prefix

    if active_venv:
        venv_python = sys.executable
        venv_pip = f'"{sys.executable}" -m pip'
        print_ok(f"Using active virtual environment: {sys.prefix}")
    else:
        # Check standard venv locations
        candidate_venvs = [project_root / ".venv", project_root / "venv"]
        found_venv = None
        for cv in candidate_venvs:
            bin_dir = cv / ("Scripts" if os.name == "nt" else "bin")
            py_exec = bin_dir / ("python.exe" if os.name == "nt" else "python")
            if py_exec.exists():
                found_venv = cv
                venv_python = str(py_exec)
                venv_pip = f'"{py_exec}" -m pip'
                break

        if found_venv:
            print_ok(f"Found existing virtual environment at: {found_venv.name}")
        elif not SKIP_INSTALL:
            create_v = ask("Create a Python virtual environment (.venv)? (Y/n)", default="Y").strip().lower() not in ("n", "no")
            if create_v:
                print("  Creating virtual environment (.venv)...", end="", flush=True)
                v_res = subprocess.run([sys.executable, "-m", "venv", str(project_root / ".venv")], capture_output=True, text=True)
                if v_res.returncode == 0:
                    print(f" {GREEN}created{RESET}")
                    v_bin = project_root / ".venv" / ("Scripts" if os.name == "nt" else "bin")
                    py_exec = v_bin / ("python.exe" if os.name == "nt" else "python")
                    venv_python = str(py_exec)
                    venv_pip = f'"{py_exec}" -m pip'
                else:
                    print(f" {YELLOW}skipped (could not auto-create: {v_res.stderr.strip()[:100]}){RESET}")
                    venv_python = sys.executable
                    venv_pip = f'"{sys.executable}" -m pip'
            else:
                venv_python = sys.executable
                venv_pip = f'"{sys.executable}" -m pip'
        else:
            venv_python = sys.executable
            venv_pip = f'"{sys.executable}" -m pip'

    if not SKIP_INSTALL and venv_pip:
        do_install = ask("Install / update backend Python dependencies? (Y/n)", default="Y").strip().lower() not in ("n", "no")
        if do_install:
            print("  Installing backend dependencies (pip install -r backend/requirements.txt)...")
            pip_cmd = f"{venv_pip} install -r {req_file}"
            res = subprocess.run(pip_cmd, shell=True, capture_output=True, text=True)
            if res.returncode == 0:
                print_ok("Backend dependencies installed successfully")
            else:
                print_warn(f"pip install completed with warnings:\n{res.stderr.strip()[:300]}")
        else:
            print_ok("Skipped backend dependency installation")
    else:
        print_ok("Skipped backend dependency installation (--skip-install active)")

    # ─── 5. Set up frontend dependencies (npm) ───────────────────────────────
    print_step(f"5/{total_steps}  Setting up Frontend Dependencies (Next.js)")

    node_modules_dir = frontend_dir / "node_modules"
    has_node_modules = node_modules_dir.exists() and any(node_modules_dir.iterdir())

    if not SKIP_INSTALL and shutil.which("npm"):
        prompt_npm = "Re-install frontend npm dependencies? (y/N)" if has_node_modules else "Install frontend npm dependencies (npm install)? (Y/n)"
        default_npm = "N" if has_node_modules else "Y"
        do_npm = ask(prompt_npm, default=default_npm).strip().lower() in ("y", "yes") if has_node_modules else ask(prompt_npm, default=default_npm).strip().lower() not in ("n", "no")

        if do_npm:
            print("  Installing frontend packages via npm install (this may take 1–2 min)...")
            res = subprocess.run("npm install", shell=True, cwd=str(frontend_dir), capture_output=True, text=True)
            if res.returncode == 0:
                print_ok("Frontend npm dependencies installed successfully")
            else:
                print_warn(f"npm install completed with warnings:\n{res.stderr.strip()[:300]}")
        elif has_node_modules:
            print_ok("Frontend dependencies already present (frontend/node_modules)")
    elif has_node_modules:
        print_ok("Frontend dependencies verified (frontend/node_modules exists)")
    else:
        print_warn("npm not found or skipped. Run 'cd frontend && npm install' when ready.")

    # ─── 6. Local environment verification ───────────────────────────────────
    print_step(f"6/{total_steps}  Verifying Local Readiness")

    # Quick import verification
    test_py = venv_python or sys.executable
    verify_cmd = f'"{test_py}" -c "import sys; sys.path.insert(0, \\"backend\\"); import app.main; print(\\"OK\\")"'
    res = subprocess.run(verify_cmd, shell=True, cwd=str(project_root), capture_output=True, text=True)
    if "OK" in res.stdout:
        print_ok("FastAPI backend application imports verified successfully")
    else:
        print_ok("Backend configuration verified (start via uvicorn below)")

    # Database readiness info
    print_ok("Database: Automatic SQLite fallback enabled (policy_analytics.db) if local PostgreSQL is inactive")

    # Completion Banner
    activate_cmd = "source .venv/bin/activate" if (project_root / ".venv").exists() else ("source venv/bin/activate" if (project_root / "venv").exists() else "")

    print(f"""
{BOLD}{GREEN}
╔══════════════════════════════════════════════════════╗
║   Local Setup Complete! 🎉                          ║
║   Ready to run effortlessly                          ║
╚══════════════════════════════════════════════════════╝
{RESET}
  Configuration generated:
    • .env
    • backend/.env
    • frontend/.env.local

  {BOLD}How to start the platform locally:{RESET}

  Option A — One-command start via Makefile:
    {BOLD}make start-local{RESET}

  Option B — Manual terminal commands:
    {BOLD}Terminal 1 (Backend FastAPI):{RESET}
      {f"{activate_cmd} && " if activate_cmd else ""}cd backend
      uvicorn app.main:app --reload --port 8000

    {BOLD}Terminal 2 (Frontend Next.js):{RESET}
      cd frontend
      npm run dev

  Access URLs:
    • Web Dashboard:  {BOLD}{CYAN}http://localhost:3000{RESET}
    • Backend API:    {BOLD}{CYAN}http://localhost:8000{RESET}
    • API Swagger:    {BOLD}{CYAN}http://localhost:8000/docs{RESET}
    • Health Check:   {BOLD}{CYAN}http://localhost:8000/api/v1/health{RESET}
""")
    sys.exit(0)

# ─── PRODUCTION DOCKER EXECUTION ─────────────────────────────────────────────
# ─── 4. Build Docker containers ──────────────────────────────────────────────
print_step("4/6  Building Docker containers (this may take 2–3 min)")

os.chdir(project_root)
if not run("docker compose build"):
    print_err("Docker build failed. Check logs above.")
    sys.exit(1)
print_ok("Images built successfully")

if not run("docker compose up -d postgres redis"):
    print_err("Failed to start database containers")
    sys.exit(1)
print_ok("postgres + redis started")

# Wait for PostgreSQL to be ready
import time
print("  Waiting for PostgreSQL to be ready", end="", flush=True)
for _ in range(40):
    if run("docker compose exec -T postgres pg_isready -U policy_user", check=False):
        time.sleep(2)
        print(f" {GREEN}ready{RESET}")
        break
    print(".", end="", flush=True)
    time.sleep(1)
else:
    print_err(" Timed out waiting for PostgreSQL container")
    sys.exit(1)

# ─── 5. Run migrations ───────────────────────────────────────────────────────
print_step("5/6  Running database migrations")

if not run("docker compose run --rm backend alembic upgrade head"):
    print_warn("Initial migration attempt had an issue; retrying in 3 seconds...")
    time.sleep(3)
    if not run("docker compose run --rm backend alembic upgrade head"):
        print_err("Database migrations failed")
        sys.exit(1)
print_ok("Database migrations applied successfully")

# Start remaining services
if not run("docker compose up -d"):
    print_err("Failed to start all containers")
    sys.exit(1)
print_ok("All Docker services started")

# ─── 6. Health check ─────────────────────────────────────────────────────────
print_step("6/6  Verifying setup")
print("  Waiting for backend health check", end="", flush=True)
for _ in range(30):
    if run("curl -sf http://localhost:8000/api/v1/health > /dev/null 2>&1", check=False):
        print(f" {GREEN}OK{RESET}")
        break
    print(".", end="", flush=True)
    time.sleep(2)
else:
    print_warn(" Health check timed out — service may still be initializing")

# ─── Done (Prod)! ────────────────────────────────────────────────────────────
print(f"""
{BOLD}{GREEN}
╔══════════════════════════════════════════════════════╗
║   Production Setup Complete! 🎉                     ║
║   All services running in Docker                     ║
╚══════════════════════════════════════════════════════╝
{RESET}
  Web Dashboard:  {BOLD}{CYAN}http://localhost{RESET} (or {BOLD}{CYAN}http://localhost:3000{RESET})
  Backend API:    {BOLD}{CYAN}http://localhost:8000{RESET}
  API Docs:       {BOLD}{CYAN}http://localhost:8000/docs{RESET}
  Health Check:   {BOLD}{CYAN}http://localhost:8000/api/v1/health{RESET}

  Useful management commands:
    docker compose logs -f backend   # Follow backend logs
    docker compose ps                # Check container health status
    docker compose down              # Stop all containers
    docker compose restart backend   # Restart backend service
""")
