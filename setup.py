from setuptools import setup, find_packages

setup(
    name="enc-server",
    version="0.1.3",
    # We are in server/, so we look for packages under src/
    package_dir={"": "src"},
    packages=find_packages(where="src"),
    install_requires=[
        "click>=8.0",
        "rich>=10.0",
        "cryptography>=3.0",
        "requests>=2.0",
        "PyYAML>=6.0",
        "argon2-cffi>=21.0",
    ],
    entry_points={
        "console_scripts": [
            "enc=enc_server.cli:main",
        ],
    },
)
