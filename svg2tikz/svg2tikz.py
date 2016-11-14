#!/usr/bin/env python
""" A program to generate TiKZ code from inkscape-generated SVGs
Future plans include generalising to SVG without depending on Inkscape
"""
# (c) 2014 by Pedro A. Aranda Gutierrez; paaguti@hotmail.com
# released under LGPL 3.0
# see LICENSE

from __future__ import print_function
from lxml import etree
import sys
import re
import codecs
import math

class TiKZMaker(object):
    _output     = None
    _unit       = "mm"
    _standalone = True
    _debug      = False
    _symbols    = None
    _nsmap      = None
    _verbose    = 1
    _dpi        = 72
    
    str2uRe   = re.compile(r"(-?\d*.?\d*e?[+-]?\d*)([a-z]{2})?")
    
    def __init__(self, output=sys.stdout, standalone = False,debug=False,unit="mm",dpi=72):
        self._output     = output
        self._unit       = unit
        self._standalone = standalone
        self._debug      = debug
        self._dpi        = dpi
        if self._debug: print ("Debugging!",file=sys.stderr)

    def log(self,msg,_verbose=1,end=None):
        if self._debug and _verbose <= self._verbose:
            print (msg,end=end,file=sys.stderr)

    @staticmethod
    def output(colordef,strmsg,file=sys.stdout):
        if len(colordef)>0: print (colordef,file=file)
        print (strmsg,file=file)

    @classmethod
    def str2u(cls,s):
        #f = float(s) if not isinstance(s,float) else s
        if cls._debug:
            print ("str2u(%s)" % repr(s),file=sys.stderr)
        if isinstance(s,float):
            f = s
            u = cls._unit
        else:
            e = TiKZMaker.str2uRe.findall(s)[0]
            n,u = e
            f = float(n)
            if u == "px":
                f *= 25.4/72.0
                u = "mm"
            else:
                if u == "":
                    u = cls._unit
        return "%.2f%s" % (f,u)

    @classmethod
    def pt2str(cls,x=None,y=None,sep=','):
        assert x is not None and y is not None
        return "(%s%s%s)" % (cls.str2u(x),sep,cls.str2u(y))

    namedTagRe = re.compile(r"({([^}]+)})(.*)")
    @classmethod
    def delNS(cls,tag):
        # if self._debug:
        #     print ("Full tag : '%s'" % tag,file=sys.stderr)
        m = cls.namedTagRe.match(tag)
        if cls._debug:
            print (m.groups(),file=sys.stderr)
        return m.group(3)

    def circle_center(self,x1,y1,r):
        """Using the algebraic solution: we have one line passing throgh the origin and (x1,y1)
We are looking for two points that are equidistant from the origin and (x1,y1). These are on a line
that is orthogonal to the first one and passes through (x1/2, y1/2).

Throws exception when no solutions are found, else returns the two points.

@param:  x1,y1 : second point for the circular arc
@param:  r     : radius of the circular arc

@returns: [(xa,ya),(xb,yb)] : the two centers for the arcs
@throws Exception if no center is found"""
        l1 = math.pow(r,2.0) - math.pow(0.5 * x1,2.0) - math.pow(0.5 * y1,2.0)
        l2 = math.pow(x1,2.0) + math.pow(y1,2.0)
        l = math.sqrt(l1/l2)
        xa = 0.5*x1 - l * y1
        ya = 0.5*y1 + l * x1
        xb = 0.5*x1 + l * y1
        yb = 0.5*y1 - l * x1
        return [(xa,ya),(xb,yb)]

    def svg_circle_arc(self,x1,y1,r):
        """Get the specs for the arc as (centre_x,centre_y,alpha,beta,radius) """
        res = []
        for pt in self.circle_center(x1,y1,r):
            alpha = math.degrees(math.atan2(-1.0 * y1, -1.0 * x1))
            beta  = math.degrees(math.atan2(y1-pt[1], x1 - pt[0]))
            res.append((pt[0],pt[1],alpha,beta,r))
            # print (res,file=sys.stderr)
        return res
    
    def svg_ellipse_arc(self,x1,y1,rx,ry):
        mu = ry/rx
        res = []
        for arc in self.svg_circle_arc(x1*mu,y1,ry):
            res.append((arc[0]/mu,arc[1],arc[2],arc[3],rx,ry))
            # print (res,file=sys.stderr)
        return res
    
    def get_loc(self,elem):
        # print (elem.tag,elem.attrib)
        # x = float(elem.attrib['x'])
        # y = float(elem.attrib['y'])
        return float(elem.xpath("string(.//@x)")),float(elem.xpath("string(.//@y)"))

    def get_dim(self,elem):
        # print (elem.tag,elem.attrib)
        # w = float(elem.attrib['width'])
        # h = float(elem.attrib['height'])
        return float(elem.xpath("string(.//@width)")),float(elem.xpath("string(.//@height)"))

    def hex2rgb(self,colour):
        self.log('hex2rgb(%s)' % colour,_verbose=2)
        if colour.lower() == 'none': return 'none'
        r = int("0x"+colour[1:3],0)
        g = int("0x"+colour[3:5],0)
        b = int("0x"+colour[5:],0)
        return "{RGB}{%d,%d,%d}" % (r,g,b)

    def rgb2colour(self,colour):
        rgbSpec = re.compile("rgb\((\d+%?),(\d+%?),(\d+%?)\)")
        m = rgbSpec.match(colour)
        if m is None: return colour, None
        r = int(m.group(1)[:-1]) * 255 if m.group(1).endswith('%') else int(m.group(1))
        g = int(m.group(2)[:-1]) * 255 if m.group(2).endswith('%') else int(m.group(2))
        b = int(m.group(3)[:-1]) * 255 if m.group(3).endswith('%') else int(m.group(3))
        return '#%02x%02x%02x' % (r,g,b) , "{RGB}{%d,%d,%d}" % (r,g,b)

    def hex2colour(self,colour,cname=None,cdef=None):
        self.log("hex2colour(%s) = " % colour,end="",_verbose=2)
        result = None
        col,rgb = self.rbg2colour(colour) if colour.startswith("rgb(") else colour,self.hex2rgb(colour)
        self.log ("colour %s --> %s,%s" % (colour,col,rgb),_verbose=2)
        d = {'none'    : 'none', 
             '#000000' : 'black',
             '#ff0000' : 'red',
             '#00ff00' : 'green',
             '#0000ff' : 'blue',
             '#ffff00' : 'yellow',
             '#00ffff' : 'cyan',
             '#ff00ff' : 'magenta',
             '#ffffff' : 'white' } 
        try :
            result = d[col]
        except:
            if cname is not None:
                cdef.append('\\definecolor{%s}%s' % (cname,rgb))
                result = cname
        self.log(result,_verbose=2)
        return result
        

    def style2colour(self,style):
        self.log("style2colour(%s)" % style,end=" = ",_verbose=2)
        stdef = []
        cdef  = []
        s2cDict = {
            'stroke':       lambda c: "draw=" + self.hex2colour(c,cname='dc',cdef=cdef),
            'fill':         lambda c: "fill=" + self.hex2colour(c,cname='fc',cdef=cdef),
            #'stroke-width': lambda c: "line width=" + self.str2u(c)
        }
        for s in style.split(';'):
            m,c = s.split(':')
            # if self._debug: 
            self.log ("Processing '%s=%s'" % (m,c),_verbose=2) 
            if m in s2cDict:
                # if self._debug: 
                self.log("Found '%s'" % m,_verbose=2)
                stdef.append(s2cDict[m](c))

        result = "[%s]" % ",".join(stdef) if len(stdef) > 0 else "", "\n".join(cdef)
        self.log("Returns %s" % repr(result), _verbose=2)
        return result
    
    def process_rect(self,elem):
        if self._debug:
            print ("***\n** rectangle\n***",file=sys.stderr)
        x,y   = self.get_loc(elem)
        w,h   = self.get_dim(elem)
        try:
            style,cdefs = self.style2colour(elem.attrib['style'])
            if self._debug: print("Result: style=%s\ncdefs= %s" % (style,cdefs),file=sys.stderr)
        except:
            style = ""
            cdefs = ""
        TiKZMaker.output(cdefs,
                         "\\draw %s %s rectangle %s ;" % (style,self.pt2str(x,y),self.pt2str(w+x,h+y)),
                         file=self._output)

    def process_circle(self,elem):
        x    = float(elem.get('cx'))
        y    = float(elem.get('cy'))
        r    = float(elem.get('r'))
        try:
            style,cdefs = self.style2colour(elem.attrib['style'])
        except:
            style = ""
            cdefs = ""
        TiKZMaker.output(cdefs,
                         "\\draw %s %s circle (%s) ;" % (style,self.pt2str(x,y),self.str2u(r)),
                         file=self._output)

    def process_ellipse(self,elem):
        x    = float(elem.get('cx'))
        y    = float(elem.get('cy'))
        rx   = float(elem.get('rx'))
        ry   = float(elem.get('ry'))
        # style = elem.attrib['style']
        try:
            style,cdefs = self.style2colour(elem.attrib['style'])
        except:
            style = ""
            cdefs = ""
        TiKZMaker.output(cdefs,
                         "\\draw %s %s ellipse %s ;" % (style,self.pt2str(x,y),self.pt2str(rx,ry,' and ')),
                         file=self._output)

    dimRe  = re.compile(r"(-?\d+(\.\d+)?)[, ](-?\d+(\.\d+)?)(\s+(\S.*))?")
    def dimChop(self,s):
        m=TiKZMaker.dimRe.match(s)
        x=float(m.group(1))
        y=float(m.group(3))
        return self.pt2str(x,y),m.group(6),x,y

    intRe = re.compile (r"(-?\d+)(\s+(\S.*))?")
    def intChop(self,s):
        m = TiKZMaker.intRe.match(s)
        return m.group(1),m.group(3),int(m.group(1))
    
    numRe = re.compile (r"(-?\d+(\.\d+)?)(\s+(\S.*))?")
    def numChop(self,s):
        m = TiKZMaker.numRe.match(s)
        return m.group(1),m.group(4),float(m.group(1))
        
    pathRe = re.compile(r"([aAcCqQlLmM] )?(-?\d+(\.\d+)?(e-?\d+)?)[, ](-?\d+(\.\d+)?(e-?\d+)?)([ ,]+(.*))?")

    # path_chop
    # @param:
    #  d:           path descriptor (string)
    #  first:       whether this is the first element or not
    #  last_spec:   last operation specification
    #  incremental: whether we are in incremental mode or not
    #  style:       style to use
    # @return
    #  rest:        path description after processing
    #  first:       should be False
    #  spec:        spec for next operation
    #  incremental: whether next operation will be incremental
    
    def path_chop(self,d,first=True,last_spec="",incremental=True,style=None):

        def path_controls(inc,p1,p2,p3):
            print (".. controls %s%s and %s%s .. %s%s" % (inc,p1,inc,p2,inc,p3),
                   file=self._output)

        def path_arc(inc,arc,lge,comment=False):
            x,y,alpha,beta,rx,ry = arc
            print ("%s%s%s arc (%5.1f:%5.1f:%s and %s)" %
                   ("%% " if comment else "",
                    inc, 
                    self.pt2str(x,y),
                    alpha if lge else beta,
                    beta  if lge else alpha,
                    self.str2u(rx),self.str2u(rx)),file=self._output)


        if self._debug:
            print ("[%s] -->> %s" % (last_spec,d),file=sys.stderr)
        if d[0].upper() == 'Z':
            print ("-- cycle",file=self._output)
            return None, False, last_spec, incremental            
        m = TiKZMaker.pathRe.match(d)
        # print (m,file=sys.stderr)
        if m is None:
            print ("ERROR: '%s' does not have aAcCqQlLmM element" % d,file=sys.stderr)
            return None, False, last_spec, incremental
        spec = m.group(1)
        x1 = float(m.group(2))
        y1 = float(m.group(5))
        pt = self.pt2str(x1,y1)
        if self._debug:
            print (" -- [%s] >> %s" % (spec,m.group(1)),file=sys.stderr)
        
        # spec=last_spec[0] if spec is None else spec[0]
        if spec is None and last_spec is not None:
            if last_spec[0].upper() == 'M':
                spec = 'L' if last_spec[0] == 'M' else 'l'
            else:
                spec = last_spec

        if spec is not None:
            spec = spec[0]
            incremental = spec != spec.upper()
        inc = "++" if incremental and not first else ""
            
        rest = m.group(9)
        ## print (" --]]>> [%s|%s]" % (spec,rest),file=sys.stderr)

        if spec in ["L","l"] or spec is None:
            print ("-- %s%s" % (inc,pt),file=self._output)
        elif spec in [ "M","m"]:
            if not first: print(";",file=self._output)
            print("\\draw %s %s%s" % (style,inc,pt),file=self._output)
        elif spec in ["c", "C"]:
            pt2,rest,x2,y2 = self.dimChop(rest)
            pt3,rest,x3,y3 = self.dimChop(rest)
            #
            # Quick hack
            #
            # %.. controls ++(4.2mm,4.2mm) and ++(12.6mm,-4.2mm) .. ++(16.9mm,0.0mm)
            # Correct
            # .. controls ++(4.2mm,4.2mm) and ++(-4.2mm,-4.2mm) .. ++(16.8mm,0.0mm)
            if incremental:
                pt2 = self.pt2str(x2-x3,y2-y3)
            else:
                if self._debug: print ("** Warning: check controls",file=sys.stderr)
                print ("%%%% Warning: check controls",file=self._output)
            path_controls (inc,pt,pt2,pt3)
        elif spec in ["Q","q"]:
            if self._debug: print (">> Decoding quadratic Bezier curve",file=sys.stderr)
            pt2,rest,x2,y2 = self.dimChop(rest)
            if spec == "Q":
                print ("%% Warning: ignoring (abs) Quadratic Bezier",file=sys.stderr)
                print ("%% This should be a quadratic Bezier with control point at %s" % pt,file=self._output)
                print (" -- %s" % (pt2),file=self._output)
            else:
                #
                # See http://www.latex-community.org/forum/viewtopic.php?t=4424&f=45
                # And above
                #
                # Q3 = P2
                # Q2 = (2*P1+P2)/3 [ -P2 ^see above^]
                # Q1 = 
                pt3 = pt2
                pt2 = self.pt2str(2.0*(x1-x2)/3.0,2.0*(y1-y2)/3)
                pt1 = self.pt2str(2.0*x1/3.0,      2.0*y1/3)
                path_controls(inc,pt1,pt2,pt3)
        elif spec in ["A","a"]:
            #
            # First 'point' were rx and ry
            #
            _,rest,xrot  = self.intChop(rest)
            _,rest,large = self.intChop(rest)
            _,rest,swap  = self.intChop(rest)
            pt2,rest,_x,_y    = self.dimChop(rest) # this is the second point
            _large =  large == 0
            _swap =   swap  == 1
            try:
                arcs = self.svg_ellipse_arc(_x,_y,x1,y1)
                if self._debug: print("arcs: ",arcs,file=sys.stderr)
                path_arc(inc,arcs[0 if _swap else 1],_large,False)
                path_arc(inc,arcs[1 if _swap else 0],_large,True)
                
            except Exception,e:
                print ("ERROR: <%s> Couldn't process spec: %c %6.1f,%6.1f %d %d %d %6.1f,%6.1f" %
                       (e, spec, x1, y1, _xrot, _large, _swap, _x, _y), file=sys.stderr)
                print ("%%%% ERROR: Couldn't process spec: %c %6.1f,%6.1f %d %d %d %d %6.1f,%6.1f" %
                       (spec, x1,y1,_xrot,_large,_swap,_x,_y), file=self._output)
        else:
            print ("Warning: didn't process '%s' in path" % spec,file=sys.stderr)
        return rest,False,spec,incremental

    def process_use(self,elem,debug=True):
        #print("TODO: process %s" % etree.tostring(elem))
        href = None
        x = None
        y = None
        print("]>]>  "+elem.xpath("string(.//@href)",namespaces = self._nsmap),file=sys.stderr)
        for n in elem.attrib:
            print (n)
            
            if re.search(r"({[^}]+})?href",n):
                if debug: print ("reference to %s" % elem.get(n))
                href = elem.get(n)
            if n == 'x': x=float(elem.get(n))
            if n == 'y': y=float(elem.get(n))
        assert href is not None, "use does not reference a symbol" % href
        assert href[0] == "#", "Only local hrefs allowed for symbols (%s)" % href
        
        try:
            print ("\\begin{scope}[shift={%s}]" % (self.pt2str(x,y)),file=self._output)
        except: pass
        
        for s in self._symbols:
            if href[1:] == s.get("id"):
                self.process_g(s)
                break
        else:
            print ("ERROR: didn't find referenced symbol '%s'" % href[1:],file=sys.stderr)
            
        if x is not None and y is not None:
            print ("\\end{scope}",file=self._output)

    def sodipodi_arc(self,cdefs,style,elem):
        rx    = float(elem.xpath("string(.//@sodipodi:rx)" ,namespaces=self._nsmap))
        ry    = float(elem.xpath("string(.//@sodipodi:ry)" ,namespaces=self._nsmap))
        cx    = float(elem.xpath("string(.//@sodipodi:cx)" ,namespaces=self._nsmap))
        cy    = float(elem.xpath("string(.//@sodipodi:cy)" ,namespaces=self._nsmap))
        start = float(elem.xpath("string(.//@sodipodi:start)" ,namespaces=self._nsmap))
        end   = float(elem.xpath("string(.//@sodipodi:end)" ,namespaces=self._nsmap))

        if end < start: end = end + 2.0 * math.pi
                
        x1 = cx + rx * math.cos(start)
        y1 = cy + ry * math.sin(start)

        for f in [self._output,sys.stderr] if self._debug else [self._output]:
            TiKZMaker.output(cdefs,
                             "\\draw %s %s arc (%.2f:%.2f:%s and %s);" % 
                             (style, self.pt2str(x1,y1),math.degrees(start),math.degrees(end),
                              self.str2u(rx),self.str2u(ry)),
                             file=f)
        
    def process_path(self,elem):
        d = elem.attrib['d']
        f = True 
        i = False
        try:
            pid = elem.attrib['id']
            print ("%% path id='%s'" % pid,file=self._output)
        except: pass
        print ("%% path spec='%s'" % d,file=self._output)
        try:
            _style = elem.attrib['style']
            if self._debug:
                print ("%% From '%s'" % _style,file=sys.stderr)
            style,cdefs = self.style2colour(_style)
            if self._debug:
                print ("%% style= '%s'" % style,file=sys.stderr)
                print ("%% colour defs = '%s'" % cdefs,file=sys.stderr)
        except Exception as e:
            style,cdefs = "",""
            
            
        spec = None

        _type = elem.xpath("string(.//@sodipodi:type)" ,namespaces=self._nsmap)
        if self._debug:
            print ("sodipodi type is '%s'" % _type,file=sys.stderr)
            print ("style is '%s'" % style,file=sys.stderr)
            
        sodipodi_dict = {
            "arc" : lambda e: self.sodipodi_arc(cdefs,style,e),
            # Add more sodipodi elements here
        }
        if _type in sodipodi_dict:
            try:
                sodipodi_dict[_type](elem)
                return
            except Exception,e: 
                print ("<*> Exception %s processing sodipodi:%s" % (e,_type),file=sys.stderr)
        if len(cdefs) > 0: print (cdefs,file=self._output)
        while d is not None and len(d) > 0:
            ## print (self.path_chop(d,f,spec,i,style),file=sys.stderr) 
            d,f,spec,i = self.path_chop(d,first=f,last_spec=spec,incremental=i,style=style)
        print (";",file=self._output)

    def process_tspan(self,txt,x,y,stdict={}):
        def dict2style(styledict={},cdefs=[]):
            def mkFont(fname):
                try:
                    return "font=" + {
                        # "serif" :      "",
                        # "Serif" :      "",
                        "sans-serif" : "\\sffamily",
                        "Sans" :       "\\sffamily",
                    }[fname]
                except:
                    return "font="
                
            def mkAlign(style):
                try:
                    al = {'start':'left','center':'center','end':'right' }[style]
                except:
                    al = 'center'
                if al != "center":
                    print ("** Warning: ignored string alignment to the %s" % al,file=sys.stderr)
                    print ("%%%% This element will be anyhow centered!",file=self._output)
                return "align=%s" % al

            pxRe = re.compile(r"(-?\d+(\.\d+(e?[+-]?\d+)))([a-z]{2})?")
            def mkFSize(style):
                try:
                    size = 0.0
                    if self._debug: print ("**TODO refine mkFSize(%s)" % style)
                    val,_,_,unit = pxRe.match(style).groups()
                    fval = float(val)
                    for _min,_max,_result in [
                            ( 0.0,  4.0, "font=\\small"),
                            ( 4.0,  6.0, ""),
                            ( 6.0, 10.0, "font=\\large"),
                            (10.0, 1e06, "font=\\LARGE")
                    ]:
                        if _min <= fval and fval < _max:
                            return _result
                    return ""
                except:
                    return ""
            result = []
            xlatestyle = {'fill' :        lambda s: self.hex2colour(s,cdefs),
                          #'font-family' : lambda s: mkFont(s),
                          'text-align':   lambda s: mkAlign(s),
                          'font-size' :   lambda s: mkFSize(s)
            }

            result = [xlatestyle[x](styledict[x]) for x in xlatestyle if x in styledict]
            self.log(repr(result),end=" --> ") # ,_verbose=2)
            fspec = "font=" + "".join([f[5:] for f in result if f.startswith("font=")])
            result = [ r for r in result if len(r)>0 and not r.startswith("font=")]
            if len(fspec) != 5: result.append(fspec)
            self.log(repr(result)) #,_verbose=2)
            # result = [r for r in result if r is not None and len(r)>0]
            return "" if len(result) == 0 else "[" + ",".join(result) + "]","\n".join(cdefs)
        
        # txt = elem.text
        s,c = dict2style(stdict)
        TiKZMaker.output("\n".join(c),"\\node %s at %s { %s };" % (s,self.pt2str(x,y),txt),file=self._output)
        
    def process_text(self,elem):
        def style2dict(st,styledict = {}):
            for s in [_s for _s in st.split(";") if len(_s) > 0]:
                k,v = s.split(':')
                styledict[k] = v
            return styledict
        
        x,y   = self.get_loc(elem)
        style = style2dict(elem.xpath("string(.//@style)",namespaces=self._nsmap))
        print ("text.x,y = %d,%d" % (x,y),file=sys.stderr)
        if elem.text is None:
            for tspan in elem.xpath(".//svg:tspan",namespaces=self._nsmap):
                _style = style2dict(tspan.xpath("string(.//@style)",namespaces=self._nsmap),
                                    dict(style))
                try:
                    _x,_y   = self.get_loc(tspan)
                    print (">> tspan.x,y = %d,%d" % (_x,_y),file=sys.stderr)
                except:
                    _x,_y = x,y
                self.process_tspan(tspan.text,_x,_y,_style)
                del _style
        else:
            print (etree.tostring(elem,pretty_print=True),file=sys.stderr)
            self.process_tspan(elem.text,x,y,style)
        del style

    transformRe = re.compile(r"(translate|rotate|matrix)\(([^)]+)\)")
    floatRe     = re.compile(r"(-?\d+(\.\d+([eE]-?\d+)?)?)")

    def transform2scope(self,elem):
        transform = elem.xpath('string(.//@transform)')
        if transform == '': return False
        if self._debug: 
            print ("transform2scope(%s)" % transform,file=sys.stderr)
        m = TiKZMaker.transformRe.match(transform)
        if self._debug: 
            print (m.groups(),file=sys.stderr)
        getFloats = TiKZMaker.floatRe.findall(m.group(2)) 
        if self._debug:
            print (getFloats,file=sys.stderr)
        nums = [ n for n,d,e in getFloats ]
        operation = m.group(1)
        if self._debug:
            print (operation,nums,file=sys.stderr)
        xform = []

        if operation == "translate":
            xform.append("shift={(%s,%s)}" % (self.str2u(nums[0]),self.str2u(nums[1] if len(nums)>1 else "0")))
        elif operation == "rotate":
            if len(nums) == 1:
                xform.append("rotate=%s" % nums[0])
            else:
                xform.append("rotate around={%s:(%s,%s)}" % (nums[0],self.str2u(nums[1]),self.str2u(nums[2])))
        elif operation == "matrix":
            xform.append("cm={%s,%s,%s,%s,(%s,%s)}" % (nums[0],nums[1],nums[2],nums[3],
                                                       self.str2u(nums[4]),self.str2u(nums[5])))
        if len(xform) > 0:
            print ("\\begin{scope}[%s]" % ",".join(xform),file=self._output)
            return True
        return False


    namedTagRe = re.compile(r"({([^}]+)})(.*)")

    def process_g(self,elem):
        if len(elem) == 0: return
        g_style = elem.get("style")
        if g_style is not None:
            print ("TODO: process global style '%s' in group" % g_style,file=sys.stderr)

        xlate = {
            'g':       lambda e: self.process_g(e),
            'text':    lambda e: self.process_text(e),
            'rect':    lambda e: self.process_rect(e),
            'circle':  lambda e: self.process_circle(e),
            'ellipse': lambda e: self.process_ellipse(e),
            'path':    lambda e: self.process_path(e),
            'use':     lambda e: self.process_use(e)
        }

        # print ("process_g(%s)" % elem.tag,file=sys.stderr)

        for child in elem:
            # print (" &&& -> %s" % child.tag,file=sys.stderr)
            tag = self.namedTagRe.match(child.tag).group(3)
            for x in xlate:
                if tag == x:
                    transform = self.transform2scope(child)
                    xlate[x](child)
                    if transform: print ("\\end{scope}",file=self._output)
                    break
            else:
                print ("WARNING: <%s ../> not processed" % tag,file=sys.stderr)
        if g_style is not None:
            pass # print ("\\end{scope}",file=self._output)

    def mkStandaloneTikz(self,svg,border="1mm"):
        print ("\\documentclass[tikz,border=%s]{standalone}\n\\usepackage{tikz}\n\\usetikzlibrary{shapes}\n\\usepackage[utf8]{inputenc}\n\\makeatletter\n\\begin{document}" % border,file=self._output)
        self.mkTikz(svg)
        print ("\\end{document}",file=self._output)

    def mkTikz(self,svg):
        self._nsmap = { k:v for k,v in svg.getroot().nsmap.iteritems() if k is not None }
        self._nsmap['svg'] = 'http://www.w3.org/2000/svg'
        if self._debug: print (repr(self._nsmap),file=sys.stderr)

        self._symbols = svg.xpath("//svg:symbol",namespaces=self._nsmap)
        if self._debug:
            print ("Getting symbols with XPATH")
            for s in self._symbols:
                print(etree.tostring(s))

        units = self._unit
        self._unit = svg.xpath("string(//svg:svg/sodipodi:namedview/@units)",namespaces=self._nsmap)
        if len(self._unit) == 0: self._unit = units

        print ("\\begin{tikzpicture}[yscale=-1,scale=0.015,baseline={([yshift=-.5ex]current bounding box.center)}]",file=self._output)
        for elem in svg.xpath("//svg:svg/svg:g",namespaces=self._nsmap):
            if len(elem) > 0:
                transform = self.transform2scope(elem)
                self.process_g(elem)
                if transform: print ("\\end{scope}",file=self._output)
        print ("\\end{tikzpicture}",file=self._output)

