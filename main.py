import logging
import random
import time
from tkinter import *
from tkinter import filedialog
import threading
import queue
from idlelib.tooltip import Hovertip

import xml.etree.ElementTree as ET

import os
import glob


# Implemented this because whoever wrote os.path didn't think of this???
def path_split_left(s):
    slash = s.find("\\")
    if slash == -1:
        slash = s.find("/")
    # Not going to compare whether / or \ is first, because I'll
    # only be using this on auto generated paths by glob.glob,
    # so it'll likely only stick to one slash type.

    if slash != -1:
        return s[0:max(slash, 1)], s[slash+1:]
    else:
        return "", s


# Contains the WIDGETS for each line. Only usable by the main thread
rename_lines = []
# Contains the DATA inside the widgets on each line. Can be used in the second thread.
# Filled by cache_rename_entries()
rename_entries = []


def cache_rename_entries():
    global rename_entries

    rename_entries = []
    for i in range(len(rename_lines)):
        rename_entries.append((
            rename_lines[i][1].get(),
            rename_lines[i][2].get(),
            rename_lines[i][3].val.get()
        ))


start_texts = [
    "Start!",
    "Begin!",
    "Let's get this started!",
    "Move it!",
    "Dew it.",
    "Let's-a go!",
    "LET'S GOOOOO"
]

# Allows the main thread (where root.update() gets called) to only access
# pending_log when the parse thread is done writing to it, and vice versa
log_queue = queue.Queue()
log_queue.put(0)

pending_log = []


def start_using_log():
    log_queue.get()


def stop_using_log():
    log_queue.put(0)


def log_console(s):
    pending_log.append(s)


global source_folder_entry, file_type_entry, output_folder_entry


