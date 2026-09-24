# -*- coding: utf-8 -*-
"""多文件室内→室外冷启动分析 HMI。"""
from __future__ import annotations
import json
import subprocess
import sys
import threading
import traceback
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import gnss_sat_status_core as core
import aux_quality as aux


APP_TITLE = "北云UG016 GNSS室内→室外冷启动分析 HMI"
ROOT = Path(__file__).resolve().parent


class App:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title(APP_TITLE)
        self.root.geometry("1160x780")
        self.root.minsize(980, 650)
        self._build_style()
        self._build_ui()
        self._running = False

    def _build_style(self):
        style = ttk.Style(self.root)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("TButton", padding=(8,5))
        style.configure("Treeview", rowheight=28, font=("Microsoft YaHei",10))
        style.configure("Heading", font=("Microsoft YaHei",10,"bold"))

    def _build_ui(self):
        top=ttk.Frame(self.root,padding=10); top.pack(fill="x")
        ttk.Button(top,text="选择文件（可多选）",command=self.select_files).pack(side="left")
        ttk.Button(top,text="全选 by_data",command=self.select_all).pack(side="left",padx=6)
        ttk.Button(top,text="移除选中",command=self.remove_selected).pack(side="left")
        ttk.Button(top,text="清空列表",command=self.clear_files).pack(side="left",padx=6)
        self.time_mode=tk.StringVar(value="per_file")
        ttk.Label(top,text="多选=每个文件独立生成一份报告；冷启动分析已合并到同一份报告").pack(side="left",padx=12)

        ttk.Button(top,text="开始分析并生成报告",command=self.run).pack(side="right",padx=6)
        ttk.Button(top,text="打开报告目录",command=self.open_report_root).pack(side="right",padx=6)

        columns=("file","size_mb","best","gsv_batch","ins")
        self.table=ttk.Treeview(self.root,columns=columns,show="headings",selectmode="extended")
        for col,text,width in (
            ("file","数据文件",420),("size_mb","大小MB",80),("best","BEST",70),
            ("gsv_batch","GSV批",70),("ins","INS",70)):
            self.table.heading(col,text=text); self.table.column(col,width=width,anchor="w")
        self.table.pack(fill="both",expand=True,padx=10,pady=8)

        self.status=ttk.Label(self.root,text="请选择 by_data 中的数据文件。",anchor="w",padding=(10,6))
        self.status.pack(fill="x")
        self.progress=ttk.Progressbar(self.root,mode="indeterminate")

    def _set_status(self,text,running=False):
        self.status.config(text=text)
        if running and not self.progress.winfo_ismapped(): self.progress.pack(fill="x",padx=10,pady=(0,10))
        if not running and self.progress.winfo_ismapped(): self.progress.pack_forget()

    def select_files(self):
        paths=filedialog.askopenfilenames(initialdir=ROOT/"by_data",title="选择GNSS原始数据（可多选）",filetypes=[("GNSS raw","*.txt *.log *.gnss *.dat"),("All files","*.*")])
        for p in paths:self._add_file(Path(p))

    def select_all(self):
        for p in sorted((ROOT/"by_data").glob("*")):
            if p.is_file(): self._add_file(p)

    def _add_file(self,path):
        for iid in self.table.get_children():
            if Path(self.table.set(iid,"file"))==path:return
        # 预扫描只统计报文，不生成报告。
        try:d=aux.parse_aux(path); counts=(len(d.best),d.counts.get("GSV_batches",0),len(d.ins))
        except Exception as e: counts=("错误",0,0)
        self.table.insert("", "end", values=(str(path),f"{path.stat().st_size/1048576:.2f}",*counts))

    def remove_selected(self):
        for iid in self.table.selection():self.table.delete(iid)

    def clear_files(self):self.table.delete(*self.table.get_children())

    def open_report_root(self):
        path=ROOT/"report";path.mkdir(exist_ok=True);subprocess.Popen(["explorer",str(path)])

    def run(self):
        if self._running:return
        items=self.table.get_children()
        if not items:
            messagebox.showwarning(APP_TITLE,"请先选择至少一个数据文件。");return
        paths=[Path(self.table.set(i,"file")) for i in items]
        mode="per_file"
        self._running=True;self._set_status("正在解析报文、计算关键事件并生成图表/报告...",True);self.progress.start(12)
        th=threading.Thread(target=self._worker,args=(paths,mode),daemon=True);th.start()

    def _worker(self,paths,mode):
        try:
            outputs=core.run_full_analysis(paths,ROOT/"report",x_mode=mode,create_memory=True,memory_root=ROOT/"Memory"); report=outputs[0][1]; report_dir=outputs[0][0]
            message=f"完成：{report.parent}"
            self.root.after(0,lambda:self._done(message,report))
        except Exception as e:
            err="".join(traceback.format_exception_only(type(e),e)).strip()
            self.root.after(0,lambda:self._error(err))

    def _done(self,message,report):
        self.progress.stop();self.progress.pack_forget();self._running=False;self._set_status(message)
        if messagebox.askyesno(APP_TITLE,"报告生成完成，是否立即打开HTML报告？"):webbrowser.open(str(report))

    def _error(self,message):
        self.progress.stop();self.progress.pack_forget();self._running=False;self._set_status("分析失败。")
        messagebox.showerror(APP_TITLE,message)

    def mainloop(self):self.root.mainloop()


if __name__=="__main__":
    App().mainloop()



