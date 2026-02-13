# The Weight of Words

A **beautiful, memory‑aware poem generator** built with **Streamlit**, **LangGraph**, and **OpenAI**.

The app generates poems through a multi‑step creative pipeline (Generator - Critic - Reviser), learns from user ratings over time, and optionally personalizes poems using stored *people memory* and *taste preferences*.

---

## 📱 What This App Does

* Generate high‑quality poems from simple prompts
* Improve poems through iterative critique and revision
* Remember people (names, relationships, notes) and reference them naturally
* Learn your taste over time (rhyme preference, length, tone, endings, etc.)
* Offer full creative control via an **Advanced** tab (model, temperature, constraints)
* Run locally **or** on Streamlit Community Cloud with Supabase/Postgres

---

## 🧠 How It Works

1. **Write**

   * You enter a theme, occasion, format, and style
   * Optional memory is injected (people + learned taste)

2. **Generate**

   * The Generator produces an initial poem

3. **Critique**

   * A Critic model evaluates the poem against constraints

4. **Revise**

   * The Reviser improves the poem using the critique

5. **Rate**

   * You rate versions (⭐ 1–5)
   * Ratings update your long‑term taste profile

6. **Improve Again**

   * You can generate additional improved versions while keeping previous ones

This flow is orchestrated using **LangGraph** for reliability and clarity.

---

## 📁 Project Structure

```
.
├── app.py                  # Streamlit UI and main application logic
├── requirements.txt        # Python dependencies
├── .env.example            # Example environment variables
├── .gitignore
│
├── agent/                  # AI agent logic
│   ├── graph.py            # LangGraph definition (Generator → Critic → Reviser)
│   ├── schemas.py          # Pydantic models (PoemRequest, Critique, etc.)
│   └── __init__.py
│
├── core/                   # Core infrastructure
│   ├── config.py           # Environment / secrets loading
│   ├── llm_factory.py      # OpenAI model creation (model, temperature, top_p)
│   ├── orchestrator.py     # High-level generation functions
│   ├── prompt_loader.py   # Loads and validates prompts.yaml
│   ├── safe_call.py        # Error-safe LLM invocation
│   ├── storage.py          # SQLite / Postgres (Supabase) storage layer
│   ├── logging_setup.py    # Structured logging
│   └── __init__.py
│
├── prompts/
│   └── prompts.yaml        # System + user prompts for Generator / Critic / Reviser
│
├── data/                   # Local SQLite database (auto-created)
│
└── .venv/                  # Local virtual environment (not committed)
```

---

## 🧩 Key Files Explained

### `app.py`

* Streamlit UI
* Tabs: **Write**, **People**, **Advanced**
* Collects user input and builds `PoemRequest`
* Displays poem versions, ratings, and memory

### `agent/graph.py`

* Defines the LangGraph workflow
* Nodes:

  * `generate_poem`
  * `criticize_poem`
  * `revise_poem`

### `core/orchestrator.py`

* Public functions:

  * `generate_only`
  * `generate_and_improve`
  * `improve_again`

### `core/storage.py`

* Abstract `Storage` interface
* Implementations:

  * `SQLiteStorage` (local dev)
  * `PostgresStorage` (Supabase / production)

### `prompts/prompts.yaml`

* Centralized prompt templates
* Required blocks:

  * `generator`
  * `critic`
  * `reviser`

---

## 🧠 Memory System

### People Memory

Stored per user:

* Name
* Relationship
* Notes (likes, dislikes, context)

Used to personalize poems naturally (e.g. hobbies, tone sensitivity).

### Taste Profile (Learned)

Updated from ratings:

* Rhyme preference
* Average length
* Reading level tendency
* Preferred ending style

Hidden by default. Viewable via **Advanced → See my taste profile**.

---

## ⚙️ Configuration

### Environment Variables

Required:

```env
OPENAI_API_KEY=your_key_here
```

Optional (for Supabase / Postgres):

```env
DATABASE_URL=postgresql://user:password@host:5432/postgres
```

* Locally: use `.env`
* Streamlit Cloud: use **Secrets** (TOML format)

---

## 🚀 Running Locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
streamlit run app.py
```

---

## ☁️ Deploying to Streamlit Cloud

1. Push code to GitHub
2. Create a Streamlit app
3. Set **Secrets**:

```toml
OPENAI_API_KEY = "sk-..."
DATABASE_URL = "postgresql://..."
```

4. Deploy 🎉

## 🪪 License

This project is licensed under the MIT License.

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

---

**The Weight of Words** is built to feel personal, expressive, and safe — a poetry studio that grows with you.