def create_window():
    root = Tk()
    root.title("Unreal Package Rename Tool!")
    root.geometry("700x700")
    root.minsize(450, 450)

    parse_thread = None

    def window_update():
        nonlocal parse_thread
        nonlocal output_console

        if parse_thread is not None and not parse_thread.is_alive():
            parse_thread = None
            toggle_items_inactive(False)

        old_yview = output_console.yview()

        # Log update (needs to be done on the main thread because it's UI)
        start_using_log()
        if len(pending_log) > 0:
            output_console.config(state=NORMAL)
            for i in range(len(pending_log)):
                output_console.insert('end', pending_log[i] + "\n")
            del pending_log[:]
            output_console.config(state=DISABLED)

            # If we were one line away from the very bottom, scroll to the end
            if old_yview[1] + ((old_yview[1] - old_yview[0]) / 7) >= 1:
                output_console.see(END)
        stop_using_log()

        root.update()

    gp_frame = LabelFrame(root, text="General Properties", padx=10, pady=10)

    def source_folder_browse():
        # nonlocal source_folder_entry
        folder = filedialog.askdirectory(initialdir=source_folder_entry.get(), title="Browse Folder")
        if folder == "":
            return
        source_folder_entry.delete(0, END)
        source_folder_entry.insert(0, folder)

    source_folder_hover_tip = """Folder from which to search for the needed files.
Can be either relative to the program's path or absolute.
You may use '.' to start in this program's path."""
    file_type_hover_tip = """Examples:

    Use MyMap.umap
        MyMap.umap

    All files of type .umap
        *.umap

    All files of type .umap in the specified folder & its sub-folders (except the given output folder)
        **/*.umap

Can't have multiple arguments because glob.glob doesn't support it."""
    output_folder_hover_tip = "Can be either relative or absolute, though it's recommended to be left relative."

    global source_folder_entry, file_type_entry, output_folder_entry

    source_folder_label = Label(gp_frame, text="Source Directory")
    Hovertip(source_folder_label, hover_delay=500, text=source_folder_hover_tip)
    source_folder_entry = Entry(gp_frame)
    source_folder_brows = Button(gp_frame, text="Browse", command=source_folder_browse)
    file_type_label = Label(gp_frame, text="File Name/Type")
    Hovertip(file_type_label, hover_delay=500, text=file_type_hover_tip)
    file_type_entry = Entry(gp_frame)
    output_folder_label = Label(gp_frame, text="Output Folder")
    Hovertip(output_folder_label, hover_delay=500, text=output_folder_hover_tip)
    output_folder_entry = Entry(gp_frame)
    output_folder_entry.insert(0, "Output")

    # Ahh yes, graphic design :]
    gp_frame.grid_columnconfigure(1, minsize=10)
    gp_frame.grid_columnconfigure(2, weight=6)
    gp_frame.grid_columnconfigure(3, minsize=70)
    gp_frame.grid_columnconfigure(4, minsize=10)
    gp_frame.grid_rowconfigure(0, minsize=26)
    gp_frame.grid_rowconfigure(1, minsize=26)
    gp_frame.grid_rowconfigure(2, minsize=26)
    source_folder_label.grid(row=0, column=0, sticky="e")
    file_type_label.grid(row=1, column=0, sticky="e")
    output_folder_label.grid(row=2, column=0, sticky="e")
    source_folder_entry.grid(row=0, column=2, sticky="we")
    file_type_entry.grid(row=1, column=2, sticky="we")
    output_folder_entry.grid(row=2, column=2, sticky="we")
    source_folder_brows.grid(row=0, column=3)

    gp_frame.pack(padx=20, pady=20, fill=X)

    rename_table_main_frame = LabelFrame(root, text="Rename Table")
    rename_table_main_frame.pack(padx=20, fill=BOTH, expand=1)

    rename_table_scrollbar = Scrollbar(rename_table_main_frame, orient=VERTICAL)
    rename_table_scrollbar.pack(side=RIGHT, fill=Y)

    rename_table_canvas = Canvas(
        rename_table_main_frame,
        yscrollcommand=rename_table_scrollbar.set,
        highlightthickness=0,
        height=0
    )
    rename_table_canvas.pack(fill=BOTH, expand=1, padx=4)

    def rename_table_scrollbar_command(*args):
        rename_table_canvas.yview(*args)
        # Because for whatever reason the main execution freezes while dragging
        # a scrollbar, it has to be updated here. Not the most elegant solution
        # but I had no other choice
        window_update()

    rename_table_scrollbar.configure(command=rename_table_scrollbar_command)

    rename_table_inner_frame = Frame(rename_table_canvas)
    rename_table_inner_id = rename_table_canvas.create_window((0, 0), window=rename_table_inner_frame, anchor="nw")

    def rename_table_bound_to_mousewheel(event):
        nonlocal rename_table_canvas
        rename_table_canvas.bind_all("<MouseWheel>", rename_table_on_mousewheel)

    def rename_table_unbound_to_mousewheel(event):
        nonlocal rename_table_canvas
        rename_table_canvas.unbind_all("<MouseWheel>")

    def rename_table_on_mousewheel(event):
        nonlocal rename_table_canvas
        rename_table_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def rename_table_update_scroll_size():
        nonlocal rename_table_canvas
        nonlocal rename_table_inner_id
        rename_table_canvas.configure(scrollregion=rename_table_canvas.bbox("all"))
        rename_table_canvas.itemconfigure(rename_table_inner_id, width=rename_table_canvas.winfo_width())

    def on_rename_table_configure(event):
        rename_table_update_scroll_size()

    rename_table_canvas.bind('<Configure>', on_rename_table_configure)
    rename_table_inner_frame.bind('<Enter>', rename_table_bound_to_mousewheel)
    rename_table_inner_frame.bind('<Leave>', rename_table_unbound_to_mousewheel)

    rename_table = Frame(rename_table_inner_frame)
    rename_table.bind('<Configure>', on_rename_table_configure)

    def find_widget_in_rename_table(w):
        for i in range(len(rename_lines)):
            for j in range(len(rename_lines[i])):
                if rename_lines[i][j] == w or rename_lines[i][j] == w.master:
                    return i
        return -1

    def remove_rename_line_at_index(index):
        for i in range(len(rename_lines[index])):
            rename_lines[index][i].grid_forget()
        del rename_lines[index]
        for i in range(index, len(rename_lines)):
            pack_rename_line(i)

    def on_button_remove(button):
        index = find_widget_in_rename_table(button)
        if index != -1:
            remove_rename_line_at_index(index)

    def insert_rename_line_at_index(index):
        tup = create_rename_line()
        rename_lines.insert(index, tup)
        for i in range(index, len(rename_lines)):
            pack_rename_line(i)

    def on_button_move_up(button):
        index = find_widget_in_rename_table(button)
        if index != -1 and index != 0:
            rename_lines[index], rename_lines[index - 1] = rename_lines[index - 1], rename_lines[index]
            pack_rename_line(index)
            pack_rename_line(index - 1)

    def on_button_move_dn(button):
        index = find_widget_in_rename_table(button)
        if index != -1 and index != len(rename_lines) - 1:
            rename_lines[index], rename_lines[index + 1] = rename_lines[index + 1], rename_lines[index]
            pack_rename_line(index)
            pack_rename_line(index + 1)

    def on_button_insert(button):
        index = find_widget_in_rename_table(button)
        if index != -1:
            insert_rename_line_at_index(index)

    def create_rename_line():
        nonlocal rename_table

        buttons_frame = Frame(rename_table)
        remove_button = Button(
            buttons_frame,
            text="X",
            command=lambda: on_button_remove(remove_button),
            bg="orangered"
        )
        move_up_button = Button(
            buttons_frame,
            text="^",
            command=lambda: on_button_move_up(move_up_button),
            bg="lightblue"
        )
        move_dn_button = Button(
            buttons_frame,
            text="v",
            command=lambda: on_button_move_dn(move_dn_button),
            bg="lightblue"
        )
        insert_button = Button(
            buttons_frame,
            text="Insert ^",
            command=lambda: on_button_insert(insert_button),
            bg="lightgreen"
        )
        remove_button.grid(row=0, column=0)
        move_up_button.grid(row=0, column=1)
        move_dn_button.grid(row=0, column=2)
        insert_button.grid(row=0, column=3)

        entry_old = Entry(
            rename_table,
            font="consolas"
        )
        entry_new = Entry(
            rename_table,
            font="consolas"
        )
        rename_table_variable = IntVar()
        rename_type_checkbox = Checkbutton(rename_table, text="Prefix", variable=rename_table_variable)
        rename_type_checkbox.val = rename_table_variable

        return buttons_frame, entry_old, entry_new, rename_type_checkbox

    def new_rename_line_at_end():
        tup = create_rename_line()
        rename_lines.append(tup)
        index = len(rename_lines) - 1
        pack_rename_line(index)
        return index

    def pack_rename_line(index):
        for i in range(len(rename_lines[index])):
            rename_lines[index][i].grid(row=index + 1, column=i, sticky="we", padx=2, pady=1)

    rename_table.columnconfigure(0, weight=0, minsize=115)
    rename_table.columnconfigure(1, weight=3, minsize=80)
    rename_table.columnconfigure(2, weight=3, minsize=80)

    button_new_entry = Button(rename_table, text="New Entry (End)", bg="lightgreen", command=new_rename_line_at_end)
    label_oldname = Label(rename_table, text="Old Name")
    label_newname = Label(rename_table, text="New Name")
    label_renametype = Label(rename_table, text="Rename type")
    button_new_entry.grid(row=0, column=0, sticky="we", padx=2, pady=1)
    label_oldname.grid(row=0, column=1)
    label_newname.grid(row=0, column=2)
    label_renametype.grid(row=0, column=3)

    rename_table_save_and_load = Frame(rename_table_inner_frame)

    def create_xml():
        folder = filedialog.asksaveasfilename(
            title="Save XML File",
            defaultextension="*.xml",
            filetypes=[("XML file", "*.xml"), ("All types", "*.*")]
        )
        if folder == "":
            return

        xml_root = ET.Element("RenameTable")
        for i in range(len(rename_lines)):
            attrib = [
                ('Old', rename_lines[i][1].get()),
                ('New', rename_lines[i][2].get()),
                ('Pre', str(rename_lines[i][3].val.get()))
            ]
            ET.SubElement(xml_root, 'e', dict(attrib))
        tree = ET.ElementTree(xml_root)
        ET.indent(tree, '    ')
        try:
            with open(folder, 'wb') as files:
                tree.write(files)

                start_using_log()
                log_console("Successfully saved XML file at path: " + folder)
                stop_using_log()
        except Exception as e:
            logging.exception(e)

            start_using_log()
            log_console(f"ERROR : exception {type(e).__name__} thrown while saving XML file at path: {folder}")
            stop_using_log()

    def read_xml():
        folder = filedialog.askopenfilename(
            title="Load XML File",
            filetypes=[("XML file", "*.xml"), ("All types", "*.*")]
        )
        if folder == "":
            return

        try:
            tree = ET.parse(folder)
            xml_root = tree.getroot()

            while len(rename_lines) > 0:
                remove_rename_line_at_index(len(rename_lines) - 1)
            for r in xml_root:
                if r.tag == 'e':
                    i = new_rename_line_at_end()
                    rename_lines[i][1].insert(0, r.attrib['Old'])
                    rename_lines[i][2].insert(0, r.attrib['New'])
                    rename_lines[i][3].val.set(int(r.attrib['Pre']))

            start_using_log()
            log_console("Successfully loaded XML file at path: " + folder)
            stop_using_log()
        except Exception as e:
            logging.exception(e)

            start_using_log()
            log_console(f"ERROR : exception {type(e).__name__} thrown while loading XML file at path: {folder}")
            stop_using_log()

    rename_table_save = Button(rename_table_save_and_load, text="Save XML File", bg="lightgreen", command=create_xml)
    rename_table_save.grid(row=0, column=0, padx=10)

    rename_table_load = Button(rename_table_save_and_load, text="Load XML File", bg="lightblue", command=read_xml)
    rename_table_load.grid(row=0, column=1, padx=10)

    rename_table_save_and_load.pack(pady=8)
    rename_table.pack(fill=X)

    def pick_random_start_button_text():
        return start_texts[random.randint(0, len(start_texts) - 1)]

    def toggle_items_inactive(b):
        if b:
            s = DISABLED
        else:
            s = NORMAL

        # nonlocal source_folder_entry
        nonlocal source_folder_brows
        # nonlocal file_type_entry
        # nonlocal output_folder_entry
        nonlocal rename_table_save, rename_table_load
        nonlocal button_new_entry
        nonlocal start_button

        source_folder_entry.config(state=s)
        source_folder_brows.config(state=s)
        file_type_entry.config(state=s)
        output_folder_entry.config(state=s)
        rename_table_save.config(state=s)
        rename_table_load.config(state=s)
        button_new_entry.config(state=s)
        start_button.config(state=s)
        if b:
            start_button.config(text="Renaming...")
        else:
            # Re-randomize
            start_button.config(text=pick_random_start_button_text())

        for i in range(len(rename_lines)):
            for button in rename_lines[i][0].winfo_children():
                button.config(state=s)
            for j in range(1, len(rename_lines[i])):
                rename_lines[i][j].config(state=s)

    # Returns a bool
    def can_start_parsing():
        if len(rename_lines) == 0:
            start_using_log()
            log_console("Please add one or more entries in the Rename Table before continuing.")
            stop_using_log()
            return False
        path = source_folder_entry.get().strip()
        if not path:
            start_using_log()
            log_console("Please include a Source directory.")
            stop_using_log()
            return False
        if not os.path.exists(path):
            start_using_log()
            log_console(f"Unable to find path: {path} Please make sure this path is valid.")
            stop_using_log()
            return False
        out = output_folder_entry.get().strip()
        if not out:
            start_using_log()
            log_console("Please include an Output folder.")
            stop_using_log()
            return False
        invalid = ':*?"<>|'
        for char in invalid:
            found = out.rfind(char)
            # The things I do for absolute path support...
            if found != -1 and (found != 1 or char != ":" or len(out) < 3 or (out[2] != "/" and out[2] != "\\")):
                start_using_log()
                log_console(f"The output folder may not contain {invalid}")
                stop_using_log()
                return False
        return True

    def on_start_button():
        nonlocal parse_thread

        if not can_start_parsing():
            return

        if parse_thread is None:
            toggle_items_inactive(True)

            # The data must be grabbed before going into the new thread, because tkinter doesn't
            # like having any of its functions called from any other thread than the main.
            source = source_folder_entry.get().strip()
            f_type = file_type_entry.get()
            output = output_folder_entry.get().strip()
            cache_rename_entries()

            parse_thread = threading.Thread(
                target=lambda: start_parsing(source, f_type, output),
                # A daemon thread, which stops when the main thread stops.
                daemon=True)
            parse_thread.start()

    start_button = Button(
        root,
        text=pick_random_start_button_text(),
        bg="lightgreen",
        padx=20,
        pady=20,
        command=on_start_button
    )
    start_button.pack(side=RIGHT, padx=(10, 24), pady=20)

    output_console_main_frame = LabelFrame(root, text="Log")
    output_console_main_frame.pack(side=LEFT, padx=(20, 10), pady=(0, 10), fill=X, expand=1)

    output_console_scrollbar = Scrollbar(output_console_main_frame, orient=VERTICAL)
    output_console_scrollbar.pack(side=RIGHT, fill=Y)

    output_console = Text(
        output_console_main_frame,
        height=8,
        yscrollcommand=output_console_scrollbar.set,
        state=DISABLED)
    output_console.pack(side=LEFT, fill=X, expand=1)

    def output_console_scrollbar_command(*args):
        output_console.yview(*args)
        # Because for whatever reason the main execution freezes while dragging
        # a scrollbar, it has to be updated here. Not the most elegant solution
        # but I had no other choice
        window_update()

    output_console_scrollbar.config(command=output_console_scrollbar_command)

    window_opened = True

    def on_window_closed():
        nonlocal window_opened
        window_opened = False

    root.protocol("WM_DELETE_WINDOW", on_window_closed)

    # Can't use mainloop because I need my own update,
    # and unfortunately I found no other way to do it.
    # HMU if you have any idea how to improve this ty
    # root.mainloop()
    while window_opened:
        window_update()

        # Capping the window update at a max of 100 times a second, because
        # according to task manager, the Power usage was "Very High"
        time.sleep(0.01)


