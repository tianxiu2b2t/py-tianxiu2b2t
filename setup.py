from setuptools import setup, find_namespace_packages

setup(
    name='tianxiu2b2t-utils',
    version='0.1.29',
    description='A collection of utilities for the tianxiu2b2t packages',
    url='https://github.com/tianxiu2b2t/py-tianxiu2b2t',
    author='tianxiu2b2t',
    author_email='administrator@ttb-network.top',
    license='MIT',
    packages=find_namespace_packages(),
    install_requires=[
        'anyio==4.9.0',
        'h11==0.14.0',
        'h2==4.2.0',
        'hpack==4.1.0',
        'hyperframe==6.1.0',
        'idna==3.10',
        'sniffio==1.3.1',
        'typing_extensions==4.13.2',
        'wsproto==1.2.0'
    ],
)
