from setuptools import setup, find_packages
from codecs import open
from os import path
from glob import glob
try:
  import pypandoc
  def readme_to_rst():
    return "\n".join([ l for l in pypandoc.convert_file("README.md", "rst").split("\n") if not "PyPI version" in l ])
except ImportError:
  def readme_to_rst():
    return ""

setup(
  name='alidock',
  version='0.0.1',
  description='Run your ALICE environment from a container easily',
  long_description=readme_to_rst(),
  url='https://github.com/dberzano/alidock',
  author='Dario Berzano',
  author_email='dario.berzano@cern.ch',
  license='GPL',
  classifiers=[

    # How mature is this project? Common values are
    #   3 - Alpha
    #   4 - Beta
    #   5 - Production/Stable
    'Development Status :: 4 - Beta',

    # Indicate who your project is intended for
    'Intended Audience :: Education',
    'Topic :: Scientific/Engineering :: Physics',

    # Pick your license as you wish (should match "license" above)
    'License :: OSI Approved :: GNU General Public License v3 (GPLv3)',

    # Specify the Python versions you support here. In particular, ensure
    # that you indicate whether you support Python 2, Python 3 or both.
    'Programming Language :: Python :: 2.7',
    'Programming Language :: Python :: 3.7',
    ],

  # What does your project relate to?
  keywords='HEP Computing',

  # You can just specify the packages manually here if your project is
  # simple. Or you can use find_packages().
  packages=find_packages(),

  # Alternatively, if you want to distribute just a my_module.py, uncomment
  # this:
  #   py_modules=["my_module"],

  # List run-time dependencies here.  These will be installed by pip when
  # your project is installed. For an analysis of "install_requires" vs pip's
  # requirements files see:
  # https://packaging.python.org/en/latest/requirements.html
  install_requires=[ "argparse", "requests", "PyYaml" ],

  python_requires='>=2.7',

  # List additional groups of dependencies here (e.g. development
  # dependencies). You can install these using the following syntax,
  # for example:
  # $ pip install -e .[dev,test]
  extras_require={
  },

  # If there are data files included in your packages that need to be
  # installed, specify them here.  If using Python 2.6 or less, then these
  # have to be included in MANIFEST.in as well.
  include_package_data=True,
  package_data={},

  # Although 'package_data' is the preferred approach, in some case you may
  # need to place data files outside of your packages. See:
  # http://docs.python.org/3.4/distutils/setupscript.html#installing-additional-files
  # In this case, 'data_file' will be installed into '<sys.prefix>/my_data'
  data_files=[],

  # To provide executable scripts, use entry points in preference to the
  # "scripts" keyword. Entry points provide cross-platform support and allow
  # pip to create the appropriate form of executable for the target platform.
  # entry_points={
  # },
  scripts = glob("bin/*")
)