def start_parsing(source, f_type, output):
    start_using_log()
    log_console("Searching for files...")
    stop_using_log()

    owd = os.getcwd()

    os.chdir(source)

    # The output might be absolute, so make sure it's a relative path
    try:
        relative_output = os.path.relpath(output)
        start_using_log()
        log_console(f"{output} as a relative path is {relative_output}")
        stop_using_log()
        ro_len = len(relative_output)
        relo = relative_output.casefold()
    except ValueError:
        relative_output = output
        start_using_log()
        log_console("Cannot make Output relative to Source because it's on a different drive.")
        stop_using_log()
        ro_len = -1
        relo = False

    def make_folder(p):
        if not p:
            return True

        if not os.path.isdir(p):
            try:
                prev_path = os.path.split(p)[0]
                # Make sure the prev path exists before we try to make this one
                if not make_folder(prev_path):
                    return False
                os.mkdir(p)
                start_using_log()
                log_console(f"Created folder {p}")
                stop_using_log()
            except Exception as e:
                logging.exception(e)
                start_using_log()
                log_console(f"ERROR : exception {type(e).__name__} while trying to create folder {p}")
                stop_using_log()
                return False
        return True

    # if not make_folder(relative_output):
    #     return

    files_parsed = 0
    for file in glob.glob(f_type, recursive=True):
        # glob.glob can also get a hold of folders for some reason
        if not os.path.isfile(file):
            continue
        # Is this file in the output folder?
        if relo and len(file) > ro_len \
                and file[0:ro_len].casefold() == relo and (file[ro_len] == "/" or file[ro_len] == "\\"):
            continue
        # split = os.path.split(file)
        output_file = os.path.join(relative_output, file)
        if not make_folder(os.path.split(output_file)[0]):
            continue
        start_using_log()
        log_console(f"Converting {file} into {output_file} ...")
        stop_using_log()
        if parse_file(file, output_file):
            files_parsed += 1

    start_using_log()
    log_console(f"Successfully parsed {files_parsed} files!")
    stop_using_log()

    os.chdir(owd)


