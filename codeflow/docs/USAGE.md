# CodeFlow Agent - Comprehensive Usage Guide

## 📖 Table of Contents
1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Installation & Configuration](#installation--configuration)
4. [CLI Commands Reference](#cli-commands-reference)
5. [Agent Capabilities](#agent-capabilities)
6. [Token Optimization: Diff Protocol](#token-optimization-diff-protocol)
7. [Advanced Workflows](#advanced-workflows)
8. [Troubleshooting](#troubleshooting)

---

## Overview

**CodeFlow Agent** is an autonomous multi-agent AI system that orchestrates entire software development workflows. Unlike traditional coding assistants that wait for prompts, CodeFlow proactively analyzes, plans, implements, tests, reviews, and deploys code changes through a collaborative team of specialized AI agents.

### Key Features
- **9 Specialized Agents**: Architect, Planner, Developer, QA, DevOps, Reviewer, Refactor, Monitor, Base
- **Token-Efficient**: Uses diff-only generation and structured state objects to reduce token usage by ~90%
- **Autonomous Operation**: Can run continuously to monitor and fix issues without human intervention
- **Groq-Powered**: Optimized for fast, cost-effective inference using Groq's LLM API
- **Safe Execution**: Fuzzy patch matching and self-correction loops prevent code corruption

---

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                     CodeFlow Orchestrator                        │
├─────────────────────────────────────────────────────────────────┤
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ PlannerAgent │→ │ Developer    │→ │ Reviewer     │          │
│  └──────────────┘  │   Agent      │  │   Agent      │          │
│                    └──────────────┘  └──────────────┘          │
│                           ↓                    ↓                │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ Architect    │← │ Consensus    │← │ QA Agent     │          │
│  │   Agent      │  │   Loop       │  │              │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
│                           ↓                                    │
│  ┌──────────────┐  ┌──────────────┐  ┌──────────────┐          │
│  │ DevOps       │← │ Refactor     │← │ Monitor      │          │
│  │   Agent      │  │   Agent      │  │   Agent      │          │
│  └──────────────┘  └──────────────┘  └──────────────┘          │
├─────────────────────────────────────────────────────────────────┤
│                    Shared Knowledge Graph                        │
│              (NetworkX + Vector Index + State Store)             │
└─────────────────────────────────────────────────────────────────┘
```

### Core Components

| Component | Purpose |
|-----------|---------|
| **WorkflowEngine** | Orchestrates agent execution order and handles consensus loops |
| **KnowledgeGraph** | Maintains codebase relationships, file dependencies, and change history |
| **ConsensusLoop** | Enables iterative debate between agents when validation fails |
| **DiffProtocol** | Generates and applies unified diffs instead of full files |
| **AgentState** | Structured Pydantic models for efficient state handoffs |

---

## Installation & Configuration

### Prerequisites
- Python 3.10+
- Groq API key (or Anthropic/OpenAI as fallback)
- Git installed for version control features

### Step 1: Install Dependencies
```bash
cd codeflow
pip install -r requirements.txt
```

### Step 2: Configure Environment
Copy the example environment file and add your API keys:
```bash
cp .env.example .env
```

Edit `.env`:
```ini
# LLM Configuration (Default: Groq)
LLM_PROVIDER=groq
LLM_MODEL=llama-3.1-70b-versatile
GROQ_API_KEY=your_groq_api_key_here

# Optional: Fallback providers
ANTHROPIC_API_KEY=your_anthropic_key
OPENAI_API_KEY=your_openai_key

# Feature Flags
ENABLE_CONSENSUS_LOOP=true
ENABLE_DIFF_PROTOCOL=true
MAX_RETRY_ATTEMPTS=3

# Monitoring
LOG_LEVEL=INFO
ENABLE_METRICS=true
```

### Step 3: Verify Installation
```bash
python -m codeflow --version
codeflow status
```

---

## CLI Commands Reference

### Global Options
| Option | Description | Default |
|--------|-------------|---------|
| `--project` | Path to project root | Current directory |
| `--verbose` | Enable debug logging | `false` |
| `--config` | Custom config file path | `.env` |
| `--dry-run` | Simulate without writing files | `false` |

### Command: `init`
Initialize CodeFlow in a new or existing project.
```bash
codeflow init [--force]
```
- Creates `.codeflow/` directory with configuration
- Analyzes existing codebase structure
- Builds initial knowledge graph

### Command: `analyze`
Perform deep static analysis without making changes.
```bash
codeflow analyze [--depth=shallow|deep] [--output=json|markdown]
```
**Options:**
- `--depth`: Analysis depth (`shallow` = metrics only, `deep` = full AST parsing)
- `--output`: Output format

**Example:**
```bash
codeflow analyze --depth=deep --output=markdown > analysis_report.md
```

### Command: `plan`
Generate a step-by-step implementation plan for a feature or fix.
```bash
codeflow plan "Implement user authentication with JWT"
```
**Output:** Structured plan with tasks, dependencies, and estimated complexity.

### Command: `execute`
Execute a task using the full agent pipeline.
```bash
codeflow execute "Add rate limiting to API endpoints" [--agents=Developer,Reviewer,QA]
```
**Options:**
- `--agents`: Comma-separated list of agents to involve
- `--consensus`: Enable iterative debate loop on failures
- `--max-iterations`: Maximum consensus loop iterations (default: 3)

**Example with consensus:**
```bash
codeflow execute "Refactor database connection pooling" --consensus --max-iterations=5
```

### Command: `review`
Automated code review of current changes or a specific PR.
```bash
codeflow review [--path=src/] [--strict]
```
**Options:**
- `--path`: Specific directory or file to review
- `--strict`: Enforce all style guides and security rules

### Command: `refactor`
Automatically detect and fix code smells.
```bash
codeflow refactor [--pattern=extract_method|inline_variable|rename] [--target=src/]
```
**Patterns:**
- `extract_method`: Identify duplicate code blocks and extract functions
- `inline_variable`: Simplify unnecessary intermediate variables
- `rename`: Standardize naming conventions

### Command: `test`
Generate and run tests for specified modules.
```bash
codeflow test [--generate] [--run] [--coverage]
```
**Options:**
- `--generate`: Create new test files
- `--run`: Execute existing tests
- `--coverage`: Generate coverage report

### Command: `deploy`
Create deployment artifacts and pipelines.
```bash
codeflow deploy [--platform=github_actions|gitlab_ci|aws] [--dry-run]
```
**Platforms:**
- `github_actions`: Generate `.github/workflows/ci.yml`
- `gitlab_ci`: Generate `.gitlab-ci.yml`
- `aws`: Generate CloudFormation/Terraform templates

### Command: `monitor`
Start continuous monitoring daemon.
```bash
codeflow monitor [--interval=60] [--alerts=email|slack]
```
**Options:**
- `--interval`: Check interval in seconds
- `--alerts`: Notification channel

### Command: `status`
Show current project health and agent activity.
```bash
codeflow status [--json]
```

---

## Agent Capabilities

### 1. ArchitectAgent
**Purpose**: High-level system design and technology decisions.
- ✅ Generate architecture diagrams (Mermaid, DOT, PlantUML)
- ✅ Evaluate technology stacks for specific requirements
- ✅ Identify architectural anti-patterns
- ✅ Plan microservice boundaries
- ✅ Assess technical debt impact

**Use Case**: 
```bash
codeflow execute "Design event-driven architecture for notification system" --agents=Architect
```

### 2. PlannerAgent
**Purpose**: Break down complex tasks into actionable steps.
- ✅ Task decomposition with dependency mapping
- ✅ Effort estimation
- ✅ Risk identification
- ✅ Resource allocation planning

### 3. DeveloperAgent
**Purpose**: Implement features and fixes.
- ✅ Generate production-ready code
- ✅ Follow existing code style
- ✅ Handle edge cases
- ✅ Write inline documentation

**Token Optimization**: Outputs only unified diffs, not full files.

### 4. QAAgent
**Purpose**: Ensure code quality and correctness.
- ✅ Generate unit, integration, and E2E tests
- ✅ Perform static analysis
- ✅ Detect security vulnerabilities (SQLi, XSS, etc.)
- ✅ Validate requirements coverage

### 5. DevOpsAgent
**Purpose**: CI/CD and infrastructure automation.
- ✅ Create pipeline configurations
- ✅ Generate Dockerfiles and Kubernetes manifests
- ✅ Set up monitoring dashboards
- ✅ Automate rollback procedures

### 6. ReviewerAgent
**Purpose**: Code review and style enforcement.
- ✅ Check adherence to PEP8/ESLint/etc.
- ✅ Identify complexity hotspots
- ✅ Suggest performance improvements
- ✅ Validate test coverage

### 7. RefactorAgent
**Purpose**: Improve code maintainability.
- ✅ Detect code smells (long methods, god classes)
- ✅ Apply refactoring patterns safely
- ✅ Reduce cyclomatic complexity
- ✅ Eliminate duplication

### 8. MonitorAgent
**Purpose**: Continuous system health tracking.
- ✅ Track error rates and latency
- ✅ Analyze log patterns
- ✅ Detect anomalies
- ✅ Trigger auto-remediation

### 9. BaseAgent
**Purpose**: Foundation class for all agents.
- Provides common utilities (diff generation, state management)
- Enforces standardized interfaces

---

## Token Optimization: Diff Protocol

CodeFlow implements a revolutionary **Diff-Only Protocol** to minimize token consumption while maximizing output quality.

### How It Works

#### Traditional Approach (High Token Usage)
```
Agent Input: [Full file content - 500 lines]
Agent Output: [Entire modified file - 500 lines]
Total Tokens: ~1000 per file
```

#### CodeFlow Diff Protocol (Low Token Usage)
```
Agent Input: [Relevant context ±5 lines around change]
Agent Output: [Unified diff - 20 lines]
@@ -45,7 +45,9 @@
 def calculate_total(items):
     total = 0
     for item in items:
-        total += item.price
+        if item.is_taxable:
+            total += item.price * 1.08
+        else:
+            total += item.price
     return total
Total Tokens: ~50 per file (95% reduction)
```

### Implementation Details

1. **Lazy Context Loading**: Only loads file sections surrounding the target change area.
2. **Fuzzy Patch Matching**: Applies diffs even if line numbers shift slightly due to concurrent edits.
3. **Self-Correction Loop**: Automatically validates generated diffs before returning; regenerates if application fails.
4. **Structured State Objects**: Agents communicate via compact JSON state rather than verbose natural language.

### Configuration
```ini
# Enable diff protocol (recommended)
ENABLE_DIFF_PROTOCOL=true

# Context window size (lines before/after change)
DIFF_CONTEXT_LINES=5

# Max retries for failed diff application
DIFF_MAX_RETRIES=3
```

---

## Advanced Workflows

### Workflow 1: Autonomous Feature Development
Complete feature implementation from description to merged PR.

```bash
# 1. Initialize and analyze
codeflow init
codeflow analyze --depth=deep

# 2. Plan the feature
codeflow plan "Add OAuth2 login with Google provider" > plan.json

# 3. Execute with full pipeline
codeflow execute "Implement OAuth2 Google login" \
  --agents=Developer,QAAgent,ReviewerAgent \
  --consensus \
  --max-iterations=3

# 4. Run generated tests
codeflow test --run --coverage

# 5. Create deployment pipeline
codeflow deploy --platform=github_actions
```

### Workflow 2: Technical Debt Reduction Sprint
Systematic refactoring of legacy codebase.

```bash
# 1. Identify code smells
codeflow analyze --depth=deep --output=json > smells.json

# 2. Auto-refactor high-priority issues
codeflow refactor --pattern=extract_method --target=src/legacy/
codeflow refactor --pattern=inline_variable --target=src/utils/

# 3. Validate with strict review
codeflow review --strict --path=src/legacy/

# 4. Generate regression tests
codeflow test --generate --path=src/legacy/
```

### Workflow 3: Incident Response Automation
Automatic detection and fixing of production issues.

```bash
# Start monitoring daemon
codeflow monitor --interval=30 --alerts=slack &

# When alert triggers, auto-execute fix
codeflow execute "Fix memory leak in image processing worker" \
  --consensus \
  --max-iterations=5 \
  --agents=Developer,QAAgent,DevOpsAgent
```

### Workflow 4: Multi-Agent Debate (Consensus Loop)
Complex problems requiring multiple perspectives.

```bash
codeflow execute "Optimize database queries for high-traffic endpoint" \
  --agents=Architect,Developer,Reviewer,DevOps \
  --consensus \
  --max-iterations=10
```

**Process Flow:**
1. Architect proposes indexing strategy
2. Developer implements query changes
3. Reviewer identifies potential race conditions
4. DevOps suggests connection pool tuning
5. Loop repeats until all agents approve
6. Final solution applied with comprehensive tests

---

## Troubleshooting

### Common Issues

#### 1. "Failed to apply diff: Line number mismatch"
**Cause**: Concurrent modifications or whitespace differences.
**Solution**: 
- The fuzzy patch matcher should handle this automatically.
- If persistent, increase context lines: `DIFF_CONTEXT_LINES=10`
- Run `codeflow analyze` to refresh knowledge graph.

#### 2. "Rate limit exceeded" (Groq API)
**Cause**: Too many rapid requests.
**Solution**:
- Add delay between requests: `REQUEST_DELAY_MS=1000`
- Upgrade Groq plan or switch to fallback provider.
- Enable response caching: `ENABLE_CACHE=true`

#### 3. "Consensus loop exceeded max iterations"
**Cause**: Agents cannot agree on solution.
**Solution**:
- Increase max iterations: `--max-iterations=10`
- Simplify the task into smaller subtasks.
- Manually review conflict points in logs.

#### 4. "ModuleNotFoundError: No module named 'codeflow'"
**Cause**: Package not installed in current environment.
**Solution**:
```bash
pip install -e /path/to/codeflow
# Or add to PYTHONPATH
export PYTHONPATH=/path/to/codeflow:$PYTHONPATH
```

#### 5. Agents producing hallucinated imports
**Cause**: LLM generating non-existent libraries.
**Solution**:
- Enable strict validation: `ENABLE_IMPORT_VALIDATION=true`
- Use `--strict` flag with execute command.
- ReviewerAgent will catch and reject invalid imports.

### Debug Mode
Enable verbose logging for troubleshooting:
```bash
codeflow execute "..." --verbose
LOG_LEVEL=DEBUG codeflow monitor
```

### Viewing Audit Logs
All agent actions are logged to `.codeflow/logs/`:
```bash
tail -f .codeflow/logs/agent_activity.log
cat .codeflow/logs/consensus_debate_20240403.json
```

---

## Best Practices

1. **Start Small**: Begin with single-file refactors before attempting full-feature development.
2. **Use Consensus Wisely**: Enable `--consensus` only for complex tasks; it increases token usage.
3. **Review Generated Diffs**: Always review critical changes before committing, especially for security-sensitive code.
4. **Keep Knowledge Graph Fresh**: Run `codeflow analyze` after major manual changes.
5. **Set Clear Boundaries**: Use `--target` flags to limit agent scope and prevent unintended modifications.

---

## Contributing

See `CONTRIBUTING.md` for guidelines on adding new agents, tools, or protocols.

## License

MIT License - See `LICENSE` file for details.

## Support

- GitHub Issues: https://github.com/your-org/codeflow/issues
- Documentation: https://codeflow.dev/docs
- Discord Community: https://discord.gg/codeflow
