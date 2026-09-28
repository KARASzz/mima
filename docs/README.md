# Crypto Canvas

> Visualizable file encryption — "画图即加密"

A demo Python tool that encrypts files (≤10 MB) into single, self-contained PNG
images. The encryption key is derived from a user-drawn trajectory on the complex
plane, and the encryption process intentionally pulls both CPU (multiprocessing +
Argon2id) and GPU (OpenGL fragment shader) to full utilization while a 16×16 pixel
character runs on screen.

The PNG carries everything needed to decrypt: ciphertext encoded as colored
pixels, plus the trajectory, salt, and metadata in PNG `tEXt` chunks. Sharing the
image is sharing the locked file.

## Features

- **Single PNG output** — ciphertext, key material, and visualization in one file
- **Trajectory-based visual cipher** — draw on the complex plane → 256-byte permutation
- **AES-256-GCM + Argon2id** — industrial-strength encryption with intentional CPU stress
- **OpenGL fragment shader window** — GPU pinned at ~60 FPS during encryption
- **Pixel character animation** — 16×16 character runs left (encrypt) / right (decrypt)
- **Lossless HSV encoding** — every byte maps to a unique RGB pixel
- **Trajectory integrity check** — SHA-256 of the trajectory is stored in PNG metadata; tampering is detected on decrypt

---

## ⚠️ macOS Platform Limitations

> **If you are running this on macOS, read this first.**

Both the GPU stress window (OpenGL fragment shader) and the pixel character
animation window (tkinter) **silently no-op on macOS**. The crypto pipeline
itself runs correctly on every platform; only the visual feedback is suppressed
on macOS.

### Why

- macOS AppKit (Cocoa) requires every `NSWindow` to be instantiated on the
  **main thread**.
- Both windows run in **worker threads** so they do not block the encrypt /
  decrypt pipeline.
- On macOS, calling AppKit from a worker thread triggers
  `NSInternalInconsistencyException` — an **uninterceptable C++ exception**
  that crashes the whole process.
- To prevent the crash, the implementer added `sys.platform == "darwin"` guards
  in `crypto/gpu_window.py` and `crypto/runner.py`. When running on macOS, both
  `start()` methods log an info message and return immediately.

### Impact

| Component                     | Linux / Windows | macOS                       |
|-------------------------------|-----------------|-----------------------------|
| Encrypt / decrypt pipeline    | works           | works                       |
| Argon2id CPU stress           | works           | works                       |
| Multiprocessing parallel AES  | works           | works                       |
| OpenGL GPU stress window      | runs            | **skipped (silent no-op)**  |
| Pixel character animation     | runs            | **skipped (silent no-op)**  |
| Trajectory drawing GUI        | runs            | runs (matplotlib backend)   |

On macOS, encrypt / decrypt completes successfully and produces the same output
PNG, but you will **not** see the GPU crunch window or the running pixel
character. On Linux / Windows, every component runs as designed.

### Workarounds (out of scope)

Making the visual feedback work on macOS would require one of:

- Running tkinter / OpenGL on the main thread while crypto runs in a worker
  thread (requires process-based or threading orchestration across the entry
  point).
- Using platform-specific alternatives (e.g. PyObjC + `NSAppKit`, or running
  inside a bundler that pre-spawns the GUI thread).

This is out of scope for the demo. The core crypto functionality works on all
platforms.

---

## Installation

```bash
pip install -r requirements.txt
```

Requires Python 3.10+, NumPy, Pillow, PyOpenGL, glfw, matplotlib, pycryptodome,
argon2-cffi, and pytest (for `selftest`).

---

## Usage

```bash
# Encrypt a file (interactive trajectory drawing)
python crypto_canvas.py encrypt myfile.txt

# Decrypt a PNG back to the original file
python crypto_canvas.py decrypt myfile.txt.png

# Show PNG metadata (algorithm, trajectory, salt, ...)
python crypto_canvas.py info myfile.txt.png

# Run all tests
python crypto_canvas.py selftest
```

### CLI flags

| Flag                          | Applies to  | Description                                                                |
|-------------------------------|-------------|----------------------------------------------------------------------------|
| `-o, --output <path>`         | encrypt/decrypt | Custom output path (default: `<file>.png` for encrypt, `<file>_decrypted` for decrypt) |
| `--no-gpu`                    | encrypt/decrypt | Skip the OpenGL fragment-shader GPU stress window                          |
| `--no-runner`                 | encrypt/decrypt | Skip the tkinter pixel-character animation window                          |
| `--trajectory <file.json>`    | encrypt     | Use a pre-saved trajectory (`examples/circle.traj`) and skip the GUI       |
| `--help`                      | all         | Show subcommand help                                                       |

> Note: `--no-gpu` and `--no-runner` are the only opt-outs. On macOS the two
> windows are already skipped automatically (see **macOS Platform Limitations**).

---

## Example output