def main():
    import argparse
    
    parser = argparse.ArgumentParser(description=__doc__,formatter_class=argparse.RawDescriptionHelpFormatter,epilog="")
    parser.add_argument('--version', action='version', version='%(prog)s 2.0')
    parser.add_argument("-d","--debug",
                        dest="debug",      
                        action = "store_true", 
                        help="Enable debugging messages")
    parser.add_argument("-a","--auto",
                        dest="auto",      
                        action = "store_true", 
                        help="Create output name from source")
    parser.add_argument("-o","--output",
                        dest="output",
                        default=None,  
                        help="Write to file(default is stdout)")
    parser.add_argument("-b","--border",
                        dest="border",
                        default="1mm",  
                        help="Set standalone border (default:1mm)")
    parser.add_argument("-r","--dpi",
                        dest="dpi",
                        type=int,default=72,
                        help="Resolution (assume 72dpi)")
    parser.add_argument("-s","--standalone",
                        dest="standalone", 
                        action = "store_true",
                        help="Make a standalone LaTEX file")
    parser.add_argument("--code",
                        dest="code", 
                        default="utf-8",
                        help="Output file coding")
    parser.add_argument("infile",metavar="INFILE", type=str, help="Input file")
    
    args = parser.parse_args()

    if args.auto:
        import os
        args.output = os.path.splitext(args.infile)[0]+ ".tex"
        print (" %s --> %s " % (args.infile,args.output),file=sys.stderr)

    processor = TiKZMaker(sys.stdout if args.output is None else codecs.open(args.output,"w",args.code),
                          debug=args.debug,
                          dpi=args.dpi)
    try:
        tree = etree.parse(args.infile)

        if args.standalone:
            processor.mkStandaloneTikz(tree,border=args.border)
        else:
            processor.mkTikz(tree)
    except IndexError:
        parser.print_help()

if __name__ == "__main__":
    main()
