from setuptools import setup

setup(
    name="pgautogeomindex",
    version="0.11.0",
    author="Rory McCann",
    author_email="rory@technomancy.org",
    py_modules=['pgautogeomindex'],
    platforms=['any',],
    license = 'GPLv3+',
    install_requires=[
        'psycopg2',
        ],
    entry_points={
        'console_scripts': [
            'pgautogeomindex = pgautogeomindex:main',
        ]
    },
    classifiers=[
        'Development Status :: 4 - Beta',
        'Environment :: Console',
        'Intended Audience :: System Administrators',
        'Operating System :: Unix',
        'Topic :: Database :: Database Engines/Servers',
        'Topic :: System :: Systems Administration',
        'Programming Language :: Python :: 2',
    ],
)
