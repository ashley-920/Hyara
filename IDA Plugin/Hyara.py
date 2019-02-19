import idaapi 
import idc
import idautils
from PIL import Image
from PIL.ImageQt import ImageQt
from collections import OrderedDict

if idaapi.IDA_SDK_VERSION >= 700:
    ida7_version = 1
else:
    ida7_version = 0

try:
    from PyQt5.QtCore import *
    from PyQt5.QtGui import *
    from PyQt5.QtWidgets import *
except:
    from PySide.QtCore import *
    from PySide.QtGui import *
    from PySide import QtGui
    #from PySide.QtWidgets import *
from capstone import *

import idautils

import binascii
import io
import os
import re
import time
import pefile
import yara
import csv
import hashlib

from functools import partial
from os.path import expanduser

def table_click(row, column):
    variable_name = tableWidget.item(row, 0).text()
    if idaapi.ask_yn(idaapi.ASKBTN_NO, "Delete Yara Rule : " + variable_name) == idaapi.ASKBTN_YES:
        del ruleset_list[variable_name]
        tableWidget.setRowCount(len(ruleset_list.keys()))
        tableWidget.setColumnCount(4)
        tableWidget.setHorizontalHeaderLabels(["Variable_name", "Rule", "Start", "End"])
        for idx, name in enumerate(ruleset_list.keys()):
            tableWidget.setItem(idx, 0, QTableWidgetItem(name))
            tableWidget.setItem(idx, 1, QTableWidgetItem(ruleset_list[name][0]))
            tableWidget.setItem(idx, 2, QTableWidgetItem(ruleset_list[name][1]))
            tableWidget.setItem(idx, 3, QTableWidgetItem(ruleset_list[name][2]))
        layout.addWidget(tableWidget)

ruleset_list = {}
tableWidget = QTableWidget()
tableWidget.cellDoubleClicked.connect(table_click)

layout = QVBoxLayout()
StartAddress = QLineEdit()
EndAddress = QLineEdit()
flag = 0
header_clicked = 0
c = None

def get_string(addr):
    out = ""
    assem_data = idc.GetDisasm(addr)
    print(addr)
    if "text \"UTF-16LE\"" in assem_data or "unicode 0," in assem_data:
        while True:

            if idc.Byte(addr) == 0 and idc.Byte(addr+1) == 0:
                addr += 2
                break
            else:
                out += chr(idc.Byte(addr))
                out += chr(idc.Byte(addr+1))
            addr += 2
        return out.decode("utf-16le"), addr

    else:
        while True:
            if idc.Byte(addr) != 0:

                out += chr(idc.Byte(addr))
            else:
                addr += 1
                break
            addr += 1
    
        return out, addr

class YaraHighlighter(QSyntaxHighlighter):
    def __init__(self, document):
        QSyntaxHighlighter.__init__(self, document)

        quote_color = QTextCharFormat()
        color_ = QColor()
        color_.setRgb(255, 127, 80)
        quote_color.setForeground(color_)

        keyword_color = QTextCharFormat()
        color_ = QColor()
        color_.setRgb(135, 206, 235)
        keyword_color.setForeground(color_)

        hex_color = QTextCharFormat()
        color_ = QColor()
        color_.setRgb(0, 153, 0)
        hex_color.setForeground(color_)

        comment_color = QTextCharFormat()
        color_ = QColor()
        color_.setRgb(187, 93, 0)
        comment_color.setForeground(color_)

        keywords = [
            "\\ball\\b", "\\band\\b", "\\bany\\b", "\\bascii\\b", "\\bat\\b", "\\bcondition\\b", "\\bcontains\\b",
            "\\bentrypoint\\b", "\\bfalse\\b", "\\bfilesize\\b", "\\bfullword\\b", "\\bfor\\b", "\\bglobal\\b", "\\bin\\b",
            "\\bimport\\b", "\\binclude\\b", "\\bint8\\b", "\\bint16\\b", "\\bint32\\b", "\\bint8be\\b", "\\bint16be\\b",
            "\\bint32be\\b", "\\bmatches\\b", "\\bmeta\\b", "\\bnocase\\b", "\\bnot\\b", "\\bor\\b", "\\bof\\b",
            "\\bprivate\\b", "\\brule\\b", "\\bstrings\\b", "\\bthem\\b", "\\btrue\\b", "\\buint8\\b", "\\buint16\\b",
            "\\buint32\\b", "\\buint8be\\b", "\\buint16be\\b", "\\buint32be\\b", "\\bwide\\b"
        ]

        self.highlightingRules = [(QRegExp(keyword), keyword_color) # keyword
                for keyword in keywords]

        self.highlightingRules.append((QRegExp("\{[\S\s]*\}"), hex_color)) # hex string
        self.highlightingRules.append((QRegExp("\/.*\/"), quote_color)) # regex
        self.highlightingRules.append((QRegExp("\/\*[\S\s]*\*\/"), comment_color)) # comment
        self.highlightingRules.append((QRegExp("\/\/.*"), comment_color)) # comment
        self.highlightingRules.append((QRegExp("\".*\""), quote_color)) # double quote
        self.highlightingRules.append((QRegExp("\'.*\'"), quote_color)) # single quote

    def highlightBlock(self, text):
        for pattern, format in self.highlightingRules:
            expression = QRegExp(pattern)
            index = expression.indexIn(text)

            while index >= 0:
                length = expression.matchedLength()
                self.setFormat(index, length, format)
                index = expression.indexIn(text, index + length)

        self.setCurrentBlockState(0)

