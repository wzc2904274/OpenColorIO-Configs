#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Defines objects creating the *ACES* configuration.
"""

import math
#import numpy
import os
#import pprint
import shutil
import string
import sys

import PyOpenColorIO as ocio

import aces_ocio.create_aces_colorspaces as aces
import aces_ocio.create_arri_colorspaces as arri
import aces_ocio.create_canon_colorspaces as canon
import aces_ocio.create_red_colorspaces as red
import aces_ocio.create_sony_colorspaces as sony
import aces_ocio.create_general_colorspaces as general

from aces_ocio.generate_lut import (
    generate_1d_LUT_from_CTL,
    generate_3d_LUT_from_CTL,
    write_SPI_1d)
from aces_ocio.process import Process
from aces_ocio.utilities import ColorSpace, mat44_from_mat33, sanitize_path, compact

__author__ = 'ACES Developers'
__copyright__ = 'Copyright (C) 2014 - 2015 - ACES Developers'
__license__ = ''
__maintainer__ = 'ACES Developers'
__email__ = 'aces@oscars.org'
__status__ = 'Production'

__all__ = ['ACES_OCIO_CTL_DIRECTORY_ENVIRON',
           'ACES_OCIO_CONFIGURATION_DIRECTORY_ENVIRON',
           'set_config_default_roles',
           'write_config',
           'generate_OCIO_transform',
           'create_config',
           'generate_LUTs',
           'generate_baked_LUTs',
           'create_config_dir',
           'get_transform_info',
           'get_ODT_info',
           'get_LMT_info',
           'create_ACES_config',
           'main']

ACES_OCIO_CTL_DIRECTORY_ENVIRON = 'ACES_OCIO_CTL_DIRECTORY'
ACES_OCIO_CONFIGURATION_DIRECTORY_ENVIRON = 'ACES_OCIO_CONFIGURATION_DIRECTORY'


def set_config_default_roles(config,
                             color_picking='',
                             color_timing='',
                             compositing_log='',
                             data='',
                             default='',
                             matte_paint='',
                             reference='',
                             scene_linear='',
                             texture_paint=''):
    """
    Sets given *OCIO* configuration default roles.

    Parameters
    ----------
    config : config
        *OCIO* configuration.
    color_picking : str or unicode
        Color picking role title.
    color_timing : str or unicode
        Color timing role title.
    compositing_log : str or unicode
        Compositing log role title.
    data : str or unicode
        Data role title.
    default : str or unicode
        Default role title.
    matte_paint : str or unicode
        Matte painting role title.
    reference : str or unicode
        Reference role title.
    scene_linear : str or unicode
        Scene linear role title.
    texture_paint : str or unicode
        Texture painting role title.

    Returns
    -------
    bool
         Definition success.
    """

    if color_picking:
        config.setRole(ocio.Constants.ROLE_COLOR_PICKING, color_picking)
    if color_timing:
        config.setRole(ocio.Constants.ROLE_COLOR_TIMING, color_timing)
    if compositing_log:
        config.setRole(ocio.Constants.ROLE_COMPOSITING_LOG, compositing_log)
    if data:
        config.setRole(ocio.Constants.ROLE_DATA, data)
    if default:
        config.setRole(ocio.Constants.ROLE_DEFAULT, default)
    if matte_paint:
        config.setRole(ocio.Constants.ROLE_MATTE_PAINT, matte_paint)
    if reference:
        config.setRole(ocio.Constants.ROLE_REFERENCE, reference)
    if scene_linear:
        config.setRole(ocio.Constants.ROLE_SCENE_LINEAR, scene_linear)
    if texture_paint:
        config.setRole(ocio.Constants.ROLE_TEXTURE_PAINT, texture_paint)

    return True


def write_config(config, config_path, sanity_check=True):
    """
    Writes the configuration to given path.

    Parameters
    ----------
    parameter : type
        Parameter description.

    Returns
    -------
    type
         Return value description.
    """

    if sanity_check:
        try:
            config.sanityCheck()
        except Exception, e:
            print e
            print 'Configuration was not written due to a failed Sanity Check'
            return

    with open(config_path, mode='w') as fp:
        fp.write(config.serialize())


def generate_OCIO_transform(transforms):
    """
    Object description.

    Parameters
    ----------
    parameter : type
        Parameter description.

    Returns
    -------
    type
         Return value description.
    """

    interpolation_options = {
        'linear': ocio.Constants.INTERP_LINEAR,
        'nearest': ocio.Constants.INTERP_NEAREST,
        'tetrahedral': ocio.Constants.INTERP_TETRAHEDRAL
    }
    direction_options = {
        'forward': ocio.Constants.TRANSFORM_DIR_FORWARD,
        'inverse': ocio.Constants.TRANSFORM_DIR_INVERSE
    }

    ocio_transforms = []

    for transform in transforms:

        # lutFile transform
        if transform['type'] == 'lutFile':
            ocio_transform = ocio.FileTransform(
                src=transform['path'],
                interpolation=interpolation_options[
                    transform['interpolation']],
                direction=direction_options[transform['direction']])
            ocio_transforms.append(ocio_transform)
        
        # matrix transform
        elif transform['type'] == 'matrix':
            ocio_transform = ocio.MatrixTransform()
            # MatrixTransform member variables can't be initialized directly.
            # Each must be set individually.
            ocio_transform.setMatrix(transform['matrix'])

            if 'offset' in transform:
                ocio_transform.setOffset(transform['offset'])

            if 'direction' in transform:
                ocio_transform.setDirection(
                    direction_options[transform['direction']])

            ocio_transforms.append(ocio_transform)

        # exponent transform
        elif transform['type'] == 'exponent':
            ocio_transform = ocio.ExponentTransform()
            ocio_transform.setValue(transform['value'])
            ocio_transforms.append(ocio_transform)

        # log transform
        elif transform['type'] == 'log':
            ocio_transform = ocio.LogTransform(
                base=transform['base'],
                direction=direction_options[transform['direction']])

            ocio_transforms.append(ocio_transform)

        # color space transform
        elif transform['type'] == 'colorspace':
            ocio_transform = ocio.ColorSpaceTransform( src=transform['src'],
                dst=transform['dst'],
                direction=direction_options['forward'] )
            ocio_transforms.append(ocio_transform)

        # unknown type
        else:
            print("Ignoring unknown transform type : %s" % transform['type'])

    if len(ocio_transforms) > 1:
        group_transform = ocio.GroupTransform()
        for transform in ocio_transforms:
            group_transform.push_back(transform)
        transform = group_transform
    else:
        transform = ocio_transforms[0]

    return transform

def add_colorspace_alias(config, reference_colorspace, colorspace, colorspace_alias_names):
    """
    Object description.

    Parameters
    ----------
    parameter : type
        Parameter description.

    Returns
    -------
    type
         Return value description.
    """

    for alias_name in colorspace_alias_names:
        if alias_name == colorspace.name.lower():
            return

        print( "Adding alias colorspace space %s, alias to %s" % (
            alias_name, colorspace.name))

        compact_family_name = "Aliases"

        ocio_colorspace_alias = ocio.ColorSpace(
            name=alias_name,
            bitDepth=colorspace.bit_depth,
            description=colorspace.description,
            equalityGroup=colorspace.equality_group,
            family=compact_family_name,
            isData=colorspace.is_data,
            allocation=colorspace.allocation_type,
            allocationVars=colorspace.allocation_vars)

        if colorspace.to_reference_transforms != []:
            print("Generating To-Reference transforms")
            ocio_transform = generate_OCIO_transform([{
                'type': 'colorspace',
                'src': colorspace.name,
                'dst': reference_colorspace.name,
                'direction': 'forward'
                }])
            ocio_colorspace_alias.setTransform(
                ocio_transform,
                ocio.Constants.COLORSPACE_DIR_TO_REFERENCE)

        if colorspace.from_reference_transforms != []:
            print("Generating From-Reference transforms")
            ocio_transform = generate_OCIO_transform([{
                'type': 'colorspace',
                'src': reference_colorspace.name,
                'dst': colorspace.name,
                'direction': 'forward'
                }])
            ocio_colorspace_alias.setTransform(
                ocio_transform,
                ocio.Constants.COLORSPACE_DIR_FROM_REFERENCE)

        config.addColorSpace(ocio_colorspace_alias)


def create_config(config_data, nuke=False):
    """
    Object description.

    Parameters
    ----------
    parameter : type
        Parameter description.

    Returns
    -------
    type
         Return value description.
    """

    # Creating the *OCIO* configuration.
    config = ocio.Config()

    # Setting configuration overall values.
    config.setDescription('An ACES config generated from python')
    config.setSearchPath('luts')

    # Defining the reference colorspace.
    reference_data = config_data['referenceColorSpace']
    print('Adding the reference color space : %s' % reference_data.name)

    reference = ocio.ColorSpace(
        name=reference_data.name,
        bitDepth=reference_data.bit_depth,
        description=reference_data.description,
        equalityGroup=reference_data.equality_group,
        family=reference_data.family,
        isData=reference_data.is_data,
        allocation=reference_data.allocation_type,
        allocationVars=reference_data.allocation_vars)

    config.addColorSpace(reference)

    # Add alias
    if reference_data.aliases != []:
        add_colorspace_alias(config, reference_data,
            reference_data, reference_data.aliases)

    print("")

    # Creating the remaining colorspaces.
    for colorspace in sorted(config_data['colorSpaces']):
        print('Creating new color space : %s' % colorspace.name)

        ocio_colorspace = ocio.ColorSpace(
            name=colorspace.name,
            bitDepth=colorspace.bit_depth,
            description=colorspace.description,
            equalityGroup=colorspace.equality_group,
            family=colorspace.family,
            isData=colorspace.is_data,
            allocation=colorspace.allocation_type,
            allocationVars=colorspace.allocation_vars)

        if colorspace.to_reference_transforms:
            print('Generating To-Reference transforms')
            ocio_transform = generate_OCIO_transform(
                colorspace.to_reference_transforms)
            ocio_colorspace.setTransform(
                ocio_transform,
                ocio.Constants.COLORSPACE_DIR_TO_REFERENCE)

        if colorspace.from_reference_transforms:
            print('Generating From-Reference transforms')
            ocio_transform = generate_OCIO_transform(
                colorspace.from_reference_transforms)
            ocio_colorspace.setTransform(
                ocio_transform,
                ocio.Constants.COLORSPACE_DIR_FROM_REFERENCE)

        config.addColorSpace(ocio_colorspace)

        #
        # Add alias to normal colorspace, using compact name
        #
        if colorspace.aliases != []:
            add_colorspace_alias(config, reference_data, 
                colorspace, colorspace.aliases)

        print('')

    # Defining the *views* and *displays*.
    displays = []
    views = []

    # Defining a *generic* *display* and *view* setup.
    if not nuke:
        for display, view_list in config_data['displays'].iteritems():
            for view_name, colorspace in view_list.iteritems():
                config.addDisplay(display, view_name, colorspace.name)
                if not (view_name in views):
                    views.append(view_name)
            displays.append(display)

    # Defining the *Nuke* specific set of *views* and *displays*.
    else:
        for display, view_list in config_data['displays'].iteritems():
            for view_name, colorspace in view_list.iteritems():
                if view_name == 'Output Transform':
                    view_name = 'View'
                    config.addDisplay(display, view_name, colorspace.name)
                    if not (view_name in views):
                        views.append(view_name)
            displays.append(display)

        linear_display_space_name = config_data['linearDisplaySpace'].name
        log_display_space_name = config_data['logDisplaySpace'].name

        config.addDisplay('linear', 'View', linear_display_space_name)
        displays.append('linear')
        config.addDisplay('log', 'View', log_display_space_name)
        displays.append('log')

    # Setting the active *displays* and *views*.
    config.setActiveDisplays(','.join(sorted(displays)))
    config.setActiveViews(','.join(views))

    set_config_default_roles(
        config,
        color_picking=reference.getName(),
        color_timing=reference.getName(),
        compositing_log=reference.getName(),
        data=reference.getName(),
        default=reference.getName(),
        matte_paint=reference.getName(),
        reference=reference.getName(),
        scene_linear=reference.getName(),
        texture_paint=reference.getName())

    config.sanityCheck()

    return config

def generate_LUTs(odt_info,
                  lmt_info,
                  shaper_name,
                  aces_CTL_directory,
                  lut_directory,
                  lut_resolution_1d=4096,
                  lut_resolution_3d=64,
                  cleanup=True):
    """
    Object description.

    Parameters
    ----------
    parameter : type
        Parameter description.

    Returns
    -------
    dict
         Colorspaces and transforms converting between those colorspaces and
         the reference colorspace, *ACES*.
    """

    print('generateLUTs - begin')
    config_data = {}

    # Initialize a few variables
    config_data['displays'] = {}
    config_data['colorSpaces'] = []

    # -------------------------------------------------------------------------
    # *ACES Color Spaces*
    # -------------------------------------------------------------------------

    # *ACES* colorspaces
    (aces_reference,
     aces_colorspaces, 
     aces_displays,
     aces_log_display_space) = aces.create_colorspaces(aces_CTL_directory,
                                                       lut_directory, 
                                                       lut_resolution_1d,
                                                       lut_resolution_3d,
                                                       lmt_info,
                                                       odt_info,
                                                       shaper_name,
                                                       cleanup)

    config_data['referenceColorSpace'] = aces_reference

    for cs in aces_colorspaces:
        config_data['colorSpaces'].append(cs)

    for name, data in aces_displays.iteritems():
        config_data['displays'][name] = data

    config_data['linearDisplaySpace'] = aces_reference
    config_data['logDisplaySpace'] = aces_log_display_space

    # -------------------------------------------------------------------------
    # *Camera Input Transforms*
    # -------------------------------------------------------------------------

    # *Log-C* to *ACES*.
    arri_colorSpaces = arri.create_colorspaces(lut_directory,
                                               lut_resolution_1d)
    for cs in arri_colorSpaces:
        config_data['colorSpaces'].append(cs)

    # *Canon-Log* to *ACES*.
    canon_colorspaces = canon.create_colorspaces(lut_directory,
                                                 lut_resolution_1d)
    for cs in canon_colorspaces:
        config_data['colorSpaces'].append(cs)

    # *RED* colorspaces to *ACES*.
    red_colorspaces = red.create_colorspaces(lut_directory, 
                                             lut_resolution_1d)
    for cs in red_colorspaces:
        config_data['colorSpaces'].append(cs)

    # *S-Log* to *ACES*.
    sony_colorSpaces = sony.create_colorspaces(lut_directory,
                                               lut_resolution_1d)
    for cs in sony_colorSpaces:
        config_data['colorSpaces'].append(cs)

    # -------------------------------------------------------------------------
    # General Color Spaces
    # -------------------------------------------------------------------------
    general_colorSpaces = general.create_colorspaces(lut_directory,
                                                     lut_resolution_1d,
                                                     lut_resolution_3d)
    for cs in general_colorSpaces:
        config_data['colorSpaces'].append(cs)

    print('generateLUTs - end')
    return config_data


def generate_baked_LUTs(odt_info,
                        shaper_name,
                        baked_directory,
                        config_path,
                        lut_resolution_1d,
                        lut_resolution_3d,
                        lut_resolution_shaper=1024):
    """
    Object description.

    Parameters
    ----------
    parameter : type
        Parameter description.

    Returns
    -------
    type
         Return value description.
    """

    odt_info_C = dict(odt_info)
    for odt_CTL_name, odt_values in odt_info.iteritems():
        if odt_CTL_name in ['Academy.Rec2020_100nits_dim.a1.0.0',
                            'Academy.Rec709_100nits_dim.a1.0.0',
                            'Academy.Rec709_D60sim_100nits_dim.a1.0.0']:
            odt_name = odt_values['transformUserName']

            odt_values_legal = dict(odt_values)
            odt_values_legal['transformUserName'] = '%s - Legal' % odt_name
            odt_info_C['%s - Legal' % odt_CTL_name] = odt_values_legal

            odt_values_full = dict(odt_values)
            odt_values_full['transformUserName'] = '%s - Full' % odt_name
            odt_info_C['%s - Full' % odt_CTL_name] = odt_values_full

            del (odt_info_C[odt_CTL_name])

    for odt_CTL_name, odt_values in odt_info_C.iteritems():
        odt_prefix = odt_values['transformUserNamePrefix']
        odt_name = odt_values['transformUserName']

        # *Photoshop*
        for input_space in ['ACEScc', 'ACESproxy']:
            args = ['--iconfig', config_path,
                    '-v',
                    '--inputspace', input_space]
            args += ['--outputspace', '%s' % odt_name]
            args += ['--description',
                     '%s - %s for %s data' % (odt_prefix,
                                              odt_name,
                                              input_space)]
            args += ['--shaperspace', shaper_name,
                     '--shapersize', str(lut_resolution_shaper)]
            args += ['--cubesize', str(lut_resolution_3d)]
            args += ['--format',
                     'icc',
                     os.path.join(baked_directory,
                                  'photoshop',
                                  '%s for %s.icc' % (odt_name, input_space))]

            bake_LUT = Process(description='bake a LUT',
                               cmd='ociobakelut',
                               args=args)
            bake_LUT.execute()

        # *Flame*, *Lustre*
        for input_space in ['ACEScc', 'ACESproxy']:
            args = ['--iconfig', config_path,
                    '-v',
                    '--inputspace', input_space]
            args += ['--outputspace', '%s' % odt_name]
            args += ['--description',
                     '%s - %s for %s data' % (
                         odt_prefix, odt_name, input_space)]
            args += ['--shaperspace', shaper_name,
                     '--shapersize', str(lut_resolution_shaper)]
            args += ['--cubesize', str(lut_resolution_3d)]

            fargs = ['--format',
                     'flame',
                     os.path.join(
                         baked_directory,
                         'flame',
                         '%s for %s Flame.3dl' % (odt_name, input_space))]
            bake_LUT = Process(description='bake a LUT',
                               cmd='ociobakelut',
                               args=(args + fargs))
            bake_LUT.execute()

            largs = ['--format',
                     'lustre',
                     os.path.join(
                         baked_directory,
                         'lustre',
                         '%s for %s Lustre.3dl' % (odt_name, input_space))]
            bake_LUT = Process(description='bake a LUT',
                               cmd='ociobakelut',
                               args=(args + largs))
            bake_LUT.execute()

        # *Maya*, *Houdini*
        for input_space in ['ACEScg', 'ACES2065-1']:
            args = ['--iconfig', config_path,
                    '-v',
                    '--inputspace', input_space]
            args += ['--outputspace', '%s' % odt_name]
            args += ['--description',
                     '%s - %s for %s data' % (
                         odt_prefix, odt_name, input_space)]
            if input_space == 'ACEScg':
                lin_shaper_name = '%s - AP1' % shaper_name
            else:
                lin_shaper_name = shaper_name
            args += ['--shaperspace', lin_shaper_name,
                     '--shapersize', str(lut_resolution_shaper)]

            args += ['--cubesize', str(lut_resolution_3d)]

            margs = ['--format',
                     'cinespace',
                     os.path.join(
                         baked_directory,
                         'maya',
                         '%s for %s Maya.csp' % (odt_name, input_space))]
            bake_LUT = Process(description='bake a LUT',
                               cmd='ociobakelut',
                               args=(args + margs))
            bake_LUT.execute()

            hargs = ['--format',
                     'houdini',
                     os.path.join(
                         baked_directory,
                         'houdini',
                         '%s for %s Houdini.lut' % (odt_name, input_space))]
            bake_LUT = Process(description='bake a LUT',
                               cmd='ociobakelut',
                               args=(args + hargs))
            bake_LUT.execute()


def create_config_dir(config_directory, bake_secondary_LUTs):
    """
    Object description.

    Parameters
    ----------
    parameter : type
        Parameter description.

    Returns
    -------
    type
         Return value description.
    """

    lut_directory = os.path.join(config_directory, 'luts')
    dirs = [config_directory, lut_directory]
    if bake_secondary_LUTs:
        dirs.extend([os.path.join(config_directory, 'baked'),
                     os.path.join(config_directory, 'baked', 'flame'),
                     os.path.join(config_directory, 'baked', 'photoshop'),
                     os.path.join(config_directory, 'baked', 'houdini'),
                     os.path.join(config_directory, 'baked', 'lustre'),
                     os.path.join(config_directory, 'baked', 'maya')])

    for d in dirs:
        not os.path.exists(d) and os.mkdir(d)

    return lut_directory

def get_transform_info(ctl_transform):
    """
    Object description.

    Parameters
    ----------
    parameter : type
        Parameter description.

    Returns
    -------
    type
         Return value description.
    """

    with open(ctl_transform, 'rb') as fp:
        lines = fp.readlines()

    # Retrieving the *transform ID* and *User Name*.
    transform_id = lines[1][3:].split('<')[1].split('>')[1].strip()
    transform_user_name = '-'.join(
        lines[2][3:].split('<')[1].split('>')[1].split('-')[1:]).strip()
    transform_user_name_prefix = (
        lines[2][3:].split('<')[1].split('>')[1].split('-')[0].strip())

    return transform_id, transform_user_name, transform_user_name_prefix


def get_ODT_info(aces_CTL_directory):
    """
    Object description.

    For versions after WGR9.

    Parameters
    ----------
    parameter : type
        Parameter description.

    Returns
    -------
    type
         Return value description.
    """

    # TODO: Investigate usage of *files_walker* definition here.
    # Credit to *Alex Fry* for the original approach here.
    odt_dir = os.path.join(aces_CTL_directory, 'odt')
    all_odt = []
    for dir_name, subdir_list, file_list in os.walk(odt_dir):
        for fname in file_list:
            all_odt.append((os.path.join(dir_name, fname)))

    odt_CTLs = [x for x in all_odt if
                ('InvODT' not in x) and (os.path.split(x)[-1][0] != '.')]

    odts = {}

    for odt_CTL in odt_CTLs:
        odt_tokens = os.path.split(odt_CTL)

        # Handling nested directories.
        odt_path_tokens = os.path.split(odt_tokens[-2])
        odt_dir = odt_path_tokens[-1]
        while odt_path_tokens[-2][-3:] != 'odt':
            odt_path_tokens = os.path.split(odt_path_tokens[-2])
            odt_dir = os.path.join(odt_path_tokens[-1], odt_dir)

        # Building full name,
        transform_CTL = odt_tokens[-1]
        odt_name = string.join(transform_CTL.split('.')[1:-1], '.')

        # Finding id, user name and user name prefix.
        (transform_ID,
         transform_user_name,
         transform_user_name_prefix) = get_transform_info(
            os.path.join(aces_CTL_directory, 'odt', odt_dir, transform_CTL))

        # Finding inverse.
        transform_CTL_inverse = 'InvODT.%s.ctl' % odt_name
        if not os.path.exists(
                os.path.join(odt_tokens[-2], transform_CTL_inverse)):
            transform_CTL_inverse = None

        # Add to list of ODTs
        odts[odt_name] = {}
        odts[odt_name]['transformCTL'] = os.path.join(odt_dir, transform_CTL)
        if transform_CTL_inverse is not None:
            odts[odt_name]['transformCTLInverse'] = os.path.join(
                odt_dir, transform_CTL_inverse)

        odts[odt_name]['transformID'] = transform_ID
        odts[odt_name]['transformUserNamePrefix'] = transform_user_name_prefix
        odts[odt_name]['transformUserName'] = transform_user_name

        forward_CTL = odts[odt_name]['transformCTL']

        print('ODT : %s' % odt_name)
        print('\tTransform ID               : %s' % transform_ID)
        print('\tTransform User Name Prefix : %s' % transform_user_name_prefix)
        print('\tTransform User Name        : %s' % transform_user_name)
        print('\tForward ctl                : %s' % forward_CTL)
        if 'transformCTLInverse' in odts[odt_name]:
            inverse_CTL = odts[odt_name]['transformCTLInverse']
            print('\tInverse ctl                : %s' % inverse_CTL)
        else:
            print('\tInverse ctl                : %s' % 'None')

    print('\n')

    return odts


def get_LMT_info(aces_CTL_directory):
    """
    Object description.

    For versions after WGR9.

    Parameters
    ----------
    parameter : type
        Parameter description.

    Returns
    -------
    type
         Return value description.
    """

    # TODO: Investigate refactoring with previous definition.

    # Credit to Alex Fry for the original approach here
    lmt_dir = os.path.join(aces_CTL_directory, 'lmt')
    all_lmt = []
    for dir_name, subdir_list, file_list in os.walk(lmt_dir):
        for fname in file_list:
            all_lmt.append((os.path.join(dir_name, fname)))

    lmt_CTLs = [x for x in all_lmt if
                ('InvLMT' not in x) and ('README' not in x) and (
                    os.path.split(x)[-1][0] != '.')]

    lmts = {}

    for lmt_CTL in lmt_CTLs:
        lmt_tokens = os.path.split(lmt_CTL)

        # Handlimg nested directories.
        lmt_path_tokens = os.path.split(lmt_tokens[-2])
        lmt_dir = lmt_path_tokens[-1]
        while lmt_path_tokens[-2][-3:] != 'ctl':
            lmt_path_tokens = os.path.split(lmt_path_tokens[-2])
            lmt_dir = os.path.join(lmt_path_tokens[-1], lmt_dir)

        # Building full name.
        transform_CTL = lmt_tokens[-1]
        lmt_name = string.join(transform_CTL.split('.')[1:-1], '.')

        # Finding id, user name and user name prefix.
        (transform_ID,
         transform_user_name,
         transform_user_name_prefix) = get_transform_info(
            os.path.join(aces_CTL_directory, lmt_dir, transform_CTL))

        # Finding inverse.
        transform_CTL_inverse = 'InvLMT.%s.ctl' % lmt_name
        if not os.path.exists(
                os.path.join(lmt_tokens[-2], transform_CTL_inverse)):
            transform_CTL_inverse = None

        lmts[lmt_name] = {}
        lmts[lmt_name]['transformCTL'] = os.path.join(lmt_dir, transform_CTL)
        if transform_CTL_inverse is not None:
            lmts[lmt_name]['transformCTLInverse'] = os.path.join(
                lmt_dir, transform_CTL_inverse)

        lmts[lmt_name]['transformID'] = transform_ID
        lmts[lmt_name]['transformUserNamePrefix'] = transform_user_name_prefix
        lmts[lmt_name]['transformUserName'] = transform_user_name

        forward_CTL = lmts[lmt_name]['transformCTL']

        print('LMT : %s' % lmt_name)
        print('\tTransform ID               : %s' % transform_ID)
        print('\tTransform User Name Prefix : %s' % transform_user_name_prefix)
        print('\tTransform User Name        : %s' % transform_user_name)
        print('\t Forward ctl               : %s' % forward_CTL)
        if 'transformCTLInverse' in lmts[lmt_name]:
            inverse_CTL = lmts[lmt_name]['transformCTLInverse']
            print('\t Inverse ctl                : %s' % inverse_CTL)
        else:
            print('\t Inverse ctl                : %s' % 'None')

    print('\n')

    return lmts


def create_ACES_config(aces_CTL_directory,
                       config_directory,
                       lut_resolution_1d=4096,
                       lut_resolution_3d=64,
                       bake_secondary_LUTs=True,
                       cleanup=True):
    """
    Creates the ACES configuration.

    Parameters
    ----------
    parameter : type
        Parameter description.

    Returns
    -------
    type
         Return value description.
    """

    lut_directory = create_config_dir(config_directory, bake_secondary_LUTs)

    odt_info = get_ODT_info(aces_CTL_directory)
    lmt_info = get_LMT_info(aces_CTL_directory)

    shaper_name = 'Output Shaper'
    config_data = generate_LUTs(odt_info,
                                lmt_info,
                                shaper_name,
                                aces_CTL_directory,
                                lut_directory,
                                lut_resolution_1d,
                                lut_resolution_3d,
                                cleanup)

    print('Creating "generic" config')
    config = create_config(config_data)
    print('\n\n\n')

    write_config(config,
                 os.path.join(config_directory, 'config.ocio'))

    print('Creating "Nuke" config')
    nuke_config = create_config(config_data, nuke=True)
    print('\n\n\n')

    write_config(nuke_config,
                 os.path.join(config_directory, 'nuke_config.ocio'))

    if bake_secondary_LUTs:
        generate_baked_LUTs(odt_info,
                            shaper_name,
                            os.path.join(config_directory, 'baked'),
                            os.path.join(config_directory, 'config.ocio'),
                            lut_resolution_1d,
                            lut_resolution_3d,
                            lut_resolution_1d)

    return True


def main():
    """
    Object description.

    Parameters
    ----------
    parameter : type
        Parameter description.

    Returns
    -------
    type
         Return value description.
    """

    import optparse

    p = optparse.OptionParser(description='An OCIO config generation script',
                              prog='createACESConfig',
                              version='createACESConfig 0.1',
                              usage='%prog [options]')
    p.add_option('--acesCTLDir', '-a', default=os.environ.get(
        ACES_OCIO_CTL_DIRECTORY_ENVIRON, None))
    p.add_option('--configDir', '-c', default=os.environ.get(
        ACES_OCIO_CONFIGURATION_DIRECTORY_ENVIRON, None))
    p.add_option('--lutResolution1d', default=4096)
    p.add_option('--lutResolution3d', default=64)
    p.add_option('--dontBakeSecondaryLUTs', action='store_true')
    p.add_option('--keepTempImages', action='store_true')

    options, arguments = p.parse_args()

    aces_CTL_directory = options.acesCTLDir
    config_directory = options.configDir
    lut_resolution_1d = int(options.lutResolution1d)
    lut_resolution_3d = int(options.lutResolution3d)
    bake_secondary_LUTs = not options.dontBakeSecondaryLUTs
    cleanup_temp_images = not options.keepTempImages

    # TODO: Investigate the following statements.
    try:
        args_start = sys.argv.index('--') + 1
        args = sys.argv[args_start:]
    except:
        args_start = len(sys.argv) + 1
        args = []

    print('command line : \n%s\n' % ' '.join(sys.argv))

    assert aces_CTL_directory is not None, (
        'process: No "{0}" environment variable defined or no "ACES CTL" '
        'directory specified'.format(
            ACES_OCIO_CTL_DIRECTORY_ENVIRON))

    assert config_directory is not None, (
        'process: No "{0}" environment variable defined or no configuration '
        'directory specified'.format(
            ACES_OCIO_CONFIGURATION_DIRECTORY_ENVIRON))

    return create_ACES_config(aces_CTL_directory,
                              config_directory,
                              lut_resolution_1d,
                              lut_resolution_3d,
                              bake_secondary_LUTs,
                              cleanup_temp_images)


if __name__ == '__main__':
    main()