# GameLQA

![License](https://img.shields.io/badge/license-MIT-blue.svg)
![Next.js](https://img.shields.io/badge/Next.js-14-black)
![TypeScript](https://img.shields.io/badge/TypeScript-5-blue)

**Vision AI game localization QA — detect UI text errors from screenshots and video.**

Upload game screenshots or a video clip. Vision models identify untranslated strings, truncation, encoding errors, and terminology issues. Export a structured LQA report as CSV.

---

## Features

- 🖼️ **Screenshot analysis** — drag-and-drop PNG / JPG / WEBP
- 🎬 **Video frame extraction** — upload video, set interval (e.g. every 5s), frames extracted in-browser via Canvas
- 📄 **Reference string CSV** — upload `source,target` pairs to detect untranslated content
- 🏷️ **Severity classification** — Critical / Major / Minor per issue
- 📋 **Structured LQA report** — export full CSV with frame, severity, category, description, suggestion
- ☁️ **OpenAI-compatible + DashScope** — `gpt-4o`, `qwen-vl-max`, or any vision-capable model
- 🔷 **Anthropic Claude** — `claude-3-5-sonnet` recommended for vision tasks
- ⚡ **Local Ollama** — use `llava:13b`, `minicpm-v`, or any local vision model

## Issue Categories

| Category | Description |
|----------|-------------|
| Untranslated | Source language text still visible in UI |
| Truncation | Text cut off at UI boundaries |
| Overflow | Text extends outside UI element |
| Encoding/Font | Garbled or missing characters |
| Terminology | Wrong term per glossary |
| Fluency | Grammar or naturalness issues |
| Placeholder | Developer string or variable leaked |
| Reference Mismatch | Differs from provided reference string |

## Quick Start

```bash
git clone https://github.com/Grayson0130/gamelqa.git
cd gamelqa
npm install
npm run dev
# → http://localhost:3001
```

## Supported Vision Providers

| Mode | Provider | Example model |
|------|----------|--------------|
| ⚡ Local | Ollama | `llava:13b`, `minicpm-v` |
| ☁️ OpenAI fmt | OpenAI | `gpt-4o` |
| ☁️ OpenAI fmt | DashScope | `qwen-vl-max` |
| 🔷 Anthropic | Claude | `claude-3-5-sonnet-20241022` |

## Reference CSV Format

```csv
source,target
"ATTACK","攻撃"
"MENU","メニュー"
```

## Tech Stack

Next.js 14 · TypeScript · openai SDK · @anthropic-ai/sdk · Canvas API · papaparse

## License

MIT © [Jinhui Zhao](https://github.com/Grayson0130)
