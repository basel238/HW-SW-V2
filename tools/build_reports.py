#!/usr/bin/env python3
"""Build reviewed PDF and required TXT reports from versioned JSON sources.

Usage: python3 tools/build_reports.py
Dependency: reportlab. Images and evidence are retained under docs/reports.
This does not select new results, execute benchmarks, or perform Git operations.
"""
import json
from pathlib import Path
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_LEFT
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, PageBreak, KeepTogether, Flowable
from reportlab.lib.pagesizes import A4

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / 'docs/reports'
W, H = A4
WIDTH = W - 84
styles = getSampleStyleSheet()
styles.add(ParagraphStyle(name='BodyCustom',fontName='Helvetica',fontSize=10.1,leading=14.1,spaceAfter=9,textColor=colors.HexColor('#253044')))
styles.add(ParagraphStyle(name='SmallCustom',parent=styles['BodyCustom'],fontSize=8.4,leading=11.3,spaceAfter=7))
styles.add(ParagraphStyle(name='CellCustom',parent=styles['BodyCustom'],fontSize=8.7,leading=11.5,spaceAfter=0))
styles.add(ParagraphStyle(name='TitleCustom',fontName='Helvetica-Bold',fontSize=23,leading=27,spaceAfter=13,textColor=colors.HexColor('#183A60')))
styles.add(ParagraphStyle(name='HeadingCustom',fontName='Helvetica-Bold',fontSize=15.5,leading=19,spaceAfter=12,textColor=colors.HexColor('#183A60')))
styles.add(ParagraphStyle(name='LabelCustom',fontName='Helvetica-Bold',fontSize=9,leading=12,spaceAfter=8,textColor=colors.HexColor('#188477')))
styles.add(ParagraphStyle(name='CodeCustom',fontName='Courier',fontSize=8.2,leading=11.4,spaceAfter=9))

def p(s,style='BodyCustom'):
    return Paragraph(escape(s).replace('\n','<br/>'),styles[style])

class Architecture(Flowable):
    def __init__(self):
        Flowable.__init__(self);self.width=WIDTH;self.height=164
    def draw(self):
        c=self.canv
        boxes=[(0,99,110,51,['Python renderer','build contiguous batch']),
               (137,99,110,51,['Proposed transport','driver / DMA or MMIO']),
               (274,99,237,51,['Implemented ready/valid RTL','operand registers + sequential controller']),
               (274,17,237,56,['Shared FP64 datapath','add/sub | multiply | iterative sqrt','rounded operations, result + status'])]
        for x,y,w,h,lines in boxes:
            c.setFillColor(colors.HexColor('#EDF3F7'));c.setStrokeColor(colors.HexColor('#527796'));c.roundRect(x,y,w,h,5,fill=1,stroke=1)
            for i,line in enumerate(lines):
                c.setFillColor(colors.HexColor('#253044'));c.setFont('Helvetica',8.6);c.drawCentredString(x+w/2,y+h-16-i*12,line)
        c.setStrokeColor(colors.HexColor('#188477'))
        for x1,y1,x2,y2 in [(111,124,136,124),(248,124,273,124),(392,98,392,74)]:
            c.line(x1,y1,x2,y2)
            if x1==x2:c.line(x2,y2,x2-3,y2+5);c.line(x2,y2,x2+3,y2+5)
            else:c.line(x2,y2,x2-5,y2+3);c.line(x2,y2,x2-5,y2-3)
        c.setFont('Helvetica',8.1);c.setFillColor(colors.HexColor('#596477'));c.drawString(0,51,'CPU retains scene traversal, shading and image output.')
        c.drawString(0,37,'Transport and renderer offload are proposed, not deployed.')

def make(bench):
    src=json.loads((SOURCE/f'{bench}_source.json').read_text())
    out=SOURCE/f'report_{bench}.pdf'
    story=[];plain=[src['title'],'HW/SW Co-design | Evidence reviewed 20 September 2026','']
    for i,page in enumerate(src['pages']):
        if i:story.append(PageBreak())
        story.append(p(f"{bench.upper()}  /  {page['section']}",'LabelCustom'))
        story.append(p(page['title'],'TitleCustom' if i==0 else 'HeadingCustom'))
        plain.extend([page['section'].upper(),page['title'],''])
        for block in page['blocks']:
            typ=block['type']
            if typ in ('p','small','code'):
                story.append(p(block['text'],{'p':'BodyCustom','small':'SmallCustom','code':'CodeCustom'}[typ]));plain.extend([block['text'],''])
            elif typ=='table':
                rows=[[p(str(v),'CellCustom') for v in row] for row in block['rows']]
                widths=[WIDTH*x for x in block.get('widths',[1/len(rows[0])]*len(rows[0]))]
                t=Table(rows,colWidths=widths,hAlign='LEFT',repeatRows=1)
                t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E5EDF4')),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),7),('RIGHTPADDING',(0,0),(-1,-1),7),('TOPPADDING',(0,0),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),7),('LINEBELOW',(0,0),(-1,0),.6,colors.HexColor('#527796')),('LINEBELOW',(0,1),(-1,-1),.25,colors.HexColor('#D5DCE5'))]))
                story.extend([t,Spacer(1,11)]);plain.extend([' | '.join(str(v) for v in row) for row in block['rows']]);plain.append('')
            elif typ=='image':
                img=Image(str(SOURCE/block['path']));ratio=img.imageHeight/img.imageWidth
                width=min(WIDTH,block.get('width',WIDTH));height=width*ratio
                if height>block.get('max_height',235):height=block.get('max_height',235);width=height/ratio
                img.drawWidth=width;img.drawHeight=height
                story.extend([img,Spacer(1,5),p(block['caption'],'SmallCustom')]);plain.extend([f"Figure: docs/reports/{block['path']}",block['caption'],''])
            elif typ=='architecture':
                story.extend([Architecture(),p('Implemented accelerator boundary is the ready/valid RTL. The host transport is an integration proposal.','SmallCustom')]);plain.extend(['Block diagram: CPU renderer -> proposed transport -> operand registers/controller -> shared FP64 add/sub, multiply and sqrt -> result/status -> CPU. See docs/HARDWARE_DESIGN.md for detailed integration.',''])
        # Catch an overfull authored page before silent flow to the next page.
        start=max((j for j,x in enumerate(story) if isinstance(x,PageBreak)),default=-1)+1
        total=sum(x.wrap(WIDTH,H)[1]+x.getSpaceBefore()+x.getSpaceAfter() for x in story[start:])
        if total>H-97:raise ValueError(f'{bench} authored page {i+1} too tall: {total:.1f}')
    def footer(canvas,doc):
        canvas.setStrokeColor(colors.HexColor('#D5DCE5'));canvas.line(42,38,W-42,38)
        canvas.setFont('Helvetica',8);canvas.setFillColor(colors.HexColor('#596477'))
        canvas.drawString(42,25,'HW/SW Co-design | '+bench+' | 20 September 2026')
        canvas.drawRightString(W-42,25,str(doc.page))
    doc=SimpleDocTemplate(str(out),pagesize=A4,rightMargin=42,leftMargin=42,topMargin=40,bottomMargin=51,title=src['title'],author='HW/SW Co-design project')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    (ROOT/f'report_{bench}.txt').write_text('\n'.join(plain)+'\n')
    print(out)

if __name__=='__main__':
    for bench in ('raytrace','nbody'):make(bench)
