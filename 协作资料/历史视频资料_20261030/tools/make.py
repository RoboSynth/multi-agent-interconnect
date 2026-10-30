"""Render scenes: python make.py <out-dir> replay [--still t ...]"""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent))
import engine

def load(name):
    mod = __import__("scene_" + name)
    return mod.SCENE, mod.LINES

if __name__ == "__main__":
    out, name, *rest = sys.argv[1:]
    out = Path(out); out.mkdir(parents=True, exist_ok=True)
    scene, lines = load(name)
    if rest and rest[0] == "--still":
        for t in rest[1:]:
            engine.still(scene, float(t), 32.0, out / f"{name}-{t}.png", lines[1])
    else:
        print(engine.render(scene, lines, out, name))
