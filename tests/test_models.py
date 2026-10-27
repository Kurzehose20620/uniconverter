"""3D models through Blender in the background."""

import pytest
from conftest import needs_blender

from uniconverter import router

pytestmark = needs_blender

CUBE_OBJ = """o Cube
v -1 -1 -1
v 1 -1 -1
v 1 1 -1
v -1 1 -1
v -1 -1 1
v 1 -1 1
v 1 1 1
v -1 1 1
f 1 2 3 4
f 5 8 7 6
f 1 5 6 2
f 2 6 7 3
f 3 7 8 4
f 5 1 4 8
"""


@pytest.fixture(scope="module")
def cube(tmp_path_factory):
    p = tmp_path_factory.mktemp("models") / "cube.obj"
    p.write_text(CUBE_OBJ)
    return p


@pytest.mark.parametrize("target", ["glb", "stl", "ply"])
def test_obj_to(cube, tmp_path, opts, target):
    out = tmp_path / f"cube.{target}"
    router.convert_one(cube, out, opts())
    data = out.read_bytes()
    assert len(data) > 100
    if target == "glb":
        assert data[:4] == b"glTF"
    if target == "ply":
        assert data.startswith(b"ply")


def test_glb_back_to_obj(cube, tmp_path, opts):
    glb = tmp_path / "cube.glb"
    router.convert_one(cube, glb, opts())
    out = tmp_path / "back.obj"
    router.convert_one(glb, out, opts())
    text = out.read_text()
    assert text.count("\nv ") >= 8 and "\nf " in text   # glTF may split vertices
