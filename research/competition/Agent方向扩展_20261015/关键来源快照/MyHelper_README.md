<p align="center">
  <img src="assets/myhelper-logo.svg" alt="MyHelper" width="120" />
</p>

<h1 align="center">MyHelper</h1>

<p align="center">
  <strong>Your AI Desktop Co-pilot -- see your screen, point at your UI, guide your workflow.</strong>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11+-blue" alt="Python" />
  <img src="https://img.shields.io/badge/GUI-PyQt6-green" alt="PyQt6" />
  <img src="https://img.shields.io/badge/LLM-OpenAI%20%7C%20Anthropic%20%7C%20Gemini-orange" alt="Multi-Provider" />
  <img src="https://img.shields.io/badge/platform-Windows%20%7C%20Linux%20%7C%20macOS-lightgrey" alt="Platform" />
  <img src="https://img.shields.io/badge/license-MIT-blue" alt="License" />
</p>

---

## What is MyHelper?

MyHelper is a **vision-powered desktop assistant** that captures your screen, sends it to a multimodal LLM, and **physically points** at UI elements with a floating triangle cursor. It's not just a chatbot -- it's an AI that *sees what you see* and *shows you where to click*.

> **The killer feature**: The LLM outputs `[POINT:650,420:Save Button]` tags embedded in its response. MyHelper parses these, denormalizes them to your actual screen coordinates, and smoothly animates an always-on-top triangle cursor to hover over that exact UI element -- with a text bubble explaining what it is. It's like having someone stand behind you and point at your screen.

## Highlights

- **Visual Pointing** -- The LLM analyzes your screenshot and drives an animated cursor to point at buttons, menus, input fields, or any UI element it identifies. No more guessing "which button did it mean?"
- **Multi-Provider** -- Works with OpenAI, Anthropic, and Gemini API formats. Bring your own API key, use a local LM Studio / Ollama / vLLM instance, or connect to any OpenAI-compatible endpoint.
- **Auto-Discovery** -- The connection test doesn't just ping -- it asks the model to self-report its capabilities (vision, reasoning, tools, context window size), then verifies with actual API probes. You get ground-truth capability badges, not guesses.
- **Streaming** -- Responses stream token-by-token with smart buffering (>=4 chars) to keep the UI smooth without excessive Qt signal overhead.
- **Polished UI** -- Glassmorphism design with gradient backgrounds, fade+slide animations on every card, toast notifications, animated page transitions, and a status chip with a breathing pulse. It looks like a premium macOS app, on any platform.
- **Profile Manager** -- Save unlimited provider profiles (name, URL, model, key) and switch between them from a dropdown on the chat page. Everything persists in SQLite with WAL mode.
- **Context Memory** -- Configurable conversation history (0-50 turns) with automatic compaction when approaching the context window limit.
- **Resilient** -- Exponential backoff retry (1s, 5s, 20s, 60s, 120s) on transient failures, with user-visible retry status.
- **Coordinate Calibration** -- Fine-tune X/Y offsets if the model's coordinates are slightly off for your setup.
- **CJK-First** -- Built with Chinese users in mind: CJK font stack, Chinese-first system prompt, fluent Chinese UI. English works equally well.

## How It Works

```
+--------------+     Screenshot (JPEG base64)     +--------------+
|              | --------------------------------> |              |
|  Your Screen |                                  |  Vision LLM  |
|              | <-------------------------------- |              |
+--------------+   Text + [POINT:x,y:label]       +--------------+
                                                   tags embedded
                                                         |
                                                         v
                                                  +--------------+
                                                  |  Triangle    |
                                                  |  Cursor      |
                                                  |  animates    |
                                                  |  to target   |
                                                  +--------------+
```

