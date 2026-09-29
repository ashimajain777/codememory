<div align="center">
  <h1>🧠 CodeMemory</h1>
  <p><b>The AI-Powered Organizational Memory for Technical Debt and Workarounds</b></p>
</div>

---

## 🛑 The Problem
Codebases rot not because of bad code, but because of **lost context**. A developer adds a `HACK` or a temporary workaround to bypass a transient issue (e.g., a third-party API throttling bug). Months later, the API is fixed, but the workaround remains because nobody remembers *why* it was added or is too afraid to remove it. 

**Technical debt becomes permanent because organizational memory is volatile.**

## 💡 The Solution
**CodeMemory** is an end-to-end AI agent system that acts as the long-term memory for your engineering organization. It tracks workarounds from the moment they are merged to the moment they can be safely removed, surfacing the context exactly where developers need it.

CodeMemory doesn't just find `TODO`s; it **understands them, tracks them across file refactors, clusters them to find root causes, and challenges developers to remove them when their conditions are met.**

---

## ✨ Key Features

### 1. 🛡️ The "Reality Checker" (Automated PR Reviews)
When a developer opens a PR, CodeMemory’s AI persona (powered by Groq) analyzes the changes. 
- If a new hack is added, it asks: *"What is the exact condition for removing this?"*
- If the PR resolves the condition for an *existing* hack, the Reality Checker comments on the PR, suggesting the developer delete the obsolete workaround.

### 2. 🧩 Contextual IDE Hover Cards (`vscode-ext/`)
Developers don't need to dig through Jira or `git blame` to understand weird code. CodeMemory provides a native VS Code extension. Hovering over a tracked workaround displays:
- **What it is** and **Why it exists**
- **The exact condition required to remove it**
- **Risk level** and **Status** (Open, Condition Met, Retired)

### 3. 📊 Org-Level Debt Ledger & Root-Cause Clustering (`web/`)
A beautiful, interactive web dashboard that visualizes your codebase's active hacks over time. 
- **Smart Tracking**: CodeMemory tracks hacks even if the file is renamed or the code is moved around.
- **Root-Cause Detection**: If it detects multiple hacks related to the same underlying issue (e.g., *"Third Stripe throttling workaround detected"*), it flags a systemic root cause to engineering leadership.

### 4. 🔒 Enterprise Privacy Gate (`privacy_gate.py`)
Security first. CodeMemory includes a built-in privacy gate with on-prem/local-only execution modes that redacts sensitive PII or proprietary secrets before any data touches the LLM.

---

## 🏗️ Architecture & How It Works

CodeMemory is built with a modular, agentic architecture:
1. **Ingestion Engine (`ingest.py`)**: Processes Git commits chronologically. It uses **Hindsight** for semantic memory recall and **Groq (`qwen/qwen3.8-27b`)** for lightning-fast LLM classification.
2. **Scanner (`scan_repo.py`)**: Crawls existing repositories to identify undocumented technical debt using heuristics and LLM validation.
3. **Personas (`personas.py`)**: Specialized system prompts (`REALITY_CHECKER`, `ONBOARDING_ENGINEER`) that dictate how the AI interacts with the codebase.
4. **Client Interfaces**: 
   - GitHub PR Review Action (`tools/pr_comment.py`)
   - VS Code Extension (`vscode-ext/extension.js`)
   - Dashboard (`web/app.js`)

---

## 🚀 Getting Started

### Prerequisites
- Python 3.10+
- Node.js (for the web dashboard and VS Code extension)
- A Groq API Key
- Hindsight Memory Backend

### 1. Environment Setup
Clone the repository and set up your environment:
```bash
cp .env.example .env
# Edit .env with your GROQ_API_KEY and HINDSIGHT_BASE_URL
pip install -r requirements.txt
```

### 2. Run the Ingestion Pipeline
To analyze a repository and generate the memory graph:
```bash
python codememory/ingest.py 
```
*(Check out the `sample_repo/` included in the project for a rich, pre-built synthetic history of a payments service dealing with Stripe API throttling!)*

### 3. Launch the Dashboard
```bash
cd codememory/web
# Serve the static files
python -m http.server 8000
```
Visit `http://localhost:8000` to explore the Debt Ledger.

### 4. Install the VS Code Extension
Open the `codememory/vscode-ext` folder in VS Code, press `F5` to launch the Extension Development Host, and open the `sample_repo` to see live hover cards over tracked hacks!

---

## 🏆 Why CodeMemory 
Most AI coding tools focus on *writing* code faster. **CodeMemory focuses on *maintaining* code better.** By integrating seamlessly into the developer's existing workflow (IDE and PRs) and using semantic AI memory to outlast human turnover, CodeMemory solves a multi-billion dollar enterprise problem: the silent accumulation of permanent technical debt.