class YaraIcon(idaapi.PluginForm):
    def SaveIcon(self, idx):
        global ruleset_list, tableWidget, layout
        data_ = self.img[idx][int(self.LineEdit1.text(),16):int(self.LineEdit1.text(),16) + int(self.LineEdit2.text(),10)]
        ruleset_list[self.LineEdit3.text()] = ["{" + binascii.hexlify(data_).upper() + "}", hex(int(self.LineEdit1.text(),16)), hex(int(self.LineEdit1.text(),16) + int(self.LineEdit2.text(),10))]
        tableWidget.setRowCount(len(ruleset_list.keys()))
        tableWidget.setColumnCount(4)
        tableWidget.setHorizontalHeaderLabels(["Variable_name", "Rule", "Start", "End"])
        for idx, name in enumerate(ruleset_list.keys()):
            tableWidget.setItem(idx, 0, QTableWidgetItem(name))
            tableWidget.setItem(idx, 1, QTableWidgetItem(ruleset_list[name][0]))
            tableWidget.setItem(idx, 2, QTableWidgetItem(ruleset_list[name][1]))
            tableWidget.setItem(idx, 3, QTableWidgetItem(ruleset_list[name][2]))
        layout.addWidget(tableWidget)

    def YaraMaker(self):
        for idx in range(len(self.img)):
            data_ = self.img[idx][int(self.LineEdit1.text(),16):int(self.LineEdit1.text(),16) + int(self.LineEdit2.text(),10)]
            self.LineEdit_list[idx].setText("{" + binascii.hexlify(data_).upper() + "}")

    def OnCreate(self, form):
        try:
            self.parent = self.FormToPyQtWidget(form)
        except:
            self.parent = self.FormToPySideWidget(form)

        try:
            self.pe = pefile.PE(GetInputFilePath().decode("utf-8"))
        except:
            self.pe = pefile.PE(GetInputFilePath())
        self.EntryPoint = self.pe.OPTIONAL_HEADER.AddressOfEntryPoint
        self.ImageBase = self.pe.OPTIONAL_HEADER.ImageBase
        self.section_list = {}
        self.img = []
        self.img_label = []
        self.LineEdit_list = []
        self.PushButton_list = []
        self.label1 = QLabel("Start Offset : ")
        self.label2 = QLabel("Length : ")
        self.label3 = QLabel("Variable name : ")
        self.label4 = QLabel("Icon Size")
        icon1 = QLabel("Icon")
        icon1.setAlignment(Qt.AlignCenter)
        icon2 = QLabel("Icon Size")
        icon2.setAlignment(Qt.AlignCenter)
        icon3 = QLabel("Rule")
        icon3.setAlignment(Qt.AlignCenter)
        icon4 = QLabel("Save Rule")
        icon4.setAlignment(Qt.AlignCenter)

        self.LineEdit1 = QLineEdit()
        self.LineEdit2 = QLineEdit()
        self.LineEdit3 = QLineEdit()
        self.PushButton1 = QPushButton("Enter")
        self.PushButton1.clicked.connect(self.YaraMaker) 

        for section in self.pe.sections:
            self.section_list[section.Name.decode("utf-8").replace("\x00","")] = [hex(section.VirtualAddress), hex(section.SizeOfRawData), hex(section.PointerToRawData)]

        for entry in self.pe.DIRECTORY_ENTRY_RESOURCE.entries:
            resource_type = entry.name
            if resource_type is None:
                resource_type = pefile.RESOURCE_TYPE.get(entry.struct.Id)

            for directory in entry.directory.entries:
                for resource in directory.directory.entries:
                    name = str(resource_type)
                    if name in "RT_ICON":
                        name = str(resource_type)
                        offset = resource.data.struct.OffsetToData
                        size = resource.data.struct.Size
                        RVA_ = int(self.section_list['.rsrc'][0],16) - int(self.section_list['.rsrc'][2],16) # VirtualAddress - PointerToRawData
                        real_offset = offset - RVA_
                        img_size = hex(size)[2:]
                        if len(img_size) % 2 == 1:
                            img_size = "0"+img_size

                        img_ = "\x00\x00\x01\x00\x01\x00\x30\x30\x00\x00\x01\x00\x08\x00" + bytearray.fromhex(img_size)[::-1] + "\x00\x00\x16\x00\x00\x00"
                        try:
                            f = open(GetInputFilePath().decode("utf-8"),"rb")
                        except:
                            f = open(GetInputFilePath(), "rb")
                        f.seek(real_offset)
                        img_ += f.read(size)
                        f.close()
                        self.img.append(img_)
                        # print(hex(offset), real_offset)

        self.layout = QVBoxLayout()
        GL0 = QGridLayout()
        GL0.addWidget(self.label3, 0, 0)
        GL0.addWidget(self.LineEdit3, 0, 1)
        GL0.addWidget(self.label1, 0, 2)
        GL0.addWidget(self.LineEdit1, 0, 3)
        GL0.addWidget(self.label2, 0, 4)
        GL0.addWidget(self.LineEdit2, 0, 5)
        GL0.addWidget(self.PushButton1, 0, 6)
        self.layout.addLayout(GL0)

        GL1 = QGridLayout()
        GL1.addWidget(icon1, 0, 0)
        GL1.addWidget(icon2, 0, 1)
        GL1.addWidget(icon3, 0, 2)
        GL1.addWidget(icon4, 0, 3)
        for idx,i in enumerate(self.img):
            ## https://stackoverflow.com/questions/35655755/qpixmap-argument-1-has-unexpected-type-pngimagefile?rq=1
            ## https://stackoverflow.com/questions/32908639/open-pil-image-from-byte-file
            image2 = Image.open(io.BytesIO(i))
            qimage = ImageQt(image2)
            pixmap = QPixmap.fromImage(qimage)

            self.img_label.append(QLabel())
            self.img_label[idx].setPixmap(pixmap)
            GL1.addWidget(self.img_label[idx], idx+1, 0)
            GL1.addWidget(QLabel(hex(len(i))),idx+1, 1)

            self.LineEdit_list.append(QLineEdit())
            GL1.addWidget(self.LineEdit_list[idx], idx+1, 2)

            self.PushButton_list.append(QPushButton("Enter"))
            self.PushButton_list[idx].clicked.connect(partial(self.SaveIcon,idx))
            GL1.addWidget(self.PushButton_list[idx], idx+1, 3)

        self.layout.addLayout(GL1)
        self.parent.setLayout(self.layout)

    def OnClose(self, form):
        pass

