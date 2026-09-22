# -*- coding: utf-8 -*-
"""扩展分析：GSV信号质量、INSPVAXA质量、定位σ/差分龄期、位置跳变与状态链路。"""
from __future__ import annotations
from dataclasses import dataclass, field
from math import radians, sin, cos, sqrt, atan2
from typing import Callable


@dataclass
class GsvSatellite:
    constellation: str
    prn: int
    elevation_deg: float | None
    azimuth_deg: float | None
    snr_dbhz: float | None
    @property
    def has_signal(self): return self.snr_dbhz is not None and self.snr_dbhz > 0

@dataclass
class GsvEpoch:
    t: float
    week: int
    tow: float
    visible_total: int
    satellites: list[GsvSatellite] = field(default_factory=list)
    @property
    def with_snr(self): return sum(s.has_signal for s in self.satellites)
    @property
    def snr_values(self): return [s.snr_dbhz for s in self.satellites if s.has_signal]
    @property
    def high_visible(self): return sum((s.elevation_deg or 0)>=30 for s in self.satellites)
    @property
    def high_with_snr(self): return sum((s.elevation_deg or 0)>=30 and s.has_signal for s in self.satellites)
    @property
    def above_35dbhz(self): return sum(s.has_signal and s.snr_dbhz>=35 for s in self.satellites)

@dataclass
class InsSample:
    t: float; week:int; tow:float; time_status:str; ins_status:str; pos_type:str
    lat_sigma:float|None; lon_sigma:float|None; hgt_sigma:float|None

@dataclass
class BestQuality:
    t: float; week:int; tow:float; time_status:str; sol_status:str; pos_type:str
    lat:float; lon:float; hgt:float
    lat_sigma:float; lon_sigma:float; hgt_sigma:float
    station_id:str; diff_age:float|None; sol_age:float|None
    tracked:int; used:int; l1:int; multi:int

@dataclass
class KsxtSample:
    t: float
    utc_text: str
    positioning_status:int|None
    positioning_satellites:int|None
    diff_age:float|None
    base_satellites:int|None

@dataclass
class AuxData:
    gsv_epochs:list[GsvEpoch]=field(default_factory=list)
    ins:list[InsSample]=field(default_factory=list)
    best:list[BestQuality]=field(default_factory=list)
    ksxt:list[KsxtSample]=field(default_factory=list)
    counts:dict[str,int]=field(default_factory=dict)
    bad_counts:dict[str,int]=field(default_factory=dict)
    gsv_time_alignment:str="GSV时间=该批次前最近BESTGNSSPOSA头时间（顺序近似，GSV自身无GPS周/周内秒）"


GSV_PREFIXES={"GPGSV":"GPS","GLGSV":"GLONASS","GAGSV":"Galileo","GBGSV":"BDS","GQGSV":"QZSS"}

def crc32_manual(data:bytes)->int:
    c=0
    for b in data:
        c^=b
        for _ in range(8): c=(c>>1)^0xEDB88320 if c&1 else c>>1
    return c&0xffffffff

def _num(v):
    try:
        if v is None or v=="": return None
        return float(v)
    except ValueError: return None

def _valid_payload(line:bytes)->str|None:
    star=line.rfind(b"*")
    if star<=0:return None
    try:
        if line.startswith(b"$KSXT,"):
            expected=int(line[star+1:star+9],16);actual=crc32_manual(line[1:star])
        elif line.startswith(b"$"):
            expected=int(line[star+1:star+3],16);actual=0
            for b in line[1:star]:actual^=b
        elif line.startswith(b"#"):
            expected=int(line[star+1:star+9],16);actual=crc32_manual(line[1:star])
        else:
            return None
        return line[1:star].decode("ascii","strict") if expected==actual else None
    except (ValueError,UnicodeDecodeError):return None


def _time(hf):
    try:
        week=int(hf[5]);tow=float(hf[6])
        if 0<=tow<604800:return week*604800.0+tow,week,tow
    except (ValueError,IndexError):pass
    return None