SINGLE_BYTE_ENCODING = 'ascii'
# If this is wrong, someone please tell me
DOUBLE_BYTE_ENCODING = 'utf-16'

global f
global version
global total_nudge


def parse_file_deprecated(filename, output_directory):
    """
    # Mmmm spaghetti bolognese
    s1 = filename.rsplit("/", 1)
    if len(s1) == 2:
        index = 1
        output_directory = s1[0] + "/"
    else:
        index = 0
        output_directory = ""
    s2 = s1[index].rsplit("\\", 1)
    if len(s2) == 2:
        output_directory += s2[0] + "/"
        output_filename = s2[1]
    else:
        output_filename = s1[0]
    output_directory += OUTPUT_FOLDER
    """

    # do_the_thing(filename, )

    """
    try:
        # do_the_thing(filename, output_directory)
        pass
    except FileNotFoundError:
        print("Error, could not find file " + filename)
    except BadTagRead:
        print("Missing Package File Tag 'C1 83 2A 9E'. Is this a real unreal package?")
    except IndexMismatchError as err:
        print("Index export mismatch with original: orig = " + err.o + ", exp = " + err.e + ", expBytes = " + err.b)
    except BaseException as err:
        print(f"Unexpected {err=}, {type(err)=}")
    """


def test_index():
    global version
    version = 0
    val, byt = read_index()
    print(val, byt)
    byt2 = turn_int_into_index(val)
    print(byt2)