class YaraChecker(idaapi.PluginForm):
    def choose_path(self):
        path = QFileDialog.getExistingDirectory(
            self.parent,
            "Open a folder",
            expanduser("~"),
            QFileDialog.ShowDirsOnly)

        if path:
            self.path.setText(path)

    def choose_path2(self):
        path = QFileDialog.getExistingDirectory(
            self.parent,
            "Open a folder",
            expanduser("~"),
            QFileDialog.ShowDirsOnly)

        if path:
            self.path2.setText(path)

    def export_csv(self):
        f = open(self.path2.text() + "\\result.csv", 'wb')
        wr = csv.writer(f)
        wr.writerow(["Path", "Filename", "Address", "Variable_name"])
        row = self.tableWidget.rowCount()
        #col = self.tableWidget.columnCount()
        
        for i in range(0,row):
            wr.writerow([self.tableWidget.item(i,0).text().encode("utf-8"),
                            self.tableWidget.item(i,1).text().encode("utf-8"),
                            self.tableWidget.item(i,2).text().encode("utf-8"),
                            self.tableWidget.item(i,3).text().encode("utf-8")
                    ])
        f.close()
        print("[*] Export csv file Complete.")

    def Search(self):
        if self.CheckButton.isChecked():
            rule = yara.compile(source=self.TextEdit1.toPlainText())
            result = {}
            for i in os.walk(self.path.text()):
                for j in i[2]:
                    try:
                        f = open(i[0] + "\\" + j, "rb")
                        data = f.read()
                        matches = rule.match(data=data)
                        f.close()
                        for match in matches:
                            strings = match.strings[0]
                            result[os.path.basename(j)] = [i[0], hex(strings[0]).replace("L",""), strings[1], binascii.hexlify(strings[2])]
                    except IOError: # Permission denied
                        continue
            self.tableWidget.setRowCount(len(result.keys()))
            self.label4.setText(str(len(result.keys())))
            
            for idx, filename in enumerate(result.keys()):
                self.tableWidget.setItem(idx, 0, QTableWidgetItem(result[filename][0]))
                self.tableWidget.setItem(idx, 1, QTableWidgetItem(filename))
                self.tableWidget.setItem(idx, 2, QTableWidgetItem(result[filename][1]))
                self.tableWidget.setItem(idx, 3, QTableWidgetItem(result[filename][2]))
                self.tableWidget.setItem(idx, 4, QTableWidgetItem(result[filename][3]))
            self.layout.addWidget(self.tableWidget)
        else:
            rule = yara.compile(source=self.TextEdit1.toPlainText())
            result = {}
            for i in os.listdir(self.path.text()):
                try:
                    f = open(self.path.text() + "\\" + i, "rb")
                    data = f.read()
                    matches = rule.match(data=data)
                    f.close()
                    for match in matches:
                        strings = match.strings[0]
                        result[i] = [self.path.text(), hex(strings[0]).replace("L",""), strings[1], binascii.hexlify(strings[2])]
                except IOError: # Permission denied
                    continue
            self.tableWidget.setRowCount(len(result.keys()))
            self.label4.setText(str(len(result.keys())))
            
            for idx, filename in enumerate(result.keys()):
                self.tableWidget.setItem(idx, 0, QTableWidgetItem(result[filename][0]))
                self.tableWidget.setItem(idx, 1, QTableWidgetItem(filename))
                self.tableWidget.setItem(idx, 2, QTableWidgetItem(result[filename][1]))
                self.tableWidget.setItem(idx, 3, QTableWidgetItem(result[filename][2]))
                self.tableWidget.setItem(idx, 4, QTableWidgetItem(result[filename][3]))
            self.layout.addWidget(self.tableWidget)

    def SortingTable(self):
        global header_clicked

        if header_clicked == 0:
            self.tableWidget.setSortingEnabled(True)
            hedaer_clicked = 1
        else:
            self.tableWidget.setSortingEnabled(False)
            header_clicked = 0

    def OnCreate(self, form):
        check_button = 0
        try:
            self.parent = self.FormToPyQtWidget(form)
        except:
            self.parent = self.FormToPySideWidget(form)
        self.label1 = QLabel("Folder Path : ")
        self.path = QLineEdit()
        self.PathButton = QPushButton("Path")
        self.PathButton.clicked.connect(self.choose_path)        
        self.label2 = QLabel("Yara rule")
        self.TextEdit1 = QPlainTextEdit()
        self.TextEdit1.setStyleSheet("""QPlainTextEdit{
                                            font-family:'Consolas';}""")
        self.highlighter = YaraHighlighter(self.TextEdit1.document())
        self.CheckButton = QCheckBox()
        self.label5 = QLabel("Recursive Option")
        self.TextEdit1.insertPlainText(self.data)
        self.SearchButton = QPushButton("Search")
        self.SearchButton.clicked.connect(self.Search)
        self.label3 = QLabel("Detect Count : ")
        self.label4 = QLabel("0")
        self.path2 = QLineEdit()
        self.PathButton2 = QPushButton("Path")
        self.PathButton2.clicked.connect(self.choose_path2)
        self.EnterButton = QPushButton("Enter")
        self.EnterButton.clicked.connect(self.export_csv)

        self.layout = QVBoxLayout()
        GL1 = QGridLayout()
        GL1.addWidget(self.label1, 0, 0)
        GL1.addWidget(self.path, 0, 1)
        GL1.addWidget(self.PathButton, 0, 2)
        GL1.addWidget(self.label5, 0, 3)
        GL1.addWidget(self.CheckButton, 0, 4)
        GL1.addWidget(self.label3, 0, 5)
        GL1.addWidget(self.label4, 0, 6)
        self.layout.addLayout(GL1)

        self.layout.addWidget(self.label2)
        self.layout.addWidget(self.TextEdit1)
        self.layout.addWidget(self.SearchButton)

        GL2 = QGridLayout()
        GL2.addWidget(QLabel("CSV Export"), 0, 0)
        GL2.addWidget(self.path2, 0, 1)
        GL2.addWidget(self.PathButton2, 0, 2)
        GL2.addWidget(self.EnterButton, 0, 3)
        self.layout.addLayout(GL2)

        self.tableWidget = QTableWidget()
        self.tableWidget.setRowCount(0)
        self.tableWidget.setColumnCount(5)
        self.tableWidget.setHorizontalHeaderLabels(["Path", "Filename", "Address", "Variable name", "String"])
        header = self.tableWidget.horizontalHeader()
        header.sectionClicked.connect(self.SortingTable)
        self.layout.addWidget(self.tableWidget)

        self.parent.setLayout(self.layout)

    def OnClose(self, form):
        pass

