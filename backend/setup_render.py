# setup_render.py
# Run from the backend/ directory: python setup_render.py

import os
import sys
import subprocess
from pathlib import Path

class C:
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    GRAY = '\033[90m'
    BOLD = '\033[1m'
    END = '\033[0m'

def print_header(text):
    print(f"\n{C.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C.END}")
    print(f"{C.YELLOW} {text} {C.END}")
    print(f"{C.CYAN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━{C.END}\n")

def read_file_safe(path: str) -> str:
    """
    Read a file with automatic encoding detection.
    Fixes UTF-16/UTF-8-BOM files by rewriting them as clean UTF-8.
    """
    p = Path(path)
    if not p.exists():
        return ""
    
    # Try common encodings in order of likelihood
    for enc in ['utf-8', 'utf-8-sig', 'utf-16', 'utf-16-le', 'utf-16-be', 'cp1252']:
        try:
            content = p.read_text(encoding=enc)
            # If it wasn't UTF-8, rewrite it in UTF-8 to fix the file permanently
            if enc != 'utf-8':
                p.write_text(content, encoding='utf-8')
                print(f"  {C.GREEN}✓ Repaired {path} encoding ({enc} → utf-8){C.END}")
            return content
        except UnicodeDecodeError:
            continue
        except Exception:
            continue
    
    # Ultimate fallback — read raw bytes, strip non-ASCII
    try:
        raw = p.read_bytes()
        # Decode as latin-1 (1:1 byte mapping), then re-encode as utf-8
        content = raw.decode('latin-1', errors='replace')
        p.write_text(content, encoding='utf-8')
        print(f"  {C.YELLOW}⚠️  Forced {path} to UTF-8 (some chars may be corrupted){C.END}")
        return content
    except Exception as e:
        print(f"  {C.RED}❌ Could not read {path}: {e}{C.END}")
        return ""

def write_file(path: str, content: str, unix_newlines: bool = False):
    """Write file with UTF-8 encoding. Optionally force LF line endings."""
    p = Path(path)
    if unix_newlines:
        with p.open("w", encoding="utf-8", newline="\n") as f:
            f.write(content)
    else:
        p.write_text(content, encoding="utf-8")

