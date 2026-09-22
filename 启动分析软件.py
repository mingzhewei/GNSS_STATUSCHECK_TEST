# -*- coding: utf-8 -*-
"""北云UG016室内→室外冷启动分析软件快捷启动器。"""
import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from gnss_sat_status_hmi import App
if __name__=="__main__":App().mainloop()