class YaraDetector(idaapi.PluginForm):
    def choose_path(self):
        path = QFileDialog.getOpenFileName(
            self.parent,
            "Open a file",
            expanduser("~"),
            "Yara Rule Files(*.yar *.yara)")

        if path:
            self.path.setText(path[0])

    def Search(self):
        result = []
        if self.CheckButton.isChecked():
            rule = yara.compile(source=self.rule)
        else:
            rulepath = open(self.path.text(), "r")
            rule = yara.compile(source=rulepath.read())
            rulepath.close()
        
        matches = rule.match(data=self.data)
        for match in matches:
            for i in match.strings:
                result.append([hex(i[0]).replace("L",""), match.rule, i[1], i[2]])

        self.tableWidget.setRowCount(len(result))
        
        for idx, i in enumerate(result):
            self.tableWidget.setItem(idx, 0, QTableWidgetItem(hex(int(i[0], 16)).replace("L","")))
            self.tableWidget.setItem(idx, 1, QTableWidgetItem(i[1]))
            self.tableWidget.setItem(idx, 2, QTableWidgetItem(i[2]))
            text_endea = idaapi.get_segm_by_name(".text").endEA
            size = idaapi.get_fileregion_ea(int(i[0], 16))

            if size < text_endea:
                a = []
                info = idaapi.get_inf_structure()
                if info.is_64bit():
                    md = Cs(CS_ARCH_X86, CS_MODE_64)
                elif info.is_32bit():
                    md = Cs(CS_ARCH_X86, CS_MODE_32)

                for i in md.disasm(i[3], 0x1000):
                    a.append(i.mnemonic + " " + i.op_str)
                self.tableWidget.setItem(idx, 3, QTableWidgetItem(' || '.join(a)))
            else:
                self.tableWidget.setItem(idx, 3, QTableWidgetItem(i[3]))

        self.layout.addWidget(self.tableWidget)

    def jump_addr(self, row, column):
        addr = int(self.tableWidget.item(row, 0).text(), 16) # RAW
        RVA = 0

        for i in range(len(self.Seg)-1):
            if self.Seg[i][0] < addr < self.Seg[i+1][0]:
                ## https://reverseengineering.stackexchange.com/questions/2835/how-to-extract-the-input-file-offset-of-a-byte-in-idapython
                RVA = idaapi.get_fileregion_ea(addr)
                break
                
        jumpto(RVA)

    def OnCreate(self, form):
        try:
            f = open(GetInputFilePath().decode("utf-8"), "rb")
        except:
            f = open(GetInputFilePath(), "rb")
        self.data = f.read()
        f.close()

        self.Seg = [[idaapi.get_fileregion_offset(i), i] for i in Segments()]
        self.Seg.append([len(self.data), 0])

        try:
            self.parent = self.FormToPyQtWidget(form)
        except:
            self.parent = self.FormToPySideWidget(form)
        self.path = QLineEdit()
        self.label1 = QLabel("Yara Path : ")
        self.PathButton = QPushButton("Yara File")
        self.PathButton.clicked.connect(self.choose_path)
        self.label2 = QLabel("Hyara Rule")
        self.CheckButton = QCheckBox()
        self.SearchButton = QPushButton("Search")
        self.SearchButton.clicked.connect(self.Search)

        self.layout = QVBoxLayout()
        GL1 = QGridLayout()
        GL1.addWidget(self.label1, 0, 0)
        GL1.addWidget(self.path, 0, 1)
        GL1.addWidget(self.PathButton, 0, 2)
        GL1.addWidget(self.label2, 0, 3)
        GL1.addWidget(self.CheckButton, 0, 4)
        self.layout.addLayout(GL1)
        self.layout.addWidget(self.SearchButton)

        self.tableWidget = QTableWidget()
        self.tableWidget.cellClicked.connect(self.jump_addr)
        self.tableWidget.setRowCount(0)
        self.tableWidget.setColumnCount(4)
        self.tableWidget.setHorizontalHeaderLabels(["Address", "Rule name", "Variable name", "String"])
        self.layout.addWidget(self.tableWidget)

        self.parent.setLayout(self.layout)

    def OnClose(self, form):
        pass

## https://gist.github.com/romainthomas/bce94f1c37215f644e0c
class Wrapper(idaapi.IDAViewWrapper):
    def __init__(self, title, num):
        idaapi.IDAViewWrapper.__init__(self, title)
        self.num = num

    def OnViewClick(self, px, py, state):
        widget = idaapi.pycim_get_tcustom_control(self)
        from_mouse = False

        line = idaapi.get_custom_viewer_curline(widget, from_mouse)
        line = line[line.find(":")+len(":"):]
        if ida7_version == 1:
            line = binascii.hexlify(line).split("2002")[0]
            line = binascii.unhexlify(line)
        else:
            line = binascii.hexlify(line).split("0213")[0]
            line = binascii.unhexlify(line)
        
        if self.num == "1":
            StartAddress.setText(line)
        elif self.num == "2":
            EndAddress.setText(line)

