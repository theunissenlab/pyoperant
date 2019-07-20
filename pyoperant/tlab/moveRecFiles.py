#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Created on Fri Jul 19 21:24:58 2019
Processed wav recorded files in startFolder and copiesthem to endFolder
A ramp is added and wave files are also scaled by dBScale
@author: frederictheunissen
"""

# Dependencies
# Global dependecies
import numpy as np
import os

# Local dependencies
from soundsig.sound import WavFile, addramp
from soundsig.signal import bandpass_filter

# Global parameters
#startFolder = '/Users/frederictheunissen/Documents/Data/Seewiesen/stimStart'
#endFolder = '/Users/frederictheunissen/Documents/Data/Seewiesen/stimEnd'
startFolder = 'C:/Users/soundrec/Raven Lite 2.0/Clips'
endFolder = 'C:/Users/soundrec/stimuli/Playback/online'

dBScale = 40   # Increases sound intensity by 40 db

#  Begining of scrip

# Find all the wave files
isound = 0
for fname in os.listdir(startFolder):
    if fname.endswith('.wav'):
        isound += 1;

        # Read the sound file and store its name
        print ('Processing sound %d:%s\n' % (isound, fname))
        soundIn = WavFile(file_name=os.path.join(startFolder, fname))
        pathIn, filename = os.path.split(fname)
        filename, file_extension = os.path.splitext(filename)

        # Process the sound: bandpass, ramp, scale
        soundFilt = bandpass_filter(soundIn.data, sample_rate = soundIn.sample_rate, low_freq=400, high_freq=10000)
        soundFilt = addramp(soundFilt, samp_rate=soundIn.sample_rate, ramp_duration=5)
        soundFilt = np.power(10, dBScale/20)*soundFilt

        sathigh = np.where(soundFilt > 2**15-1)
        satlow = np.where(soundFilt < -2**15+1)
        if sathigh[0].size != 0:
            soundFilt[sathigh[0]] = 2**15 - 1
        if satlow[0].size != 0:
            soundFilt[satlow[0]] = -2**15 + 1
        if sathigh[0].size != 0 or satlow[0].size != 0:
            print('Warning: file %s saturates after processing' % fname)

        # Write sound file
        fnameOut = os.path.join(endFolder, filename+'Filt'+file_extension)

        soundOut = WavFile()
        soundOut.sample_depth = soundIn.sample_depth  # in bytes
        soundOut.sample_rate = soundIn.sample_rate  # in Hz
        soundOut.data = np.round(soundFilt).astype(int)
        soundOut.num_channels = 1

        soundOut.to_wav(fnameOut)
