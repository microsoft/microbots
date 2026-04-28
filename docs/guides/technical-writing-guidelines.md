# Technical Writing Guidelines

This guide defines the writing standards for all Microbots documentation — tutorials, guides, API references, and blog posts. Following these guidelines ensures that every article is consistent in quality, tone, and structure.

*This guide is inspired by and adapted from [DigitalOcean's Technical Writing Guidelines](https://www.digitalocean.com/community/tutorials/digitalocean-s-technical-writing-guidelines), licensed under [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/).*

There are four sections in this guide:

- **Style**, our high-level approach to writing technical content
- **Structure**, an explanation of our layout and content expectations
- **Formatting**, a Markdown reference for MkDocs Material
- **Terminology**, a guide to common terms and word usage

Read the **Style** and **Structure** sections in their entirety before you begin writing. Use the **Formatting** and **Terminology** sections as references while drafting.

---

## Style

Microbots documentation is written for developers and engineers who want to learn, build, and automate with confidence. Every article should be:

- Comprehensive and written for all experience levels
- Technically detailed and correct
- Practical, useful, and self-contained
- Friendly but formal

### Comprehensive and Written for All Experience Levels

Articles should be as clear and detailed as possible without making assumptions about the reader's background knowledge.

Explicitly include every command a reader needs — from creating a virtual environment to the final working setup. Provide all explanations and background information the reader needs to understand the tutorial. The goal is for readers to **learn the concepts**, not just copy and paste code.

**Avoid** words like "simple," "straightforward," "easy," "simply," "obviously," and "just." These words make assumptions about the reader's knowledge. A reader who hears something is "easy" may be frustrated when they encounter an issue. Instead, encourage readers by providing the explanations they need to be successful.

### Technically Detailed and Correct

Articles must be technically accurate and follow industry best practices. Do not provide large blocks of configuration or code and ask readers to paste it, trusting that it works and is safe. Provide all the details necessary for readers to understand and trust the article.

- Every command should have a detailed explanation, including options and flags as necessary.
- Every block of code should be followed by prose that describes what it does and why it works that way.
- When you ask the reader to execute a command or modify a file, first explain what it does and why.

**Authors must test their tutorials** by following them exactly as written on a fresh environment to ensure accuracy and identify missing steps.

### Practical, Useful, and Self-contained

Once a reader has finished an article, they should have installed, built, or set up something from start to finish. Emphasize a practical approach — at the end of an article, the reader should have a usable environment or example to build upon.

- Link to existing Microbots documentation as prerequisites that readers should complete before beginning the tutorial.
- Link to other Microbots articles for additional information within the body of the tutorial.
- Only send readers to external sites when there is no existing Microbots article and the information cannot be summarized inline.

### Friendly but Formal

Articles aim for a friendly but formal tone. This means articles do not include jargon, memes, excessive slang, emoji, or jokes. We write for a global audience, so aim for a tone that works across language and cultural boundaries.

- **Do not** use the first person singular (e.g., "I think …").
- **Use** the second person (e.g., "You will configure …") to keep the focus on the reader and what they will accomplish.
- In some cases, use the first person plural (e.g., "We will examine …").

Use motivational language focused on outcomes. For example, instead of "You will learn how to install Microbots," write "In this tutorial, you will install Microbots and create your first bot." This approach motivates the reader and focuses on the goal.

---

## Structure

Microbots articles have a consistent structure that includes an introduction, prerequisites, and a conclusion. The specific structure depends on the type of article.

### Procedural Tutorials (Step-by-step)

```
# Title (H1)
### Introduction (H3)
## Prerequisites (H2)
## Step 1 — Doing the First Thing (H2)
## Step 2 — Doing the Next Thing (H2)
…
## Step n — Doing the Last Thing (H2)
## Conclusion (H2)
```

### Conceptual Articles

```
# Title (H1)
### Introduction (H3)
## Prerequisites (optional) (H2)
## Subtopic 1 (H2)
## Subtopic 2 (H2)
…
## Subtopic n (H2)
## Conclusion (H2)
```

### Title

Think carefully about what the reader will accomplish by following your tutorial. Include the **goal** of the tutorial in the title, not just the tools involved. Keep titles under 60 characters when possible.

**Good:** "Microbots : Introduction, Installation Guide and Creating Your First MicroBot"

The title should communicate both the tool and the outcome.

### Introduction

The introduction is typically one to three paragraphs. Its purpose is to motivate the reader, set expectations, and summarize what they will do. Answer these questions:

1. **What** is the tutorial about? What software is involved?
2. **Why** should the reader learn this? What are the practical benefits?
3. **What will the reader do** in this tutorial? Be specific.
4. **What will the reader have accomplished** when finished? What new skills will they have?

Keep the focus on the reader. Use "you will configure" rather than "we will learn how to."

### Prerequisites

The Prerequisites section spells out exactly what the reader should have or do before starting. Format it as a **checklist** the reader can follow:

```markdown
## Prerequisites

To complete this tutorial, you will need:

- **Python 3.10+** installed on your machine. See the [Pre-requisites](../getting-started/prerequisites.md) guide.
- **Docker** installed and running. See the [Pre-requisites](../getting-started/prerequisites.md#docker) guide.
- A working **Azure OpenAI** API key, endpoint, and deployed model. See the [Microbot Installation](../getting-started/installation-guide.md) guide.
```

Each prerequisite must link to an existing Microbots article or official documentation. Be specific — "Familiarity with Python" is not actionable; instead write "Familiarity with Python virtual environments. See [Python venv documentation](https://docs.python.org/3/library/venv.html)."

### Steps

Steps are the core of your tutorial. Each step:

- Begins with a **level 2 heading** in the format: `## Step N — Gerund Phrase`
- Starts with an introductory sentence describing what the reader will do and why
- Contains commands, code listings, files, and explanations

**Example:**

```markdown
## Step 1 — Setting Up the Project Directory

In this step, you will create a project folder and initialize a Python virtual environment. This isolates your dependencies from the system Python installation.
```

### Transitions

Each step should end with a brief closing sentence that:

1. Summarizes what the reader accomplished
2. Introduces what they will do next

**Example:**

> You have now installed the Microbots package and configured your LLM credentials. In the next step, you will create a sample project with a deliberate error for the bot to analyze.

Vary the language so transitions do not feel repetitive.

### Conclusion

The conclusion summarizes what the reader accomplished. Use "you configured" or "you built" rather than "we learned how to."

Include:

- A brief recap of what was accomplished
- Suggestions for what the reader can do next
- Links to related Microbots tutorials or API references
- Links to external resources where appropriate

---

## Formatting

Microbots documentation is written in Markdown and rendered with MkDocs Material. Follow these formatting conventions.

### Headers

| Level | Usage |
|-------|-------|
| H1 (`#`) | Title only — one per article |
| H2 (`##`) | Major sections: Introduction, Prerequisites, Steps, Conclusion |
| H3 (`###`) | Subsections within a step or section |
| H4 (`####`) | Use sparingly; prefer restructuring into multiple steps instead |

For procedural tutorials, step headers should include step numbers followed by an em dash (—) and use the gerund (-ing form):

```markdown
## Step 1 — Installing Microbots
```

### Line-level Formatting

**Bold** text should be used for:

- Visible GUI text
- Hostnames and usernames
- Term lists
- Emphasis when changing context (e.g., switching to a different terminal)

*Italics* should only be used when introducing technical terms. For example: *The Microbots framework uses OverlayFS for copy-on-write filesystem protection.*

`Inline code` formatting should be used for:

- Command names, like `pip`
- Package names, like `microbots`
- File names and paths, like `~/.env`
- Example URLs, like `https://your-resource-name.openai.azure.com`
- Ports, like `:8000`
- Key presses, in ALL CAPS, like `ENTER`. For simultaneous keys, use `CTRL+C`

### Code Blocks

Code blocks should be used for:

- Commands the reader needs to execute
- Files and scripts
- Terminal output
- Interactive dialogues

Always include a **title** on code blocks using the `title` attribute:

````markdown
```bash title="Terminal"
pip install microbots
```
````

For file contents, use the filename as the title:

````markdown
```python title="log_analysis_bot.py" linenums="1"
from microbots import LogAnalysisBot
```
````

#### Explaining Commands

Every command should be preceded by a description of what it does. After the command, provide additional details about arguments and flags:

````markdown
Execute the following command to create a Python virtual environment:

```bash title="Terminal"
python -m venv .venv
```

The `-m venv` flag tells Python to run the `venv` module, which creates an isolated virtual environment in the `.venv` directory.
````

#### Showing Output

Separate command output from the command itself using a distinct code block with an explanatory sentence:

````markdown
Run the bot:

```bash title="Terminal"
python log_analysis_bot.py
```

The program's output will print to the screen:

```text title="Output"
Root cause identified from /var/log/build.log: ...
```
````

#### Highlighting Changes

When modifying an existing file, show the relevant section and explain what changed and why. Use comments or callouts to draw attention to the specific lines.

### Admonitions

Use MkDocs Material admonitions for notes, warnings, and tips:

```markdown
!!! note
    For advanced authentication options, see the Authentication Guide.

!!! warning
    This action will delete all data in the container.

!!! tip
    You can use `logging.basicConfig(level=logging.INFO)` to see step-by-step bot output.
```

Use them sparingly. Reserve `warning` for actions that could cause data loss or security issues. Use `tip` for helpful but optional information.

### Images

When including images:

- Use descriptive alt text for screen reader accessibility
- Use the `.png` file format
- Place images in the `docs/images/` directory under a subfolder named after the article
- Keep image height as short as possible

```markdown
![Architecture diagram showing Docker container isolation](../images/microbots-safety-first-ai-agent/architecture.png)
```

### Navigation Cards

Use navigation cards (rather than plain-text links) for Previous/Next links. Place the **Previous** card at the top of the article and the **Next** card at the bottom:

```html
<!-- Previous card at the top -->
<div class="nav-cards" markdown>
<a href="../previous-page/" class="nav-card nav-card--prev">
<div class="nav-card-label">&larr; Previous</div>
<div class="nav-card-title">Previous Page Title</div>
</a>
</div>

<!-- Next card at the bottom -->
<div class="nav-cards" markdown>
<a href="../next-page/" class="nav-card nav-card--next">
<div class="nav-card-label">Next &rarr;</div>
<div class="nav-card-title">Next Page Title</div>
</a>
</div>
```

For articles that have prerequisites the reader should complete first, add prerequisite cards at the top alongside the Previous card:

```html
<div class="nav-cards" markdown>
<a href="../previous-page/" class="nav-card nav-card--prev">
<div class="nav-card-label">&larr; Previous</div>
<div class="nav-card-title">Previous Page Title</div>
</a>
<a href="../prerequisites/" class="nav-card nav-card--prereq">
<div class="nav-card-label">Pre-requisite</div>
<div class="nav-card-title">Pre-requisites</div>
</a>
</div>
```

---

## Terminology

### Users and Variables

- Use `your-resource-name` as the default placeholder for Azure resource names.
- Use `your-api-key-here` as the default placeholder for API keys.
- Always highlight variables that readers need to change.

### Bot Names

Use the official class name with proper capitalization:

| Correct | Incorrect |
|---------|-----------|
| `LogAnalysisBot` | Log Analysis Bot, loganalysisbot |
| `ReadingBot` | Reading Bot, readingbot |
| `WritingBot` | Writing Bot, writingbot |
| `BrowsingBot` | Browsing Bot, browsingbot |
| `AgentBoss` | Agent Boss, agentboss |
| `CopilotBot` | Copilot Bot, copilotbot |

### LLM Providers

Use the provider/model format when referencing models:

- `azure-openai/gpt-5-swe-agent`
- `anthropic/claude-sonnet-4-20250514`
- `ollama/llama3`

### Permission Labels

Use ALL CAPS for permission labels: `READ_ONLY`, `READ_WRITE`.

### Software and Tools

- Use the official capitalization from the project's website: **Docker**, **Python**, **MkDocs**, **TypeScript**.
- Link to the software's home page the first time it is mentioned.

### Technical Best Practices

- Always test tutorials on a fresh environment before submitting.
- Use the `--8<--` snippet syntax for including example files rather than duplicating code.
- Keep code examples minimal and focused on the concept being taught.
- Ensure all external links are valid at the time of writing and add the External Links Disclaimer admonition when external links are present.
