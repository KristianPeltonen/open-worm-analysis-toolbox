# -*- coding: utf-8 -*-
"""
Pre-features calculation methods.

These methods are exclusively called by NormalizedWorm.from_BasicWorm_factory

The methods of the classes below are all static, so their grouping into
classes is only for convenient grouping and does not have any further 
functional meaning.

Original notes from Schafer Lab paper on this process:
------------------------------------------------------
"Once the worm has been thresholded, its contour is extracted by tracing the
worm''s perimeter. The head and tail are located as sharp, convex angles on
either side of the contour. The skeleton is extracted by tracing the midline of
the contour from head to tail. During this process, widths and angles are
measured at each skeleton point to be used later for feature computation. At
each skeleton point, the width is measured as the distance between opposing
contour points that determine the skeleton midline.  Similarly, each skeleton
point serves as a vertex to a bend and is assigned the supplementary angle to
this bend. The supplementary angle can also be expressed as the difference in
tangent angles at the skeleton point. This angle provides an intuitive
measurement. Straight, unbent worms have an angle of 0 degrees. Right angles 
are 90 degrees. And the largest angle theoretically possible, a worm bending 
back on itself, would measure 180 degress. The angle is signed to provide the 
bend's dorsal-ventral orientation. When the worm has its ventral side internal 
to the bend (i.e., the vectors forming the angle point towards the ventral 
side), the bending angle is signed negatively.

Pixel count is a poor measure of skeleton and contour lengths. For this reason,
we use chain-code lengths (Freeman 1961). Each laterally-connected pixel is
counted as 1. Each diagonally-connected pixel is counted as sqrt(2). The
supplementary angle is determined, per skeleton point, using edges 1/12 the
skeleton''s chain-code length, in opposing directions, along the skeleton. When
insufficient skeleton points are present, the angle remains undefined (i.e. the
first and last 1/12 of the skeleton have no bending angle defined). 1/12 of the
skeleton has been shown to effectively measure worm bending in previous 
trackers and likely reflects constraints of the bodywall muscles, their 
innervation, and cuticular rigidity (Cronin et al. 2005)."

"""
import warnings
import numpy as np
import matplotlib.pyplot as plt

from .. import config, utils

# If you are interested to know why the following line didn't work:
# import scipy.signal.savgol_filter as sgolay
# check out this: http://stackoverflow.com/questions/29324814/
# Instead we use the following statement:
from scipy.signal import savgol_filter as sgolay

