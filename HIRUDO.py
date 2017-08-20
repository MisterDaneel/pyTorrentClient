from threading import Thread, activeCount
from time import sleep
import base64
import json
import sys
import os

from tkFont import Font
from Tkinter import *
import tkSimpleDialog
import tkFileDialog
import ttk

import libs.t411api as tapi

sys.dont_write_bytecode = True

try:
    import libs.my_libtorrent as trnt
except ImportError:
    raise ImportError('The package: python-libtorrent is required.')

#
# CONFIG
#
initial_dir = '~'

script_path = os.path.realpath(__file__)
script_dir = os.path.dirname(script_path)
configuration_path = os.path.join(script_dir, 'configuration.json')
if os.path.isfile(configuration_path):
    with open(configuration_path) as configuration_file:
        configuration = json.load(configuration_file)
else:
    configuration = {}


class BACKUPACTIVETORRENTS():

    def __init__(self):
        self.backup_dic = {}
        self.backup_file = os.path.join(script_dir, '.back')

    def load_backup(self):
        if not os.path.isfile(self.backup_file):
            return {}
        with open(self.backup_file, 'r') as f:
            backup_b64 = f.read()
        backup_string = base64.b64decode(backup_b64)
        self.backup_dic = json.loads(backup_string)
        files = []
        for _, torrent_file in self.backup_dic.iteritems():
            if os.path.isfile(torrent_file):
                files.append(torrent_file)
        return files

    def write_backup(self):
        backup_string = json.dumps(self.backup_dic)
        backup_b64 = base64.b64encode(backup_string)
        with open(self.backup_file, 'w') as f:
            f.write(backup_b64)

    def add_file(self, torrent_name, torrent_file):
        self.backup_dic[torrent_name] = torrent_file
        self.write_backup()

    def pop_file(self, torrent_name):
        self.backup_dic.pop(torrent_name, None)
        self.write_backup()


