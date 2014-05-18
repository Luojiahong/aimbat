#!/usr/bin/env python
#------------------------------------------------
# Filename: qualctrl.py
#   Author: Xiaoting Lou
#    Email: xlou@u.northwestern.edu
#
# Copyright (c) 2009-2012 Xiaoting Lou
#------------------------------------------------
"""
Python module for interactively measuring body wave travel times and quality control.
Used by ttpick.py

	PickPhaseMenuMore
		||
	PickPhaseMenu + Buttons: ICCS-A  Sync  ICCS-B  MCCC  SACP2


:copyright:
	Xiaoting Lou

:license:
	GNU General Public License, Version 3 (GPLv3) 
	http://www.gnu.org/licenses/gpl.html
"""


from pylab import *
import os, sys, copy
from matplotlib.mlab import l2norm
from matplotlib.widgets import SpanSelector, Button, CheckButtons
from matplotlib import transforms
from matplotlib.font_manager import FontProperties
from ttconfig import PPConfig, QCConfig, CCConfig, MCConfig, getParser
from sacpickle import loadData, SacDataHdrs, taperWindow
from plotutils import TimeSelector, pickLegend
from plotphase import sacp2
from pickphase import PickPhase, PickPhaseMenu
from qualsort import initQual, seleSeis, sortSeisQual, sortSeisHeader, sortSeisHeaderDiff
from algiccs import ccWeightStack, checkCoverage
from algmccc import mccc, findPhase, eventListName, rcwrite

import Tkinter
import tkMessageBox

def getOptions():
	""" Parse arguments and options. """
	parser = getParser()
	maxsel = 37
	maxdel = 3
	maxnum = maxsel, maxdel
	twcorr = -15, 15
	sortby = '1'
	fill = 1
	reltime = 0
	xlimit = -30, 30
	parser.set_defaults(xlimit=xlimit)
	parser.set_defaults(twcorr=twcorr)
	parser.set_defaults(reltime=reltime)
	parser.set_defaults(maxnum=maxnum)
	parser.set_defaults(sortby=sortby)
	parser.set_defaults(fill=fill)
	parser.add_option('-b', '--boundlines', action="store_true", dest='boundlines_on',
		help='Plot bounding lines to separate seismograms.')
	parser.add_option('-n', '--netsta', action="store_true", dest='nlab_on',
		help='Label seismogram by net.sta code instead of SAC file name.')
	parser.add_option('-m', '--maxnum',  dest='maxnum', type='int', nargs=2,
		help='Maximum number of selected and deleted seismograms to plot. Defaults: {0:d} and {1:d}.'.format(maxsel, maxdel))
	parser.add_option('-p', '--phase',  dest='phase', type='str',
		help='Seismic phase name: P/S .')
	parser.add_option('-s', '--sortby', type='str', dest='sortby',
		help='Sort seismograms by i (file indices), or 0/1/2/3 (quality factor all/ccc/snr/coh), or t (time pick diff), or a given header (az/baz/dist..). Append - for decrease order, otherwise increase. Default is {:s}.'.format(sortby))
	parser.add_option('-t', '--twcorr', dest='twcorr', type='float', nargs=2,
		help='Time window for cross-correlation. Default is [{:.1f}, {:.1f}] s'.format(twcorr[0],twcorr[1]))
	parser.add_option('-g', '--savefig', action="store_true", dest='savefig',
		help='Save figure instead of showing.')
	opts, files = parser.parse_args(sys.argv[1:])
	if len(files) == 0:
		print parser.usage
		sys.exit()
	return opts, files

# ############################################################################### #
#                                                                                 #
#                              CLASS: PickPhaseMenuMore                           #
#                                                                                 #
# ############################################################################### #

