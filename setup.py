"""
Setup Hydra ETL Framework

Installation :
    pip install -e .

Commande disponible après installation :
    hydra run <job_dir>
"""

from setuptools import find_packages, setup

setup(
    name="hydra-etl",
    version="1.2.0",
    description="Hydra ETL Framework - Pipeline ETL déclaratif",
    author="Votre Nom",
    author_email="votre.email@example.com",
    packages=find_packages(exclude=["tests", "tests.*", "examples", "examples.*"]),
    python_requires=">=3.9",
    install_requires=[
        "pandas>=2.0.0",
        "pydantic>=2.0.0",
        "PyYAML>=6.0",
    ],
    entry_points={
        "console_scripts": [
            "hydra=cli.hdrctl:main",
            "hdrctl=cli.hdrctl:main",
        ],
    },
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
    ],
)
