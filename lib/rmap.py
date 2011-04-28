"""This module supports loading all the data components required to make
a CRDS lookup table for an instrument.
"""
import os
import os.path
import collections
import re
import ast
import json

from crds import log, timestamp
from crds.config import CRDS_ROOT

# ===================================================================

Filetype = collections.namedtuple("Filetype","header_keyword,extension,rmap")
Failure = collections.namedtuple("Failure","header_keyword,message")
Filemap = collections.namedtuple("Filemap","date,file,comment")

# ===================================================================

class RmapError(Exception):
    """Exception in load_rmap."""
    def __init__(self, *args):
        Exception.__init__(self, " ".join([str(x) for x in args]))
        
class FormatError(RmapError):
    "Something wrong with context or rmap file format."
    pass

# ===================================================================

class Rmap(object):
    """An Rmap is the abstract baseclass for loading anything with the
    general structure of a header followed by data.
    """
    def __init__(self, filename, header, data, **keys):
        self.filename = filename
        self.header = header
        self.data = data
    
    @classmethod
    def check_file_format(cls, filename):
        """Make sure the basic file format for `filename` is valid and safe."""
        lines = open(filename).readlines()
        clean = cls._clean_lines(lines)
        basename = os.path.basename(filename)
        remainder = cls._check_syntax(basename, "header", clean)
        remainder = cls._check_syntax(basename, "data", remainder)
        if remainder != ["},"]:
            raise FormatError("Extraneous input following data in " + repr(basename))
    
    @classmethod
    def _clean_lines(cls, lines):
        """Remove empty lines and comment lines"""
        clean = []
        for line in lines:
            line = line.strip()
            if (not line) or line.startswith("#"):
                continue
            clean.append(line.strip())
        return clean

    @classmethod
    def _key_value_split(cls, line):
        """Split line on first : not inside quoted string or tuple."""
        inside_quote = False
        inside_tuple = 0
        for index, char in enumerate(line):
            if char == "'":
                inside_quote = not inside_quote
            elif inside_quote:
                continue
            elif char == '(':
                inside_tuple += 1
            elif char == ')':
                inside_tuple -= 1
            elif char == ":" and (not inside_quote) and (not inside_tuple):
                key = line[:index]
                value = line[index+1:]
                value = value.split("#")[0]
                return key.strip(), value.strip()
        return line, None

    @classmethod
    def _check_syntax(cls, filename, section, lines):
        if not re.match("^(}, )?{$", lines[0]):
            raise FormatError("Invalid %s block opening in " % (section,) + repr(filename))        
        for lineno, line in enumerate(lines[1:]):
            key, value = cls._key_value_split(line)
            if key in ["}", "}, {"] and value is None:
                break
            elif key == "}," and value is None:
                continue
            elif not cls._match_key(key):
                raise FormatError("Invalid %s keyword " % section + repr(key) + " in " + repr(filename))
            elif not cls._match_value(value):
                raise FormatError("Invalid %s value for " % section + key + " = " + repr(value) + " in " + repr(filename))
        return lines[lineno+1:]  # should be no left-overs

    @classmethod
    def _match_key(cls, key):
        return cls._match_simple(key) or cls._match_string_tuple(key)
    
    @classmethod
    def _match_value(cls, value):
        return (value == "{") or cls._match_simple(value) or cls._match_string_tuple(value)

    @classmethod
    def _match_simple(cls, value):
        return re.match("^'[A-Za-z0-9_.:/ \*\%\-]*',?$", value)
    
    @classmethod
    def _match_string_tuple(cls, value):
        return re.match("^\((\s*'[A-Za-z0-9_.:/ \*\%\-]*',?\s*)*\),?$", value)

    @classmethod
    def from_file(cls, fname, *args, **keys):
        cls.check_file_format(fname)
        try:
            header, data = ast.literal_eval(open(fname).read())
        except Exception, exc:
            raise RmapError("Can't load", cls.__name__, "file:", repr(os.path.basename(fname)), str(exc))
        rmap = cls(fname, header, data, *args, **keys)
        rmap.validate_file_load()
        return rmap
    
    def validate_file_load(self):
        """Validate assertions about the contents of this rmap."""
        pass
    
    def to_json(self):
        rmap = dict(header=self.header, data=self.data)
        return json.dumps(keys_to_strings(rmap))
    
    @classmethod
    def from_json(cls, json_str):
        rmap = strings_to_keys(json.loads(json_str))
        header = rmap["header"]
        data = rmap["data"]
        return cls("<json>", header, data, **header)
    
    def locate_mapping(self, basename):
        locate = get_object("crds." + self.observatory + ".locate.locate_mapping")
        return locate(basename)
    
    def locate_reference(self, basename):
        locate = get_object("crds." + self.observatory + ".locate.locate_reference")
        return locate(basename)
    