class PickPhaseMenuMore:
	""" Pick phase for multiple seismograms and array stack
		Button: Sync
	"""
	def __init__(self, gsac, opts, axs):
		self.gsac = gsac
		self.opts = opts
		self.axs = axs
		self.axstk = self.axs['Fstk']
		if not 'stkdh' in gsac.__dict__:
			if opts.filemode == 'sac' and os.path.isfile(opts.fstack):
				gsac.stkdh = SacDataHdrs(opts.fstack, opts.delta)
			else:
				hdrini, hdrmed, hdrfin = opts.qcpara.ichdrs
				self.cchdrs = [hdrini, hdrmed]
				self.twcorr = opts.ccpara.twcorr
				# check data coverage
				opts.ipick = hdrini
				opts.twcorr = opts.ccpara.twcorr
				checkCoverage(gsac, opts) 
				gsac.selist = gsac.saclist
				self.ccStack()
		self.initPlot()
		self.plotStack()
		self.addEarthquakeInfo()
		self.setLabels()
		self.connect()

	def initPlot(self):
		""" Plot waveforms """
		gsac = self.gsac
		opts = self.opts
		sortSeis(gsac, opts)
		self.ppm = PickPhaseMenu(gsac, opts, self.axs)
		# make the legend box invisible
		if self.opts.pick_on:
			self.ppm.axpp.get_legend().set_visible(False)

	def addEarthquakeInfo(self):
		""" Set Earthquake Info
		  * Magnitude
		  * Location (Lat and Long)
		  * Depth
		"""
		gsac = self.gsac
		# get required parameters
		locationLat = round(gsac.event[6],2)
		locationLon = round(gsac.event[7],2)
		depth = round(gsac.event[8],2)
		magnitude = round(gsac.event[9],2)

		infoaxis = self.axs['Info']

		# remove axes markings
		infoaxis.axes.get_xaxis().set_ticks([])
		infoaxis.axes.get_yaxis().set_visible(False)

		# write the info into the axis plot
		infoaxis.text(0.1,0.8,'Magnitude: '+str(magnitude))
		infoaxis.text(0.1,0.6,'Lat: '+str(locationLat))
		infoaxis.text(0.1,0.4,'Lon: '+str(locationLon))
		infoaxis.text(0.1,0.2,'Depth: '+str(depth))

	def setLabels(self):
		""" Set plot attributes """
		self.ppm.axpp.set_title('Seismograms')
		if self.opts.filemode == 'pkl':
			axstk = self.axstk
			trans = transforms.blended_transform_factory(axstk.transAxes, axstk.transAxes)
			axstk.text(1,1.01,self.opts.pklfile,transform=trans, va='bottom', ha='right',color='k')
		axpp = self.ppm.axpp
		trans = transforms.blended_transform_factory(axpp.transAxes, axpp.transData)
		font = FontProperties()
		font.set_family('monospace')
		axpp.text(1.025, 0, ' '*8+'qual= CCC/SNR/COH', transform=trans, va='center', 
			color='k', fontproperties=font)

	def plotStack(self):
		""" Plot array stack and span """
		colorwave = self.opts.pppara.colorwave
		stkybase = 0
		ppstk = PickPhase(self.gsac.stkdh, self.opts,self.axstk, stkybase, colorwave, 1) 
		ppstk.plotPicks()
		ppstk.disconnectPick()
		self.ppstk = ppstk
		self.axstk.set_title('Array Stack')
		self.ppstk.stalabel.set_visible(False)
		if self.opts.ynorm == 1.0:
			self.axstk.set_ylim(stkybase-0.5, stkybase+0.5)
		self.axstk.set_yticks([stkybase])
		self.axstk.set_yticklabels([])
		self.axstk.axvline(x=0, color='k', ls=':')
		# plot legend
		pppara = self.opts.pppara
		pickLegend(self.axstk, pppara.npick, pppara.pickcolors, pppara.pickstyles, False)
		self.plotSpan()

	def plotSpan(self):
		""" Span for array stack """
		axstk = self.axstk
		self.xzoom = [axstk.get_xlim(),]
		def on_select(xmin, xmax):
			""" Mouse event: select span. """
			if self.span.visible:
				print 'span selected: %6.1f %6.1f ' % (xmin, xmax)
				xxlim = (xmin, xmax)
				axstk.set_xlim(xxlim)
				self.xzoom.append(xxlim)
				if self.opts.upylim_on:
					print ('upylim')
					ppstk.updateY(xxlim)
				axstk.figure.canvas.draw()
		pppara = self.opts.pppara
		a, col = pppara.alphatwsele, pppara.colortwsele
		mspan = pppara.minspan * self.opts.delta
		self.span = TimeSelector(axstk, on_select, 'horizontal', minspan=mspan, useblit=False,
			rectprops=dict(alpha=a, facecolor=col))

	# -------------------------------- SORTING ---------------------------------- #

	# Sort seismograms by 
	#    --------------
	# * | file indices |
	#    --------------
	#                   ----- ----- ----- -----
	# * quality factor | all | ccc | snr | coh |
	#                   ----- ----- ----- -----
	#                 ---- ----- ------
	# * given header | az | baz | dist |
	#                 ---- ----- ------
	
	def sorting(self, event):
		""" Sort the seismograms in particular order """
		gsac = self.gsac
		sortAxes = self.getSortAxes()
		self.sort_connect()
		show()

	def getSortAxes(self):
		figsort = figure(figsize=(15, 12))
		self.figsort = figsort

		backend = get_backend().lower()
		if backend == 'tkagg':
			get_current_fig_manager().window.wm_geometry("1000x900+720+80")

		x0 = 0.05
		xx = 0.10
		yy = 0.04
		xm = 0.02
		dy = 0.15
		dx = 0.12
		y0 = 0.90

		"""Allocating size of buttons"""
		# file indices (filenames)
		rectfile = [x0, y0-dy*1, xx, yy]
		# quality
		rectqall = [x0+dx*0, y0-2*dy, xx, yy]
		rectqccc = [x0+dx*1, y0-2*dy, xx, yy]
		rectqsnr = [x0+dx*2, y0-2*dy, xx, yy]
		rectqcoh = [x0+dx*3, y0-2*dy, xx, yy]
		# headers
		recthnpts = [x0+dx*0, y0-3*dy, xx, yy]
		recthb = [x0+dx*1, y0-3*dy, xx, yy]
		recthe = [x0+dx*2, y0-3*dy, xx, yy]
		recthdelta = [x0+dx*3, y0-3*dy, xx, yy]
		recthstla = [x0+dx*0, y0-3.5*dy, xx, yy]
		recthstlo = [x0+dx*1, y0-3.5*dy, xx, yy]
		recthdist = [x0+dx*2, y0-3.5*dy, xx, yy]
		recthaz = [x0+dx*3, y0-3.5*dy, xx, yy]
		recthbaz = [x0+dx*0, y0-4*dy, xx, yy]
		recthgcarc = [x0+dx*1, y0-4*dy, xx, yy]
		# quit
		rectquit = [0.2, y0-5*dy, 0.2, yy]

		"""writing buttons to axis"""
		sortAxs = {}
		self.figsort.text(0.1,y0-dy*0.5,'Sort by file Index Name: ')
		sortAxs['file'] = figsort.add_axes(rectfile)
		self.figsort.text(0.1,y0-dy*1.5,'Sort by Quality: ')
		sortAxs['qall'] = figsort.add_axes(rectqall)
		sortAxs['qccc'] = figsort.add_axes(rectqccc)
		sortAxs['qsnr'] = figsort.add_axes(rectqsnr)
		sortAxs['qcoh'] = figsort.add_axes(rectqcoh)
		self.figsort.text(0.1,y0-dy*2.5,'Sort by Header: ')
		sortAxs['hnpts'] = figsort.add_axes(recthnpts)
		sortAxs['hb'] = figsort.add_axes(recthb)
		sortAxs['he'] = figsort.add_axes(recthe)
		sortAxs['hdelta'] = figsort.add_axes(recthdelta)
		sortAxs['hstla'] = figsort.add_axes(recthstla)
		sortAxs['hstlo'] = figsort.add_axes(recthstlo)
		sortAxs['hdist'] = figsort.add_axes(recthdist)
		sortAxs['haz'] = figsort.add_axes(recthaz)
		sortAxs['hbaz'] = figsort.add_axes(recthbaz)
		sortAxs['hgcarc'] = figsort.add_axes(recthgcarc)
		# quit
		sortAxs['quit'] = figsort.add_axes(rectquit)

		self.sortAxs = sortAxs

		self.summarize_sort()

	def summarize_sort(self):
		sortAxs = self.sortAxs
		figsort = self.figsort

		# size of text summary box
		rectsumm = [0.55, 0.05, 0.40, 0.90]

		sortAxs['summary'] = figsort.add_axes(rectsumm)

		# remove axes markings on summary field
		sortAxs['summary'].get_xaxis().set_ticks([])
		sortAxs['summary'].get_yaxis().set_visible([])

		# define constants
		x0 = 0.03
		x1 = 0.20
		y0 = 0.95
		dy = 0.03

		# explain what the summaries are
		sortAxs['summary'].text(x0,y0-dy*0,'FILENAMES')
		sortAxs['summary'].text(x0,y0-dy*1,'File: ')
		sortAxs['summary'].text(x1,y0-dy*1,'Sort in alphabetical order by filename')

		sortAxs['summary'].text(x0,y0-dy*3,'QUALITY:')
		sortAxs['summary'].text(x0,y0-dy*4,'All: ')
		sortAxs['summary'].text(x1,y0-dy*4,'Weighted Ratio of all quality measures')
		sortAxs['summary'].text(x0,y0-dy*5,'CCC: ')
		sortAxs['summary'].text(x1,y0-dy*5,'Cross-coefficient Coefficient')
		sortAxs['summary'].text(x0,y0-dy*6,'SNR: ')
		sortAxs['summary'].text(x1,y0-dy*6,'Signal-to-noise Ratio')
		sortAxs['summary'].text(x0,y0-dy*7,'COH: ')
		sortAxs['summary'].text(x1,y0-dy*7,'time domain coherence')

		sortAxs['summary'].text(x0,y0-dy*9,'OTHER HEADERS:')
		sortAxs['summary'].text(x0,y0-dy*10,'NPTS: ')
		sortAxs['summary'].text(x1,y0-dy*10,'Number of points per data component')
		sortAxs['summary'].text(x0,y0-dy*11,'B: ')
		sortAxs['summary'].text(x1,y0-dy*11,'Beginning value of the independent variable')
		sortAxs['summary'].text(x0,y0-dy*12,'E: ')
		sortAxs['summary'].text(x1,y0-dy*12,'Ending value of the independent variable')
		sortAxs['summary'].text(x0,y0-dy*13,'Delta: ')
		sortAxs['summary'].text(x1,y0-dy*13,'Increment between evenly spaced samples')
		sortAxs['summary'].text(x0,y0-dy*14,'STLA: ')
		sortAxs['summary'].text(x1,y0-dy*14,'Station latitude (deg, north positive)')
		sortAxs['summary'].text(x0,y0-dy*15,'STLO: ')
		sortAxs['summary'].text(x1,y0-dy*15,'Station longitude (deg, east positive)')
		sortAxs['summary'].text(x0,y0-dy*16,'DIST: ')
		sortAxs['summary'].text(x1,y0-dy*16,'Station to event distance (km)')
		sortAxs['summary'].text(x0,y0-dy*17,'AZ: ')
		sortAxs['summary'].text(x1,y0-dy*17,'Event to station azimuth (deg)')
		sortAxs['summary'].text(x0,y0-dy*18,'BAZ: ')
		sortAxs['summary'].text(x1,y0-dy*18,'Station to event azimuth (deg)')
		sortAxs['summary'].text(x0,y0-dy*19,'GCARC: ')
		sortAxs['summary'].text(x1,y0-dy*19,'Station to event great circle arc length (deg)')

	""" Connect button events. """
	def sort_connect(self):
		"""write the position for the buttons into self"""
		self.axfile = self.sortAxs['file']
		self.axqall = self.sortAxs['qall']
		self.axqccc = self.sortAxs['qccc']
		self.axqsnr = self.sortAxs['qsnr']
		self.axqcoh = self.sortAxs['qcoh']
		self.axqcoh = self.sortAxs['qcoh']
		self.axhnpts = self.sortAxs['hnpts']
		self.axhb = self.sortAxs['hb']
		self.axhe = self.sortAxs['he']
		self.axhdelta = self.sortAxs['hdelta']
		self.axhstla = self.sortAxs['hstla']
		self.axhstlo = self.sortAxs['hstlo']
		self.axhdist = self.sortAxs['hdist']
		self.axhaz = self.sortAxs['haz']
		self.axhbaz = self.sortAxs['hbaz']
		self.axhgcarc = self.sortAxs['hgcarc']
		self.axquit = self.sortAxs['quit']

		"""add a button to the correct place as defined by the axes
		   Also label the buttons here, as seen in the GUI
		"""
		self.bnfile = Button(self.axfile, 'File')
		self.bnqall = Button(self.axqall, 'All')
		self.bnqccc = Button(self.axqccc, 'CCC')
		self.bnqsnr = Button(self.axqsnr, 'SNR')
		self.bnqcoh = Button(self.axqcoh, 'COH')
		self.bnhnpts = Button(self.axhnpts, 'NPTS')
		self.bnhb = Button(self.axhb, 'B')
		self.bnhe = Button(self.axhe, 'E')
		self.bnhdelta = Button(self.axhdelta, 'Delta')
		self.bnhstla = Button(self.axhstla, 'STLA')
		self.bnhstlo = Button(self.axhstlo, 'STLO')
		self.bnhdist = Button(self.axhdist, 'Dist')
		self.bnhaz = Button(self.axhaz, 'AZ')
		self.bnhbaz = Button(self.axhbaz, 'BAZ')
		self.bnhgcarc = Button(self.axhgcarc, 'GCARC')
		self.bnquit = Button(self.axquit, 'Quit')

		""" each button changes the way the seismograms are sorted """
		self.cidfile = self.bnfile.on_clicked(self.sort_file)
		self.cidqall = self.bnqall.on_clicked(self.sort_qall)
		self.cidqccc = self.bnqccc.on_clicked(self.sort_qccc)
		self.cidqsnr = self.bnqsnr.on_clicked(self.sort_qsnr)
		self.cidqcoh = self.bnqcoh.on_clicked(self.sort_qcoh)
		self.cidhnpts = self.bnhnpts.on_clicked(self.sort_hnpts)
		self.cidhb = self.bnhb.on_clicked(self.sort_hb)
		self.cidhe = self.bnhe.on_clicked(self.sort_he)
		self.cidhdelta = self.bnhdelta.on_clicked(self.sort_hdelta)
		self.cidhstla = self.bnhstla.on_clicked(self.sort_hstla)
		self.cidhstlo = self.bnhstlo.on_clicked(self.sort_hstlo)
		self.cidhdist = self.bnhdist.on_clicked(self.sort_hdist)
		self.cidhaz = self.bnhaz.on_clicked(self.sort_haz)
		self.cidhbaz = self.bnhbaz.on_clicked(self.sort_hbaz)
		self.cidhgcarc = self.bnhgcarc.on_clicked(self.sort_hgcarc)

		# dismiss window when done
		self.bnquit.on_clicked(self.dismiss_sort)

	def sort_disconnect(self):
		self.bnfile.disconnect(self.cidfile)
		self.bnqall.disconnect(self.cidqall)
		self.bnqccc.disconnect(self.cidqccc)
		self.bnqsnr.disconnect(self.cidqsnr)
		self.bnqcoh.disconnect(self.cidqcoh)
		self.bnhnpts.disconnect(self.cidhnpts)
		self.bnhb.disconnect(self.cidhb)
		self.bnhe.disconnect(self.cidhe)
		self.bnhdelta.disconnect(self.cidhdelta)
		self.bnhstla.disconnect(self.cidhstla)
		self.bnhstlo.disconnect(self.cidhstlo)
		self.bnhdist.disconnect(self.cidhdist)
		self.bnhaz.disconnect(self.cidhaz)
		self.bnhbaz.disconnect(self.cidhbaz)
		self.bnhgcarc.disconnect(self.cidhgcarc)

	def sort_file(self, event):
		self.opts.sortby = 'i';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_qall(self, event):
		self.opts.sortby = 'all';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_qccc(self, event):
		self.opts.sortby = '1';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_qsnr(self, event):
		self.opts.sortby = '2';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_qcoh(self, event):
		self.opts.sortby = '3';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_hnpts(self, event):
		self.opts.sortby = 'npts';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_hb(self, event):
		self.opts.sortby = 'b';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_he(self, event):
		self.opts.sortby = 'e';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_hdelta(self, event):
		self.opts.sortby = 'delta';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_hkstnm(self, event):
		self.opts.sortby = 'kstnm';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_hstla(self, event):
		self.opts.sortby = 'stla';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_hstlo(self, event):
		self.opts.sortby = 'stlo';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_hdist(self, event):
		self.opts.sortby = 'dist';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_haz(self, event):
		self.opts.sortby = 'az';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_hbaz(self, event):
		self.opts.sortby = 'baz';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def sort_hgcarc(self, event):
		self.opts.sortby = 'gcarc';
		self.replot()
		self.ppm.axpp.figure.canvas.draw()
		return

	def dismiss_sort(self, event):
		"""Dismiss the sorting selection popup Window"""
		self.sort_disconnect()
		close(self.figsort)

	# -------------------------------- SORTING ---------------------------------- #

	def on_zoom(self, event):
		""" Zoom back to previous xlim when event is in event.inaxes.
		"""
		evkey = event.key
		axstk = self.axstk
		if not axstk.contains(event)[0] or evkey is None: return
		xzoom = self.xzoom
		if evkey.lower() == 'z' and len(xzoom) > 1:
			del xzoom[-1]
			axstk.set_xlim(xzoom[-1])
			print 'Zoom back to: %6.1f %6.1f ' % tuple(xzoom[-1])
			if self.opts.upylim_on:
				for pp in self.pps:
					del pp.ynorm[-1]
					setp(pp.lines[0], ydata=pp.ybase+pp.sacdh.data*pp.ynorm[-1])
			axstk.figure.canvas.draw()

	def replot(self):
		""" Replot seismograms and array stack after running iccs.
		"""
		self.ppstk.disconnect()
		self.ppstk.axpp.cla()
		self.plotStack()
		opts = self.opts
		sortSeis(self.gsac, self.opts)
		self.ppm.initIndex()
		self.ppm.replot(0)
		self.setLabels()

	def connect(self):
		""" Connect button events. """
		# write the position for the buttons into self
		self.axccim = self.axs['CCIM']
		self.axccff = self.axs['CCFF']
		self.axsync = self.axs['Sync']
		self.axmccc = self.axs['MCCC']
		self.axsac2 = self.axs['SAC2']
		self.axsort = self.axs['Sort']

		# name the buttons
		self.bnccim = Button(self.axccim, 'ICCS-A')
		self.bnccff = Button(self.axccff, 'ICCS-B')
		self.bnsync = Button(self.axsync, 'Sync')
		self.bnmccc = Button(self.axmccc, 'MCCC')
		self.bnsac2 = Button(self.axsac2, 'SAC P2')
		self.bnsort = Button(self.axsort, 'Sort')

		self.cidccim = self.bnccim.on_clicked(self.ccim)
		self.cidccff = self.bnccff.on_clicked(self.ccff)
		self.cidsync = self.bnsync.on_clicked(self.sync)
		self.cidmccc = self.bnmccc.on_clicked(self.mccc)
		self.cidsac2 = self.bnsac2.on_clicked(self.plot2)
		self.cidsort = self.bnsort.on_clicked(self.sorting)

		self.cidpress = self.axstk.figure.canvas.mpl_connect('key_press_event', self.on_zoom)

	def disconnect(self):
		""" Disconnect button events. """
		self.bnccim.disconnect(self.cidccim)
		self.bnccff.disconnect(self.cidccff)
		self.bnsync.disconnect(self.cidsync)
		self.bnmccc.disconnect(self.cidmccc)
		self.bnsac2.disconnect(self.cidsac2)
		self.bnsort.disconnect(self.cidsort)

		self.axccim.cla()
		self.axccff.cla()
		self.axsync.cla()
		self.axmccc.cla()
		self.axsac2.cla()
		self.axsort.cla()

	def syncPick(self):
		""" Sync final time pick hdrfin from array stack to all traces. 
		"""
		self.getPicks()
		tshift = self.tfin - self.tmed
		hdrini, hdrmed, hdrfin = self.opts.qcpara.ichdrs
		for sacdh in self.gsac.saclist:
			tfin = sacdh.gethdr(hdrmed) + tshift
			sacdh.sethdr(hdrfin, tfin)

	def syncWind(self):
		""" Sync time window relative to hdrfin from array stack to all traces. 
			Times saved to twhdrs are alway absolute.
		"""
		wh0, wh1 = self.opts.qcpara.twhdrs
		hdrini, hdrmed, hdrfin = self.opts.qcpara.ichdrs
		self.getWindow(hdrfin)
		twfin = self.twcorr
		for sacdh in self.gsac.saclist:
			tfin = sacdh.gethdr(hdrfin)
			th0 = tfin + twfin[0]
			th1 = tfin + twfin[1]
			sacdh.sethdr(wh0, th0)
			sacdh.sethdr(wh1, th1)
			
	def sync(self, event):
		""" Sync final time pick and time window from array stack to each trace and update current page.
		"""
		hdrini, hdrmed, hdrfin = self.opts.qcpara.ichdrs
		wh0, wh1 = self.opts.qcpara.twhdrs
		if self.ppstk.sacdh.gethdr(hdrfin) == -12345.:
			print '*** hfinal %s is not defined. Pick at array stack first! ***' % hdrfin
			return
		self.syncPick()
		self.syncWind()
		twfin = self.twcorr
		for pp in self.ppm.pps:
			sacdh = pp.sacdh
			tfin = sacdh.gethdr(hdrfin)
			ipk = int(hdrfin[1])
			tpk = tfin - sacdh.reftime
			pp.timepicks[ipk].set_xdata(tpk)
			th0 = tfin + twfin[0]
			th1 = tfin + twfin[1]
			pp.twindow = [th0, th1]
			pp.resetWindow()
		print '--> Sync final time picks and time window... You can now run CCFF to refine final picks.'
	
	def getWindow(self, hdr):
		""" Get time window twcorr (relative to hdr) from array stack, which is from last run. 
		"""
		ppstk = self.ppstk
		tw0, tw1 = ppstk.twindow
		t0 = ppstk.sacdh.gethdr(hdr)
		if t0 == -12345.:
			print ('Header {0:s} not defined'.format(hdr))
			return
		twcorr = [tw0-t0, tw1-t0]
		self.twcorr = twcorr

	def getPicks(self):
		""" Get time picks of stack
		"""
		hdrini, hdrmed, hdrfin = self.opts.qcpara.ichdrs
		self.tini = self.gsac.stkdh.gethdr(hdrini)
		self.tmed = self.gsac.stkdh.gethdr(hdrmed)
		self.tfin = self.gsac.stkdh.gethdr(hdrfin)

	def ccim(self, event):
		# running ICCS-B will erase everything you did. Make sure the user did not hit it by mistake
		tkMessageBox.showwarning("Will Erase Work!","This will erase everything you manually selected. \nAre you sure?")

		""" Run iccs with time window from final stack. Time picks: hdrini, hdrmed.
		"""
		hdrini, hdrmed, hdrfin = self.opts.qcpara.ichdrs
		self.cchdrs = hdrini, hdrmed
		self.getWindow(self.cchdrs[0])
		self.ccStack()
		self.getPicks()
		self.replot()

	def ccff(self, event):
		""" Run iccs with time window from final stack. Time picks: hdrfin, hdrfin.
		"""
		hdrini, hdrmed, hdrfin = self.opts.qcpara.ichdrs
		if self.gsac.stkdh.gethdr(hdrfin) == -12345.:
			print '*** hfinal %s is not defined. Sync first! ***' % hdrfin
			return
		# running ICCS-B will erase everything you did. Make sure the user did not hit it by mistake
		tkMessageBox.showwarning("Will Erase Work!","This will erase everything you manually selected. \nAre you sure?")
		
		self.cchdrs = hdrfin, hdrfin
		self.getWindow(self.cchdrs[0])
		self.getPicks()
		self.ccStack()
		stkdh = self.gsac.stkdh
		stkdh.sethdr(hdrini, self.tini)
		stkdh.sethdr(hdrmed, self.tmed)
		self.replot()

	def ccStack(self):
		""" 
		Call iccs.ccWeightStack. 
		Change reference time pick to the input pick before ICCS and to the output pick afterwards.
		"""
		opts = self.opts
		ccpara = opts.ccpara
		opts.ccpara.twcorr = self.twcorr
		ccpara.cchdrs = self.cchdrs
		hdr0, hdr1 = int(ccpara.cchdrs[0][1]), int(ccpara.cchdrs[1][1])
		stkdh, stkdata, quas = ccWeightStack(self.gsac.selist, self.opts)
		stkdh.selected = True
		stkdh.sethdr(opts.qcpara.hdrsel, 'True    ')
		self.gsac.stkdh = stkdh
		if opts.reltime != hdr1:
			out = '\n--> change opts.reltime from %i to %i'
			print out % (opts.reltime, hdr1)
		opts.reltime = hdr1

	def mccc(self, event):
		""" Run mccc.py  """
		gsac = self.gsac
		mcpara = self.opts.mcpara
		rcfile = mcpara.rcfile
		ipick = mcpara.ipick
		wpick = mcpara.wpick
		self.getWindow(ipick)
		timewindow = self.twcorr
		tw = timewindow[1]-timewindow[0]
		taperwindow = taperWindow(timewindow, mcpara.taperwidth)
		mcpara.timewindow = timewindow
		mcpara.taperwindow = taperwindow
		evline, mcname = eventListName(gsac.event, mcpara.phase)
		mcpara.evline = evline
		mcpara.mcname = mcname
		mcpara.kevnm = gsac.kevnm
		#rcwrite(ipick, timewindow, taperwindow, rcfile)
		solution = mccc(gsac, mcpara)
		wpk = int(wpick[1])
		if self.opts.reltime != wpk:
			out = '\n--> change opts.reltime from %i to %i'
			print out % (self.opts.reltime, wpk)
		self.opts.reltime = wpk
		self.replot()

	def plot2(self, event):
		""" Plot P2 stack of seismograms for defined time picks (ichdrs + wpick).
		"""
		opts = copy.copy(self.opts)
		twin_on = opts.twin_on
		pick_on = opts.pick_on
		reltime = opts.reltime
		ynorm = opts.ynorm
		fill = opts.fill
		selist = self.gsac.selist

		tpicks = opts.qcpara.ichdrs + [opts.mcpara.wpick,]
		npick = len(tpicks)
		tlabs = 'ABCDE'

		fig2 = figure(figsize=(9,12))
		fig2.clf()
		subplots_adjust(bottom=.05, top=0.96, left=.1, right=.97, wspace=.5, hspace=.24)
		opts.twin_on = False
		opts.pick_on = False
		ax0 = fig2.add_subplot(npick,1,1)
		axsacs = [ ax0 ] + [ fig2.add_subplot(npick,1,i+1, sharex=ax0) for i in range(1, npick) ]
		for i in range(npick):
			opts.reltime = int(tpicks[i][1])
			ax = axsacs[i]
			sacp2(selist, opts, ax)
			tt = '(' + tlabs[i] + ')'
			trans = transforms.blended_transform_factory(ax.transAxes, ax.transAxes)
			ax.text(-.05, 1, tt, transform=trans, va='center', ha='right', size=16)	

		opts.ynorm = ynorm
		opts.twin_on = twin_on
		opts.pick_on = pick_on
		opts.reltime = reltime
		opts.fill = fill
		opts.zero_on = False

		show()