#%%
class WormParsing(object):
    """
    This might eventually move somewhere else, but at least it is 
    contained within the class. It was originally in the Normalized Worm 
    code which was making things a bit overwhelming.
    
    TODO: Self does not refer to WormParsing ...
    
    """
    #%%    
    @staticmethod
    def compute_area(contour):
        """
        Compute the area of the worm, for each frame of video, from a 
        normalized contour.

        Parameters
        -------------------------
        contour: a (98,2,n)-shaped numpy array
            The contour points, in order around the worm, with two redundant
            points at the head and tail.
        
        Returns
        -------------------------
        area: float
            A numpy array of scalars, giving the area in each 
            frame of video.  so if there are 4000 frames, area would have
            shape (4000,)
        
        """
        # We do this to avoid a RuntimeWarning taking the nanmean of 
        # frames with nothing BUT nan entries: for those frames nanmean 
        # returns nan (correctly) but still raises a RuntimeWarning.
        with warnings.catch_warnings():
            warnings.simplefilter('ignore', category=RuntimeWarning)
            contour_mean = np.nanmean(contour, 0, keepdims=False)
    
        # Centre the contour about the origin for each frame
        # this is technically not necessary but it shrinks the magnitude of 
        # the coordinates we are about to multiply for a potential speedup
        contour -= contour_mean
    
        # We want a new 3D array, where all the points (i.e. axis 0) 
        # are shifted forward by one and wrapped.
        # That is, for a given frame:
        #  x' sub 1 = x sub 2, 
        #  x' sub 2 = x sub 3, 
        #  ...,
        #  x` sub n = x sub 1.     (this is the "wrapped" index)
        # Same for y.
        contour_plus_one = contour.take(range(1,np.shape(contour)[0]+1),
                                        mode='wrap', axis=0)
    
        # Now we use the Shoelace formula to calculate the area of a simple
        # polygon for each frame.
        # Credit to Avelino Javer for suggesting this.
        signed_area = np.nansum(contour[:,0,:]*contour_plus_one[:,1,:] -
                                contour[:,1,:]*contour_plus_one[:,0,:], 0) / 2
    
        # Frames where the contour[:,:,k] is all NaNs will result in a 
        # signed_area[k] = 0.  We must replace these 0s with NaNs.
        signed_area[np.flatnonzero(np.isnan(contour[0,0,:]))] = np.NaN

        return np.abs(signed_area)

  


    @staticmethod
    def compute_skeleton_and_widths(h_ventral_contour, 
                                    h_dorsal_contour, 
                                    frames_to_plot=[]):
    
        """
        
        See definition of code in SkeletonCalculatorType1
        
        This code was moved into its own class as it is really just one
        function and it was taking up too much of this class. We also might
        incorporate alternative algorithms
        """
        
        (h_widths, h_skeleton) = SkeletonCalculatorType1.compute_skeleton_and_widths(
                                    h_ventral_contour, 
                                    h_dorsal_contour, 
                                    frames_to_plot=[])  
        
        
        return (h_widths, h_skeleton)


    #%%
    @staticmethod
    def compute_skeleton_length(skeleton):
        """
        Computes the length of the skeleton for each frame.
        
        Computed from the skeleton by converting the chain-code 
        pixel length to microns.
        
        Parameters
        ----------
        skeleton: numpy array of shape (k,2,n)
            The skeleton positions for each frame.
            (n is the number of frames, and
             k is the number points in each frame)

        Returns
        -----------
        length: numpy array of shape (n)
            The (chain-code) length of the skeleton for each frame.
        
        """
        # For each frame, sum the chain code lengths to get the total length
        return np.sum(WormParsing.chain_code_lengths(skeleton),
                      axis=0)


    #%%
    @staticmethod
    def compute_angles(h_skeleton):
        """
        Calculate the angles

        From the Schafer Lab description:
        
        "Each normalized skeleton point serves as a vertex to a bend and is assigned the supplementary angle to
        this bend. The supplementary angle can also be expressed as the difference in
        tangent angles at the skeleton point. This angle provides an intuitive
        measurement. Straight, unbent worms have an angle of 0 degrees. Right angles 
        are 90 degrees. And the largest angle theoretically possible, a worm bending 
        back on itself, would measure 180 degress."
        
        Parameters
        ----------------
        h_skeleton: list of length n, of lists of skeleton coordinate points.
            The heterocardinal skeleton

        Returns
        ----------------
        numpy array of shape (49,n)
            An angle for each normalized point in each frame.


        Notes
        ----------------
        Original code in:
        https://github.com/JimHokanson/SegwormMatlabClasses/blob/master/
                 %2Bseg_worm/%2Bworm/%40skeleton/skeleton.m
        https://github.com/JimHokanson/SegwormMatlabClasses/tree/master/
                 %2Bseg_worm/%2Bcv/curvature.m
        
        Note, the above code is written for the non-normalized worm ...
        edge_length= total_length/12
        
        Importantly, the above approach calculates angles not between
        neighboring pairs but over a longer stretch of pairs (pairs that
        exceed the edge length). The net effect of this approach is to
        smooth the angles
        
        vertex index - First one where the distance from the tip to this
                       point is greater than the edge length
        
        s = norm_data[]
        
        temp_s = np.full([config.N_POINTS_NORMALIZED,n_frames],np.NaN)
        for iFrame in range(n_frames):
           temp_   

        TODO: sign these angles using ventral_mode ?? - @MichaelCurrie

        """                  
        temp_angle_list = [] # TODO: pre-allocate the space we need
                      
        for frame_index, cur_skeleton in enumerate(h_skeleton):
            if cur_skeleton is None:
                temp_angle_list.append([])
            else:
                sx = cur_skeleton[0,:]
                sy = cur_skeleton[1,:]
                cur_skeleton2 = np.rollaxis(cur_skeleton, 1)
                cc = WormParsing.chain_code_lengths_cum_sum(cur_skeleton2)
    
                # This is from the old code
                edge_length = cc[-1]/12               
                
                # We want all vertices to be defined, and if we look starting
                # at the left_I for a vertex, rather than vertex for left and
                # right then we could miss all middle points on worms being 
                # vertices
                
                left_lengths = cc - edge_length
                right_lengths = cc + edge_length
    
                valid_vertices_I = utils.find((left_lengths > cc[0]) & \
                                              (right_lengths < cc[-1]))
                
                left_lengths = left_lengths[valid_vertices_I]
                right_lengths = right_lengths[valid_vertices_I]                
                
                left_x = np.interp(left_lengths,cc,sx)
                left_y = np.interp(left_lengths,cc,sy)
            
                right_x = np.interp(right_lengths,cc,sx)
                right_y = np.interp(right_lengths,cc,sy)
    
                d2_y = sy[valid_vertices_I] - right_y
                d2_x = sx[valid_vertices_I] - right_x
                d1_y = left_y - sy[valid_vertices_I]
                d1_x = left_x - sx[valid_vertices_I] 
    
                frame_angles = np.arctan2(d2_y, d2_x) - np.arctan2(d1_y ,d1_x)
                
                frame_angles[frame_angles > np.pi] -= 2*np.pi
                frame_angles[frame_angles < -np.pi] += 2*np.pi
                
                # Convert to degrees
                frame_angles *= 180/np.pi
                
                all_frame_angles = np.full_like(cc, np.NaN)
                all_frame_angles[valid_vertices_I] = frame_angles
                
                temp_angle_list.append(all_frame_angles)

                
        return WormParsing.normalize_all_frames(temp_angle_list, 
                                                h_skeleton)


    #%%
    @staticmethod
    def chain_code_lengths(skeleton):
        """
        Computes the chain-code lengths of the skeleton for each frame.
        
        Computed from the skeleton by converting the chain-code 
        pixel length to microns.
        
        These chain-code lengths are based on the Freeman 8-direction
        chain codes:
        
        3  2  1
        4  P  0
        5  6  7        
        
        Given a sequence of (x,y)-coordinates, we could obtain a sequence of
        direction vectors, coded according to the following scheme.
        
        However, since we just need the lengths, we don't need to actually
        calculate all of these codes.  Instead we just calculate the 
        Euclidean 2-norm from pixel i to pixel i+1.
        
        Note:
        Our method is actually different than if we stepped from pixel 
        to pixel in one-pixel increments, since in our method the distances 
        can be something other than multiples of the 1- or sqrt(2)- steps 
        characteristic in Freeman 8-direction chain codes.
        
        
        Parameters
        ----------
        skeleton: numpy array of shape (k,2,n)
            The skeleton positions for each frame.
            (n is the number of frames, and
             k is the number points in each frame)

        Returns
        -----------
        length: numpy array of shape (n)
            The (chain-code) length of the skeleton for each frame.        

        """
        # For each frame, for x and y, take the difference between skeleton
        # points: (hence axis=0).  Resulting shape is (k-1,2,n)
        skeleton_diffs = np.diff(skeleton, axis=0)
        # Now for each frame, for each (diffx, diffy) pair along the skeleton,
        # find the magnitude of this vector.  Resulting shape is (k-1,n)
        chain_code_lengths = np.linalg.norm(skeleton_diffs, axis=1)

        return chain_code_lengths
        
    #%%
    @staticmethod
    def chain_code_lengths_cum_sum(skeleton):
        """
        Compute the Freeman 8-direction chain-code length.
        
        Calculate the distance between a set of points and then calculate
        their cumulative distance from the first point.
        
        The first value returned has a value of 0 by definition.

        """
        if np.size(skeleton) == 0:
            # Handle empty set - don't add 0 as first element
            distances = WormParsing.chain_code_lengths(skeleton)
        else:
            distances = np.concatenate(
                    [np.array([0.0]), 
                     WormParsing.chain_code_lengths(skeleton)])

        return np.cumsum(distances)

    #%%
    @staticmethod
    def normalize_all_frames_xy(heterocardinal_property):
        """
        Normalize a "heterocardinal" skeleton or contour into a "homocardinal"
        one, where each frame has the same number of points.
        
        We always normalize to config.N_POINTS_NORMALIZED points per frame.

        Parameters
        --------------
        prop_to_normalize: list of numpy arrays
            the outermost dimension, that of the lists, has length n
            the numpy arrays are of shape 

        Returns
        --------------
        numpy array of shape (49,2,n)
        
        """
        return WormParsing.normalize_all_frames(heterocardinal_property, 
                                                heterocardinal_property)

        n_frames = len(heterocardinal_property)
        norm_data = np.full([config.N_POINTS_NORMALIZED, 2, n_frames],
                            np.NaN)

        for iFrame, cur_frame_value in enumerate(heterocardinal_property):
            if cur_frame_value is not None:
                # We need cur_frame_value to have shape (k,2), not (2,k)
                cur_frame_value2 = np.rollaxis(cur_frame_value, 1)
                cc = WormParsing.chain_code_lengths_cum_sum(cur_frame_value2)
                norm_data[:,iFrame] = \
                            WormParsing.normalize_parameter(cur_frame_value, 
                                                            cc)
                norm_data[:,0,iFrame] = WormParsing.normalize_parameter(cur_frame_value[0,:], cc)
                norm_data[:,1,iFrame] = WormParsing.normalize_parameter(cur_frame_value[1,:], cc)
        
        return norm_data            
    
    #%%
    @staticmethod
    def normalize_all_frames(prop_to_normalize, xy_data):
        """
        Normalize a (heterocardinal) array of lists of variable length
        down to a numpy array of shape (49,n).
        
        Parameters
        --------------
        prop_to_normalize: numpy array
            2d or 1d
        xy_data: numpy array
        
        Returns
        --------------
        numpy array of shape (49,n)
            prop_to_normalize, now normalized down to 49 points per frame
        
        """        
        norm_data_shape = ([config.N_POINTS_NORMALIZED] +
                           list(np.shape(prop_to_normalize)))
        # Start with an empty numpy array
        norm_data = np.full(norm_data_shape, np.NaN)
        for iFrame, (cur_frame_value, cur_xy) in \
                                enumerate(zip(prop_to_normalize, xy_data)):
            if cur_xy is not None:
                # We need cur_xy to have shape (k,2), not (2,k)
                cur_xy2 = np.rollaxis(cur_xy, axis=1)
                cc = WormParsing.chain_code_lengths_cum_sum(cur_xy2)
                norm_data[...,iFrame] = \
                            WormParsing.normalize_parameter(cur_frame_value, 
                                                            cc)
        
        return norm_data 
    
    #%%
    @staticmethod
    def normalize_parameter(prop_to_normalize, old_lengths):
        """
        This function finds where all of the new points will be when evenly
        sampled (in terms of chain code length) from the first to the last 
        point in the old data.

        These points are then related to the old points. If a new point is at
        an old point, the old point data value is used. If it is between two
        old points, then linear interpolation is used to determine the new 
        value based on the neighboring old values.

        NOTE: This method should be called for just one frame's data at a time.

        NOTE: For better or worse, this approach does not smooth the new data,
        since it just linearly interpolates.

        See http://docs.scipy.org/doc/numpy/reference/generated/
            numpy.interp.html

        Parameters
        -----------
        prop_to_normalize: numpy array of shape (k,) or (2,k)
            The parameter to be interpolated, where k is the number of
            points.
        old_lengths: numpy array of shape (k)
            The positions along the worm where the property was
            calculated.  It is these positions that are to be "normalized",
            or made to be evenly spaced.  The parameter will then be 
            calculated at the new, evenly spaced, positions.

        Returns
        -----------
        Numpy array of shape (k,) or (k,2) depending on the provided
        shape of prop_to_normalize
        
        Notes
        ------------
        Old code:
        https://github.com/openworm/SegWorm/blob/master/ComputerVision/
                chainCodeLengthInterp.m

        """
        # Create n evenly spaced points between the first and last point in 
        # old_lengths
        new_lengths = np.linspace(old_lengths[0], old_lengths[-1],
                                  config.N_POINTS_NORMALIZED)

        # Interpolate in both the 2-d and 1-d cases
        if len(np.shape(prop_to_normalize)) == 2:
            # Assume shape is (2,k,n)
            interp_x = np.interp(new_lengths, old_lengths, prop_to_normalize[0,:])
            interp_y = np.interp(new_lengths, old_lengths, prop_to_normalize[1,:])
            # Compbine interp_x and interp_y together in shape ()
            return np.rollaxis(np.array([interp_x, interp_y]), axis=1)
        else:
            # Assume shape is (k,n)
            return np.interp(new_lengths, old_lengths, prop_to_normalize)