# ===================================================================

def keys_to_strings(d):
    """Convert non-string keys of `d` into strings for json encoding."""
    if not isinstance(d, dict):
        return d
    results = {}
    for key, value in d.items():
        converted = keys_to_strings(value)
        if not isinstance(key, (str, unicode)):
            results[repr(key)] = converted
        else:
            results[key] = converted
    return results
    
def strings_to_keys(d):
    """Convert string keys of `d` which contain tuple reprs back into tuples.""" 
    if not isinstance(d, dict):
        return d
    results = {}
    for key, value in d.items():
        converted = strings_to_keys(value)
        if isinstance(key, (str, unicode)) and "(" in key:
            results[ast.literal_eval(key)] = converted
        else:
            results[key] = converted
    return results

# ===================================================================

"""
{
    'observatory':'HST',
    'parkey' : ('INSTRUME'),
    'class' : 'crds.PipelineContext',
}, {
    'ACS':'icontext_hst_acs_00023.con',
    'COS':'icontext_hst_cos_00023.con', 
    'STIS':'icontext_hst_stis_00023.con',
    'WFC3':'icontext_hst_wfc3_00023.con',
    'NICMOS':'icontext_hst_nicmos_00023.con',
}
"""



class PipelineContext(Rmap):
    """A pipeline context describes the context mappings for each instrument
    of a pipeline.
    """
    def __init__(self, filename, header, data, observatory):
        Rmap.__init__(self, filename, header, data)
        self.observatory = observatory.lower()
        self.selections = {}
        for instrument, imap in data.items():
            instrument = instrument.lower()
            filepath = "/".join([CRDS_ROOT, self.observatory, instrument, imap])
            self.selections[instrument] = InstrumentContext.from_file(filepath, observatory, instrument)

    def get_best_refs(self, header, date=None):
        header = dict(header.items())
        instrument = header["INSTRUME"].lower()
        if date == "now":
            date = timestamp.now()
        if date:
            header["DATE"] = date
        else:
            header["DATE"] = header["DATE-OBS"] + " " + header["TIME-OBS"]
        header["DATE"] = timestamp.reformat_date(header["DATE"])
        return self.selections[instrument].get_best_refs(header)
    
    def reference_names(self):
        """Return the list of reference files associated with this pipeline context."""
        files = set()
        for instrument in self.selections:
            for file in self.selections[instrument].reference_names():
                files.add(file)
        return sorted(list(files))
    
    def mapping_names(self):
        """Return the list of pipeline, instrument, and reference map files associated with
        this pipeline context.
        """
        files = set([os.path.basename(self.filename)])
        for instrument in self.selections:
            files.update(self.selections[instrument].mapping_names())
        return sorted(list(files))


"""
{
    'observatory':'HST',
    'parkey' : ('INSTRUME'),
    'class' : 'crds.PipelineContext',
}, {
    'ACS':'icontext_hst_acs_00023.con',
    'COS':'icontext_hst_cos_00023.con', 
    'STIS':'icontext_hst_stis_00023.con',
    'WFC3':'icontext_hst_wfc3_00023.con',
    'NICMOS':'icontext_hst_nicmos_00023.con',
}
"""

# ===================================================================

"""
{
    'observatory':'HST',
    'instrument': 'ACS',
    'parkey' : ('REFTYPE',),
    'class' : 'crds.InstrumentContext',
}, {
    'BIAS':  'rmap_hst_acs_bias_0021.rmap',
    'CRREJ': 'rmap_hst_acs_crrej_0003.rmap',
    'CCD':   'rmap_hst_acs_ccd_0002.rmap',
    'IDC':   'rmap_hst_acs_idc_0005.rmap',
    'LIN':   'rmap_hst_acs_lin_0002.rmap',
    'DISTXY':'rmap_hst_acs_distxy_0004.rmap',
    'BPIX':  'rmap_hst_acs_bpic_0056.rmap',
    'MDRIZ': 'rmap_hst_acs_mdriz_0001.rmap',
    ...
}
"""