# ############################################################################### #
#                                                                                 #
#                              CLASS: PickPhaseMenuMore                           #
#                                                                                 #
# ############################################################################### #

# ############################################################################### #
#                                                                                 #
#                               SORTING SEISMOGRAMS                               #
#                                                                                 #
# ############################################################################### #

def sortSeis(gsac, opts):
	'Sort seismograms by file indices, quality factors, time difference, or a given header.'
	sortby = opts.sortby
	print 'WHAT TO SORT BY: ' 
	print sortby 
	# determine increase/decrease order
	if sortby[-1] == '-':
		sortincrease = False
		sortby = sortby[:-1]
	else:
		sortincrease = True
	opts.labelqual = True 
	# sort 
	if sortby == 'i':   # by file indices
		gsac.selist, gsac.delist = seleSeis(gsac.saclist)
	elif sortby == 't':	# by time difference
		ipick = opts.qcpara.ichdrs[0]
		wpick = 't'+str(opts.reltime)
		if ipick == wpick:
			print ('Same time pick: {0:s} and {1:s}. Exit'.format(ipick, wpick))
			sys.exit()
		gsac.selist, gsac.delist = sortSeisHeaderDiff(gsac.saclist, ipick, wpick, sortincrease)
	elif sortby.isdigit() or sortby in opts.qheaders + ['all',]: # by quality factors
		if sortby == '1' or sortby == 'ccc':
			opts.qweights = [1, 0, 0]
		elif sortby == '2' or sortby == 'snr':
			opts.qweights = [0, 1, 0]
		elif sortby == '3' or sortby == 'coh':
			opts.qweights = [0, 0, 1]
		gsac.selist, gsac.delist = sortSeisQual(gsac.saclist, opts.qheaders, opts.qweights, opts.qfactors, sortincrease)
	else: # by a given header
		gsac.selist, gsac.delist = sortSeisHeader(gsac.saclist, sortby, sortincrease)
	return