def parse_file(filename, output_directory):
    global f
    global version
    global total_nudge
    # original_name = input("Please input the name you want to replace: ")
    # new_name = input("Please input the name with which you want to replace the above: ")
    # original_name = "PackageTesy1"
    # new_name = "PackageTesss1"

    try:
        f = open(filename, 'rb')
    except Exception as e:
        logging.exception(e)
        start_using_log()
        log_console(f"ERROR : exception {type(e).__name__} while trying to open " + filename)
        stop_using_log()
        return False

    try:
        # name_convert_nudge = len(new_name) - len(original_name)

        tag = f.read(4)
        if tag != b'\xC1\x83\x2A\x9E':
            start_using_log()
            log_console(f"ERROR : Missing Package File Tag 'C1 83 2A 9E'. Is {filename} an unreal package?")
            stop_using_log()
            return False

        total_nudge = 0

        version = read_word_as_int(False)

        # Needs to be under the version, so it can know how
        # to format the output string: index or dword?
        # new_name_byte = turn_string_into_bytes(new_name)

        licensee = f.read(2)
        if version >= 249:
            header_size = read_dword_as_int(False)
        if version >= 269:
            folder_name, folder_name_byte = read_string()
        package_flags = f.read(4)
        name_count = read_dword_as_int(False)
        name_offset = read_dword_as_int(False)

        # In memory of the Old Method(tm)
        # I will remove this... eventually. Just not now, I'm too emotionally attached to it.
        """
        export_count = read_dword_as_int(False)
        export_offset = read_dword_as_int(False)
        import_count = read_dword_as_int(False)
        import_offset = read_dword_as_int(False)
        if version < 68:
            heritage_count = f.read(4)
            heritage_offset = read_dword_as_int(False)
        if version >= 415:
            depends_offset = read_dword_as_int(False)
        if version >= 623:
            import_export_guids_offset = read_dword_as_int(False)
            import_export_guids_count = f.read(8)
        if version >= 584:
            thumbnail_table_offset = read_dword_as_int(False)
        rest_of_header = f.read(name_offset - f.tell())

        # Debug Constants
        print_names = True
        print_export = True

        until_export_table = f.read(export_offset - f.tell())

        def export_debug_print(a, b):
            y = a - len(b)
            if y <= 0:
                return ""
            s = ""
            for k in range(y):
                s += " "
            return b + s

        curr = f.tell()
        f.seek(import_offset)
        for x in range(import_count):
            s = export_debug_print(8, str(x))
            r, t = read_index()
            s += export_debug_print(8, str(r))
            r, t = read_index()
            s += export_debug_print(8, str(r))
            r = read_dword_as_int(True)
            s += export_debug_print(8, str(r))
            r, t = read_index()
            s += export_debug_print(8, str(r))
            if r > 0:
                s += name_table_array[r]
            print(s)
        f.seek(curr)

        export_table = b''
        for x in range(export_count):
            s = export_debug_print(8, str(x))

            export_class, export_class_byte = read_index()
            export_super, export_super_byte = read_index()
            export_table += export_class_byte + export_super_byte

            export_table += f.read(4)

            export_name, export_name_byte = read_index()
            export_table += export_name_byte

            seek_count = 0
            # I'm not sure if this is right, but epic did a fantastic job documenting their changes.
            if version >= 491:
                # This is stores the number at the end of an actor name + 1
                # (So for StaticMeshActor_2 it would be 3)
                # This was possibly made to prevent storing names like
                # StaticMeshActor_0, StaticMeshActor_1 etc. separately,
                # therefore taking up less space in the file.
                # If 0, it won't append a number.

                seek_count += 4
                export_number = read_dword_as_int(False)
                f.seek(f.tell() - 4)
            if version >= 220:
                seek_count += 4
            if version >= 195:
                seek_count += 8
            else:
                seek_count += 4
            export_table += f.read(seek_count)

            export_serial_size, export_serial_size_byte = read_index()
            s += export_debug_print(16, str(export_serial_size_byte.hex(" ")))
            export_table += export_serial_size_byte
            if export_serial_size > 0:
                export_serial_offset, export_serial_offset_byte = read_index()
                s += export_debug_print(16, str(export_serial_offset_byte.hex(" ")))
                export_serial_offset = nudge_offset(export_serial_offset)
                s += export_debug_print(16, str(turn_int_into_index(export_serial_offset).hex(" ")))
                export_table += turn_int_into_index(export_serial_offset)

            if 220 <= version < 543:
                export_huh1 = read_dword_as_int(False)
                export_table += turn_int_into_dword(export_huh1, False) + f.read(export_huh1 * 12)
            if version >= 247:
                export_table += f.read(4)
            if version >= 322:
                export_huh2 = read_dword_as_int(False)
                export_table += turn_int_into_dword(export_huh2, False) + f.read((export_huh2 * 4) + 16)
            if version >= 487:
                export_table += f.read(4)

            if export_name != 0:
                s += name_table_array[export_name]
                if version >= 491 and export_number > 0:
                    s += "_" + str(export_number-1)
            print(s)
        """
        rest_of_file = f.read()

        end_of_file = f.tell()

        f.seek(name_offset)

        # Name table time
        name_table = b''
        name_table_array = []
        for x in range(name_count):
            string_string, string_byte = read_string()
            # if print_names:
            if True:
                print(x, string_string)
            name_table_array.append(string_string)

            matching_prefix = -1
            matching_direct = -1
            for i in range(len(rename_entries)):
                old_name = rename_entries[i][0]
                # Original name empty?
                if not old_name:
                    continue

                # Is Prefix checked?
                if rename_entries[i][2]:
                    if \
                            matching_prefix == -1 \
                            and len(string_string) > len(old_name) \
                            and string_string[0:len(old_name)] == old_name:
                        matching_prefix = i
                elif string_string == old_name:
                    matching_direct = i
                    break

            if matching_direct != -1 or matching_prefix != -1:
                if matching_direct != -1:
                    new_name = rename_entries[matching_direct][1]
                else:
                    # New prefix + old name without the old prefix
                    new_name = \
                        rename_entries[matching_prefix][1] + \
                        string_string[len(rename_entries[matching_prefix][0]):]
                print(f"Converted {string_string} into {new_name}")
                string_byte = turn_string_into_bytes(new_name)
                total_nudge += len(new_name) - len(string_string)

            name_table += string_byte

            if version >= 141:
                seek_count = 8
            else:
                seek_count = 4
            name_table += f.read(seek_count)

        name_offset = end_of_file

        f.close()
    except Exception as e:
        logging.exception(e)
        start_using_log()
        log_console(f"ERROR : unexpected exception {type(e).__name__} while parsing " + filename)
        stop_using_log()

        f.close()
        return False

    try:
        g = open(output_directory, 'wb')
    except Exception as e:
        logging.exception(e)
        start_using_log()
        log_console(f"ERROR : exception {type(e).__name__} while trying to create/override " + output_directory)
        stop_using_log()
        return False

    try:
        # Write header
        g.write(tag + turn_int_into_word(version, False) + licensee)
        if version >= 249:
            # Don't ask me why, but apparently they consider the name table,
            # among other stuff, part of the header?? For some reason???
            header_size = nudge_offset(header_size)
            g.write(turn_int_into_dword(header_size, False))
        if version >= 269:
            g.write(folder_name_byte)
        g.write(package_flags)
        g.write(turn_int_into_dword(name_count, False) + turn_int_into_dword(name_offset, False))

        # In memory of the Old Method(tm)
        """
        export_offset = nudge_offset(export_offset)
        g.write(turn_int_into_dword(export_count, False) + turn_int_into_dword(export_offset, False))
        import_offset = nudge_offset(import_offset)
        g.write(turn_int_into_dword(import_count, False) + turn_int_into_dword(import_offset, False))
        if version < 68:
            heritage_offset = nudge_offset(heritage_offset)
            g.write(heritage_count + turn_int_into_dword(heritage_offset, False))
        if version >= 415:
            depends_offset = nudge_offset(depends_offset)
            g.write(turn_int_into_dword(depends_offset, False))
        if version >= 623:
            import_export_guids_offset = nudge_offset(import_export_guids_offset)
            g.write(turn_int_into_dword(import_export_guids_offset, False) + import_export_guids_count)
        if version >= 584:
            # I'm not even going to try to understand in what format this is supposed to be. I just
            # know it's a byte position that's after the name table, and that's good enough for me.
            thumbnail_table_offset = nudge_offset(thumbnail_table_offset)
            g.write(turn_int_into_dword(thumbnail_table_offset, False))

        # Write all bytes until the name table
        g.write(rest_of_header)

        # Write the name table
        g.write(name_table)

        # Write all bytes until the export table
        g.write(until_export_table)

        # Write export table
        g.write(export_table)
        """

        # Self-explanatory :P
        g.write(rest_of_file)

        g.write(name_table)

        g.close()
    except Exception as e:
        logging.exception(e)
        start_using_log()
        log_console(f"ERROR : unexpected exception {type(e).__name__} while writing " + output_directory)
        stop_using_log()

        g.close()
        return False

    return True


