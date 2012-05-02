from distutils.core import setup
import os

def read(fname):
    return open(os.path.join(os.path.dirname(__file__), fname)).read()

setup(
    name = 'pyoperant',
    version = '0.0.3',
    author = 'Justin Kiggins',
    author_email = 'justin.kiggins@gmail.com',
    description = 'hardware interface and controls for operant conditioning in the Gentner Lab',
    long_description = read('README.txt'),
    packages = ['pyoperant'],
    scripts = ['tricks/lights.py','tricks/2ac_seq_decide.py'],
    requires = ['pyephem'],
    license = "GNU Affero General Public License v3",
    classifiers = [
        "Development Status :: 2 - Pre-Alpha",
        "Environment :: Console",
        "Intended Audience :: Science/Research",
        "License :: OSI Approved :: GNU Affero General Public License v3",
        "Natural Language :: English",
        "Operating System :: Unix",
        "Programming Language :: Python :: 2.7",
        "Topic :: Scientific/Engineering",
        ],
    )