# ############################################################################### #
#                                                                                 #
#                               SORTING SEISMOGRAMS                               #
#                                                                                 #
# ############################################################################### #

# ############################################################################### #
#                                                                                 #
#                                  PARSING OPTIONS                                #
#                                                                                 #
# ############################################################################### #

def getDataOpts():
	'Get SAC Data and Options'
	opts, ifiles = getOptions()
	pppara = PPConfig()
	qcpara = QCConfig()
	ccpara = CCConfig()
	mcpara = MCConfig()

	gsac = loadData(ifiles, opts, pppara)


	mcpara.delta = opts.delta
	opts.qheaders = qcpara.qheaders
	opts.qweights = qcpara.qweights
	opts.qfactors = qcpara.qfactors
	opts.hdrsel = qcpara.hdrsel
	opts.fstack = ccpara.fstack
	ccpara.qqhdrs = qcpara.qheaders
	ccpara.twcorr = opts.twcorr
	# find phase:
	if opts.phase is None:
		phase = findPhase(ifiles[0])
		print ('Found phase to be: ' + phase + '\n')
	else:
		phase = opts.phase
	mcpara.phase = phase
	opts.qcpara = qcpara
	opts.ccpara = ccpara
	opts.mcpara = mcpara
	opts.pppara = pppara
	# more options:
	opts.upylim_on = False
	opts.twin_on = True
	opts.sort_on = True
	opts.pick_on = True
	opts.zero_on = False
	opts.nlab_on = True
	opts.ynormtwin_on = True
	#checkCoverage(gsac, opts)
	initQual(gsac.saclist, opts.hdrsel, opts.qheaders)
	return gsac, opts