def parse_aux(path)->AuxData:
    d=AuxData(); gsv_batch={}; gsv_sats=[]; gsv_last_ref=None
    with open(path,"rb") as f:
        for raw in f:
            line=raw.rstrip(b"\r\n")
            if not line:continue
            if line.startswith(b"#"):
                text=_valid_payload(line)
                name=line[1:line.find(b",",1)].decode("ascii","ignore") if b"," in line else ""
                if text is None:
                    d.bad_counts[name]=d.bad_counts.get(name,0)+1;continue
                if ";" not in text:continue
                h,b=text.split(";",1);hf=h.split(",");bf=b.split(",")
                tm=_time(hf)
                if not tm:continue
                t,week,tow=tm
                if hf[0]=="INSPVAXA" and len(bf)>=23:
                    d.ins.append(InsSample(t,week,tow,hf[4].strip(),bf[0].strip(),bf[1].strip(),_num(bf[12]),_num(bf[13]),_num(bf[14])))
                    d.counts["INSPVAXA"]=d.counts.get("INSPVAXA",0)+1
                elif hf[0]=="BESTGNSSPOSA" and len(bf)>=21:
                    d.best.append(BestQuality(t,week,tow,hf[4].strip(),bf[0].strip(),bf[1].strip(),float(bf[2]),float(bf[3]),float(bf[4]),float(bf[7]),float(bf[8]),float(bf[9]),bf[10].strip('"'),_num(bf[11]),_num(bf[12]),int(bf[13]),int(bf[14]),int(bf[15]),int(bf[16])))
                    d.counts["BESTGNSSPOSA"]=d.counts.get("BESTGNSSPOSA",0)+1
                    gsv_last_ref=d.best[-1]
            elif line.startswith(b"$"):
                text=_valid_payload(line)
                name=line[1:line.find(b",",1)].decode("ascii","ignore") if b"," in line else ""
                if text is None:
                    d.bad_counts[name]=d.bad_counts.get(name,0)+1;continue
                fs=text.split(",")
                if fs[0]=="KSXT" and len(fs)>=22:
                    ref=d.best[-1] if d.best else None
                    if ref is not None:
                        d.ksxt.append(KsxtSample(ref.t,fs[0],int(fs[10]) if fs[10] else None,int(fs[13]) if fs[13] else None,_num(fs[20]),int(fs[21]) if fs[21] else None))
                        d.counts["KSXT"]=d.counts.get("KSXT",0)+1
                    continue
                if fs[0] not in GSV_PREFIXES:continue
                try:total=int(fs[1]);no=int(fs[2]);visible=int(fs[3])
                except (ValueError,IndexError):continue
                if total<1 or no<1 or no>total:continue
                key=fs[0]
                # 手册4.1.8：同一系统可有多条GSV，序号从1到总消息数。同一秒内按系统完整批次解析。
                if no==1:
                    if gsv_batch and key in gsv_batch:
                        _flush_gsv_batch(d,gsv_batch,gsv_sats,gsv_last_ref)
                        gsv_batch={};gsv_sats=[]
                    if not gsv_batch:
                        gsv_batch={};gsv_sats=[]
                gsv_batch[key]=total
                for k in range(4,len(fs),4):
                    try:prn=int(fs[k])
                    except ValueError:continue
                    gsv_sats.append(GsvSatellite(GSV_PREFIXES[key],prn,_num(fs[k+1]),_num(fs[k+2]),_num(fs[k+3])))
                # 所有已出现系统的最后一个序号均达到该系统总消息数时，作为完整批次。
                if all(no==total for key,total in gsv_batch.items()):
                    _flush_gsv_batch(d,gsv_batch,gsv_sats,gsv_last_ref)
                    gsv_batch={};gsv_sats=[]
    if gsv_batch:_flush_gsv_batch(d,gsv_batch,gsv_sats,gsv_last_ref)
    return d

def _flush_gsv_batch(d:AuxData,batch,sats,ref):
    if not batch or ref is None:return
    # GSV自身无GPS周/周内秒，采用本批次开始前最近BESTGNSSPOSA头时间为顺序近似。
    g=GsvEpoch(ref.t,ref.week,ref.tow,0,sats)
    g.visible_total=len(sats)
    d.gsv_epochs.append(g)
    d.counts["GSV_batches"]=d.counts.get("GSV_batches",0)+1
def horizontal_distance_m(lat1,lon1,lat2,lon2):
    # WGS84短距离近似；仅用于位置跳变筛查，不作为计量误差。
    R=6378137.0
    p1,p2=radians(lat1),radians(lat2);dl=radians(lon2-lon1);dp=p2-p1
    a=sin(dp/2)**2+cos(p1)*cos(p2)*sin(dl/2)**2
    return 2*R*atan2(sqrt(a),sqrt(1-a))


def summarize_quality(aux:AuxData):
    out=[];prev=None
    for s in aux.best:
        hsigma=max(s.lat_sigma,s.lon_sigma) if s.lat_sigma is not None and s.lon_sigma is not None else None
        jump=None if prev is None else horizontal_distance_m(prev.lat,prev.lon,s.lat,s.lon)
        out.append({"t":s.t,"week":s.week,"tow":s.tow,"time_status":s.time_status,"sol":s.sol_status,"pos":s.pos_type,"h_sigma":hsigma,"v_sigma":s.hgt_sigma,"jump_m":jump,"diff_age":s.diff_age,"sol_age":s.sol_age,"station":s.station_id,"tracked":s.tracked,"used":s.used,"l1":s.l1,"multi":s.multi})
        prev=s
    return out

def parse_gsv_batches_strict(path):
    """严格按手册4.1.8解析GSV：总消息数/序号/视野内卫星数，每条最多4颗，不足4颗为空字段。"""
    result=[]; pending={}; pending_time=None
    with open(path,"rb") as f:
        for raw in f:
            line=raw.rstrip(b"\r\n")
            if not line.startswith(b"$"):continue
            name=line[1:line.find(b",",1)].decode("ascii","ignore") if b"," in line else ""
            if name not in GSV_PREFIXES:continue
            text=_valid_payload(line)
            if text is None:continue
            fs=text.split(",")
            try:total=int(fs[1]);no=int(fs[2]);visible=int(fs[3])
            except (ValueError,IndexError):continue
            if total<1 or no<1 or no>total:continue
            key=fs[0]
            # GSV每一秒由多个同系统消息组成；同一系统同序号只保留一条，避免跨秒混批。
            pending.setdefault(key,{})
            if no not in pending[key]:
                sats=[]
                for k in range(4,len(fs),4):
                    try:prn=int(fs[k])
                    except ValueError:continue
                    sats.append(GsvSatellite(GSV_PREFIXES[key],prn,_num(fs[k+1]),_num(fs[k+2]),_num(fs[k+3])))
                pending[key][no]=(visible,sats)
            if len(pending)==len(GSV_PREFIXES) and all(len(v)==total for v in pending.values()):
                pass
    return result


