"""3D models through Blender in the background (glb, gltf, obj, fbx, stl, ply, usd, abc)."""

import functools
import subprocess
import tempfile
from pathlib import Path

from ..errors import ConvError
from . import tools
from .tools import need, run

BLENDER_SCRIPT = r"""
import os
import sys
import tempfile

import bpy

argv = sys.argv[sys.argv.index("--") + 1:]
src, dst = argv[0], argv[1]
se = os.path.splitext(src)[1].lower().lstrip(".")
de = os.path.splitext(dst)[1].lower().lstrip(".")

bpy.ops.wm.read_factory_settings(use_empty=True)

importers = {
    "glb": lambda: bpy.ops.import_scene.gltf(filepath=src),
    "gltf": lambda: bpy.ops.import_scene.gltf(filepath=src),
    "obj": lambda: bpy.ops.wm.obj_import(filepath=src),
    "fbx": lambda: (bpy.ops.wm.fbx_import if hasattr(bpy.ops.wm, "fbx_import")
                    else bpy.ops.import_scene.fbx)(filepath=src),
    "stl": lambda: bpy.ops.wm.stl_import(filepath=src),
    "ply": lambda: bpy.ops.wm.ply_import(filepath=src),
    "abc": lambda: bpy.ops.wm.alembic_import(filepath=src),
}
for k in ("usd", "usdc", "usdz", "usda"):
    importers[k] = lambda: bpy.ops.wm.usd_import(filepath=src)
importers[se]()

# Embedded textures (GLB/USDZ) are first written out as real files. OBJ/MTL and
# separate glTF reference files, so their textures go next to the target; formats
# that embed textures (glb, fbx, usdz) pick them up from a temporary folder.
if de in ("obj", "gltf"):
    tex_dir = os.path.dirname(dst)
else:
    tex_dir = tempfile.mkdtemp(prefix="uniconverter-tex-")
for img in bpy.data.images:
    missing = img.filepath and not os.path.exists(bpy.path.abspath(img.filepath))
    if img.packed_file or img.source == "GENERATED" or missing:
        os.makedirs(tex_dir, exist_ok=True)
        name = (img.name or "texture").replace("/", "_")
        if not name.lower().endswith((".png", ".jpg", ".jpeg")):
            name += ".png"
        out = os.path.join(tex_dir, name)
        img.filepath_raw = out
        try:
            img.file_format = "PNG" if out.lower().endswith(".png") else "JPEG"
        except Exception:
            pass
        try:
            img.save()
        except Exception as e:
            print("texture could not be saved:", img.name, e)
        img.filepath = out
        img.filepath_raw = out
        img.source = "FILE"
        try:
            img.reload()
        except Exception:
            pass

exporters = {
    "obj": lambda: bpy.ops.wm.obj_export(filepath=dst, export_materials=True, path_mode="STRIP",
                                         forward_axis="NEGATIVE_Z", up_axis="Y"),
    "glb": lambda: bpy.ops.export_scene.gltf(filepath=dst, export_format="GLB"),
    "gltf": lambda: bpy.ops.export_scene.gltf(filepath=dst, export_format="GLTF_SEPARATE"),
    "fbx": lambda: bpy.ops.export_scene.fbx(filepath=dst, path_mode="COPY", embed_textures=True),
    "stl": lambda: bpy.ops.wm.stl_export(filepath=dst),
    "ply": lambda: bpy.ops.wm.ply_export(filepath=dst),
    "usdz": lambda: bpy.ops.wm.usd_export(filepath=dst),
    "usdc": lambda: bpy.ops.wm.usd_export(filepath=dst),
}
exporters[de]()
"""


@functools.cache
def _offline_flag(blender):
    """--offline-mode (Blender 4.2+) keeps Blender from going online."""
    try:
        out = subprocess.run([blender, "--help"], capture_output=True, text=True,
                             timeout=60).stdout
    except (OSError, subprocess.SubprocessError):
        return []
    return ["--offline-mode"] if "--offline-mode" in out else []


def model_convert(src: Path, dst: Path, opts):
    need(tools.BLENDER, "Blender", "brew install --cask blender")
    with tempfile.TemporaryDirectory() as td:
        script = Path(td) / "convert.py"
        script.write_text(BLENDER_SCRIPT, encoding="utf-8")
        run([tools.BLENDER, "-b", "--factory-startup", *_offline_flag(tools.BLENDER),
             "--python-exit-code", "1", "--python", script, "--",
             src.resolve(), dst.resolve()],
            err_hint="Blender could not convert the model")
    if not dst.exists():
        raise ConvError("Blender produced no output file")
