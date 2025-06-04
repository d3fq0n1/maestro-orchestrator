import os
import subprocess
import sys
import webbrowser
import time

def run(cmd, shell=True, cwd=None):
    print(f"→ {cmd}")
    result = subprocess.run(cmd, shell=shell, cwd=cwd)
    if result.returncode != 0:
        print(f"❌ Command failed: {cmd}")
        sys.exit(result.returncode)

def start_process(cmd, cwd=None):
    return subprocess.Popen(cmd, shell=True, cwd=cwd)

print("📦 Starting Full Manual Verification Script for Maestro-Orchestrator (Non-Docker Mode)")

# Step 1: Create virtual environment
if not os.path.exists("venv"):
    run("python -m venv venv")

# Step 2: Activate & install requirements
venv_python = "venv\\Scripts\\python.exe"
run(f"{venv_python} -m pip install -r requirements.txt")

# Step 3: Copy .env if needed
if not os.path.exists(".env"):
    if os.path.exists(".env.template"):
        run("copy .env.template .env", shell=True)
        print("✅ .env created from template.")
    else:
        print("❌ .env.template not found. Cannot continue.")
        sys.exit(1)

# Step 4: Launch backend in background
print("\n🚀 Launching FastAPI backend...")
backend_process = start_process("venv\\Scripts\\uvicorn.exe main:app --port 8000")

# Step 5: Launch frontend
print("\n📦 Setting up frontend...")
ui_dir = os.path.join(os.getcwd(), "ui")
run("npm install", cwd=ui_dir)
print("🚀 Launching Vite frontend...")
frontend_process = start_process("npm run dev", cwd=ui_dir)

# Step 6: Open browser tabs
time.sleep(3)
webbrowser.open("http://localhost:5173")
webbrowser.open("http://localhost:8000/docs")

print("\n✅ Maestro-Orchestrator is running.")
print("   Frontend: http://localhost:5173")
print("   Backend Docs: http://localhost:8000/docs")

print("\nPress Ctrl+C to stop both processes.")
try:
    backend_process.wait()
    frontend_process.wait()
except KeyboardInterrupt:
    print("\n🛑 Stopping processes...")
    backend_process.terminate()
    frontend_process.terminate()