class SkeletonCalculatorType1(object):
    
    """
    The main method in this clas is compute_skeleton_and_widths. All other
    methods are just subfunctions of this main method.

    """    
    
    @staticmethod
    def compute_skeleton_and_widths(h_ventral_contour, 
                                    h_dorsal_contour, 
                                    frames_to_plot=[]):
        """
        Compute widths and a heterocardinal skeleton from a heterocardinal 
        contour.
        
        Parameters
        -------------------------
        h_ventral_contour: list of numpy arrays.
            Each frame is an entry in the list.
        h_dorsal_contour: 
        frames_to_plot: list of ints
            Optional list of frames to plot, to show exactly how the 
            widths and skeleton were calculated.
            

        Returns
        -------------------------
        (h_widths, h_skeleton): tuple
            h_widths : the heterocardinal widths, frame by frame
            h_skeleton : the heterocardinal skeleton, frame by frame.


        Original algorithm notes:
        -------------------------
        Original code for this algorithm can be found at:
        https://github.com/JimHokanson/SegwormMatlabClasses/blob/master/%2Bseg_worm/%2Bworm/%40skeleton/linearSkeleton.m
        Which calls an initial skeletonization algorithm:
        https://github.com/JimHokanson/SegwormMatlabClasses/blob/master/%2Bseg_worm/%2Bcv/skeletonize.m
        Which then gets refined:
        https://github.com/JimHokanson/SegwormMatlabClasses/blob/master/%2Bseg_worm/%2Bworm/%40skeleton/cleanSkeleton.m        
        
        Widths are simply the distance between two "corresponding" sides of
        the contour. The question is how to get these two locations. 

        From Ev's Thesis: 3.3.1.6 - page 126 (or 110 as labeled in document)
        -------------------------        
        For each section, we begin at its center on both sides of the contour.
        We then walk, pixel by pixel, in either direction until we hit the end 
        of the section on opposite sides, for both directions. The midpoint, 
        between each opposing pixel pair, is considered the skeleton and the 
        distance between these pixel pairs is considered the width for each 
        skeleton point.
        
        Food tracks, noise, and other disturbances can form spikes on the 
        worm contour. When no spikes are present, our walk attempts to 
        minimize the width between opposing pairs of pixels. When a spike 
        is present, this strategy may cause one side to get stuck in the 
        spike while the opposing side walks.
        
        Therefore, when a spike is present, the spiked side walks while the 
        other sideremains still.
        
        """
        FRACTION_WORM_SMOOTH = 1.0/12.0
        SMOOTHING_ORDER = 3
        PERCENT_BACK_SEARCH = 0.3;
        PERCENT_FORWARD_SEARCH = 0.3;
        END_S1_WALK_PCT = 0.15;

        num_frames = len(h_ventral_contour) # == len(h_dorsal_contour)

        h_skeleton = [None] * num_frames
        h_widths = [None] * num_frames

        profile_times = {'sgolay':0, 
                         'transpose':0, 
                         'h__getBounds':0,
                         'compute_normal_vectors':0,
                         'h__getMatches':0,
                         'h__updateEndsByWalking':0,
                         'hstack':0,
                         'final calculations':0}


        for frame_index, (s1, s2) in \
                        enumerate(zip(h_ventral_contour, h_dorsal_contour)):
            
            # If the frame has no contour values, assign no skeleton 
            # or widths values
            if s1 is None:
                continue

            if len(s1) > 250:
                # Allow downsampling if the # of points is ridiculous
                # 200 points seems to be a good number
                # TODO
                pass
            #Smoothing of the contour
            #------------------------------------------            
            start = utils.timing_function()
            # Step 1: filter
            filter_width_s1 = utils.round_to_odd(s1.shape[1] * 
                                                 FRACTION_WORM_SMOOTH)    
            s1[0, :] = sgolay(s1[0, :], filter_width_s1, SMOOTHING_ORDER)
            s1[1, :] = sgolay(s1[1, :], filter_width_s1, SMOOTHING_ORDER)

            filter_width_s2 = utils.round_to_odd(s2.shape[1] * 
                                                 FRACTION_WORM_SMOOTH)    
            s2[0, :] = sgolay(s2[0, :], filter_width_s2, SMOOTHING_ORDER)
            s2[1, :] = sgolay(s2[1, :], filter_width_s2, SMOOTHING_ORDER)
            profile_times['sgolay'] += utils.timing_function()-start
            
            
            
            #Calculation of distances
            #-----------------------------------
            start = utils.timing_function()
            # TODO: Allow downsampling if the # of points is ridiculous
            # 200 points seems to be a good #
            # This operation gives us a matrix that is len(s1) x len(s2)
            dx_across = np.transpose(s1[0:1, :]) - s2[0, :]
            dy_across = np.transpose(s1[1:2, :]) - s2[1, :]
            d_across = np.sqrt(dx_across**2 + dy_across**2)
            dx_across = dx_across / d_across
            dy_across = dy_across / d_across
            profile_times['transpose'] += utils.timing_function()-start
            
            
            #Determining bounds for possible projection pairs
            #------------------------------------------------
            start = utils.timing_function()
            left_I, right_I = SkeletonCalculatorType1.h__getBounds(s1.shape[1],
                                                       s2.shape[1],
                                                       PERCENT_BACK_SEARCH,
                                                       PERCENT_FORWARD_SEARCH)

            profile_times['h__getBounds'] += utils.timing_function()-start
            start = utils.timing_function()

            
            # For each point on side 1, calculate normalized orthogonal values
            norm_x, norm_y = utils.compute_normal_vectors(s1)

            profile_times['compute_normal_vectors'] += utils.timing_function()-start
            start = utils.timing_function()

                   
            # For each point on side 1, find which side 2 the point pairs with
            dp_values1, match_I1 = \
                            SkeletonCalculatorType1.h__getMatches(s1, s2,
                                                      norm_x, norm_y,
                                                      dx_across, dy_across,
                                                      d_across,
                                                      left_I, right_I)

            profile_times['h__getMatches'] += utils.timing_function()-start
            start = utils.timing_function()


            I_1, I_2 = SkeletonCalculatorType1.h__updateEndsByWalking(d_across,
                                                          match_I1,
                                                          s1, s2,
                                                          END_S1_WALK_PCT)

            profile_times['h__updateEndsByWalking'] += utils.timing_function()-start
            start = utils.timing_function()

            # TODO: Make this a function
            # ------------------------------------
            # We're looking to the left and to the right to ensure that
            # things are ordered

            #                                    current is before next    
            is_good = np.hstack((True, np.array((I_2[1:-1] <= I_2[2:]) & \
            #                                    current after previous            
                                                (I_2[1:-1] >= I_2[:-2])), 
                                                 True))

            profile_times['hstack'] += utils.timing_function()-start
            start = utils.timing_function()
            
            I_1 = I_1[is_good]
            I_2 = I_2[is_good]
            
            s1_x  = s1[0, I_1]
            s1_y  = s1[1, I_1]
            s1_px = s2[0, I_2] #s1_pair x
            s1_py = s2[1, I_2]
        
            #Final calculations
            #-----------------------
            #TODO: Allow smoothing on x & y
            widths1 = np.sqrt((s1_px - s1_x)**2 + (s1_py - s1_y)**2) # Widths
            h_widths[frame_index] = widths1
            
            skeleton_x = 0.5 * (s1_x + s1_px)
            skeleton_y = 0.5 * (s1_y + s1_py)
            h_skeleton[frame_index] = np.vstack((skeleton_x, skeleton_y))

            profile_times['final calculations'] += utils.timing_function()-start


            # Optional plotting code
            if frame_index in frames_to_plot:
                fig = plt.figure()
                # ARRANGE THE PLOTS AS:
                # AX1 AX1 AX2
                # AX1 AX1 AX3
                ax1 = plt.subplot2grid((2,3), (0,0), rowspan=2, colspan=2)
                #ax2 = plt.subplot2grid((2,3), (0,2))
                ax3 = plt.subplot2grid((2,3), (1,2))
                ax1.set_title("Frame #%d of %d" % (frame_index,
                                                   len(h_ventral_contour)))

                # The points along one side of the worm
                ax1.scatter(s1[0,:], s1[1,:], marker='o', 
                            edgecolors='r', facecolors='none')
                # The points along the other side
                ax1.scatter(s2[0,:], s2[1,:], marker='o', 
                            edgecolors='b', facecolors='none')
                
                # To plot the widths, we need to run
                # plot([x1,x2],[y1,y2]), for each line segment
                for i in range(np.shape(s1_px)[0]):
                    ax1.plot([s1_px[i], s1_x[i]], [s1_py[i], s1_y[i]], 
                             color='g')

                # The skeleton points
                ax1.scatter(skeleton_x, skeleton_y, marker='D', 
                            edgecolors='b', facecolors='none')
                # The skeleton points, connected
                ax1.plot(skeleton_x, skeleton_y, color='navy')

                """
                # TODO: Jim's original method for plotting this was:
                # Width should really be plotted as a function of 
                # distance along the skeleton
                cum_dist = h__getSkeletonDistance(skeleton_x, skeleton_y)
                
                ax2.plot(cum_dist./cum_dist[-1], h_widths[frame_index], 
                         'r.-')
                hold on
                ax2.plot(np.linspace(0,1,49), nw_widths[:,iFrame], 'g.-')
                hold off
                """

                # Now let's plot each of the 200+ width values as the 
                # y coordinate.
                ax3.set_title = "Worm width at each calculation point"
                ax3.set_xlabel("Calculation point")
                ax3.set_ylabel("Width")
                with plt.style.context('fivethirtyeight'):
                    ax3.plot(h_widths[frame_index], color='green', 
                             linewidth=2)

                plt.show()
            
        print(profile_times)
        return (h_widths, h_skeleton)    

    @staticmethod
    def h__getBounds(n1, n2, p_left, p_right):
        """
        Returns slice starts and stops
        #TODO: Rename everything to start and stop

        Parameters
        ---------------
        n1:
        n2:
        p_left:
        p_right:

        Returns
        ---------------
        left_I, right_I

        """
        pct = np.linspace(0, 1, n1)
        left_pct = pct - p_left
        right_pct = pct + p_right

        left_I = np.floor(left_pct*n2)
        right_I = np.ceil(right_pct*n2)
        left_I[left_I < 0] = 0;
        right_I[right_I >= n2] = n2 - 1
        
        return left_I, right_I
    
    @staticmethod
    def h__getMatches(s1, s2, 
                      norm_x, norm_y, 
                      dx_across, dy_across, 
                      d_across, 
                      left_I, right_I):
        """
        For a given frame,        
        For each point on side 1, find which side 2 the point pairs with
        
        Parameters
        ---------------
        s1: a list of coordinates
        s2: a list of coordinates
        norm_x:
        norm_y:
        dx_across:
        dy_across:
        d_across:
        left_I:
        right_I:
        
        Returns
        ---------------        
        (dp_values, match_I)
        
        """
        n_s1 = s1.shape[1]
        match_I = np.zeros(n_s1,dtype=np.int)
        match_I[0] = 0
        match_I[-1] = s2.shape[1]
        
        dp_values = np.zeros(n_s1)
        all_signs_used = np.zeros(n_s1)

        #There is no need to do the first and last point
        for I, (lb, rb) in enumerate(zip(left_I[1:-1], right_I[1:-1])):

            I = I + 1
            [abs_dp_value, dp_I, sign_used] = SkeletonCalculatorType1.\
                h__getProjectionIndex(norm_x[I], norm_y[I],
                                      dx_across[I,lb:rb], dy_across[I,lb:rb],
                                      lb, 
                                      d_across[I,lb:rb], 0)
            all_signs_used[I] = sign_used
            dp_values[I] = abs_dp_value
            match_I[I] = dp_I
            
        if not np.all(all_signs_used[1:-1] == all_signs_used[1]):
            if np.sum(all_signs_used) > 0:
                sign_use = 1
                I_bad = utils.find(all_signs_used[1:-1] != 1) + 1
            else:
                I_bad = utils.find(all_signs_used[1:-1] != -1) + 1
                sign_use = -1
                
            for I in I_bad:    
                lb = left_I[I]
                rb = right_I[I]
                [abs_dp_value, dp_I, sign_used] = SkeletonCalculatorType1.\
                  h__getProjectionIndex(norm_x[I], norm_y[I],
                                        dx_across[I,lb:rb], dy_across[I,lb:rb],
                                        lb,
                                        d_across[I,lb:rb], sign_use)
                all_signs_used[I] = sign_used
                dp_values[I] = abs_dp_value
                match_I[I] = dp_I    


        return (dp_values, match_I)
    
    @staticmethod
    def h__getProjectionIndex(vc_dx_ortho, vc_dy_ortho, 
                              dx_across_worm, dy_across_worm,
                              left_I, d_across, sign_use):
        """
        
        Matlab code:
        nvc_local = nvc(nvc_indices_use,:);
        
        dx_across_worm = cur_point(1) - nvc_local(:,1);
        dy_across_worm = cur_point(2) - nvc_local(:,2);
        
        d_magnitude = sqrt(dx_across_worm.^2+dy_across_worm.^2);
        
        dx_across_worm = dx_across_worm./d_magnitude;
        dy_across_worm = dy_across_worm./d_magnitude;
        
        """
                
        #SPEED: Compute normalized distances for all pairs ...
        #Might need to downsample
        
        dp = dx_across_worm*vc_dx_ortho + dy_across_worm*vc_dy_ortho;
        
        # I'd like to not have to do this step, it has to do with 
        # the relationship between the vulva and non-vulva side. This 
        # should be consistent across the entire animal and could be 
        # passed in, unless the worm rolls.
        sign_used = -1;
        if sign_use == 0 and np.sum(dp) > 0:
            # Instead of multiplying by -1 we could hardcode the flip of 
            # the logic below (e.g. max instead of min, > vs <)
            dp = -1*dp
            sign_used = 1
        elif sign_use == 1:
            dp = -1*dp
            sign_used = 1
        
        # This is slow, presumably due to the memory allocation ...
        #                   < right                     
        #possible = [dp(1:end-1) < dp(2:end) false] & \
        #                   < left
        #           [false dp(2:end) < dp(1:end-1)]
        
        # In Matlab:
        #possible = (dp(2:end-1) < dp(3:end)) & (dp(2:end-1) < dp(1:end-2));
        possible = (dp[1:-2] < dp[2:-1]) & (dp[1:-2] < dp[0:-3])
        
        Ip = utils.find(possible)
        if len(Ip) == 1:
            dp_I = Ip+1
            dp_value = dp[dp_I]
        elif len(Ip) > 1:
            temp_I = np.argmin(d_across[Ip])
            dp_I = Ip[temp_I]+1
            dp_value = dp[dp_I]
        else:
            dp_I = np.argmin(dp)
            dp_value = dp[dp_I]
        
        I = left_I + dp_I
    
        return (dp_value,I,sign_used)
    
    @staticmethod
    def h__updateEndsByWalking(d_across, match_I1, s1, s2, END_S1_WALK_PCT):
        
        """
        Update ends by walking.
        
        Parameters
        ----------
        d_across:
        match_I1:
        s1: list of numpy arrays, with the arrays having shape (2,ki)
            One side of the contour.  ki is the number of points in frame i
        s2: list of numpy arrays, with the arrays having shape (2,ki)
            The other side of the contour.  ki is the number of points in 
            frame i
        END_S1_WALK_PCT:
        
        Returns
        -------
        (I_1, I_2)
        
        """
        n_s1 = s1.shape[1]
        n_s2 = s2.shape[1]
        
        
        end_s1_walk_I = np.ceil(n_s1*END_S1_WALK_PCT)
        end_s2_walk_I = 2*end_s1_walk_I
        p1_I, p2_I = SkeletonCalculatorType1.h__getPartnersViaWalk(0, end_s1_walk_I,
                                                       0, end_s2_walk_I,
                                                       d_across,
                                                       s1, s2)
        
        match_I1[p1_I] = p2_I
        
        keep_mask = np.zeros(len(match_I1), dtype=np.bool)
        keep_mask[p1_I] = True
        
        # Add
        end_s1_walk_backwards = n_s1 - end_s1_walk_I + 1
        end_s2_walk_backwards = n_s2 - end_s2_walk_I + 1
        
        
        p1_I,p2_I = \
            SkeletonCalculatorType1.h__getPartnersViaWalk(n_s1-1, end_s1_walk_backwards,
                                              n_s2-1, end_s2_walk_backwards,
                                              d_across,
                                              s1, s2)

        match_I1[p1_I] = p2_I
        keep_mask[p1_I] = True
        
        # Anything in between we'll use the projection appproach
        keep_mask[end_s1_walk_I+1:end_s1_walk_backwards] = True
        
        # Always keep ends
        keep_mask[0]   = True
        keep_mask[-1] = True
    
        match_I1[0] = 0
        match_I1[-1] = n_s2-1
        
    
        # This isn't perfect but it removes some back and forth behavior
        # of the matching. We'd rather drop points and smooth
        I_1 = utils.find(keep_mask)
        I_2 = match_I1[keep_mask]

        return (I_1,I_2)
        
    @staticmethod
    def h__getPartnersViaWalk(s1, e1, s2, e2, d, xy1, xy2):
        """
        
        Intro
        -----
        This is is an implentation of:
        https://github.com/JimHokanson/SegwormMatlabClasses/blob/master/%2Bseg_worm/%2Bcv/skeletonize.m
        
        In the SegWorm code this is the main algorithm for going from a 
        contour to a skeleton (and widths). However in this implementation
        it only gets called for the head and tail. The original implementation
        calls this code many times after dividing the worm up into chunks
        based on finding large bend angles and the midpoint of the worm.        
        
        Why used here
        -------------
        This is used at the ends rather than the projection as the projection
        is looking for a line that is orthogonal to the slope of the contour
        that makes a nice bisection of the worm. However at the ends this
        falls apart. Consider a worm that is slighly like a diamond and how
        the lines that are orthgonal to the end points form horrible lines
        for widths estimation.
        
        
        Example contour of the head or tail with a bit of the body:
        
              /\        
             /\ \           
            /  \ \
           |    \ |    
           |     \| #Bad    
           |------| #Good    
           
        The hypen line  is orthogonal to the left contour and provides a good
        estimate of a line that is orthogonal to the skeleton.
        
        The inner diagonal line is orthogonal to the left contour but is a poor
        choice for a line that is orthogonal to the skeleton.
        
        Algorithm
        ---------
        More on this can be found in Ev Yemini's thesis. The basic ideas is
        we start with pairs on both sides of the contour and ask whether or
        not each point on one side of the contour should partner with its
        current point or the next point on the other side, given the widths
        between them. Parterning
            
        Parameters
        ----------
        s1: start index for side 1
        e1: end index for side 1 (inclusive)
        s2: start index for side 2
        e2: end index for side 2 (inclusive)
        d: distance from I1 to I2 is d(I1,I2)

        Returns
        -------
        (p1_I, p2_I) tuple
            p1_I: numpy array
                Each element represents one of a pair of indices that 
                belong together. In other words p1_I[i] goes with p2_I[i]
    
        """

        # TODO: remove hardcode, base on max of e1-s1+1 
        p1_I = np.zeros(200, dtype=np.int)
        p2_I = np.zeros(200, dtype=np.int)
    
        c1 = s1 # Current 1 index
        c2 = s2 # Current 2 index
        cur_p_I = -1 # Current pair index
        
        while c1 != e1 and c2 != e2:
            cur_p_I += 1
            
            # We are either going up or down based on which end we are
            # starting from (beggining or end)
            if e1 < s1:
                next1 = c1-1
                next2 = c2-1        
            else:
                next1 = c1+1
                next2 = c2+1
            
            # JAH: At this point
            # Need to handle indexing () vs [] and indexing spans (if any)
            # as well as 0 vs 1 based indexing (if any)
            try:
                v_n1c1 = xy1[:,next1] - xy1[:,c1]
            except:
                import pdb
                pdb.set_trace()
                
            v_n2c2 = xy2[:,next2] - xy2[:,c2]
            
            #216,231
            d_n1n2 = d[next1,next2]
            d_n1c2 = d[next1,c2]
            d_n2c1 = d[c1,next2]
            
            
            if d_n1c2 == d_n2c1 or (d_n1n2 <= d_n1c2 and d_n1n2 <= d_n2c1):
                #Advance along both contours
                
                p1_I[cur_p_I] = next1;
                p2_I[cur_p_I] = next2;
                
                c1 = next1;
                c2 = next2;
                
            elif np.sum((v_n1c1*v_n2c2) > 0):
                # Contours go similar directions
                # Follow smallest width
                if d_n1c2 < d_n2c1:
                    # Consume smaller distance, then move the base of the
                    # vector further forward
                    p1_I[cur_p_I] = next1
                    p2_I[cur_p_I] = c2
                    
                    # This bit always confuses me
                    # c1  n1
                    #
                    #
                    # c2  x  x  x  n2
                    #
                    # Advance c1 so that d_n2_to_c1 is smaller next time
                    c1 = next1
                else:
                    p1_I[cur_p_I] = c1
                    p2_I[cur_p_I] = next2
                    c2 = next2
            else:
                
                if cur_p_I == 1:
                    prev_width = 0
                else:
                    prev_width = d[p1_I[cur_p_I-1],p2_I[cur_p_I-1]]

                if (d_n1c2 > prev_width and d_n2c1 > prev_width):
                    p1_I[cur_p_I] = next1
                    p2_I[cur_p_I] = next2
                    
                    c1 = next1
                    c2 = next2
                elif d_n1c2 < d_n2c1:
                    p1_I[cur_p_I] = next1
                    p2_I[cur_p_I] = c2
                    c1 = next1
                else:
                    p1_I[cur_p_I] = c1
                    p2_I[cur_p_I] = next2
                    c2 = next2

        p1_I = p1_I[:cur_p_I]
        p2_I = p2_I[:cur_p_I]
        
        return (p1_I, p2_I)
        #p1_I[cur_p_I+1:] = []
        #p2_I[cur_p_I+1:] = []    
    