# ############################################################################### #
#                                                                                 #
#                                  PARSING OPTIONS                                #
#                                                                                 #
# ############################################################################### #

# ############################################################################### #
#                                                                                 #
#                        SETUP LOCATIONS OF BUTTONS AND PLOTS                     #
#                                                                                 #
# ############################################################################### #

def getAxes(opts):
	""" Get axes for plotting """
	fig = figure(figsize=(14, 12.5))
	backend = get_backend().lower()
	if backend == 'tkagg':
		get_current_fig_manager().window.wm_geometry("1300x1050+700+0")
	rcParams['legend.fontsize'] = 10

	rectseis = [0.12, 0.04, 0.66, 0.82]
	rectfstk = [0.12, 0.89, 0.66, 0.08]
	rectinfo = [0.86, 0.89, 0.12, 0.09]

	xx = 0.06
	yy = 0.04
	xm = 0.02
	dy = 0.05
	y2 = rectfstk[1] + rectfstk[3] - yy
	yccim = y2 
	ysync = y2 - dy*1
	yccff = y2 - dy*2
	ymccc = y2 - dy*3
	y1 = ymccc - 1.5*dy

	yfron = y1 - dy*0
	yprev = y1 - dy*1
	ynext = y1 - dy*2
	ysave = y1 - dy*3
	yquit = y1 - dy*4
	ysac2 = yquit - dy*1.5
	ysort = ysac2 - dy*1.5

	rectfron = [xm, yfron, xx, yy]
	rectprev = [xm, yprev, xx, yy]
	rectnext = [xm, ynext, xx, yy]
	rectsave = [xm, ysave, xx, yy]
	rectquit = [xm, yquit, xx, yy]
	rectccim = [xm, yccim, xx, yy]
	rectsync = [xm, ysync, xx, yy]
	rectccff = [xm, yccff, xx, yy]
	rectmccc = [xm, ymccc, xx, yy]
	rectsac2 = [xm, ysac2, xx, yy]
	rectsort = [xm, ysort, xx, yy]

	axs = {}
	axs['Seis'] = fig.add_axes(rectseis)
	axs['Fstk'] = fig.add_axes(rectfstk, sharex=axs['Seis'])
	axs['Info'] = fig.add_axes(rectinfo)

	axs['Fron'] = fig.add_axes(rectfron)
	axs['Prev'] = fig.add_axes(rectprev)
	axs['Next'] = fig.add_axes(rectnext)
	axs['Save'] = fig.add_axes(rectsave)
	axs['Quit'] = fig.add_axes(rectquit)
	axs['CCIM'] = fig.add_axes(rectccim)
	axs['Sync'] = fig.add_axes(rectsync)
	axs['CCFF'] = fig.add_axes(rectccff)
	axs['MCCC'] = fig.add_axes(rectmccc)
	axs['SAC2'] = fig.add_axes(rectsac2)
	axs['Sort'] = fig.add_axes(rectsort)

	return axs

# ############################################################################### #
#                                                                                 #
#                        SETUP LOCATIONS OF BUTTONS AND PLOTS                     #
#                                                                                 #
# ############################################################################### #

def main():
	gsac, opts = getDataOpts()
	axs = getAxes(opts)
	ppmm = PickPhaseMenuMore(gsac, opts, axs)
	fmt = 'pdf'
	fmt = 'png'
	if opts.savefig:
		if opts.pklfile is None:
			fignm = 'ttpick.' + fmt
		else:
			fignm = opts.pklfile + '.' + fmt
		savefig(fignm, format=fmt, dpi=300)
	else:
		show()

if __name__ == "__main__":
	main()


