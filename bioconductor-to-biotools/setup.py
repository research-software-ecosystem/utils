#!/usr/bin/env python3
"""
Setup script for bc2bt package.
"""

from setuptools import setup, find_packages

# Read the README file
with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

# Read requirements
with open("requirements.txt", "r", encoding="utf-8") as fh:
    requirements = [
        line.strip() for line in fh if line.strip() and not line.startswith("#")
    ]

setup(
    name="bc2bt",
    version="0.1.0",
    author="Hervé Ménager",
    author_email="herve.menager@pasteur.fr",
    description="Bioconductor to bio.tools synchronization package",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/hmenager/bc2bt",
    packages=find_packages(exclude=["tests", "tests.*", "examples", "examples.*"]),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Science/Research",
        "Topic :: Scientific/Engineering :: Bio-Informatics",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Programming Language :: Python :: 3.13",
    ],
    python_requires=">=3.9",
    install_requires=requirements,
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "black>=23.0",
            "flake8>=6.0",
            "mypy>=1.0",
        ],
        "docs": [
            "sphinx>=6.0",
            "sphinx-rtd-theme>=1.2",
        ],
    },
    entry_points={
        "console_scripts": [
            "bc2bt-sync=bc2bt.cli:sync_command",
            "bc2bt-convert=bc2bt.cli:convert_command",
            "bc2bt-compare=bc2bt.cli:compare_command",
            "bc2bt-update=bc2bt.cli:update_command",
        ],
    },
    include_package_data=True,
    zip_safe=False,
)
