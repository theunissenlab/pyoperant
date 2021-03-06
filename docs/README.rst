pyoperant
=========

Pyoperant is a framework to easily construct and share new operant behavior paradigms.

With PyOperant, you can write a single behavior script that works across different species, different computers, different hardware, different rewards, different modalities.

Installation
------------
To get set up, install python and python header files and portaudio (which is necsessary for PyAudio)

```shell
sudo apt install python python-dev portaudio19-dev
```

When installing portaudio there was a prompt to allow realtime priority to jackd. I don't know what this means but I said yes.

Running a Virtual Pecking Test Box (Theunissen lab)
---------------------------------------------------

Use `pyoperant/tlab/pecking_and_playback_test.yaml` or `pyoperant/tlab/pecking_test.yaml` as a template; copy the file to a folder. Currently the main script in `pyoperant/tlab/pecking_test.py` is configured to look in the path `~/configs/` for files named `Box*.yaml` (e.g. if you run `python -m pyoperant.tlab.pecking_test test 1` it will read the yaml at `~/configs/Box1.yaml`.

Fill in the paths to `stim_directory` and `experiment_path`, make sure `panel` is set to `!python/object/apply:pyoperant.tlab.local_tlab.BoxVirtual {}` and add stimulus wav files in the folders `{stim_directory}/reward`, `{stim_directory}/nonreward`, and `{stim_directory}/preference` if testing preference tests too.


***

Operant logic is easy
---------------------

#. Present a stimulus
#. Get the subject’s response
#. If the response matches the stimulus, then reward the subject

Writing operant protocols should be easy, but in practice...
------------------

Error checking, data storage, and machine-specific hardware interactions often obfuscate the simplicity of the task, limiting its flexibility and power. This limitation becomes increasingly apparent when deploying high-throughput behavioral experiment control systems, transferring subjects from a training panel to an electrophysiology panel, or simply trying to share behavioral protocols. 

A better way
------------

PyOperant deals with these challenges by providing a cross-platform object-oriented framework to easily construct, conveniently share, and rapidly iterate on new operant behavior paradigms.

#. Abstract physical component manipulation from low-level hardware manipulation
#. Define behavioral protocols as classes which can be extended through object inheritance

Further, experimenters are able to integrate their behavioral protocols with other Python packages for online data analysis or experimental control. We currently use pyoperant in the Gentner Lab to control 36 operant panels.

Documentation
-------------

PyOperant abstracts behavioral protocol logic from hardware interactions through a machine-specific configuration file. In the local.py configuration file, the experimenter defines the operant panels available for use. A Panel consists of a collection of Component objects and a set of standard methods to manipulate the Component. These Component objects are mirrors of their physical counterparts, such as a food hopper, response port, speaker, or house light.

Behavioral protocols can be modifed and extended through object inheritance. The modular architecture of PyOperant also allows experimenters to integrate their behavioral protocols with other Python packages for online data analysis or experimental control.

PyOperant’s hardware support currently includes PortAudio & Comedi. Future support will include NiDAQmx and Cambridge Electronic Designs.

http://pyoperant.readthedocs.org/en/dev/index.html

Architecture
------------

Behaviors
~~~~~~~~~

Behaviors are Python classes which run the operant experiment. They associate the subject with the hardware panel the subject is interacting with and save experimental data appropriately. They are instantiated with various experimental parameters, such as stimulus identities and associations, block designs, and reinforcement schedules.

There are a couple of built-in behaviors: TwoAltChoice, which runs two alternative choice tasks and Lights, which simply turns the house light on and off according to a schedule. These can be inherited to change specific methods without changing the rest of the behavioral protocol.

Panels
~~~~~~

Panels are the highest level of hardware abstraction. They maintain panel components as attributes and have standard methods for resetting and testing the panel. Many Behaviors rely on specific panel components and methods to be present. 

Panels are defined by the experimenter locally.

Components
~~~~~~~~~~

Components are common hardware components, such as a Hopper, a ResponsePort, a HouseLight, or an RGBLight. Many components rely on multiple hardware IO channels. For example, a Hopper requires both a solenoid (to activate the Hopper) and an IR beam detector (to check if the Hopper is raised). Calling the ‘feed’ method on a Hopper checks to make sure that the hopper is down, raises the hopper, checks to make sure the hopper raised, waits the appropriate length of time, then lowers the hopper, finally checking one more time to make sure the hopper dropped. If there is an incongruity between the status of the solenoid and the IR beam, the Hopper component raises the appropriate error, which the Behavior script can deal with appropriately.

Hardware IO Classes
~~~~~~~~~~~~~~~~~~~

Hawdware IO classes standardize inputs and outputs that are available for Components and Panels to use.

Hardware interfaces
~~~~~~~~~~~~~~~~~~~

Hardware interfaces are wrappers around hardware drivers and APIs that allow hardware IO classes to work.


Developers
----------

Justin Kiggins & Marvin Thielk

Gentner Lab - http://gentnerlab.ucsd.edu