class InstrumentContext(Rmap):
    """An instrument context describes the rmaps associated with each filetype
    of an instrument.
    """
    def __init__(self, filename, header, data, observatory, instrument):
        Rmap.__init__(self, filename, header, data)
        self.observatory = observatory.lower()
        self.instrument = instrument.lower()
        self._selectors = {}
        for reftype, rmap_info in data.items():
            rmap_ext, rmap_name = rmap_info
            filepath = "/".join([CRDS_ROOT, self.observatory, self.instrument, rmap_name])
            self._selectors[reftype] = ReferenceRmap.from_file(
                filepath, self.observatory, self.instrument, reftype)

    def get_best_ref(self, reftype, header):
        return self._selectors[reftype.lower()].get_best_ref(header)

    def get_best_refs(self, header):
        refs = {}
        for reftype in self._selectors:
            log.verbose("\nGetting bestref for", repr(reftype))
            try:
                refs[reftype] = self.get_best_ref(reftype, header)
            except Exception, e:
                refs[reftype] = "NOT FOUND " + str(e)
        return refs

    def get_binding(self, header):
        """Given a header,  return the binding of all keywords pertinent to all reftypes
        for this instrument.
        """
        binding = {}
        for reftype in self._selectors:
            binding.update(self._selectors[reftype].get_binding(header))
        return binding
    
    def reference_names(self):
        files = set()
        for selector in self._selectors.values():
            for file in selector.reference_names():
                files.add(file)
        return sorted(list(files))
    
    def mapping_names(self):
        files = [os.path.basename(self.filename)]
        for selector in self._selectors.values():
            files.append(os.path.basename(selector.filename))
        return files
    
# ===================================================================

class ReferenceRmap(Rmap):
    """ReferenceRmap manages loading the rmap associated with a single reference
    filetype and instantiating an appropriate selector from the rmap header and data.
    """
    def __init__(self, filename, header, data, observatory, instrument, reftype, **keys):
        Rmap.__init__(self, filename, header, data)
        self.instrument = instrument.lower()
        self.observatory = observatory.lower()
        self.reftype = reftype.lower()
        cls = get_object(header.get("class", "crds.selectors.ReferenceSelector"))
        self._selector = cls(header, data)

    def validate_file_load(self):
        got = self.header["reftype"].lower()
        if got != self.reftype:
            raise RmapError("Expected reftype=" + repr(self.reftype), "but got reftype=", repr(got))

    def get_best_ref(self, header):
        return self._selector.choose(header)
    
    def reference_names(self):
        return self._selector.reference_names()
    
# ===================================================================

def get_object(dotted_name):
    """Import the given `dotted_name` and return the object."""
    parts = dotted_name.split(".")
    pkgpath = ".".join(parts[:-1])
    cls = parts[-1]
    namespace = {}
    exec "from " + pkgpath + " import " + cls in namespace, namespace
    return namespace[cls]


# ===================================================================

def write_rmap(filename, header, data):
    """Write out the specified `header` and `data` to `filename` in rmap format."""
    file = open(filename,"w+")
    write_rmap_dict(file, header)
    write_rmap_dict(file, data)
    file.write("\n")

def write_rmap_dict(file, the_dict, indent_level=1):
    """Write out a (nested) dictionary in a simple format amenable to validation
    and differencing.
    """
    indent = " "*4*indent_level
    file.write("{\n")
    for key, value in the_dict.items():
        file.write(indent + repr(key) + " : ")
        if isinstance(value, dict):
            write_rmap_dict(file, value, indent_level+1)
        elif isinstance(value, Filemap):
            file.write(repr(value.file) + ", #" + value.comment + "\n")
        else:
            file.write(repr(value) + ",\n")
    indent_level -= 1
    if indent_level > 0:
        file.write(indent_level*" "*4 + "},\n")
    else:
        file.write("}, ")
        
# ===================================================================

PIPELINE_CONTEXTS = {}

def context_to_observatory(context_file):
    """
    >>> context_to_observatory('hst_acs_biasfile.rmap')
    'hst'
    """
    return context_file.split("_")[0].split(".")[0]

def get_pipeline_context(context_file):
    """Recursively load the specified `context_file` and add it to
    the global pipeline cache.
    """
    if context_file not in PIPELINE_CONTEXTS:
        observatory = context_to_observatory(context_file)
        filepath = "/".join([CRDS_ROOT, observatory, context_file])
        PIPELINE_CONTEXTS[context_file] = PipelineContext.from_file(filepath, observatory)
    return PIPELINE_CONTEXTS[context_file]

# ===================================================================

def get_best_refs(header, pcontext_file="hst.pmap", date=None):
    context = get_pipeline_context(pcontext_file)
    return context.get_best_refs(header, date)

# ===================================================================

def test():
    """Run module doctests."""
    import doctest, rmap
    return doctest.testmod(rmap)

if __name__ == "__main__":
    print test()

