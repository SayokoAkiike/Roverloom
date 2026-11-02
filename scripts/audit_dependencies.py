"""Lists installed Python dependencies and the licenses they declare. Not legal advice.

Reads package metadata only, and uses no network. A declared license can be wrong or incomplete,
so a person must still check what matters before any public release.

Run from python/: uv run python ../scripts/audit_dependencies.py
"""

import importlib.metadata


def declared_license(package: importlib.metadata.Distribution) -> str:
    metadata = package.metadata
    expression = metadata.get("License-Expression")
    if expression:
        return str(expression)
    classifiers = [
        value.split(" :: ")[-1]
        for value in metadata.get_all("Classifier", [])
        if value.startswith("License ::")
    ]
    if classifiers:
        return "; ".join(classifiers)
    text = metadata.get("License")
    return str(text).splitlines()[0][:60] if text else "NOT DECLARED"


def main() -> None:
    packages = sorted(
        importlib.metadata.distributions(), key=lambda d: str(d.metadata["Name"]).lower()
    )
    for package in packages:
        print(f"{package.metadata['Name']:<28} {package.version:<12} {declared_license(package)}")


if __name__ == "__main__":
    main()
