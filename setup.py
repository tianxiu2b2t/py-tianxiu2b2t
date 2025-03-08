from setuptools import setup

setup(
    name='tianxiu2b2t-utils',
    version='0.1.1',
    description='A collection of utilities for the tianxiu2b2t packages',
    url='https://github.com/tianxiu2b2t/py-tianxiu2b2t',
    author='tianxiu2b2t',
    author_email='administrator@ttb-network.top',
    license='MIT',
    packages=[
        'src/anyio',
        'src/cache'
    ],
)