1. You type a question (e.g., "How do I change the font size in this settings window?")
2. MyHelper captures your screen, resizes to max 1024px wide, encodes as JPEG base64
3. The image + your question + conversation history are sent to your configured LLM
4. The LLM responds with text, and optionally embeds `[POINT:x,y:label]` tags
5. MyHelper strips the tags from the displayed text, renders them as clickable buttons in the chat card
6. The triangle cursor smoothly animates to the screen position, pulses on arrival, and shows a text bubble with the label

## Quick Start

### Prerequisites

- Python **3.11+**
- A multimodal LLM endpoint (vision-capable). Options:
  - **Cloud**: OpenAI (GPT-4o), Anthropic (Claude 3+), Google (Gemini 2.5+)
  - **Local**: [LM Studio](https://lmstudio.ai/), [Ollama](https://ollama.com/), [vLLM](https://docs.vllm.ai/) with a vision model like `qwen2.5-vl`

### Installation

```bash
# Clone
git clone https://github.com/TTxyz/MyHelper.git
cd MyHelper

# Install in editable mode
pip install -e .

# Launch
myhelper
# or: python -m myhelper
```

### Configuration

1. Open MyHelper, switch to the Config tab
2. Fill in your model connection:
   - **API Format** -- `OpenAI` for most endpoints, `Anthropic` for Claude, `Gemini` for Gemini
   - **Base URL** -- e.g., `https://api.openai.com/v1` or `http://127.0.0.1:1234/v1` for LM Studio
   - **Model** -- e.g., `gpt-4o`, `claude-3-5-sonnet`, `qwen2.5-vl-7b`
   - **API Key** -- your key (use `lm-studio` for LM Studio, `ollama` for Ollama)
3. Click **Test Connection** -- MyHelper will probe the model's capabilities
4. Click **Save Settings**
5. Optionally save the profile with **Add Model** for quick switching

## Architecture

```
src/myhelper/
|-- app.py                  # QApplication bootstrap, logging setup
|-- main.py / __main__.py   # Entry points
|-- config.py               # Constants, defaults, provider presets
|-- core/
|   |-- settings_store.py   # Thread-safe SQLite singleton (key-value + profile CRUD)
|   |-- paths.py            # Runtime directory resolution
|-- services/
|   |-- llm_service.py      # LLM API client: multi-provider, streaming, capability probing
|   |-- screen_capture.py   # PIL ImageGrab to JPEG base64
|-- ui/
|   |-- chat_window.py      # MainWindow: chat cards, config panel, custom widget library
|   |-- triangle_cursor.py  # Always-on-top animated pointing cursor
|   |-- workers.py          # QThread workers for non-blocking LLM calls
|-- utils/
    |-- resources.py        # Asset path resolver
```

### Design Decisions

| Decision | Rationale |
|----------|-----------|
| **0-1000 normalized coordinates** | Resolution-independent; works across any screen size |
| **>=4 char streaming buffer** | Reduces Qt signal overhead without visible stutter |
| **Capability probing via LLM self-report + API verification** | Detects vision/reasoning/tools support reliably across unknown models |
| **SQLite with WAL + thread-safe singleton** | Concurrent reads without blocking writes; no external DB server |
| **5-tier exponential backoff** | Handles rate limits and transient failures gracefully |
| **History compaction at 80% threshold** | Keeps context usage predictable; drops oldest turns first |

## Usage Tips

- **Ctrl+Enter** to send a message (or click Send)
- Use **Guide Next Step** to have the AI walk you through a workflow step-by-step with visual pointing
- Toggle **Attach Screenshot** to send questions without a screenshot (text-only mode)
- Enable **Auto Point** for automatic cursor animation through all pointed elements
- Adjust **Offset X/Y** if coordinates are consistently off (rarely needed)
- The cursor follows your mouse at 30fps when idle, switches to smooth animation during AI pointing

## Contributing

Contributions welcome. Areas that would benefit from community help:

- Test suite (pytest + Qt testing)
- macOS-specific screen capture improvements
- Dark mode theme
- Plugin system for custom LLM providers
- Voice input support

## License

MIT (c) [TTxyz](https://github.com/TTxyz)
