# Contributing to Maestro-Orchestrator

Maestro-Orchestrator pluralizes synthetic intelligence by enabling multiple AI agents to collaborate, dissent, and reach consensus using quorum-based logic. Contributions are welcome and appreciated.

---

## Table of Contents

- [Getting Started](#getting-started)
- [Development Environment Setup](#development-environment-setup)
- [Coding Standards](#coding-standards)
- [Testing](#testing)
- [Submitting Changes](#submitting-changes)
- [Community Guidelines](#community-guidelines)
- [License](#license)

---

## Getting Started

1. **Fork the repository** using GitHub's UI.
2. **Clone your fork**:
   ```bash
   git clone https://github.com/your-username/maestro-orchestrator.git
   cd maestro-orchestrator
   ```
3. **Create a feature branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

---

## Development Environment Setup

### Prerequisites

- **Python 3.10+**
- **Node.js** + **npm** (for frontend)
- **Docker** + **docker-compose** (optional for full containerization)

### Backend (FastAPI)

1. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Configure environment:
   ```bash
   cp .env.example .env
   # Edit .env and insert valid API keys
   ```
4. Launch API:
   ```bash
   uvicorn backend.main:app --reload --port 8000
   ```

### Frontend (React + Vite)

1. From project root:
   ```bash
   cd frontend
   npm install
   ```
2. Run development server:
   ```bash
   npm run dev
   ```

The frontend will be served at `http://localhost:5173`.

---

## Using Docker

To run both backend and frontend together:

```bash
cp .env.example .env   # add your API keys
docker-compose up --build
```

The application (UI + API) will be available at `http://localhost:8000`.

---

## Coding Standards

- **Python**: Follow [PEP8](https://peps.python.org/pep-0008/). Use `black` for formatting and `flake8` for linting.
- **JavaScript/TypeScript**: Use `eslint` and `prettier`.
- Include inline comments where logic is complex or orchestration is non-obvious.
- Write meaningful commit messages (e.g. `fix: quorum logic rounding error`).

---

## Testing

### Backend

```bash
pytest tests/
```

### Frontend

```bash
cd frontend
npm test
```

Ensure all tests pass before submitting PRs.

---

## Submitting Changes

1. Add and commit:
   ```bash
   git add .
   git commit -m "short but clear description"
   ```
2. Push your branch:
   ```bash
   git push origin feature/your-feature-name
   ```
3. Open a Pull Request via GitHub. Describe your change clearly and reference any related issues.

---

## Community Guidelines

- **Respect dissent** — this project is built around diversity of thought, even among machines.
- **Keep it constructive** — suggest improvements with context and intent.
- **Use issues** — report bugs, propose ideas, or ask questions via GitHub Issues.

---

## License

By contributing, you agree that your contributions will be licensed under the project's terms.

- [LICENSE.md](LICENSE.md) (custom license)
- [commercial_license.md](commercial_license.md) (for use terms)

---

For more context, refer to:
- [`README.md`](./README.md)
- [`agents.md`](./docs/agents.md)
- [`quorum_logic.md`](./docs/quorum_logic.md)
