from setuptools import setup, find_namespace_packages

def read_requirements():
    with open('requirements.txt', 'r', encoding='utf-16le') as f:
        return [
            ''.join((
                char for char in line.strip() if char.isascii()
            ))
            for line in f.readlines()
            if not line in (
                'setuptools'
            )
        ]

setup(
    name='tianxiu2b2t-utils',
    version='0.1.31',
    description='A collection of utilities for the tianxiu2b2t packages',
    url='https://github.com/tianxiu2b2t/py-tianxiu2b2t',
    author='tianxiu2b2t',
    author_email='administrator@ttb-network.top',
    license='MIT',
    packages=find_namespace_packages(),
    install_requires=read_requirements()
)