def main():
    print(f"{C.CYAN}🚀 Nimbus Render Deployment Setup{C.END}\n")

    # ─── 1. Verify directory ───
    if not Path("manage.py").exists():
        print(f"{C.RED}❌ Error: manage.py not found. Run this from the backend/ directory.{C.END}")
        sys.exit(1)

    # ─── 2. Add production dependencies ───
    print(f"{C.YELLOW}📦 Adding production dependencies to requirements.txt...{C.END}")
    required_packages = [
        "gunicorn", "whitenoise", "dj-database-url", 
        "celery", "redis", "django-storages", 
        "boto3", "psycopg2-binary", "sentry-sdk"
    ]
    
    # Read with safe encoding detection (fixes UTF-16 corruption)
    existing_content = read_file_safe("requirements.txt")
    existing_reqs = existing_content.splitlines() if existing_content else []
    
    # Normalize: strip whitespace + BOM chars from each line
    existing_reqs = [line.strip().lstrip('\ufeff') for line in existing_reqs if line.strip()]
    
    # Build the new list
    new_lines = list(existing_reqs)
    added = []
    for pkg in required_packages:
        pkg_lower = pkg.lower().replace("-", "_")
        if not any(line.lower().replace("-", "_").startswith(pkg_lower) for line in existing_reqs):
            new_lines.append(pkg)
            added.append(pkg)
    
    # Rewrite the whole file cleanly in UTF-8
    req_path = Path("requirements.txt")
    req_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")
    
    if added:
        for pkg in added:
            print(f"  {C.GREEN}+ Added {pkg}{C.END}")
    else:
        print(f"  {C.GREEN}✓ All packages already present (file rewritten as clean UTF-8){C.END}")

    # ─── 3. Create render.yaml ───
    print(f"\n{C.YELLOW}📝 Creating render.yaml...{C.END}")
    render_yaml = """services:
  - type: web
    name: nimbus-api
    runtime: python
    plan: starter
    buildCommand: "bash ./build.sh"
    startCommand: "gunicorn config.wsgi:application --bind 0.0.0.0:$PORT --workers 2 --timeout 120"
    healthCheckPath: /api/docs/
    envVars:
      - key: PYTHON_VERSION
        value: 3.13.0
      - key: DJANGO_SETTINGS_MODULE
        value: config.settings
      - key: DEBUG
        value: "False"
      - key: DATABASE_URL
        fromDatabase:
          name: nimbus-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          name: nimbus-redis
          type: redis
          property: connectionString
      - key: SECRET_KEY
        generateValue: true
      - key: WEB_CONCURRENCY
        value: "2"

  - type: worker
    name: nimbus-worker
    runtime: python
    plan: starter
    buildCommand: "pip install -r requirements.txt"
    startCommand: "celery -A config worker --loglevel=info --concurrency=2"
    envVars:
      - key: PYTHON_VERSION
        value: 3.13.0
      - key: DJANGO_SETTINGS_MODULE
        value: config.settings
      - key: DATABASE_URL
        fromDatabase:
          name: nimbus-db
          property: connectionString
      - key: REDIS_URL
        fromService:
          name: nimbus-redis
          type: redis
          property: connectionString
      - key: SECRET_KEY
        fromService:
          type: web
          name: nimbus-api
          envVarKey: SECRET_KEY

databases:
  - name: nimbus-db
    databaseName: nimbus_db
    plan: free
    postgresMajorVersion: "16"

  - name: nimbus-redis
    plan: free
    ipAllowList: []
"""
    write_file("render.yaml", render_yaml, unix_newlines=True)
    print(f"  {C.GREEN}✓ render.yaml created{C.END}")

    # ─── 4. Create build.sh ───
    print(f"\n{C.YELLOW}🔨 Creating build.sh...{C.END}")
    build_sh = """#!/usr/bin/env bash
set -o errexit

echo "Installing dependencies..."
pip install -r requirements.txt

echo "Collecting static files..."
python manage.py collectstatic --no-input

echo "Running migrations..."
python manage.py migrate --no-input

echo "Build complete!"
"""
    write_file("build.sh", build_sh, unix_newlines=True)
    print(f"  {C.GREEN}✓ build.sh created (Unix LF line endings){C.END}")

    # ─── 5. Create Celery config ───
    print(f"\n{C.YELLOW}⚙️  Creating Celery config...{C.END}")
    config_dir = Path("config")
    config_dir.mkdir(exist_ok=True)

    celery_py = config_dir / "celery.py"
    if not celery_py.exists():
        celery_content = """import os
from celery import Celery

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

app = Celery('nimbus')
app.config_from_object('django.conf:settings', namespace='CELERY')
app.autodiscover_tasks()
"""
        write_file(str(celery_py), celery_content)
        print(f"  {C.GREEN}✓ config/celery.py created{C.END}")
    else:
        print(f"  {C.GRAY}✓ config/celery.py already exists{C.END}")

    init_py = config_dir / "__init__.py"
    init_content = read_file_safe(str(init_py)) if init_py.exists() else ""
    if "celery" not in init_content:
        with init_py.open("a", encoding="utf-8") as f:
            f.write("\n\n# Load Celery app when Django starts\nfrom .celery import app as celery_app\n__all__ = ('celery_app',)\n")
        print(f"  {C.GREEN}✓ config/__init__.py updated for Celery{C.END}")

    # ─── 6. Create .env.example ───
    print(f"\n{C.YELLOW}🔐 Creating .env.example...{C.END}")
    env_example = """# Copy to .env for local development (never commit .env to git)
DEBUG=True
SECRET_KEY=dev-secret-key-change-me
DATABASE_URL=postgres://nimbus_app:password@localhost:5432/zambia_mfi
REDIS_URL=redis://localhost:6379/0
ALLOWED_HOSTS=localhost,127.0.0.1,.onrender.com

# External file storage (required on Render — filesystem is ephemeral)
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_STORAGE_BUCKET_NAME=
AWS_S3_REGION_NAME=eu-west-1

# Error monitoring (optional)
SENTRY_DSN=
"""
    write_file(".env.example", env_example)
    print(f"  {C.GREEN}✓ .env.example created{C.END}")

    # ─── 7. Update .gitignore ───
    print(f"\n{C.YELLOW}🙈 Updating .gitignore...{C.END}")
    gitignore_entries = [
        "venv/", "env/", ".env", "*.sqlite3", "db.sqlite3", 
        "__pycache__/", "*.pyc", "staticfiles/", "media/", 
        ".DS_Store", "*.log", ".idea/", ".vscode/"
    ]
    
    gitignore_path = Path(".gitignore")
    current_gitignore = read_file_safe(".gitignore").splitlines() if gitignore_path.exists() else []
    current_gitignore = [line.strip().lstrip('\ufeff') for line in current_gitignore if line.strip()]
    
    with gitignore_path.open("a", encoding="utf-8") as f:
        for entry in gitignore_entries:
            if entry not in current_gitignore:
                f.write(f"{entry}\n")
    print(f"  {C.GREEN}✓ .gitignore updated{C.END}")

    # ─── 8. Print manual steps ───
    print_header("⚠️  MANUAL STEPS — edit config/settings.py:")
    print(f"""{C.BOLD}STEP A. At the TOP of settings.py, add:{C.END}
    {C.GRAY}import os{C.END}
    {C.GRAY}import dj_database_url{C.END}

{C.BOLD}STEP B. Replace DEBUG / SECRET_KEY / ALLOWED_HOSTS:{C.END}
    {C.GRAY}DEBUG = os.environ.get('DEBUG', 'True') == 'True'{C.END}
    {C.GRAY}SECRET_KEY = os.environ.get('SECRET_KEY', 'dev-fallback'){C.END}
    {C.GRAY}ALLOWED_HOSTS = os.environ.get('ALLOWED_HOSTS', 'localhost,127.0.0.1').split(','){C.END}

{C.BOLD}STEP C. In MIDDLEWARE, add after 'SecurityMiddleware':{C.END}
    {C.GRAY}'whitenoise.middleware.WhiteNoiseMiddleware',{C.END}

{C.BOLD}STEP D. Wrap the DATABASES block with:{C.END}
    {C.GRAY}if 'DATABASE_URL' in os.environ:{C.END}
    {C.GRAY}    DATABASES = {{'default': dj_database_url.config(conn_max_age=600)}}{C.END}
    {C.GRAY}else:{C.END}
    {C.GRAY}    # ... your existing sqlite config ...{C.END}

{C.BOLD}STEP E. Near the STATIC settings, add:{C.END}
    {C.GRAY}STATIC_ROOT = BASE_DIR / 'staticfiles'{C.END}
    {C.GRAY}STATICFILES_STORAGE = 'whitenoise.storage.CompressedManifestStaticFilesStorage'{C.END}

{C.BOLD}STEP F. At the very BOTTOM of settings.py, add:{C.END}
    {C.GRAY}CSRF_TRUSTED_ORIGINS = ['https://*.onrender.com']{C.END}
    {C.GRAY}CELERY_BROKER_URL = os.environ.get('REDIS_URL', 'redis://localhost:6379/0'){C.END}
    {C.GRAY}CELERY_RESULT_BACKEND = os.environ.get('REDIS_URL', 'redis://localhost:6379/0'){C.END}
    """)

    # ─── 9. Git commit & push ───
    response = input(f"\n{C.YELLOW}Commit and push to Git now? (y/n): {C.END}").strip().lower()
    
    if response == 'y':
        print(f"\n{C.YELLOW}🔀 Committing and pushing...{C.END}")
        try:
            subprocess.run(["git", "add", "."], check=True)
            subprocess.run(["git", "commit", "-m", "chore: prepare backend for Render deployment"], check=True)
            
            remote_check = subprocess.run(["git", "remote", "get-url", "origin"], capture_output=True, text=True)
            
            if remote_check.returncode == 0:
                subprocess.run(["git", "push", "origin", "HEAD"], check=True)
                print(f"{C.GREEN}✅ Pushed to remote successfully!{C.END}")
            else:
                print(f"\n{C.YELLOW}⚠️  No git remote configured. Set it up first:{C.END}")
                print(f"    {C.GRAY}git remote add origin https://github.com/YOUR_USER/YOUR_REPO.git{C.END}")
                print(f"    {C.GRAY}git branch -M main{C.END}")
                print(f"    {C.GRAY}git push -u origin main{C.END}")
                
        except subprocess.CalledProcessError as e:
            print(f"{C.RED}❌ Git command failed: {e}{C.END}")
    else:
        print(f"\n{C.YELLOW}⏸️  Skipped. When ready, run:{C.END}")
        print(f"    {C.GRAY}git add .{C.END}")
        print(f"    {C.GRAY}git commit -m 'chore: prepare for Render'{C.END}")
        print(f"    {C.GRAY}git push origin HEAD{C.END}")

    print(f"\n{C.GREEN}🎉 Setup complete! Next steps:{C.END}")
    print("  1. Push to GitHub if you haven't")
    print("  2. Go to https://dashboard.render.com → New → Blueprint")
    print("  3. Select your repo, review render.yaml, click Apply")
    print("  4. Add AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY to nimbus-api env vars\n")

if __name__ == "__main__":
    main()