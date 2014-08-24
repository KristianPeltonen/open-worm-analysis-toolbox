# -*- coding: utf-8 -*-
"""
Test harness for OpenWorm's movement validation tool

@authors: @JimHokanson, @MichaelCurrie

"""

import sys, os

# We must add .. to the path so that we can perform the 
# import of movement_validation while running this as 
# a top-level script (i.e. with __name__ = '__main__')
sys.path.append('..') 
import movement_validation
user_config = movement_validation.user_config
NormalizedWorm = movement_validation.NormalizedWorm
WormFeatures = movement_validation.WormFeatures


def main():
    """
    Compare Schafer-generated features with our new code's generated features

    """
    # Set up the necessary file paths for file loading
    #----------------------

    # Take one example worm folder from our user_config.py file
    norm_folder = os.path.join(user_config.DROPBOX_PATH,
                               user_config.NORMALIZED_WORM_PATH)

    matlab_generated_file_path = os.path.join(
        os.path.abspath(norm_folder),
        '..', '..', '..', 'results',
        'mec-4 (u253) off food x_2010_04_21__17_19_20__1_features.mat')

    data_file_path = os.path.join(os.path.abspath(norm_folder),
                                  "norm_obj.mat")

    eigen_worm_file_path = os.path.join(os.path.abspath(norm_folder),
                                        "masterEigenWorms_N2.mat")

    # OPENWORM
    #----------------------
    # Load the normalized worm from file
    nw = NormalizedWorm(data_file_path, eigen_worm_file_path)

    # Generate the OpenWorm movement validation repo version of the features
    openworm_features = WormFeatures(nw,[])

    # SCHAFER LAB
    #----------------------
    # Load the Matlab codes generated features from disk
    matlab_worm_features = \
        WormFeatures.from_disk(matlab_generated_file_path)

    # COMPARISON
    #----------------------
    # Show the results of the comparison
    print("Locomotion: " + 
        str(matlab_worm_features.locomotion == openworm_features.locomotion))

    print("Posture: " +
        str(matlab_worm_features.posture == openworm_features.posture))

    print("Morphology: " +
        str(matlab_worm_features.morphology == openworm_features.morphology))

    print("Path: " +
        str(matlab_worm_features.path == openworm_features.path))


if __name__ == '__main__':
    main()