class TKTORRENTGUI(ttk.Frame):
    sort_dir = True     # descending

    def __init__(self, name='hirudo'):
        ttk.Frame.__init__(self, name=name)
        self.pack(expand=Y, fill=BOTH)
        self.master.title('HIRUDO')
        self.torrent_thread_list = {}
        self.is_popup = False
        if 'number_of_active_torrents' in configuration:
            self.active_torrents = configuration['number_of_active_torrents']
        else:
            self.active_torrents = 5
        if 'upload_limit' in configuration and configuration['upload_limit']:
            self.upload_limit = int(configuration['upload_limit'])
        else:
            self.upload_limit = 500000
        if 'download_limit' in configuration and\
                configuration['download_limit']:
            self.download_limit = configuration['download_limit']
        else:
            self.download_limit = 9000000
        if 'output_folder' in configuration:
            self.output_folder = configuration['output_folder']
        else:
            self.output_folder = ''
        self.create_widgets()

        self.backup = BACKUPACTIVETORRENTS()
        for torrent_file in self.backup.load_backup():
            self.load_file(torrent_file)

    def create_file_bar(self, menu):
        file_bar = Menu(menu)
        menu.add_cascade(label='File', menu=file_bar)
        file_bar.add_command(label='Add file', command=self.add_file)
        file_bar.add_command(label='Add folder', command=self.add_folder)
        file_bar.add_command(label='Maximum number of active torrents',
                             command=self.set_number_of_active_torrents)
        file_bar.add_command(label='Download limit',
                             command=self.set_download_limit)
        file_bar.add_command(label='Upload limit',
                             command=self.set_upload_limit)
        file_bar.add_command(label='Exit', command=self.exit)

    def create_torrent_bar(self, menu):
        torrent_bar = Menu(menu)
        menu.add_cascade(label='Torrent', menu=torrent_bar)
        torrent_bar.add_command(label='Start', command=self.call_start)
        torrent_bar.add_command(label='Stop', command=self.call_stop)
        torrent_bar.add_command(label='Delete', command=self.delete)

    def create_widgets(self):
        # Bar
        menu = Menu(self)
        self.master.config(menu=menu)
        # File bar
        self.create_file_bar(menu)
        # Torrent bar
        self.create_torrent_bar(menu)
        # Search bar
        #  torrent_bar = Menu(menu)
        #  menu.add_cascade(label='Search', menu=torrent_bar)
        #  torrent_bar.add_command(label='Keywords',
        #                          command=self.search_keywords)
        # Torrent panel
        self.create_torrent_panel()

    def right_click(self, event):
        if self.is_popup:
            self.popupMenu.destroy()
            self.is_popup = False
        else:
            # Popup menu
            self.popupMenu = Menu(self, tearoff=0)
            self.popupMenu.add_command(label='Start', command=self.call_start)
            self.popupMenu.add_command(label='Stop', command=self.call_stop)
            self.popupMenu.add_command(label='Delete', command=self.delete)
            self.popupMenu.post(event.x_root, event.y_root)
            self.is_popup = True

    def exit_popup(self, event):
        if self.is_popup:
            self.popupMenu.destroy()
            self.is_popup = False

    def select_all(self, event):
        for item in self.table.get_children():
            self.table.selection_add(item)

    def create_torrent_panel(self):
        frame = Frame(self)
        frame.pack(side=TOP, fill=BOTH, expand=Y)
        # table
        self.torrent_cols = ('Torrent', 'State')
        self.table = ttk.Treeview(columns=self.torrent_cols, show='headings')
        # scrollbars
        ysb = ttk.Scrollbar(orient=VERTICAL, command=self.table.yview)
        xsb = ttk.Scrollbar(orient=HORIZONTAL, command=self.table.xview)
        self.table['yscroll'] = ysb.set
        self.table['xscroll'] = xsb.set
        # add table and scrollbars to frame
        self.table.grid(in_=frame, row=0, column=0, sticky=NSEW)
        ysb.grid(in_=frame, row=0, column=1, sticky=NS)
        xsb.grid(in_=frame, row=1, column=0, sticky=EW)
        # set frame resize priorities
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        # bind callback
        self.table.bind('<Double-1>',  self.call_start)
        self.table.bind('<Button-3>',  self.right_click)
        self.table.bind('<Button-1>',  self.exit_popup)
        self.table.bind('<Escape>',    self.exit_popup)
        self.table.bind('<Control-a>', self.select_all)
        # configure column headings
        for c in self.torrent_cols:
            self.table.heading(c, text=c.title(),
                               command=lambda c=c:
                               self.column_sort(c, TKTORRENTGUI.sort_dir))
            self.table.column(c, width=Font().measure(c.title()))

    def column_sort(self, col, descending=False):
        # grab values
        data = [(self.table.set(child, col), child) for
                child in self.table.get_children('')]
        # reorder data
        data.sort(reverse=descending)
        for indx, item in enumerate(data):
            # item[1] = item Identifier
            self.table.move(item[1], '', indx)
        TKTORRENTGUI.sort_dir = not descending

    def load_file(self, torrent_file):
        thread = trnt.TORRENTTHREAD(torrent_file)
        name = thread.GetTorrentName()
        if name not in self.torrent_thread_list:
            self.torrent_thread_list[name] = thread
        self.backup.add_file(name, torrent_file)
        for item in self.table.get_children():
            if self.table.item(item)['text'] == name:
                return
        values = (name, 'NEW')
        self.table.insert('', 'end', text=name, values=values)
        for idx, val in enumerate(values):
            iwidth = Font().measure(val)
            if self.table.column(self.torrent_cols[idx], 'width') < iwidth:
                self.table.column(self.torrent_cols[idx], width=iwidth)

    def add_folder(self):
        options = {}
        options['initialdir'] = initial_dir
        options['mustexist'] = False
        options['parent'] = self
        options['title'] = 'DownDirectory'
        folder = tkFileDialog.askdirectory(**options)
        for file in os.listdir(folder):
            if file.endswith('.torrent'):
                torrent_file = os.path.join(folder, file)
                self.load_file(torrent_file)

    def add_file(self):
        options = {}
        options['initialdir'] = initial_dir
        options['parent'] = self
        options['filetypes'] = [('Torrent file', '*.torrent')]
        torrent_file = tkFileDialog.askopenfilename(**options)
        if torrent_file.endswith('.torrent'):
            self.load_file(torrent_file)

    def set_number_of_active_torrents(self):
        options = {}
        options['title'] = 'Number Of Active Torrents'
        options['prompt'] = 'Number Of Active Torrents'
        options['initialvalue'] = self.active_torrents
        options['parent'] = self
        options['minvalue'] = 0
        options['maxvalue'] = 50
        self.active_torrents = tkSimpleDialog.askinteger(**options)
        configuration['number_of_active_torrents'] = self.active_torrents
        with open(configuration_path, 'w') as configuration_file:
            json.dump(configuration, configuration_file,
                      indent=4, sort_keys=True)

    def set_upload_limit(self):
        options = {}
        options['title'] = 'Upload Limit'
        options['prompt'] = 'Upload Limit'
        options['initialvalue'] = self.upload_limit
        options['parent'] = self
        options['minvalue'] = 0
        options['maxvalue'] = 100000000000
        self.upload_limit = tkSimpleDialog.askinteger(**options)
        configuration['upload_limit'] = self.upload_limit
        with open(configuration_path, 'w') as configuration_file:
            json.dump(configuration, configuration_file,
                      indent=4, sort_keys=True)
        for name in self.torrent_thread_list:
            torrent = self.torrent_thread_list[name]
            if torrent.isAlive():
                torrent.SetUploadLimit(self.upload_limit)

    def set_download_limit(self):
        options = {}
        options['title'] = 'Download Limit'
        options['prompt'] = 'Download Limit'
        options['initialvalue'] = self.download_limit
        options['parent'] = self
        options['minvalue'] = 0
        options['maxvalue'] = 100000000000
        self.download_limit = tkSimpleDialog.askinteger(**options)
        configuration['download_limit'] = self.download_limit
        with open(configuration_path, 'w') as configuration_file:
            json.dump(configuration, configuration_file,
                      indent=4, sort_keys=True)
        for name in self.torrent_thread_list:
            torrent = self.torrent_thread_list[name]
            if torrent.isAlive():
                torrent.SetDownloadLimit(self.download_limit)

    def OnSearchSelection(self, response, api):
        torrents = []
        # Sort result by seeders and by size
        torrents = sorted(
            response['torrents'], key=lambda torrent: (
                int(torrent['seeders']),
                int(torrent['size'])),
            reverse=True)
        # Print result
        frame = Frame(self)
        frame.pack()
        listResults = Listbox(frame)
        # Print results
        for i, t in enumerate(torrents):
            listResults.insert(i, '%s (seeders: %s, size: %dmo, id: %s)' %
                               (t['name'], t['seeders'],
                                int(t['size'])/1000000, t['id']))

        def select(event):
            result = listResults.curselection()
            torrent_file = api.download(int(torrents[result[0]]['id']))
            self.load_file(torrent_file)
            frame.destroy()

        def clear():
            frame.destroy()
        btn = Button(frame, text='Cancel', command=clear)
        listResults.bind('<Double-Button-1>', select)
        listResults.bind('<Enter>', select)
        listResults.pack()
        btn.pack()

    def search_keywords(self):
        options = {}
        options['parent'] = self
        torrent_name = tkSimpleDialog.askstring('Search keywords',
                                                'Example: Mad Max 2015',
                                                **options)
        api = tapi.T411API()
        api.connect(configuration["loginT411"], configuration["passwordT411"])
        response = api.search(torrent_name)
        self.OnSearchSelection(response, api)

    def exit(self):
        for item in self.table.get_children():
            name = self.table.item(item)['text']
            if not name:
                continue
            if name in self.torrent_thread_list:
                if self.torrent_thread_list[name].isAlive():
                    self.torrent_thread_list[name].Stop()
                self.torrent_thread_list.pop(name, None)
            self.table.delete(item)
        self.quit()

    def call_start(self, event=None):
        for item in self.table.selection():
            if item:
                self.start(item)

    def start(self, item):
        name = self.table.item(item)['text'].encode('utf8')
        if not name:
            return
        if activeCount() > self.active_torrents:
            return
        if name in self.torrent_thread_list and\
                not self.torrent_thread_list[name].isAlive():
            torrent_file = self.torrent_thread_list[name].torrentFile
            thread = trnt.TORRENTTHREAD(torrent_file)
            self.torrent_thread_list.pop(name, None)
            thread.SetEditGui(self.edit)
            thread.SetItem(item)
            folder = os.path.dirname(os.path.realpath(torrent_file))
            thread.SetOutput(folder)
            if 'user_passkey' in configuration and\
                    'leech_passkey' in configuration:
                thread.SetPasskey(configuration['user_passkey'],
                                  configuration['leech_passkey'])
            thread.SetDownloadLimit(self.download_limit)
            thread.SetUploadLimit(self.upload_limit)
            if self.output_folder:
                thread.SetOutput(self.output_folder)
            thread.start()
            self.torrent_thread_list[name] = thread

    def call_stop(self):
        for item in self.table.selection():
            if item:
                self.stop(item)

    def stop(self, item):
        name = self.table.item(item)['text']
        if not name:
            return
        if name in self.torrent_thread_list:
            if self.torrent_thread_list[name].isAlive():
                self.torrent_thread_list[name].Stop()

    def edit(self, item, value):
        torrentName = self.table.item(item)['text'].replace('.torrent', '')
        self.table.item(item, values=(torrentName, value))

    def delete(self):
        for item in self.table.selection():
            name = self.table.item(item)['text']
            if not name:
                return
            if name in self.torrent_thread_list:
                if self.torrent_thread_list[name].isAlive():
                    self.torrent_thread_list[name].Stop()
                os.remove(self.torrent_thread_list[name].torrentFile)
                self.torrent_thread_list.pop(name, None)
            self.table.delete(item)
            self.backup.pop_file(name)


# Hide hidden elements
def hideHidden():
    root = Tk()
    try:
        # call a dummy dialog with an impossible option to initialize the file
        # dialog without really getting a dialog window; this will throw a
        # TclError, so we need a try...except :
        try:
            root.tk.call('tk_getOpenFile', '-foobarbaz')
        except TclError:
            pass
        # now set the magic variables accordingly
        root.tk.call('set', '::tk::dialog::file::showHiddenBtn', '1')
        root.tk.call('set', '::tk::dialog::file::showHiddenVar', '0')
    except:
        pass


#
# MAIN
#
if __name__ == '__main__':
    hideHidden()
    TKTORRENTGUI().mainloop()