class Hyara(idaapi.PluginForm):
    def YaraExport(self):

        def pretty_hex(data):
            return ' '.join(data[i:i+2] for i in range(0, len(data), 2))

        def rich_header():
            try:
                pe = pefile.PE(GetInputFilePath().decode("utf-8"))
            except:
                pe = pefile.PE(GetInputFilePath())

            rich_header = pe.parse_rich_header()
            return hashlib.md5(rich_header['clear_data']).hexdigest()

        def imphash():
            try:
                pe = pefile.PE(GetInputFilePath().decode("utf-8"))
            except:
                pe = pefile.PE(GetInputFilePath())
            return pe.get_imphash()

        global ruleset_list
        info = idaapi.get_inf_structure()
        if info.is_64bit():
            md = Cs(CS_ARCH_X86, CS_MODE_64)
        elif info.is_32bit():
            md = Cs(CS_ARCH_X86, CS_MODE_32)
        result = "import \"hash\"\n"
        result += "import \"pe\"\n\n"
        result += "rule " + self.Variable_name.text() + "\n{\n"
        result += "  meta:\n"
        result += "      tool = \"https://github.com/hy00un/Hyara\"\n"
        result += "      version = \"" + "1.8" + "\"\n"
        result += "      date = \"" + time.strftime("%Y-%m-%d") + "\"\n"
        result += "      MD5 = \"" + idautils.GetInputFileMD5() + "\"\n"
        result += "  strings:\n"
        for name in ruleset_list.keys():
            try:
                CODE = bytearray.fromhex(ruleset_list[name][0][1:-1].strip().replace("\\x"," "))
                print(CODE)
                print(type(CODE))
                if self.CheckBox1.isChecked():
                    result += "      /*\n"
                    for i in md.disasm(bytes(CODE), 0x1000):
                        byte_data = "".join('{:02X}'.format(x) for x in i.bytes)
                        result += "          %-10s\t%-30s\t\t|%s" % (i.mnemonic.upper(), i.op_str.upper().replace("0X","0x"), byte_data.upper()) + "\n"
                    result += "      */\n"

                ## http://sparksandflames.com/files/x86InstructionChart.html
                ## https://pnx.tf/files/x86_opcode_structure_and_instruction_overview.png
                ## http://ref.x86asm.net/coder32.html
                ## http://www.mathemainzel.info/files/x86asmref.html #
                if self.CheckBox2.isChecked(): # yara wildcard isChecked()
                    opcode = []
                    CODE = bytearray.fromhex(ruleset_list[name][0][1:-1].strip().replace("\\x"," "))
                    for i in md.disasm(bytes(CODE), 0x1000):
                        byte_data = "".join('{:02X}'.format(x) for x in i.bytes)

                        if byte_data.startswith("FF"): # ex) ff d7 -> call edi
                            opcode.append("FF [1-5]")

                        elif byte_data.startswith("0F"): # ex) 0f 84 bb 00 00 00 -> jz loc_40112A, 0f b6 0b -> movzx cx, byte ptr [ebx]
                            opcode.append("0F [1-5]") # (multi byte)

                        elif re.compile("7[0-9A-F]").match(byte_data): # jo, jno, jb, jnb, jz, jnz, jbe, ja, js, jns, jp, jnp, jl, jnl, jle, jnle
                            opcode.append(byte_data[:2]+" ??") # ex) 7c 7f -> jl 0x81 (7c only 1 byte) (1byte < have 0f)

                        elif i.mnemonic == "push":
                            if re.compile("5[0-7]|0(6|E)|1(6|E)").match(byte_data): # push e[a-b-c]x ..
                                opcode.append(byte_data[:1]+"?")
                            elif re.compile("6(8|A)+").match(byte_data):
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "pop":
                            if re.compile("5[8-F]|07|1(7|F)").match(byte_data): # pop e[a-b-c]x ..
                                opcode.append(byte_data[:1]+"?")
                            elif re.compile("8F").match(byte_data):
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "mov":
                            if re.compile("B[8-F]").match(byte_data): # ex) b8 01 22 00 00 -> mov eax, 0x2201, bf 38 00 00 00 -> mov edi, 38 , 8b 54 24 10 -> mov edx, [esp+32ch+var_31c]
                                opcode.append(byte_data[:2]+" [4]")
                            elif re.compile("B[0-7]").match(byte_data): # ex) b7 60 -> mov bh, 0x60
                                opcode.append("B? "+byte_data[2:])
                            elif re.compile("8[8-9A-C]|8E").match(byte_data): # ex) 8b 3d a8 e1 40 00 -> mov edi, ds:GetDlgItem
                                opcode.append(byte_data[:2]+" [1-4]") # ex) 8b 5c 24 14 -> mob ebx, [esp+10+ThreadParameter] , 8b f0 -> mov esi, eax
                            elif re.compile("C[6-7]").match(byte_data): # ex) c7 44 24 1c 00 00 00 00 -> mov [esp+338+var_31c], 0
                                opcode.append(byte_data[:2]+" [2-8]")
                            elif re.compile("A[0-3]").match(byte_data):
                                opcode.append(byte_data[:2]+" [1-4]") # ex) a1 60 40 41 00 -> mov eax, __security_cookie
                            else:
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "inc":
                            if re.compile("4[0-7]").match(byte_data):
                                opcode.append(byte_data[:1]+"?")
                            else:
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "dec":
                            if re.compile("4[8-9A-F]").match(byte_data): # 48 ~ 4f
                                opcode.append(byte_data[:1]+"?")
                            else:
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "xor":
                            if re.compile("3[0-3]").match(byte_data):
                                opcode.append(byte_data[:2]+" [1-4]")
                            elif re.compile("34").match(byte_data): # ex) 34 da -> xor al, 0xda 
                                opcode.append(byte_data[:2]+" ??")
                            elif re.compile("35").match(byte_data): # ex) 35 da 00 00 00 -> xor eax, 0xda
                                opcode.append("35 [4]")
                            else:
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "add":
                            if re.compile("0[0-3]").match(byte_data):
                                opcode.append(byte_data[:2]+" [1-4]")
                            elif re.compile("04").match(byte_data): # ex) 04 da -> xor al, 0xda 
                                opcode.append(byte_data[:2]+" ??")
                            elif re.compile("05").match(byte_data): # ex) 05 da 00 00 00 -> xor eax, 0xda
                                opcode.append("05 [4]")
                            else:
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "call":
                            if re.compile("E8").match(byte_data):
                                opcode.append("E8 [4]") # call address(?? ?? ?? ??)
                            else:
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "test":
                            if re.compile("8[4-5]|A8").match(byte_data): # ex) 84 ea -> test dl, ch
                                opcode.append(byte_data[:2]+" ??") 
                            elif re.compile("A9").match(byte_data): # ex) a9 ea 00 00 00 -> test eax, 0xea
                                opcode.append("A9 [4]")
                            elif re.compile("F[6-7]").match(byte_data):
                                opcode.append(byte_data[:2]+" [2-7]")
                            else:
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "and":
                            if re.compile("8[0-3]").match(byte_data):
                                opcode.append(byte_data[:2] + " " + byte_data[2:3] + "? [4]") # ex) 81 e3 f8 07 00 00 -> and ebx, 7f8
                            elif re.compile("2[0-3]").match(byte_data):
                                opcode.append(byte_data[:2]+" [1-4]")
                            elif re.compile("24").match(byte_data):
                                opcode.append(byte_data[:2]+" ??") # ex) 22 d1 -> and dl, cl
                            elif re.compile("25").match(byte_data):
                                opcode.append(byte_data[:2]+" [4]")
                            else:
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "lea":
                            if re.compile("8D").match(byte_data): # ex) 8d 9b 00 00 00 00 -> lea ebx, [ebx+0] == 8d 1b
                                opcode.append("8D [1-6]")
                            else:
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "sub":
                            if re.compile("2[8A-B]").match(byte_data): # ex) 2a 5c 24 14 -> sub	bl, byte ptr [esp + 0x14]
                                opcode.append(byte_data[:2]+" [1-4]")
                            elif re.compile("2C").match(byte_data): # ex) 28 da -> sub dl, bl
                                opcode.append(byte_data[:2]+" ??")
                            elif re.compile("2D").match(byte_data): # ex) 2d da 00 00 00 -> sub eax, 0xda
                                opcode.append("2D [4]")
                            elif re.compile("8[2-3]").match(byte_data):
                                opcode.append("8? "+byte_data[2:])
                            else:
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "or":
                            if re.compile("0[8A-B]").match(byte_data): # ex) 08 14 30 -> or byte ptr [eax + esi], dl , 0b 5c 24 14 -> or ebx, dword ptr [esp + 0x14]
                                opcode.append(byte_data[:2]+" [1-4]")
                            elif re.compile("0C").match(byte_data): # ex) 0c ea -> or al, 0xea
                                opcode.append(byte_data[:2]+" ??")
                            elif re.compile("0D").match(byte_data): # ex) 0d ea 00 00 00 -> or eax, 0xea
                                opcode.append("0D [4]")
                            else:
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "cmp":
                            if re.compile("3[8A-B]").match(byte_data):
                                opcode.append(byte_data[:2]+" [1-4]")
                            elif re.compile("3C").match(byte_data): # ex) 3a ea -> cmp ch, dl
                                opcode.append(byte_data[:2]+" ??")
                            elif re.compile("3D").match(byte_data): # ex) 3d ea 00 00 00 -> cmp eax, 0xea
                                opcode.append("3D [4]")
                            else:
                                opcode.append(pretty_hex(byte_data))

                        elif i.mnemonic == "shl" or i.mnemonic == "sar":
                            if re.compile("C[0-1]").match(byte_data): # ex) c1 fa 02 -> sar edx, 2 , 
                                opcode.append(byte_data[:2]+" [2]")
                            elif re.compile("D[0-3]").match(byte_data): # ex) d0 fa -> sar dl, 1
                                opcode.append(byte_data[:2]+" ??")
                            else:
                                opcode.append(pretty_hex(byte_data))
                        
                        elif i.mnemonic == "xchg":
                            if re.compile("9[1-7]").match(byte_data):
                                opcode.append(byte_data[:1]+"?")
                            elif re.compile("8[6-7]").match(byte_data):
                                opcode.append(byte_Data[:2]+ " [1-6]")
                            else:
                                opcode.append(pretty_hex(byte_data))

                        else:
                            opcode.append(pretty_hex(byte_data))


                    try:
                        if ''.join(opcode)[-1] == "]": # syntax error, unexpected '}', expecting _BYTE_ or _MASKED_BYTE_ or '(' or '['
                            opcode.append("??")
                    except:
                        pass

                    result += "      $" + name + " = {" + ' '.join(opcode).upper() + "}\n"
                else:
                    opcode = pretty_hex(ruleset_list[name][0][1:-1])
                    result += "      $" + name + " = {" + opcode.upper() +"}\n"
            except ValueError: # string option
                result += "      $" + name + " = " + ruleset_list[name][0]+"\n"
        result += "  condition:\n"
        result += "      all of them"
        if self.CheckBox4.isChecked():
            result += " and hash.md5(pe.rich_signature.clear_data) == \"" + rich_header() + "\""
        
        if self.CheckBox5.isChecked():
            result += " and pe.imphash() == \"" + imphash() + "\""
        result += "\n}"
        self.TextEdit1.clear()
        self.TextEdit1.insertPlainText(result)

    def DeleteRule(self):
        global ruleset_list, tableWidget, layout

        if idaapi.ask_yn(idaapi.ASKBTN_NO, "Delete Yara Rule") == idaapi.ASKBTN_YES:
            ruleset_list = {}

        tableWidget.setRowCount(len(ruleset_list.keys()))
        tableWidget.setColumnCount(4)
        tableWidget.setHorizontalHeaderLabels(["Variable_name", "Rule", "Start", "End"])
        for idx, name in enumerate(ruleset_list.keys()):
            tableWidget.setItem(idx, 0, QTableWidgetItem(name))
            tableWidget.setItem(idx, 1, QTableWidgetItem(ruleset_list[name][0]))
            tableWidget.setItem(idx, 2, QTableWidgetItem(ruleset_list[name][1]))
            tableWidget.setItem(idx, 3, QTableWidgetItem(ruleset_list[name][2]))
        layout.addWidget(tableWidget)

    def MakeRule(self):
        global StartAddress, EndAddress
        blacklist = ["unk_", "loc_", "SEH_","sub_"]
        start = int(StartAddress.text(), 16)
        end = int(EndAddress.text(), 16)

        if self.CheckBox3.isChecked(): # Use String Option
            StringData = []
            ## https://reverseengineering.stackexchange.com/questions/3603/how-to-extract-all-the-rodata-data-and-bss-section-using-idc-script-in-ida-pro
            text_section_endEA = idaapi.get_segm_by_name(".text").endEA

            if text_section_endEA > start:
                while start <= end:
                    if "offset" in GetOpnd(start, 0) and not any(i in GetOpnd(start, 0) for i in blacklist):
                        variable = GetOpnd(start, 0).split(" ")[1]
                        add = get_name_ea(start,variable)
                        string, endEA = get_string(add)
                        StringData.append(string)

                    elif "offset" in GetOpnd(start, 1) and not any(i in GetOpnd(start, 1) for i in blacklist):
                        variable = GetOpnd(start, 1).split(" ")[1]
                        add = get_name_ea(start,variable)
                        string, endEA = get_string(add)
                        StringData.append(string)
                    
                    start = idc.NextHead(start)

                StringData = [x for x in StringData if x]
                self.TextEdit1.clear()
                for i in StringData:
                    if i == "":
                        continue

                    self.TextEdit1.insertPlainText("\""+ i.replace("\\","\\\\") + "\"" + " nocase wide ascii" + "\n")

                TE1_text = self.TextEdit1.toPlainText().rstrip('\n')
                self.TextEdit1.clear()
                self.TextEdit1.insertPlainText(TE1_text)

            else:
                while start <= end:
                    string, endEA = get_string(start)
                    StringData.append(string)
                    start = endEA
                StringData = [x for x in StringData if x]
                self.TextEdit1.clear()
                for i in StringData:
                    if i == "":
                        continue

                    self.TextEdit1.insertPlainText("\""+ i.replace("\\","\\\\") +"\"" + " nocase wide ascii" + "\n")

                TE1_text = self.TextEdit1.toPlainText().rstrip('\n')
                self.TextEdit1.clear()
                self.TextEdit1.insertPlainText(TE1_text)

        else:
            ByteCode = []
            while start <= end:
                sub_end = idc.NextHead(start)
                data = binascii.hexlify(idc.GetManyBytes(start, sub_end-start))
                ByteCode.append(data)
                start = sub_end

            self.TextEdit1.clear()
            self.TextEdit1.insertPlainText("{" + ''.join(ByteCode).upper() + "}")

    def SaveRule(self):
        global ruleset_list, tableWidget, layout, StartAddress, EndAddress
        #info = idaapi.get_inf_structure()
        #if info.is_64bit():
        #    md = Cs(CS_ARCH_X86, CS_MODE_64)
        #elif info.is_32bit():
        #    md = Cs(CS_ARCH_X86, CS_MODE_32)
        #CODE = bytearray.fromhex(self.TextEdit1.toPlainText()[1:-1].strip().replace("\\x"," "))
        #for i in md.disasm(CODE, 0x1000):
        #    print("0x%x:\t%s\t%s" %(i.address, i.mnemonic, i.op_str))
        if self.CheckBox3.isChecked(): # Use String Option
            count = 0
            data = self.TextEdit1.toPlainText().split("\n")
            for i in data:
                ruleset_list[self.Variable_name.text() + "_" + str(count)] = [i, StartAddress.text(), EndAddress.text()]
                count += 1
        else:
            ruleset_list[self.Variable_name.text()] = [self.TextEdit1.toPlainText(), StartAddress.text(), EndAddress.text()]
        
        ruleset_list = OrderedDict(sorted(ruleset_list.items(), key=lambda x: x[0]))
        tableWidget.setRowCount(len(ruleset_list.keys()))
        tableWidget.setColumnCount(4)
        tableWidget.setHorizontalHeaderLabels(["Variable_name", "Rule", "Start", "End"])
        for idx, name in enumerate(ruleset_list.keys()):
            tableWidget.setItem(idx, 0, QTableWidgetItem(name))
            tableWidget.setItem(idx, 1, QTableWidgetItem(ruleset_list[name][0]))
            tableWidget.setItem(idx, 2, QTableWidgetItem(ruleset_list[name][1]))
            tableWidget.setItem(idx, 3, QTableWidgetItem(ruleset_list[name][2]))
        layout.addWidget(tableWidget)

    def YaraChecker(self):
        self.YaraChecker = YaraChecker()
        self.YaraChecker.data = self.TextEdit1.toPlainText()
        self.YaraChecker.Show("YaraChecker")

    def YaraIcon(self):
        self.YaraIcon = YaraIcon()
        self.YaraIcon.Show("YaraIcon")

    def IDAWrapper(self, num):
        global flag, c

        if flag == 1:
            c.Unbind()
            flag = 0
            print("[*] idaapi.IDAViewWrapper Unbind")

        elif num == "1":
            c = Wrapper("IDA View-A", num)
            c.Bind()
            print("[*] StartAddress SelectWrapper")
            flag = 1

        elif num == "2":
            c = Wrapper("IDA View-A", num)
            c.Bind()
            print("[*] EndAddress SelectWrapper")
            flag = 1

    def YaraDetector(self):
        self.YaraDetector = YaraDetector()
        self.YaraDetector.rule = self.TextEdit1.toPlainText()
        self.YaraDetector.Show("YaraDetector")

    def OnCreate(self, form):
        global tableWidget, layout

        try:
            self.parent = self.FormToPyQtWidget(form)
        except:
            self.parent = self.FormToPySideWidget(form)
        self.label1 = QLabel("Variable Name : ")
        self.label_1 = QLabel("comment option")
        self.CheckBox1 = QCheckBox()
        self.label_2 = QLabel("wildcard option")
        self.CheckBox2 = QCheckBox()
        self.label_3 = QLabel("string option")
        self.CheckBox3 = QCheckBox()
        self.label_4 = QLabel("rich header")
        self.CheckBox4 = QCheckBox()
        self.label_5 = QLabel("imphash")
        self.CheckBox5 = QCheckBox()
        self.Variable_name = QLineEdit()
        self.label2 = QLabel("Start Address : ")
        # self.StartAddress = QLineEdit()
        self.PushButton1 = QPushButton("Select / Exit")
        self.PushButton1.clicked.connect(partial(self.IDAWrapper,"1"))
        self.label3 = QLabel("End Address : ")
        # self.EndAddress = QLineEdit()
        self.TextEdit1 = QPlainTextEdit()
        self.PushButton2 = QPushButton("Select / Exit")
        self.PushButton2.clicked.connect(partial(self.IDAWrapper,"2"))

        self.MakeButton = QPushButton("Make")
        self.MakeButton.clicked.connect(self.MakeRule)
        self.SaveButton = QPushButton("Save")
        self.SaveButton.clicked.connect(self.SaveRule)
        self.DeleteButton = QPushButton("Delete")
        self.DeleteButton.clicked.connect(self.DeleteRule)
        self.YaraExportButton = QPushButton("Export Yara Rule")
        self.YaraExportButton.clicked.connect(self.YaraExport)
        self.YaraCheckerButton = QPushButton("Yara Checker")
        self.YaraCheckerButton.clicked.connect(self.YaraChecker)
        self.YaraDetectorButton = QPushButton("Yara Detector")
        self.YaraDetectorButton.clicked.connect(self.YaraDetector)
        self.YaraIconButton = QPushButton("Yara Icon")
        self.YaraIconButton.clicked.connect(self.YaraIcon)

        GL1 = QGridLayout()
        GL1.addWidget(self.label1, 0, 0)
        GL1.addWidget(self.Variable_name, 0, 1)
        layout.addLayout(GL1)

        GL2 = QGridLayout()
        GL2.addWidget(self.label2, 0, 0)
        GL2.addWidget(StartAddress, 0, 1) # global variable
        GL2.addWidget(self.PushButton1, 0, 2)
        GL2.addWidget(self.label3, 0, 3)
        GL2.addWidget(EndAddress, 0, 4) # global variable
        GL2.addWidget(self.PushButton2, 0, 5)
        layout.addLayout(GL2)

        GL3 = QGridLayout()
        GL3.addWidget(self.label_1 , 0, 0)
        GL3.addWidget(self.CheckBox1, 0, 1)
        GL3.addWidget(self.label_2 , 0, 2)
        GL3.addWidget(self.CheckBox2, 0, 3)
        GL3.addWidget(self.label_3 , 0, 4)
        GL3.addWidget(self.CheckBox3, 0, 5)
        GL3.addWidget(self.label_4 , 0, 6)
        GL3.addWidget(self.CheckBox4, 0, 7)
        GL3.addWidget(self.label_5 , 0, 8)
        GL3.addWidget(self.CheckBox5, 0, 9)
        layout.addLayout(GL3)

        layout.addWidget(self.TextEdit1)

        GL4 = QGridLayout()
        GL4.addWidget(self.MakeButton, 0, 0)
        GL4.addWidget(self.SaveButton, 0, 1)
        GL4.addWidget(self.DeleteButton, 0, 2)
        GL4.addWidget(self.YaraExportButton, 0, 3)
        GL4.addWidget(self.YaraCheckerButton, 0, 4)
        GL4.addWidget(self.YaraDetectorButton, 0, 5)
        GL4.addWidget(self.YaraIconButton, 0, 6)
        layout.addLayout(GL4)

        tableWidget.setRowCount(0)
        tableWidget.setColumnCount(4)
        tableWidget.setHorizontalHeaderLabels(["Variable_name", "Rule", "Start", "End"])
        layout.addWidget(tableWidget)

        self.parent.setLayout(layout)

    def OnClose(self, form):
        pass

class YaraPlugin(idaapi.plugin_t):
    flags = idaapi.PLUGIN_UNL
    comment = "Hyara"
    help = "help"
    wanted_name = "Hyara"
    wanted_hotkey = "Ctrl+Shift+Y"

    def init(self):
        idaapi.msg("[*] Hyara Plugin\n")
        return idaapi.PLUGIN_OK

    def run(self, arg):
        plg = Hyara()
        plg.Show("Hyara")
        try:
            widget_a = find_widget("IDA View-A")
            widget_Hyara = find_widget("Hyara")
            widget_OW = find_widget("Output window")
            if widget_Hyara and widget_a:
                set_dock_pos("Hyara", "IDA View-A", DP_RIGHT)

                if widget_OW:
                    set_dock_pos("Output window", "Functions window", DP_BOTTOM)
        except:
            print "find_widget option is available version 7.0 or later"
        

    def term(self):
        pass

def PLUGIN_ENTRY():
    return YaraPlugin()
