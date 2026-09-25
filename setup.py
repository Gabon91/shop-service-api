from pathlib import Path
import re

from setuptools import find_packages, setup


ROOT = Path(__file__).resolve().parent
version_source = (ROOT / "app" / "__init__.py").read_text(encoding="utf-8")
match = re.search(r'^__version__ = "((?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*))"$',
                  version_source, re.MULTILINE)
if match is None:
    raise ValueError("Set app.__version__ to a MAJOR.MINOR.PATCH version")

requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8").splitlines()

setup(
    name="shop-service-api",
    version=match.group(1),
    description="Mini E-Commerce Store API",
    python_requires=">=3.11",
    packages=find_packages(exclude=("tests", "tests.*")),
    py_modules=["main"],
    install_requires=[line for line in requirements if line and not line.startswith("pytest==")],
)
