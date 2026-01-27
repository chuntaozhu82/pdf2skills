# skills2app Quick Start Guide

Turn your pdf2skills output into a working application in 3 simple steps.

---

## Prerequisites

- Python 3.8+
- A pdf2skills output folder (containing `full_chunks_skus/`)
- API key for SiliconFlow (GLM-4.7)

---

## Step 1: Create Your Working Folder

Create a new folder for your app project:

```bash
mkdir my_app_project
cd my_app_project
```

---

## Step 2: Copy Required Files

Copy the following into your working folder:

### 2.1 Copy Generated Skills (from pdf2skills output)

```bash
# Copy the entire full_chunks_skus folder
cp -r /path/to/your/book_output/full_chunks_skus ./

# This folder contains:
# - router.json          (skill routing information)
# - glossary.json        (domain terminology)
# - generated_skills/    (book-specific skills)
# - skus/                (knowledge units)
```

### 2.2 Copy Fixed Skills (universal document processing)

```bash
# Copy the skills_fixed folder from skills2app
cp -r /path/to/skills2app/skills_fixed ./
```

### Your folder should look like:

```
my_app_project/
├── full_chunks_skus/
│   ├── router.json
│   ├── glossary.json
│   ├── generated_skills/
│   │   └── <skill-name>/SKILL.md
│   └── skus/
└── skills_fixed/
    ├── index.json
    ├── pdf/SKILL.md
    ├── xlsx/SKILL.md
    └── ...
```

---

## Step 3: Run the Chatbot to Create Your Spec

### 3.1 Set Up Environment

Create a `.env` file in skills2app folder (if not exists):

```bash
# In the skills2app directory
cat > .env << 'EOF'
SILICONFLOW_API_KEY=your_api_key_here
SILICONFLOW_BASE_URL=https://api.siliconflow.cn/v1
OUTPUT_LANGUAGE=English
GLM_RATE_LIMIT_SECONDS=3.0
EOF
```

Change `OUTPUT_LANGUAGE=Chinese` for Chinese interface.

### 3.2 Run the Chatbot

```bash
cd /path/to/skills2app
python run_chatbot.py /path/to/my_app_project/full_chunks_skus/router.json
```

### 3.3 Follow the Prompts

The chatbot will guide you through:

1. **Choose Skills**
   - Enter `A` to use ALL skills from the book (recommended)
   - Or select specific domains/skills

2. **Describe Your App**
   - What the app should do
   - Who will use it
   - How often it will be used

3. **Confirm & Generate**
   - Review the summary
   - Generate your spec.json

---

## Output Files

After completing the chatbot, you'll have:

```
my_app_project/
├── full_chunks_skus/
│   ├── router.json           # Skill routing
│   ├── glossary.json         # Domain terms
│   ├── generated_skills/     # Book skills
│   └── specs/                # NEW: Generated specs
│       └── your-app_YYYYMMDD_HHMMSS.json
└── skills_fixed/             # Universal skills
```

---

## What to Do with the Output

The generated files provide everything a coding agent needs to build your app:

| File | Purpose |
|------|---------|
| `spec.json` | App requirements: goals, users, selected skills |
| `router.json` | Skill hierarchy and dependencies |
| `glossary.json` | Domain terminology for context |
| `generated_skills/` | Book-specific skill definitions |
| `skills_fixed/` | Universal I/O skills (PDF, Excel, etc.) |

### Hand off to a Coding Agent

You can now provide these files to Claude Code or another coding agent with instructions like:

> "Build a Python application based on the spec.json. Use the skills defined in generated_skills/ and skills_fixed/. Refer to router.json for skill dependencies and glossary.json for domain terminology."

---

## Quick Tips

### Use All Skills (Recommended)

When the chatbot asks for domain selection, just enter `A`:
```
> A
```

This includes all skills from the book - the simplest way to build a comprehensive app.

### Chinese Interface

Set `OUTPUT_LANGUAGE=Chinese` in `.env` for Chinese prompts.

### Resume if Interrupted

The chatbot doesn't save progress mid-session. If interrupted, just restart and quickly select your options again.

---

## Example Session

```
$ python run_chatbot.py ./my_project/full_chunks_skus/router.json

============================================================
 skills2app - Spec Drafter
============================================================

Hello! I'm here to help you design an application...

**Recommended:**
A. Use ALL Skills (42 skills) - Turn entire book into app (Recommended)

**Or select specific domain:**
1. Chapter 1 - Credit Basics (11 skills)
2. Chapter 2 - Investigation Methods (8 skills)
...

**Quick Start:** Enter 'A' to use all skills from the book (recommended)

> A

## All Skills Selected

Automatically selected all **42** skills from this book.

**What do you want this app to do?**

> Help loan officers assess credit risk and make approval decisions

**Who will use this app?**

> Bank loan officers and risk managers

**How often will this app be used?**
1. Daily
2. Weekly
...

> 1

Let me summarize...

**Application Name:** help-loan-officers-assess-app
**Main Goal:** Help loan officers assess credit risk and make approval decisions
...

Is this correct?
1. Yes, create my specification

> 1

Your application specification has been created!
Saved to: ./my_project/full_chunks_skus/specs/help-loan-officers-assess-app_20250127_143022.json
```

---

## Need Help?

- Type `help` anytime in the chatbot for guidance
- Type `back` to go to the previous step
- Type `quit` to exit

---

## Next Steps

After generating your spec, the next phase (coming soon) will be:

1. **App Generator** - Automatically generate Python code from spec
2. **Runtime Engine** - Execute the generated app with GLM-4.7
3. **Custom Handlers** - Real PDF/Excel processing implementations

For now, use the generated files to manually build your app or hand them to a coding agent.
