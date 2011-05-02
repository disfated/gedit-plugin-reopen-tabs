# -*- coding: utf-8 -*-

#  Copyright (C) 2008 - Eugene Khorev
#
#  This program is free software; you can redistribute it and/or modify
#  it under the terms of the GNU General Public License as published by
#  the Free Software Foundation; either version 2 of the License, or
#  (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software
#  Foundation, Inc., 59 Temple Place, Suite 330,
#  Boston, MA 02111-1307, USA.

import pygtk
pygtk.require("2.0")
import gtk
import gedit
import time
import os
import sys
import getopt
import ConfigParser
import gettext

APP_NAME = "plugin"
LOC_PATH = os.path.join(os.path.expanduser("~/.gnome2/gedit/plugins/reopen-tabs/lang"))

gettext.find(APP_NAME, LOC_PATH)
gettext.install(APP_NAME, LOC_PATH, True)

RELOADER_STATE_READY        = "ready"
RELOADER_STATE_WAIT         = "wait"
RELOADER_STATE_RELOADING    = "reloading"
RELOADER_STATE_DONE         = "done"

class ReopenTabsPlugin(gedit.Plugin):
	def __init__(self):
		gedit.Plugin.__init__(self)
		
		self._config = None
		
		self._state = RELOADER_STATE_WAIT

	def activate(self, window):
		self.read_config()

		window.connect("active-tab-changed", self._on_active_tab_changed)
		window.connect("active-tab-state-changed", self._on_active_tab_state_changed)

		# Register signal handler to ask a user to save tabs on exit
		window.connect("delete_event", self._on_destroy)
		
	def deactivate(self, window):
		pass

	def read_config(self): # Reads configuration from a file
		# Get configuration dictionary
		self._conf_path = os.path.join(os.path.expanduser("~/.gnome2/gedit/plugins/"), "reopen-tabs/plugin.conf")

		# Check if configuration file does not exists
		if not os.path.exists(self._conf_path):
			# Create configuration file
			conf_file = file(self._conf_path, "wt")
			conf_file.close()

		self._conf_file = file(self._conf_path, "r+")
		self._config = ConfigParser.ConfigParser()
		self._config.readfp(self._conf_file)
		self._conf_file.close()

		# Setup default configuration if needed
		if not self._config.has_section("common"):
			self._config.add_section("common")

		if not self._config.has_option("common", "active_document"):
			self._config.set("common", "active_document", "")

		if not self._config.has_section("documents"):
			self._config.add_section("documents")

	def write_config(self): # Saves configuration to a file
		self._conf_file = file(self._conf_path, "r+")
		self._conf_file.truncate(0)
		self._config.write(self._conf_file)
		self._conf_file.close()

	def _on_active_tab_changed(self, window, tab):
		if self._state == RELOADER_STATE_WAIT:
			self._state = RELOADER_STATE_READY
			self._on_active_tab_state_changed(window)
		
	def _on_active_tab_state_changed(self, window):
		# Check if we are not reloading and did not finished yet
		if self._state == RELOADER_STATE_READY:
			# Get active tab
			tab = window.get_active_tab()
			
			# Check if we are ready to reload
			if tab and tab.get_state() == gedit.TAB_STATE_NORMAL:
				self._state = RELOADER_STATE_RELOADING

				self._reopen_tabs(window)

				self._state = RELOADER_STATE_DONE
		
	def update_ui(self, window):
		pass

	def _on_destroy(self, widget, event): # Handles window destory (saves tabs if required)
		# Clear old document list
		self._config.remove_section("documents")

		self._docs = self._get_doc_list()
		
		# Check if there is anything to save
		if len(self._docs) > 0:
			# Check if we need ask a user to save tabs
			self._save_tabs()

		self.write_config()
		
	def _get_doc_list(self):
		# Get document URI list
		app  = gedit.app_get_default()
		win  = app.get_active_window()
		docs = win.get_documents()
		
		# Return list of documents which having URI's
		return [d.get_uri() for d in docs if d.get_uri()]
		
	def _save_tabs(self): # Save opened tabs in configuration file
		self._config.add_section("documents")
		
		# Get active document
		app = gedit.app_get_default()
		win = app.get_active_window()
	
		doc = win.get_active_document()
		if doc:
			cur_uri = doc.get_uri()
		else:
			cur_uri = None
		
		doc = None
		
		# Create new document list
		n = 1
		for uri in self._docs:
			# Setup option name
			name = "document" + str(n).rjust(3).replace(" ", "0")
		
			# Check if current document is active
			if uri == cur_uri:
				doc = name

			self._config.set("documents", name, uri)
			n = n + 1

		# Remeber active document
		if doc:
			self._config.set("common", "active_document", doc)
		
	def _reopen_tabs(self, window):
		# Get list of open documents
		docs = window.get_documents()
		open_docs = [d.get_uri() for d in docs if d.get_uri()]
		
		# Get saved active document
		active = self._config.get("common", "active_document")
		self._active_tab = None
	
		# Get document list
		docs = self._config.options("documents")
		docs.sort()

		# Check if document list is not empty
		if len(docs) > 0:
			# Get active document
			doc = window.get_active_document()
			
			# Check if document is untitled (there is empty tab)
			tab = window.get_active_tab()
			
			if doc.is_untitled():
				# Remember empty tab to close it later
				self._empty_tab = tab
			else:
				# Remember active tab (in case if there is file in a command line)
				self._empty_tab = None
				self._active_tab = tab
			
			# Process the rest documents
			for d in docs:
				# Get document uri
				uri = self._config.get("documents", d)
				
				# Check if document is not already opened
				if open_docs.count(uri) == 0:
					# Create new tab
					tab = window.create_tab_from_uri(uri, gedit.encoding_get_current(), 0, True, False)
			
					# Check if document was active (and there is NOT file in command line)
					if d == active and not self._active_tab:
						self._active_tab = tab

		# Connect handler that switches saved active document tab
		if self._active_tab:
			self._active_tab.get_document().connect("loaded", self._on_doc_loaded)

	def _on_doc_loaded(self, doc, arg): # Switches to saved active document tab
		# Activate tab
		app = gedit.app_get_default()
		win = app.get_active_window()
		win.set_active_tab(self._active_tab)
		
		# Close empty tab if any
		if self._empty_tab:
			win.close_tab(self._empty_tab)

