# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

VRChat tool suite sold on BOOTH marketplace. Python-based collection of OSC utilities, AI-powered asset tools, and a thumbnail generator. Target: Japanese VRChat users, products priced 100-500 yen.

## Running Tools

Each tool is a standalone Python script run directly:

```bash
# OSC tools (lightweight, no GPU)
python tools/osc-timer/main.py countdown 5:00
python tools/osc-timer/main.py stopwatch
python tools/osc-timer/main.py pomodoro --work 25 --break-time 5
python tools/chatbox-decorator/main.py interactive
python tools/omikuji-bot/main.py

# AI tools (GPU required)
pip install -r requirements-upscaler.txt
python tools/texture-upscaler/upscale.py input.png -o output/

pip install -r requirements-footstep.txt
python tools/footstep-generator/generate.py --surface wood --variations 3

# Thumbnail generator
pip install -r requirements.txt
python tools/thumbnail-generator/generate.py --title "ツール名" --theme purple
```

There is no unified build system, test suite, or linter configured.

## Architecture

### Directory Layout

- `tools/common/` — Shared libraries used by multiple tools
- `tools/<tool-name>/` — Each tool is self-contained with `main.py` (or similar) + `README.md`
- `docs/` — Product planning and business strategy

### Shared Libraries (`tools/common/`)

- **`osc_client.py`** — VRChat OSC wrapper over `python-osc`. Sends chatbox text, typing indicators, and avatar parameters to `127.0.0.1:9000`.
- **`gpu_utils.py`** — GPU detection for NVIDIA CUDA and AMD ROCm with CPU fallback. Used by texture-upscaler and footstep-generator.

### Tool Categories

**OSC Tools** (no GPU, use `requirements.txt`): osc-timer, chatbox-decorator, omikuji-bot. All communicate with VRChat via OSC protocol on UDP localhost:9000. Two patterns: chatbox text display and avatar parameter floats (0.0-1.0).

**AI Tools** (GPU required, separate requirements files): texture-upscaler (Real-ESRGAN, 2-4GB VRAM), footstep-generator (Stable Audio Open, 8GB+ VRAM). Both support NVIDIA CUDA and AMD ROCm. AMD requires fp32 precision to avoid NaN issues.

**Utility**: thumbnail-generator creates 620x620px BOOTH marketplace thumbnails with Pillow.

### Key Patterns

- Tools use `sys.path` manipulation to import from `tools/common/`
- CLI interfaces built with `argparse` subcommands
- Python 3.10+ required (`str | None` union type syntax)
- Deterministic seeding via `hashlib` for reproducible daily results (omikuji)
- Japanese text and Unicode throughout — tools target Japanese VRChat users

## Dependencies

Three separate requirements files to keep lightweight tools from pulling in heavy ML deps:
- `requirements.txt` — Base (python-osc, Pillow)
- `requirements-upscaler.txt` — Real-ESRGAN, OpenCV, PyTorch
- `requirements-footstep.txt` — Stable Audio, PyTorch, torchaudio
