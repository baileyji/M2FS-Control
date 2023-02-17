#!/usr/bin/env python3
import time
import numpy as np
import matplotlib.pyplot as plt
from astropy.io import fits
# from scipy.optimize import curve_fit
# from skimage.feature import peak_local_max
# from scipy.ndimage import label, morphology
# from scipy.ndimage import gaussian_filter1d, median_filter
# from scipy.ndimage import grey_closing, binary_closing, binary_opening
# from scipy.signal import find_peaks, peak_widths
import argparse
from glob import glob
import os.path
import socket
from datetime import datetime
import sys
import scipy.ndimage
import pickle
from skimage.transform import hough_circle, hough_circle_peaks
from skimage.feature import canny
from bs4 import BeautifulSoup
import requests

VICUNA_PATH = 'http://vicuna.lco.cl/~mag2op/images/'
VICUNA_IMAGENAME = 'mg1{yyyy}{mm}{dd}{hhhh}{num}.fits'

USER_ACQ_OFFSET = [-8, -11]  # Nudge from looking at second GCAM IMAGE PLOT

# Divide by two because image has half the dimensions of the GCAM GUI

GUIDE_CENTERS = ((179 // 2, 207 // 2),  # G1, G2
                 (854 // 2, 202 // 2))
ALIGN_CENTERS = ((194, 334),
                 (233, 371),
                 (233, 425),
                 (194, 461),
                 (322, 334),
                 (285, 371),
                 (285, 425),
                 (322, 461))

ACQ_HALF_WID = 10
GUIDE_HALF_WID = 24


def parse_cl():
    parser = argparse.ArgumentParser(description='Rotation Series Analyzer',
                                     add_help=True,
                                     formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-p', dest='poll', default=False,
                        required=False, action='store_true',
                        help='Poll and save GCAM1 Box Positions')
    parser.add_argument('-d', dest='dir', default='./',
                        action='store', required=False, type=str,
                        help='Input file directory')
    parser.add_argument('-g', dest='gim', default='',
                        action='store', required=False, type=str,
                        help='Guide probe center image')
    parser.add_argument('-f', dest='fetch', default=False,
                        action='store_true', required=False,
                        help='Download files from Vicuna')

    return parser.parse_args()


def fetch_files(ext='fits', url=VICUNA_PATH):
    print(f'Fetching {ext} file list from {url}...')
    try:
        page = requests.get(url).text
        soup = BeautifulSoup(page, 'html.parser')
        x = [node.get('href') for node in soup.find_all('a') if node.get('href').endswith(ext)]
        ret=list(filter(lambda x: x.split('/')[-1].startswith('mg1'), x))
    except Exception as e:
        print(f'Failed to fetch camera file names due to {e}')
        ret = []
    print('Done')
    return ret


def dl_file(name, url=VICUNA_PATH):
    try:
        response = requests.get(url + name)
        with open(name, 'wb') as f:
            f.write(response.content)
    except Exception as e:
        print(f'Failed to fetch file {name} due to {e}')


# def find_rotation(files, args):
#
#     #Finding settings
#     xslice=slice(args.x0,args.x0+args.xw)
#     yslice=slice(args.y0,args.y0+args.yw)
#
#     rotation_data=[]
#     for f in files:
#
#         print('Processing {}'.format(f))
#
#         #fetch image
#         header=fits.getheader(f)
#         im=fits.getdata(f)
#
#         #Get the counts
#         rotation_data.append(header['ROTATOR'], im[xslice,yslice].sum())
#
#     rotation_data=np.array(rotation_data)
#
#     cx=np.polyfit(rotation_data[:,0], rotation_data[:,1], 2)
#     min_x=-cx[1]/cx[0]/2
#     print('Processed {}'.format(files))
#     print('Best rotation @ {:.1f}'.format(min_x))
#
#     for r in rotation_data:
#         print('Focus: {}  {}.'.format(*r))


def extract_acq_regions(im, centers, hw):
    r = np.array(centers)[..., None] + np.array([-hw, hw + 1])
    sl = [list(map(lambda x: slice(*x), a)) for a in r.round().astype(int)]
    return [im[s[0], s[1]] for s in sl]


def showim(x, a, b, show=True):
    plt.imshow(x, origin='lower', vmin=np.percentile(x, a), vmax=np.percentile(x, b))
    plt.colorbar()
    if show:
        plt.show()


def ut_to_totalseconds(ut):
    x = datetime.strptime(ut, '%H:%M:%S')
    return x.hour * 3600 + x.minute * 60 + x.second


def query_tcs_box(s):
    s.send('ut\n'.encode('utf8'))
    ut = s.recv(9).decode('utf8').strip()
    s.send('c2box\n'.encode('utf8'))
    box = s.recv(9).decode('utf8').strip()
    s.send('rotofh\n'.encode('utf8'))
    rotoff = float(s.recv(10).decode('utf8').strip())
    seconds = ut_to_totalseconds(ut)
    box = int(box[:4]) / 10, int(box[4:]) / 10
    return (seconds,) + box + (rotoff,)


def find_guides(image, plot=False):
    edges = canny(image, sigma=3, low_threshold=.25, high_threshold=.75, use_quantiles=True)

    # Detect two radii
    hough_radii = np.linspace(70, 90, 20)
    hough_res = hough_circle(edges, hough_radii)

    # Select the most prominent 2 circles
    accums, cx, cy, radii = hough_circle_peaks(hough_res, hough_radii, total_num_peaks=2)

    if plot:
        showim(image, 1, 99, show=False)
        ax = plt.gca()
        for center_y, center_x, radius in zip(cy, cx, radii):
            ax.add_patch(plt.Circle((center_x, center_y), radius, color='r', fill=False))
        print('ACQ boxes informational ONLY! NOT COMPUTED')
        for ctr in ALIGN_CENTERS:
            ax.add_patch(plt.Rectangle(ctr, 2 * ACQ_HALF_WID, 2 * ACQ_HALF_WID, color='r', fill=False))

        plt.show()
        print('Close Window to continue')
    if cx[1] < cx[0]:
        cx = cx[::-1]
        cy = cy[::-1]
        radii = radii[::-1]
    return np.array([v for v in zip(cx, cy, radii)])


SCATTER = (250, 250)
SCATTER_HWID = (100, 50)
BOARDER = (30, 10)

border = (30, 10)
closing_shape = (5, 5)
opening_shape = (2, 2)


def poll_tcs(start_file=''):
    s = None
    data = {'bounds': []}
    interrupt_count = 0
    ut = ''
    while True:
        try:
            if s is None:
                s = socket.create_connection(('mag2tcs.lco.cl', 5800), timeout=.6)
            ut, x, y, rotoff = query_tcs_box(s)
            data[ut] = (x, y, rotoff)
            time.sleep(1)
        except TimeoutError:
            print('TCS Timeout')
            try:
                s.close()
            except:
                pass
            s = None
        except KeyboardInterrupt:
            if interrupt_count > 2:
                break
            else:
                print('Inserting marker')
                data['bounds'].append(ut)
                interrupt_count += 1
    try:
        s.close()
    except:
        pass
    data['start_file'] = start_file
    with open(os.path.join(args.dir, 'box_capture.pickle'), 'wb') as f:
        pickle.dump(data, f, pickle.HIGHEST_PROTOCOL)


if __name__ == '__main__':

    args = parse_cl()

    if args.poll:
        files = fetch_files()
        print(f'Polling TCS, starting file {files[-1]}')
        print('Press Ctrl+C to insert timestamps for\n'
              '  1. \n'
              '  2. \n'
              '  3. \n'
              '  4. To Finish\n')
        poll_tcs(start_file=files[-1])
        sys.exit(0)

    tcs_data = {}
    try:
        with open(os.path.join(args.dir, 'box_capture.pickle'), 'rb') as f:
            tcs_data = pickle.load(f)
    except IOError:
        print("Couldn't load TCS data, are you working in the directory with box_capture.pickle?")

    if args.fetch:
        files = fetch_files()
        for f in files:
            if f >= tcs_data.get('start_file', 'mg1202302130920180444.fits'):
                dl_file(f)

    if args.gim:
        guides = find_guides(fits.getdata(args.gim), plot=True)
        print(f'Guide centers were previously:\n {np.array(GUIDE_CENTERS) * 2}')
        print(f'Found guide centers: \n {guides * 2}')

        shift = guides[:, :2] - np.array(GUIDE_CENTERS)
        print(f'Shift of\n{shift * 2} (mean {2 * shift.mean(0)})')
        print('Updating ACQ Boxes, boxes at:')
        ALIGN_CENTERS = (np.array(ALIGN_CENTERS) + shift.mean(0) + USER_ACQ_OFFSET).round()
        ALIGN_CENTERS = tuple(tuple(x) for x in ALIGN_CENTERS.astype(int).tolist())
        print(ALIGN_CENTERS)
        GUIDE_CENTERS = guides[:, :2]
        guides = find_guides(fits.getdata(args.gim), plot=True)

    files = glob(os.path.join(args.dir, 'mg1*.fits'))

    print('Running on {}'.format(files))

    if not isinstance(tcs_data, dict) and tcs_data is not None:
        tcs_data = {x[0]: x[1:] for x in tcs_data}

        # early trials didn't have this data captured
        if not len(list(tcs_data.values())[0]) == 3:
            for k in tcs_data:
                tcs_data[k] = tcs_data[k] + (0,)

    data = {}

    max_tcs_time = max([k for k in tcs_data if isinstance(k,int)])

    coadd = None
    for f in files:
        file_time_str = os.path.basename(f).replace('mg1','').partition('.')[0]
        file_time = datetime.strptime(file_time_str, '%Y%m%d%H%M%S%f')
        file_total_seconds = ut_to_totalseconds(file_time.strftime('%H:%M:%S'))
        if file_total_seconds > max_tcs_time:
            print(f'Skipping {f} as it is from after TCS Data window')
            continue

        hdu = fits.open(f)[0]
        id = ut_to_totalseconds(hdu.header['UT'])
        rot = hdu.header['ROTATOR']
        im = hdu.data
        if im.shape[0] < 500:
            print(f'Skipping {f} as it is has a weird image shape')
            continue

        sw = np.array(SCATTER_HWID)
        s = (np.array(SCATTER)[..., None] + np.array([-sw, sw])).T
        background = im[slice(*s[1]), slice(*s[0])]

        noise = background.std() * 3
        mean = background.mean()

        acq_im = extract_acq_regions(im.T, ALIGN_CENTERS, ACQ_HALF_WID)

        guide_im = extract_acq_regions(im.T, GUIDE_CENTERS, GUIDE_HALF_WID)

        guide_ctrs = np.array([scipy.ndimage.center_of_mass(gim) for gim in guide_im])
        guide_ctrs += np.array(GUIDE_CENTERS) - GUIDE_HALF_WID - .5
        delta = np.diff(guide_ctrs, axis=0)[0]
        guide_slope = delta[1] / delta[0]

        data[id] = (rot, guide_ctrs, guide_slope, mean, np.array([x.mean() for x in acq_im]))
        if coadd is None:
            coadd = np.zeros_like(im, dtype=float)
        coadd += im - mean

    reference_slope = np.diff(GUIDE_CENTERS, axis=0)[0]
    reference_slope = reference_slope[1] / reference_slope[0]

    acq_sec = np.array(list(data.keys()))
    acq_fluxes = np.array([(x[-1] - x[-2]).clip(0) for x in data.values()])
    rot = np.array([x[0] for x in data.values()])
    guide_ctrs = np.array([x[1] for x in data.values()])
    guide_slopes = np.array([x[2] for x in data.values()])
    acq_fluxes -= acq_fluxes.min(0)
    active_acq = acq_fluxes.max(0) > acq_fluxes.mean(0).std()
    active_acq_num = (active_acq.nonzero()[0] + 1).tolist()
    print(f'Acquisitions active: {active_acq_num}')

    ndx = acq_sec.argsort()
    rot = rot[ndx]
    acq_sec = acq_sec[ndx]
    acq_fluxes = acq_fluxes[ndx]
    guide_ctrs = guide_ctrs[ndx]
    guide_slopes = guide_slopes[ndx]

    rot -= np.poly1d(np.polyfit(np.arange(rot.size), rot, 1))(np.arange(rot.size))

    box_pos = np.array([tcs_data.get(s, (np.nan, np.nan))[:2] for s in acq_sec])
    rotoff = np.array([tcs_data.get(s, (0, 0, np.nan))[2] for s in acq_sec])
    rotoff -= np.nanmin(rotoff)
    final_pos = box_pos[np.isfinite(box_pos.sum(1))][-1]
    # box_pos -= np.nanmedian(box_pos, axis=0)
    box_pos -= final_pos

    acq_sec -= acq_sec.min()

    mean_norm_flux = (acq_fluxes[:, active_acq] / acq_fluxes[:, active_acq].max(0)).mean(1)

    showim(coadd / len(files), 1, 99, show=False)
    for i in active_acq_num:
        plt.gca().add_patch(plt.Rectangle(ALIGN_CENTERS[i-1], 2 * ACQ_HALF_WID, 2 * ACQ_HALF_WID, color='r', fill=False))
    plt.title('Coadded image')
    plt.show()

    fig, axes = plt.subplots(4, 1, figsize=(14, 9))
    plt.sca(axes[0])
    plt.plot(acq_sec, box_pos[:, 0], label='X')
    plt.plot(acq_sec, box_pos[:, 1], label='Y')
    plt.ylabel('Box Position')
    plt.title('Acquisition Data')
    # plt.sca(axes[1])
    # plt.plot(acq_sec, acq_fluxes[:,active_acq], label=[f'A{i}' for i in active_acq_num])
    # plt.ylabel('Flux (counts)')
    # plt.legend()
    # plt.ylim(0, None)
    plt.sca(axes[1])
    plt.plot(acq_sec, acq_fluxes[:, active_acq] / acq_fluxes[:, active_acq].max(0),
             label=[f'A{i}' for i in active_acq_num], linewidth=.5)
    plt.plot(acq_sec, mean_norm_flux, label='Mean', color='black')
    plt.xlabel('Time (s)')
    plt.ylabel('Relative flux')
    plt.legend(loc='center left')
    plt.ylim(0, 1.1)

    plt.sca(axes[2])
    plt.plot(acq_sec, rot, label='Rotator')
    plt.plot(acq_sec, rotoff, label='Rotator Offset')
    plt.legend()
    plt.ylabel('Rotator (deg)')
    plt.sca(axes[3])
    plt.plot(acq_sec, guide_slopes, label='Guide Star Slope')
    plt.axhline(reference_slope, color='k')
    plt.xlabel('Time (s)')
    plt.ylabel('Guide Slope')
    plt.legend()
    plt.show()

    time_mask = acq_sec > 150
    use = np.isfinite(box_pos.sum(1)) & (np.abs(box_pos[:, 0]) < 15) & (np.abs(box_pos[:, 1]) < 15)
    # use &=time_mask

    f, ax = plt.subplots(1, 2, figsize=(8, 4))
    plt.sca(ax[0])
    xgrid = np.arange(box_pos[use, 0].min(), box_pos[use, 0].max() + 2)
    x = scipy.stats.binned_statistic(box_pos[use, 0], mean_norm_flux[use],
                                     statistic=lambda x: np.percentile(x, 90), bins=xgrid)
    plt.plot(xgrid[:-1], x.statistic, '.')
    u = np.isfinite(x.statistic)
    plt.plot(xgrid[:-1], np.poly1d(np.polyfit(xgrid[:-1][u], x.statistic[u], 2))(xgrid[:-1]))
    plt.axvline(box_pos[use][-1, 0], color='k')
    plt.title('X')
    plt.xlabel('Position (final relative)')
    plt.sca(ax[1])

    grid = np.arange(box_pos[use, 1].min(), box_pos[use, 1].max() + 2)
    x = scipy.stats.binned_statistic(box_pos[use, 1], mean_norm_flux[use],
                                     statistic=lambda x: np.percentile(x, 90), bins=grid)
    plt.plot(grid[:-1], x.statistic, '.')
    u = np.isfinite(x.statistic)
    plt.plot(grid[:-1], np.poly1d(np.polyfit(grid[:-1][u], x.statistic[u], 2))(grid[:-1]))
    plt.axvline(box_pos[use][-1, 1], color='k')
    plt.title('Y')
    plt.xlabel('Position (final relative)')
    plt.show()
