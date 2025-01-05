publish:
    rm -rf dist/*
    uv build
    uv publish

format:
    uvx ruff format skeet.py