# No out parameters :)
def nudge_offset(off):
    if off != 0:
        off += total_nudge
    return off


# Thanks to wiki.beyondunreal.com/Legacy:Package_File_Format/Data_Details
# for literally saving this project, like holy crap.
def read_index():
    global version

    if version >= 178:
        # UE3
        index_bytes = f.read(4)
        output = int.from_bytes(index_bytes, "little", signed=True)
    else:
        # UE 1 and 2
        output = 0
        signed = False
        index_bytes = b''
        for i in range(5):
            b = f.read(1)
            index_bytes += b
            x = int.from_bytes(b, "little", signed=True)
            if i == 0:
                if (x & 0x80) > 0:
                    signed = True
                output |= (x & 0x3F)
                if (x & 0x40) == 0:
                    break
            elif i == 4:
                output |= (x & 0x1F) << (6 + (3 * 7))
            else:
                output |= (x & 0x7F) << (6 + ((i - 1) * 7))
                if (x & 0x80) == 0:
                    break
        if signed:
            output *= -1
    return output, index_bytes


def turn_int_into_index(x):
    def next_byte(val, i, pro):
        if i == 4:
            return b'', pro
        bx = val if (val < 0x80) else ((val & 0x7F) + 0x80)
        out = b''
        if bx & 0x80:
            out, pro = next_byte(val >> 7, i + 1, pro)
        out = bx.to_bytes(1, "little", signed=False) + out
        return out, (pro << 7) + (bx & 0x7F)

    global version

    if version >= 178:
        return turn_int_into_dword(x, True)
    else:
        proof = 0
        v = abs(x)
        b0 = (0 if (x >= 0) else 0x80) + (v if (v < 0x40) else ((v & 0x3F) + 0x40))
        output = b''
        if b0 & 0x40:
            output, proof = next_byte(v >> 6, 0, proof)
        output = b0.to_bytes(1, "little", signed=False) + output
        proof = (proof << 6) + (b0 & 0x3F)
        if b0 & 0x80:
            proof = -proof
        if proof != x:
            # raise IndexMismatchError(x, proof, output)
            start_using_log()
            log_console(f"WARNING : index mismatch between given number {x} and the converted number {proof}")
            stop_using_log()
        return output