```bash
$ python crypto_canvas.py encrypt examples/sample.txt \
    --trajectory examples/circle.traj --no-runner --no-gpu
✓ Encrypted: examples/sample.txt -> /tmp/encrypted.png
  Size: 361 -> 4817 bytes
  Time: 0.4s

$ python crypto_canvas.py decrypt /tmp/encrypted.png --no-runner --no-gpu
✓ Decrypted: /tmp/encrypted.png -> /tmp/encrypted_decrypted
  Size: 4817 -> 361 bytes

$ python crypto_canvas.py info /tmp/encrypted.png
Algorithm: AES-256-GCM-v1
Image size: 64x64
Trajectory points: 40
Trajectory hash: a3f1d2b9c4e5f678...
Salt: 7e2c1d4b9a8f6053...
Nonce: ...
Tag: ...
```

The decrypted file is byte-for-byte identical to the original (verified by
SHA-256 in `tests/test_e2e.py`).

---

## How it works

1. **Trajectory drawing** — User draws points on a matplotlib canvas (the
   complex plane). Optionally use `--trajectory <file.json>` to skip the GUI
   with a pre-saved list of `(x, y)` points.
2. **Visual cipher** — The trajectory geometry is hashed (SHA-256) and mapped
   to a 256-byte permutation table via `crypto/trajectory.py`.
3. **Byte permutation** — The plaintext bytes are reordered by that
   permutation. This is not cryptographic on its own; it visually scrambles
   the data so the ciphertext looks like rainbow noise.
4. **Key derivation** — `Argon2id(trajectory SHA-256 fingerprint, salt)` → 32-byte
   AES-256 key (`crypto/kdf.py`). Demo parameters are intentionally aggressive
   (see Security notes below).
5. **Encryption** — AES-256-GCM in parallel chunks via `multiprocessing`
   (`crypto/cipher.py`). Output format:
   `[8 bytes plaintext length BE] + (nonce + ct + tag) × chunks`.
6. **HSV rendering** — `crypto/visualizer.py` maps every ciphertext byte to a
   unique RGB pixel (lossless, full color range).
7. **PNG output** — `crypto/container.py` writes the pixel grid plus
   `tEXt` chunks for `algo`, `trajectory`, `trajectory_hash`, `salt`, and
   `ciphertext_len`. The PNG is self-contained.
8. **Visual feedback** (non-macOS) — OpenGL fragment shader renders fullscreen
   GPU load while the pixel character runs across the screen. Both windows
   are stopped as soon as the crypto finishes.

The decrypt path is the reverse, with one extra step: the trajectory hash
stored in PNG metadata is compared against a fresh SHA-256 of the loaded
trajectory. A mismatch raises `ValueError("轨迹已被篡改")` and aborts.

---

## Security notes

This is a **demonstration tool**, not production crypto.

- The Argon2id parameters (`t=5`, `m=64 MiB`, `p=8`) are intentionally
  aggressive so the CPU stress is visible. For production use, drop to `t=1`,
  `p=4` (per spec §7.3, §17.6).
- The byte permutation is **visual only** — it does not add cryptographic
  strength. AES-256-GCM is what actually protects the data.
- The trajectory stored inside the PNG is required for decryption. Anyone who
  can read the PNG can read the trajectory; the Argon2id KDF adds a small
  amount of brute-force resistance but is not a substitute for a real password.
- Chunk lengths are inferred from the 8-byte plaintext length header at the
  start of the ciphertext (no per-chunk length metadata). Spec §2 notes this
  simplification.

---

## Project layout

```
crypto/
  cipher.py           AES-256-GCM + multiprocessing parallel chunks
  kdf.py              Argon2id key derivation (demo parameters)
  trajectory.py       SHA-256 fingerprint → 256-byte permutation
  container.py        PNG tEXt chunk read/write
  visualizer.py       Lossless byte ↔ pixel HSV encoding
  gpu_window.py       OpenGL fragment-shader stress window (skip on macOS)
  runner.py           Tkinter pixel-character animation (skip on macOS)
  trajectory_gui.py   Matplotlib interactive trajectory drawing
  encrypt.py          Encrypt orchestration (calls all layers)
  decrypt.py          Decrypt orchestration (reverse of encrypt)
crypto_canvas.py      CLI entry point (encrypt / decrypt / info / selftest)
tests/                Pytest suite (54 tests, 1 pre-existing KDF timing flake)
examples/
  circle.traj         Pre-saved trajectory (unit-circle, 40 points)
  sample.txt          Small demo plaintext
docs/                 This README + spec + plan
```

---

## Spec

The full design document is at
[`docs/superpowers/specs/2026-09-29-crypto-canvas-design.md`](../superpowers/specs/2026-09-29-crypto-canvas-design.md).
The implementation plan lives at
[`docs/superpowers/plans/2026-09-29-crypto-canvas.md`](../superpowers/plans/2026-09-29-crypto-canvas.md).

---

## License

Demo / educational use.