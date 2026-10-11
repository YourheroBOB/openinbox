"""Plug-in introspection and the UI module loader (`ui/modules/*.js`)."""
from __future__ import annotations

import re
from pathlib import Path

import features
from features import Raw, get

UI_MODULES = Path(__file__).resolve().parents[2] / "ui" / "modules"
MODULE_NAME = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_-]*\.js$")


def ui_modules() -> list[str]:
    if not UI_MODULES.is_dir():
        return []
    return sorted(p.name for p in UI_MODULES.iterdir() if p.is_file() and MODULE_NAME.match(p.name))


@get("/api/features")
def list_features(req):
    return {
        "features": list(features.LOADED),
        "routes": features.routes(),
        "ui_modules": [f"/ui/modules/{n}" for n in ui_modules()],
        "errors": list(features.ERRORS),
    }


@get("/api/ui-modules")
def list_ui_modules(req):
    return {"modules": [f"/ui/modules/{n}" for n in ui_modules()]}


@get("/ui/modules/*")
def serve_ui_module(req):
    name = req.params
    if not MODULE_NAME.match(name) or name not in ui_modules():
        return {"error": "not found"}, 404
    return Raw((UI_MODULES / name).read_bytes(), "application/javascript; charset=utf-8")