def read_string():
    str_len, str_len_byte = read_index()
    if str_len == 0:
        return "", str_len_byte
    ret = ""
    ret_byte = b''
    if str_len < 0:
        enc = DOUBLE_BYTE_ENCODING
        str_len = (str_len * -2) - 2
        seek_count = 2
    else:
        enc = SINGLE_BYTE_ENCODING
        str_len -= 1
        seek_count = 1
    if str_len != 0:
        ret_byte = f.read(str_len)
        ret = ret_byte.decode(enc)
    return ret, str_len_byte + ret_byte + f.read(seek_count)


def turn_string_into_bytes(in_string):
    str_len = len(in_string) + 1
    if in_string.isascii():
        enc = SINGLE_BYTE_ENCODING
        final_bytes = b'\x00'
    else:
        enc = DOUBLE_BYTE_ENCODING
        str_len *= -1
        final_bytes = b'\x00\x00'
    return turn_int_into_index(str_len) + in_string.encode(enc) + final_bytes


def read_word_as_int(signed):
    return read_bytes_as_int(signed, 2)


def read_dword_as_int(signed):
    return read_bytes_as_int(signed, 4)


def read_qword_as_int(signed):
    return read_bytes_as_int(signed, 8)


def read_bytes_as_int(signed=True, byte_count=0):
    return int.from_bytes(f.read(byte_count), "little", signed=signed)


def turn_int_into_word(x, signed):
    return turn_int_into_bytes(x, signed, 2)


def turn_int_into_dword(x, signed):
    return turn_int_into_bytes(x, signed, 4)


def turn_int_into_bytes(x, signed, byte_count):
    return x.to_bytes(byte_count, "little", signed=signed)


"""
class BadTagRead(Exception):
    pass


class IndexMismatchError(Exception):
    def __init__(self, x, y, z):
        self.o = str(x)
        self.e = str(y)
        self.b = str(z)
"""

if __name__ == '__main__':
    create_window()
