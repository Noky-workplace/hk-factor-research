from openpyxl import Workbook
from openpyxl.styles import Font, PatternFill
from openpyxl.utils import get_column_letter as L
F=Font(name="Arial"); B=Font(name="Arial",bold=True); Y=PatternFill("solid",fgColor="FFFF00")
S,E="20160101","20260918"; N=125
MACRO="""Sub SafeFreeze()
    Dim ws As Worksheet, c As Range, bad As Long
    For Each ws In ThisWorkbook.Worksheets
        For Each c In ws.UsedRange
            If VarType(c.Value) = vbString Then
                If InStr(c.Value, "Requesting") > 0 Then bad = bad + 1
            End If
        Next c
    Next ws
    If bad > 0 Then
        MsgBox "STOP: " & bad & " cells still loading. Wait, then run again.", vbCritical
        Exit Sub
    End If
    For Each ws In ThisWorkbook.Worksheets
        ws.UsedRange.Value = ws.UsedRange.Value
    Next ws
    MsgBox "Frozen. Now Save As a new name.", vbInformation
End Sub"""
wb=Workbook(); s=wb.active; s.title="Setup"
rows=[("Setting","Value","Note"),
 ("Index","HSCI Index","Hang Seng Composite ~500 names. This is the whole point: 5x the cross-section of HSI."),
 ("Batch first","1","Which member number this batch starts at. Members sheet lists them in order."),
 ("Batch size","125","Leave at 125. More than ~500 live BDH formulas is what stalled the earlier files."),
 ("","",""),
 ("BATCH WORKFLOW - repeat 4x in one session","",""),
 ("1","Refresh Workbook with Batch first = 1. Wait. SafeFreeze. Save As hsci_batch1.xlsx. Upload.",""),
 ("2","REOPEN the original file, set Batch first = 126. Refresh. SafeFreeze. Save As hsci_batch2.xlsx.",""),
 ("3","Again with 251 -> hsci_batch3.xlsx","" ),
 ("4","Again with 376 -> hsci_batch4.xlsx. Done: full HSCI covered.",""),
 ("","",""),
 ("IF IT STALLS","Delete the Static sheet (it is the heaviest) and refresh again; pull Static in its own pass at the end.",""),
 ("TIME","Each batch ~15 min. If you only get 2 done, that is still 250 stocks - upload what you have.","")]
for r in rows: s.append(r)
for c in s[1]: c.font=B
for r in (2,3,4): s.cell(r,2).font=Font(name="Arial",color="0000FF",bold=True); s.cell(r,2).fill=Y
s.column_dimensions["A"].width=34; s.column_dimensions["B"].width=70; s.column_dimensions["C"].width=95
mac=wb.create_sheet("MacroVBA")
for i,l in enumerate(MACRO.split("\n")): mac.cell(1+i,1,l)
mac.column_dimensions["A"].width=80
m=wb.create_sheet("Members")
m["A1"]='=BDS(Setup!$B$2,"INDX_MEMBERS")'
m["D1"]="A = member list (BDS). B = full ticker. C = ticker for THIS batch only (driven by Setup!B3)."
for r in range(1,601):
    m.cell(r,2,f'=IF(A{r}="","",A{r}&" Equity")')
    m.cell(r,3,f'=IFERROR(IF(INDEX($B$1:$B$600,Setup!$B$3+{r}-1)="","",INDEX($B$1:$B$600,Setup!$B$3+{r}-1)),"")')
m["E2"]="Members found:"; m["F2"]='=COUNTA(A1:A600)'
def tk(i): return f'IF(Members!$C${i}="","",Members!$C${i})'
def hist(name,field,extra=''):
    p=wb.create_sheet(name)
    for i in range(1,N+1):
        c=2*i-1
        p.cell(1,c,f'={tk(i)}'); p.cell(1,c).font=B
        p.cell(2,c,"Date"); p.cell(2,c+1,field)
        p.cell(3,c,f'=IF({L(c)}$1="","",BDH({L(c)}$1,"{field}","{S}","{E}"{extra}))')
    p.freeze_panes="A3"
ADJ=',"CshAdjNormal","Y","CshAdjAbnormal","Y","CapChg","Y"'
hist("Close","PX_LAST",ADJ); hist("Volume","PX_VOLUME"); hist("Turnover","TURNOVER")
hist("TotalReturnIdx","TOT_RETURN_INDEX_GROSS_DVDS"); hist("MktCap","CUR_MKT_CAP")
st=wb.create_sheet("Static")
flds=["NAME","GICS_SECTOR_NAME","CRNCY","EQY_SH_OUT","EQY_FREE_FLOAT_PCT","PE_RATIO","PX_TO_BOOK_RATIO","EQY_DVD_YLD_IND","ID_ISIN"]
st["A1"]="Ticker"; st["A1"].font=B
for j,f in enumerate(flds,start=2): st.cell(1,j,f); st.cell(1,j).font=B
for i in range(1,N+1):
    r=i+1; st.cell(r,1,f'={tk(i)}')
    for j,f in enumerate(flds,start=2):
        st.cell(r,j,f'=IF($A{r}="","",BDP($A{r},"{f}"))')
ah=wb.create_sheet("AH_Pairs")
ah["A1"]="H-share members of the AH Premium index (these are the dual-listed names):"; ah["A1"].font=B
ah["A2"]='=BDS("HSAHP Index","INDX_MEMBERS")'
ah["D1"]="Field probes - find how Bloomberg links the A-share to the H-share. Whichever returns something sensible, tell Claude."; ah["D1"].font=B
for k,f in enumerate(["DUAL_LISTED_SECURITIES","EQY_DUAL_LISTED","RELATED_SECURITIES","ID_EXCH_SYMBOL","EQY_PRIM_SECURITY_TICKER","CHINA_A_SHARE_TICKER"]):
    ah.cell(2+k,4,f); ah.cell(2+k,5,f'=BDS("939 HK Equity","{f}")'); ah.cell(2+k,6,f'=BDP("939 HK Equity","{f}")')
ah["D9"]="Column E = BDS (list), F = BDP (single). #N/A Field Not Applicable = wrong field name, that is fine."
for ws in wb.worksheets:
    for row in ws.iter_rows():
        for c in row:
            if c.font.bold is not True: c.font=F
wb.save("/mnt/user-data/outputs/v5_hsci_batch.xlsx"); print("ok",wb.sheetnames)
