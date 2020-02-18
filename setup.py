import setuptools
setuptools.setup(name='m2fscontrol',
      version='1.0',
      description='M2FS Control Python Libraries',
      author='Jeb Bailey',
      author_email='baileyji@umich.edu',
      url="https://github.com/baileyji/M2FS-Control",
      packages=setuptools.find_packages(),
      classifiers=("Programming Language :: Python :: 2",
                   "License :: OSI Approved :: MIT License",
                   "Operating System :: POSIX",
                   "Intended Audience :: Science/Research"),
      install_requires=['numpy>=1.8.0', 'jbastro', 'hole-mapper']
)